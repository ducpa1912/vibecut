/**
 * HTTP wire shapes. Every route that returns a library item or a detection state
 * goes through these functions, so the client never sees two spellings of the
 * same record.
 */

import type { Db, LibraryRow } from './db';
import { num } from './db';
import { ApiError } from './errors';
import { POSTER_TTL_SECONDS } from './limits';
import { ERROR_CODES, type ErrorCode } from './schemas';
import type { Signer } from './storage';

const SAFE_MESSAGE: Record<ErrorCode, string> = {
  unauthorized: 'Sign in to continue.',
  forbidden: 'This action is not allowed.',
  not_found: 'Not found.',
  validation: 'The request is invalid.',
  conflict: 'The request conflicts with the current state.',
  too_large: 'The file is larger than this plan allows.',
  unsupported_media: 'That file type is not supported.',
  quota: 'This upload would exceed your storage.',
  rate_limited: 'Too many requests. Try again shortly.',
  stale_detection: 'Detection changed. Review the new ranges.',
  worker_unavailable: 'The processing worker is not available.',
  source_unreadable: 'The file could not be read.',
  render_failed: 'The render failed.',
  cancelled: 'The job was cancelled.',
  internal: 'Unexpected server error.',
};

const MASK_TTL_SECONDS = 15 * 60;

function isErrorCode(value: string | null): value is ErrorCode {
  return value !== null && (ERROR_CODES as readonly string[]).includes(value);
}

/** Stored failure → the same envelope clients already handle. Detail is dropped. */
export function storedError(row: LibraryRow) {
  if (!isErrorCode(row.statusErrorCode)) return null;
  return new ApiError(row.statusErrorCode, SAFE_MESSAGE[row.statusErrorCode]).toBody();
}

/**
 * One wire shape for `GET /detect`, `POST /detect` and the library item, so a
 * client never has to reconcile two spellings of the same detection state.
 */
export async function detectionWire(
  state: Awaited<ReturnType<Db['detectionState']>>,
  signer: Signer,
) {
  const groups = await Promise.all(
    state.groups.map(async (group) => ({
      id: group.id,
      kind: group.kind,
      lane: group.lane,
      order_index: group.orderIndex,
      sample_text: group.sampleText,
      box: group.box,
      confidence: group.confidenceMilli / 1000,
      member_count: group.members.length,
      included_default: group.includedDefault,
      low_confidence: group.lowConfidence,
      members: await Promise.all(
        group.members.map(async (member) => {
          let mask = null;
          if (
            member.maskId &&
            member.maskKey &&
            member.maskFormat &&
            member.maskProvenance &&
            member.maskModelVersion
          ) {
            const ticket = await signer.presignGet(member.maskKey, MASK_TTL_SECONDS);
            mask = {
              id: member.maskId,
              kind: member.maskKind ?? 'glyph',
              format: member.maskFormat,
              url: ticket.url,
              expires_at: ticket.expiresAt,
              provenance: member.maskProvenance,
              model_version: member.maskModelVersion,
            };
          }
          return {
            id: member.id,
            text: member.text,
            range_mode: member.rangeMode,
            ranges: member.ranges,
            box: member.box,
            confidence: member.confidenceMilli / 1000,
            provenance: member.provenance,
            mask,
            included_default: member.includedDefault,
            low_confidence: member.lowConfidence,
            fill_keys: [],
          };
        }),
      ),
    })),
  );

  const run = state.run;
  const beats = state.beats.map((beat) => ({
    beat_id: beat.id,
    index: beat.index,
    start_ms: beat.startMs,
    end_ms: beat.endMs,
    status: beat.status,
    has_target: beat.hasTarget,
  }));
  return {
    run: run
      ? {
          id: run.id,
          revision: run.revision,
          status: run.status,
          progress: run.progressMilli / 1000,
          engine: run.engine,
          model_versions: run.modelVersions,
          frames_read: run.framesRead,
          frames_skipped: run.framesSkipped,
          frames_total: run.framesTotal,
          effective_fps:
            run.effectiveFpsMilli === null ? null : run.effectiveFpsMilli / 1000,
          coverage: run.coverageMilli === null ? null : run.coverageMilli / 1000,
          truncated: run.truncated,
          ocr_available: run.ocrAvailable,
          logo_model_available: run.logoModelAvailable,
          warnings: run.warnings,
          compute_seconds: run.computeSeconds,
          device_class: run.deviceClass,
          error: run.errorCode
            ? {
                code: run.errorCode,
                message: run.errorDetail ?? 'Detection failed.',
                detail: {},
                retryable: false,
                action: 'none' as const,
              }
            : null,
          started_at: run.startedAt,
          finished_at: run.finishedAt,
        }
      : null,
    groups,
    beats,
    selection_counts: {
      groups: groups.length,
      members: groups.reduce((total, group) => total + group.members.length, 0),
      beats_with_target: beats.filter((beat) => beat.has_target).length,
    },
  };
}

export async function toWireItem(row: LibraryRow, signer: Signer) {
  const poster = row.posterKey
    ? await signer.presignGet(row.posterKey, POSTER_TTL_SECONDS)
    : null;
  return {
    id: row.id,
    title: row.title,
    status: row.status,
    error: storedError(row),
    created_at: row.createdAt,
    updated_at: row.updatedAt,
    duration_ms: row.durationMs,
    width: row.width,
    height: row.height,
    fps: row.fpsNum && row.fpsDen ? row.fpsNum / row.fpsDen : null,
    has_audio: row.hasAudio,
    bytes: row.bytes,
    poster_url: poster?.url ?? null,
    poster_expires_at: poster?.expiresAt ?? null,
    detection_revision: row.detectionRevision,
    render_job_id: row.renderJobId,
    render_status: row.renderStatus,
  };
}

/** A probe blob is only exposed when it carries the facts the UI promises. */
export function probeWire(raw: Record<string, unknown> | null) {
  if (!raw) return null;
  const duration = num(raw.duration_ms as number | string | null);
  const width = num(raw.display_width as number | string | null);
  const height = num(raw.display_height as number | string | null);
  const fpsNum = num(raw.fps_num as number | string | null);
  const fpsDen = num(raw.fps_den as number | string | null);
  const frameCount = num(raw.frame_count as number | string | null);
  if (!duration || !width || !height || !fpsNum || !fpsDen || !frameCount) return null;
  return {
    duration_ms: duration,
    display_width: width,
    display_height: height,
    ...(raw.coded_width ? { coded_width: Number(raw.coded_width) } : {}),
    ...(raw.coded_height ? { coded_height: Number(raw.coded_height) } : {}),
    rotation: Number(raw.rotation ?? 0),
    fps: fpsNum / fpsDen,
    fps_num: fpsNum,
    fps_den: fpsDen,
    frame_count: frameCount,
    video_codec: String(raw.video_codec ?? 'unknown'),
    pixel_format: String(raw.pixel_format ?? 'unknown'),
    audio_codec: raw.audio_codec ? String(raw.audio_codec) : null,
    has_audio: Boolean(raw.has_audio),
  };
}
