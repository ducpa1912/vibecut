import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  UserButton,
  useAuth,
  useUser,
} from '@clerk/clerk-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Api,
  contentTypeFor,
  putToStorage,
  type ApiError,
  type UploadProgress,
} from './api';
import { asApiError } from './errors';
import { isPending } from './status';
import type { LibraryDetail, LibraryItem, UploadState } from './types';
import { Landing } from './components/Landing';
import { LibraryPanel } from './components/LibraryPanel';
import { SetupState } from './components/SetupState';
import { UploadPanel } from './components/UploadPanel';
import { ItemView } from './components/ItemView';

const MAX_BYTES = 5_000_000_000;

export function App() {
  const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY?.trim();
  if (!publishableKey) return <SetupState />;

  return (
    <ClerkProvider publishableKey={publishableKey}>
      <SignedOut>
        <Landing />
      </SignedOut>
      <SignedIn>
        <Workspace />
      </SignedIn>
    </ClerkProvider>
  );
}

function Workspace() {
  const { getToken } = useAuth();
  const { user } = useUser();
  const jwtTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE?.trim();
  const api = useMemo(
    () => new Api(() => getToken(jwtTemplate ? { template: jwtTemplate } : undefined)),
    [getToken, jwtTemplate],
  );
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const [items, setItems] = useState<LibraryItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LibraryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [upload, setUpload] = useState<UploadState | null>(null);
  const [tick, setTick] = useState(0);

  const loadLibrary = useCallback(
    async (quiet = false) => {
      if (!quiet) setLoading(true);
      try {
        const page = await api.library();
        setItems(page.items);
        setError(null);
        setTick((value) => value + 1);
      } catch (cause) {
        setError(asApiError(cause));
      } finally {
        if (!quiet) setLoading(false);
      }
    },
    [api],
  );

  useEffect(() => {
    void loadLibrary();
  }, [loadLibrary]);

  useEffect(() => {
    setDetail(null);
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let alive = true;
    setDetailLoading(true);
    api
      .item(selectedId)
      .then((value) => {
        if (alive) setDetail(value);
      })
      .catch((cause) => {
        if (alive) setError(asApiError(cause));
      })
      .finally(() => {
        if (alive) setDetailLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [api, selectedId, tick]);

  const pending =
    items.some((item) => isPending(item.status)) ||
    (detail !== null && detail.status !== 'failed' && detail.proxy === null);

  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => {
      void loadLibrary(true);
    }, 4_000);
    return () => window.clearInterval(timer);
  }, [loadLibrary, pending]);

  const runUpload = useCallback(
    async (ticket: Awaited<ReturnType<Api['createUpload']>>, file: File) => {
      setUpload((current) =>
        current ? { ...current, ticket, phase: 'uploading', error: null } : current,
      );
      const controller = new AbortController();
      abortRef.current = controller;
      await putToStorage(
        ticket,
        file,
        (progress: UploadProgress) => {
          setUpload((current) => (current ? { ...current, ...progress } : current));
        },
        controller.signal,
      );
      setUpload((current) => (current ? { ...current, phase: 'verifying' } : current));
      await api.completeUpload(ticket.upload_id, file.size);
      setUpload((current) => (current ? { ...current, phase: 'done' } : current));
      await loadLibrary(true);
      setSelectedId(ticket.library_item_id);
    },
    [api, loadLibrary],
  );

  const startUpload = useCallback(
    async (file: File) => {
      const contentType = contentTypeFor(file);
      if (!contentType) {
        setUpload(
          failedUpload(
            file,
            'That file type is not supported. Use MP4, MOV, WebM or MKV.',
          ),
        );
        return;
      }
      if (file.size > MAX_BYTES) {
        setUpload(failedUpload(file, 'Files are limited to 5 GB.'));
        return;
      }

      setUpload({
        file,
        phase: 'signing',
        ticket: null,
        loaded: 0,
        total: file.size,
        started_at: Date.now(),
        error: null,
      });
      try {
        const ticket = await api.createUpload({
          filename: file.name,
          content_type: contentType,
          bytes: file.size,
          title: file.name,
        });
        await runUpload(ticket, file);
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === 'AbortError') {
          setUpload((current) =>
            current ? { ...current, phase: 'cancelled' } : current,
          );
          return;
        }
        setUpload((current) =>
          current
            ? { ...current, phase: 'failed', error: asApiError(cause).message }
            : current,
        );
      } finally {
        abortRef.current = null;
      }
    },
    [api, runUpload],
  );

  const retryUpload = useCallback(async () => {
    if (!upload) return;
    if (upload.ticket && upload.phase === 'failed') {
      try {
        const ticket = await api.signUpload(upload.ticket.upload_id);
        await runUpload(ticket, upload.file);
        return;
      } catch {
        // The ticket may already be complete; start a fresh asset instead.
      }
    }
    await startUpload(upload.file);
  }, [api, runUpload, startUpload, upload]);

  const cancelUpload = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) void startUpload(file);
  }

  return (
    <main className="app">
      <header className="rail">
        <span className="wordmark">DuckClean</span>
        <span className="rail-actions">
          {user?.primaryEmailAddress?.emailAddress ? (
            <span className="account">{user.primaryEmailAddress.emailAddress}</span>
          ) : null}
          <UserButton />
        </span>
      </header>
      <div className="workspace">
        <LibraryPanel
          items={items}
          selectedId={selectedId}
          loading={loading}
          error={error}
          onSelect={setSelectedId}
          onRefresh={() => void loadLibrary()}
        />

        <section className="detail" aria-label="Selected clip">
          {selectedId === null ? (
            <div className="detail-empty">
              <p>Select a clip to see its measured facts and playback.</p>
            </div>
          ) : detailLoading && !detail ? (
            <div className="detail-empty">
              <p>Reading the clip.</p>
            </div>
          ) : detail ? (
            <ItemView
              key={detail.id}
              item={detail}
              onPlay={async () => {
                const ticket = await api.play(detail.id);
                return ticket.url;
              }}
              onDetect={() => api.startDetection(detail.id)}
              onDetection={() => api.detection(detail.id)}
              onRetry={() => void loadLibrary()}
            />
          ) : (
            <div className="detail-empty">
              <p>Clip not available.</p>
            </div>
          )}
        </section>
      </div>
      <div className="actionbar">
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mkv"
          onChange={onPick}
        />
        <button
          className="primary primary--wide"
          type="button"
          onClick={() => inputRef.current?.click()}
        >
          Upload a video
        </button>
      </div>
      {upload ? (
        <UploadPanel
          state={upload}
          onCancel={cancelUpload}
          onRetry={() => void retryUpload()}
          onDismiss={() => setUpload(null)}
        />
      ) : null}
    </main>
  );
}

/** A rejected file never started, so it owns a failure state with no ticket. */
function failedUpload(file: File, error: string): UploadState {
  return {
    file,
    phase: 'failed',
    ticket: null,
    loaded: 0,
    total: file.size,
    started_at: Date.now(),
    error,
  };
}
