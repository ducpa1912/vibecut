import type { UploadState } from '../types';
import { formatBytes, formatClock } from '../format';

export function UploadPanel({
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
