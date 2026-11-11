import type { LibraryItem } from '../types';
import { asRun, statusLabel, tone } from '../status';
import { ErrorBanner } from './ErrorBanner';

export function LibraryPanel({
  items,
  selectedId,
  loading,
  error,
  onSelect,
  onRefresh,
}: {
  items: LibraryItem[];
  selectedId: string | null;
  loading: boolean;
  error: { code: string; message: string; action: string } | null;
  onSelect: (id: string) => void;
  onRefresh: () => void;
}) {
  return (
    <section className="library" aria-label="Your library">
      <div className="section-head">
        <h1>Library</h1>
        <button className="link" type="button" onClick={onRefresh}>
          Refresh
        </button>
      </div>{' '}
      {error ? <ErrorBanner error={error} onRetry={onRefresh} /> : null}
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
            Upload a video and DuckClean will report its real duration, size and playback
            readiness here.
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
                onClick={() => onSelect(item.id)}
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
  );
}
