import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  UserButton,
  useAuth,
  useClerk,
  useUser,
} from '@clerk/clerk-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Api, ApiError, contentTypeFor, putToStorage, type UploadProgress } from './api';
import type { LibraryDetail, LibraryItem, LibraryStatus, UploadState } from './types';

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

function SetupState() {
  return (
    <main className="setup">
      <p className="wordmark">DuckClean</p>
      <h1>Sign-in is not configured.</h1>
      <p className="muted">
        The M1 surface is built, but this build has no Clerk publishable key. Set
        <code>VITE_CLERK_PUBLISHABLE_KEY</code> and rebuild. No sign-in button is shown
        because there is nothing real behind it.
      </p>
      <pre>
        <code>VITE_CLERK_PUBLISHABLE_KEY=pk_test_...</code>
      </pre>
    </main>
  );
}

function Landing() {
  const { openSignIn } = useClerk();
  return (
    <main className="landing">
      <p className="wordmark">DuckClean</p>
      <h1>Remove baked-in text, logos and burnt-in images from video.</h1>
      <p className="lede">
        Upload the full clip. DuckClean finds the marks, renders only the beats that
        contain them, and returns the whole video with the original audio.
      </p>
      <button className="primary" type="button" onClick={() => openSignIn()}>
        Sign in
      </button>
      <p className="fine">
        A phone can upload, review, render and download because rendering is remote.
      </p>
    </main>
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
        setUpload({
          file,
          phase: 'failed',
          ticket: null,
          loaded: 0,
          total: file.size,
          started_at: Date.now(),
          error: 'That file type is not supported. Use MP4, MOV, WebM or MKV.',
        });
        return;
      }
      if (file.size > MAX_BYTES) {
        setUpload({
          file,
          phase: 'failed',
          ticket: null,
          loaded: 0,
          total: file.size,
          started_at: Date.now(),
          error: 'Files are limited to 5 GB.',
        });
        return;
      }

      const started = Date.now();
      setUpload({
        file,
        phase: 'signing',
        ticket: null,
        loaded: 0,
        total: file.size,
        started_at: started,
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
        <section className="library" aria-label="Your library">
          <div className="section-head">
            <h1>Library</h1>
            <button className="link" type="button" onClick={() => void loadLibrary()}>
              Refresh
            </button>
          </div>

          {error ? (
            <ErrorBanner error={error} onRetry={() => void loadLibrary()} />
          ) : null}

          {loading ? (
            <div className="skeleton" aria-label="Loading library">
              <div />
              <div />
              <div />
            </div>
          ) : items.length === 0 ? (
            <div className="empty">
              <p>No clips yet.</p>
              <p className="muted">
                Upload a video and DuckClean will report its real duration, size and
                playback readiness here.
              </p>
            </div>
          ) : (
            <ul className="rows">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`row${selectedId === item.id ? ' row--active' : ''}`}
                    aria-current={selectedId === item.id ? 'true' : undefined}
                    onClick={() => setSelectedId(item.id)}
                  >
                    {item.poster_url ? (
                      <img className="poster" src={item.poster_url} alt="" />
                    ) : (
                      <span className="poster poster--empty" aria-hidden="true" />
                    )}
                    <span className="row-body">
                      <span className="row-title">{item.title}</span>
                      <span className={`status status--${tone(item.status)}`}>
                        {statusLabel(item.status)}
                      </span>
                      <span className="as-run">{asRun(item)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

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
              item={detail}
              onPlay={async () => {
                const ticket = await api.play(detail.id);
                return ticket.url;
              }}
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

function ItemView({
  item,
  onPlay,
  onRetry,
}: {
  item: LibraryDetail;
  onPlay: () => Promise<string>;
  onRetry: () => void;
}) {
  const [playUrl, setPlayUrl] = useState<string | null>(null);
  const [playError, setPlayError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    setPlayUrl(null);
    setPlayError(null);
  }, [item.id]);

  async function play() {
    setPlaying(true);
    setPlayError(null);
    try {
      setPlayUrl(await onPlay());
    } catch (cause) {
      setPlayError(asApiError(cause).message);
    } finally {
      setPlaying(false);
    }
  }

  return (
    <article className="item">
      <div className="item-media">
        {playUrl ? (
          <video
            src={playUrl}
            controls
            playsInline
            poster={item.poster_url ?? undefined}
          />
        ) : item.poster_url ? (
          <img src={item.poster_url} alt="" />
        ) : (
          <div className="media-empty">No poster yet.</div>
        )}
      </div>

      <div className="item-head">
        <div>
          <h2>{item.title}</h2>
          <p className={`status status--${tone(item.status)}`}>
            {statusLabel(item.status)}
          </p>
        </div>
        {item.proxy ? (
          <button
            className="secondary"
            type="button"
            onClick={() => void play()}
            disabled={playing}
          >
            {playing ? 'Opening' : playUrl ? 'Play again' : 'Play'}
          </button>
        ) : null}
      </div>

      {item.error ? <ErrorBanner error={item.error} onRetry={onRetry} /> : null}
      {playError ? <p className="error-text">{playError}</p> : null}

      <dl className="facts">
        <Fact
          label="Duration"
          value={formatDuration(item.duration_ms ?? item.proxy?.duration_ms)}
        />
        <Fact
          label="Frame"
          value={formatSize(
            item.width ?? item.proxy?.width,
            item.height ?? item.proxy?.height,
          )}
        />
        <Fact label="Rate" value={formatFps(item.fps ?? item.proxy?.fps)} />
        <Fact label="Size" value={formatBytes(item.bytes)} />
        <Fact
          label="Audio"
          value={item.has_audio === null ? null : item.has_audio ? 'yes' : 'none'}
        />
        <Fact label="Codec" value={item.probe?.video_codec ?? null} />
      </dl>

      <p className="as-run as-run--detail">{asRunDetail(item)}</p>

      {!item.proxy && item.status !== 'failed' ? (
        <p className="muted">
          Preparing playback. This page polls the API; it does not invent progress.
        </p>
      ) : null}
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value ?? '—'}</dd>
    </div>
  );
}

function UploadPanel({
  state,
  onCancel,
  onRetry,
  onDismiss,
}: {
  state: UploadState;
  onCancel: () => void;
  onRetry: () => void;
  onDismiss: () => void;
}) {
  const elapsed = Math.max(0.001, (Date.now() - state.started_at) / 1000);
  const rate = state.loaded > 0 ? state.loaded / elapsed : 0;
  const remaining = state.total - state.loaded;
  const eta = rate > 0 ? remaining / rate : null;
  const percent =
    state.total > 0
      ? Math.min(100, Math.round((state.loaded / state.total) * 100))
      : null;

  return (
    <aside className="upload-panel" aria-live="polite">
      <div className="upload-head">
        <strong>{state.file.name}</strong>
        <button
          className="link"
          type="button"
          onClick={onDismiss}
          aria-label="Close upload"
        >
          Close
        </button>
      </div>
      <p className="as-run">
        {state.phase === 'signing'
          ? 'Signing upload'
          : state.phase === 'uploading'
            ? `UP ${percent ?? 0}% · ${formatBytes(state.loaded)}/${formatBytes(state.total)}${
                rate > 0 ? ` · ${formatBytes(rate)}/s` : ''
              }${eta !== null ? ` · ETA ${formatClock(eta * 1000)}` : ''}`
            : state.phase === 'verifying'
              ? 'Verifying bytes with storage'
              : state.phase === 'done'
                ? 'Uploaded · preparing playback'
                : state.phase === 'cancelled'
                  ? 'Cancelled'
                  : 'Upload failed'}
      </p>

      {state.phase === 'uploading' ? (
        <div
          className="meter"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent ?? 0}
        >
          <span style={{ width: `${percent ?? 0}%` }} />
        </div>
      ) : null}

      {state.error ? <p className="error-text">{state.error}</p> : null}

      {state.phase === 'uploading' || state.phase === 'signing' ? (
        <button className="secondary" type="button" onClick={onCancel}>
          Cancel upload
        </button>
      ) : null}
      {state.phase === 'failed' ? (
        <button className="secondary" type="button" onClick={onRetry}>
          Retry upload
        </button>
      ) : null}
    </aside>
  );
}

function ErrorBanner({
  error,
  onRetry,
}: {
  error: { code: string; message: string; action: string };
  onRetry: () => void;
}) {
  return (
    <div className="error-banner" role="alert">
      <span>{error.message}</span>
      {error.action === 'retry' ? (
        <button className="link" type="button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

function asApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause;
  return new ApiError(
    {
      code: 'internal',
      message: cause instanceof Error ? cause.message : 'Something went wrong.',
      detail: {},
      retryable: true,
      action: 'retry',
    },
    0,
  );
}

function isPending(status: LibraryStatus): boolean {
  return status !== 'ready' && status !== 'failed' && status !== 'upload_incomplete';
}

function statusLabel(status: LibraryStatus): string {
  switch (status) {
    case 'uploading':
      return 'Uploading';
    case 'uploaded':
      return 'Uploaded';
    case 'probing':
      return 'Reading';
    case 'dissecting':
      return 'Splitting beats';
    case 'ready':
      return 'Ready';
    case 'upload_incomplete':
      return 'Upload incomplete';
    case 'failed':
      return 'Failed';
    case 'deleting':
      return 'Deleting';
  }
}

function tone(status: LibraryStatus): string {
  if (status === 'ready') return 'ready';
  if (status === 'failed' || status === 'upload_incomplete') return 'failed';
  if (
    status === 'uploading' ||
    status === 'uploaded' ||
    status === 'probing' ||
    status === 'dissecting'
  ) {
    return 'busy';
  }
  return 'muted';
}

function asRun(item: LibraryItem): string {
  const parts: string[] = [];
  if (item.duration_ms !== null) parts.push(`PROBE ${formatDuration(item.duration_ms)}`);
  if (item.width !== null && item.height !== null)
    parts.push(`${item.width}×${item.height}`);
  if (item.fps !== null) parts.push(formatFps(item.fps));
  if (item.bytes !== null) parts.push(formatBytes(item.bytes));
  return parts.join(' · ');
}

function asRunDetail(item: LibraryDetail): string {
  const parts: string[] = [];
  const probe = item.probe;
  if (probe) {
    parts.push(`PROBE ${formatDuration(probe.duration_ms)}`);
    parts.push(`${probe.display_width}×${probe.display_height}`);
    parts.push(formatFps(probe.fps));
    parts.push(
      `${probe.video_codec.toUpperCase()}/${probe.has_audio ? (probe.audio_codec ?? 'audio').toUpperCase() : 'silent'}`,
    );
  }
  if (item.bytes !== null) parts.push(formatBytes(item.bytes));
  return parts.length > 0 ? parts.join(' · ') : 'Measured facts appear after the probe.';
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || !Number.isFinite(bytes)) return '—';
  if (bytes < 1_000) return `${bytes} B`;
  if (bytes < 1_000_000) return `${(bytes / 1_000).toFixed(1)} KB`;
  if (bytes < 1_000_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
}

function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return '—';
  return formatClock(ms);
}

function formatClock(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0)
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function formatFps(fps: number | null | undefined): string {
  if (fps === null || fps === undefined || !Number.isFinite(fps)) return '—';
  return fps.toFixed(3);
}

function formatSize(
  width: number | null | undefined,
  height: number | null | undefined,
): string {
  if (width === null || width === undefined || height === null || height === undefined)
    return '—';
  return `${width}×${height}`;
}
