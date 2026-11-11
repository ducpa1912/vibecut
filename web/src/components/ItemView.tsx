import { useEffect, useState } from 'react';
import { asApiError } from '../errors';
import { formatBytes, formatDuration, formatFps, formatSize } from '../format';
import { asRunDetail, statusLabel, tone } from '../status';
import type { DetectionView, LibraryDetail } from '../types';
import { ErrorBanner } from './ErrorBanner';

export function ItemView({
  item,
  onPlay,
  onRetry,
  onDetect,
  onDetection,
}: {
  item: LibraryDetail;
  onPlay: () => Promise<string>;
  onRetry: () => void;
  onDetect: () => Promise<DetectionView>;
  onDetection: () => Promise<DetectionView>;
}) {
  const [playUrl, setPlayUrl] = useState<string | null>(null);
  const [playError, setPlayError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [detection, setDetection] = useState<DetectionView | null>(item.detection);
  const [detectError, setDetectError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    setDetection(item.detection);
  }, [item.id, item.detection]);

  const run = detection?.run ?? null;
  const scanning = run !== null && (run.status === 'queued' || run.status === 'running');

  // The run is real work on a worker; poll until it settles, never guess progress.
  useEffect(() => {
    if (!scanning) return;
    let alive = true;
    const timer = window.setInterval(() => {
      onDetection()
        .then((value) => {
          if (alive) setDetection(value);
        })
        .catch((cause) => {
          if (alive) setDetectError(asApiError(cause).message);
        });
    }, 2_500);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [onDetection, scanning]);

  async function detect() {
    setStarting(true);
    setDetectError(null);
    try {
      setDetection(await onDetect());
    } catch (cause) {
      setDetectError(asApiError(cause).message);
    } finally {
      setStarting(false);
    }
  }

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
      </div>{' '}
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
      ) : null}{' '}
      <section className="detection" aria-label="Detection" aria-live="polite">
        <div className="detection-head">
          <h3>Detection</h3>
          {item.beats.total > 0 ? (
            <button
              className="secondary"
              type="button"
              onClick={() => void detect()}
              disabled={starting || scanning}
            >
              {starting || scanning ? 'Scanning' : run ? 'Scan again' : 'Find text'}
            </button>
          ) : null}
        </div>

        {item.beats.total === 0 ? (
          <p className="muted">
            Beats appear here once the clip is split. Detection needs them.
          </p>
        ) : (
          <>
            <p className="as-run">
              BEATS {item.beats.total} · WITH TARGET {item.beats.with_target}
              {run ? ` · ${run.status.toUpperCase()}` : ''}
            </p>
            {detectError ? <p className="error-text">{detectError}</p> : null}
            {run ? (
              <>
                <dl className="facts">
                  <Fact
                    label="Frames"
                    value={`${run.frames_read} read / ${run.frames_skipped} skipped / ${run.frames_total}`}
                  />
                  <Fact
                    label="Coverage"
                    value={
                      run.coverage === null
                        ? null
                        : `${Math.round(run.coverage * 100)}% of frames read`
                    }
                  />
                  <Fact
                    label="OCR"
                    value={run.ocr_available ? 'available' : 'unavailable'}
                  />
                  <Fact
                    label="Logos"
                    value={run.logo_model_available ? 'available' : 'no model'}
                  />
                </dl>
                {run.error ? <p className="error-text">{run.error.message}</p> : null}
                {run.truncated ? (
                  <p className="muted">
                    This scan stopped at the worker frame cap. Frames after that were not
                    read.
                  </p>
                ) : null}
                {run.warnings.length > 0 ? (
                  <p className="as-run">WARNING {run.warnings.join(' · ')}</p>
                ) : null}
              </>
            ) : null}
            {detection && detection.groups.length > 0 ? (
              <ul className="detections">
                {detection.groups.map((group) => (
                  <li key={group.id}>
                    <span className="detection-kind">{group.kind}</span>
                    <span>{group.sample_text ?? group.members[0]?.text ?? 'region'}</span>
                    <span className="as-run">
                      {group.members.reduce(
                        (total, member) => total + member.ranges.length,
                        0,
                      )}{' '}
                      range{group.members.length === 1 ? '' : 's'} ·{' '}
                      {Math.round(group.confidence * 100)}%
                      {group.low_confidence ? ' · low' : ''}
                    </span>
                  </li>
                ))}
              </ul>
            ) : detection && run?.status === 'succeeded' ? (
              <p className="muted">No text was found in the frames that were read.</p>
            ) : null}
          </>
        )}
      </section>
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
