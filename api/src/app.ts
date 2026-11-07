import { Hono } from 'hono';
import { ZodError } from 'zod';
import type { Bindings } from './bindings';
import type { LibraryRow, UserRecord } from './db';
import { num } from './db';
import { ApiError, errorEnvelope } from './errors';
import {
  MAX_UPLOAD_BYTES,
  PLAY_TTL_SECONDS,
  POSTER_TTL_SECONDS,
  UPLOAD_TTL_SECONDS,
  CONTENT_TYPE_EXT,
  planFor,
} from './limits';
import type { Runtime, RuntimeFactory } from './runtime';
import {
  ERROR_CODES,
  libraryStatusSchema,
  uploadCompleteRequestSchema,
  uploadCreateRequestSchema,
  type ErrorCode,
} from './schemas';
import { keys, verifyUpload, type Signer } from './storage';

export type AppEnv = {
  Bindings: Bindings;
  Variables: {
    requestId: string;
    runtime: Runtime;
    user: UserRecord;
  };
};

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

function isErrorCode(value: string | null): value is ErrorCode {
  return value !== null && (ERROR_CODES as readonly string[]).includes(value);
}

/** Stored failure → the same envelope clients already handle. Detail is dropped. */
function storedError(row: LibraryRow) {
  if (!isErrorCode(row.statusErrorCode)) return null;
  return new ApiError(row.statusErrorCode, SAFE_MESSAGE[row.statusErrorCode]).toBody();
}

function cursorFor(row: LibraryRow): string {
  return btoa(`${row.createdAt}|${row.id}`);
}

function parseCursor(
  raw: string | undefined,
): { createdAt: string; id: string } | undefined {
  if (!raw) return undefined;
  try {
    const [createdAt, id] = atob(raw).split('|');
    if (
      createdAt &&
      id &&
      /^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(createdAt) &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) &&
      !Number.isNaN(Date.parse(createdAt))
    ) {
      return { createdAt: new Date(createdAt).toISOString(), id };
    }
  } catch {
    // fall through
  }
  throw new ApiError('validation', 'The cursor is invalid.');
}

function requestIdFor(header: string | undefined): string {
  if (header && /^[A-Za-z0-9_-]{8,64}$/.test(header)) return header;
  return crypto.randomUUID();
}

function allowedOrigins(value: string): string[] {
  return value
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
}

function parseLimit(raw: string | undefined): number {
  if (raw === undefined) return 25;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1 || value > 100) {
    throw new ApiError('validation', 'limit must be an integer between 1 and 100.');
  }
  return value;
}

async function toWireItem(row: LibraryRow, signer: Signer) {
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

function probeWire(raw: Record<string, unknown> | null) {
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

export function createApp(runtimeFor: RuntimeFactory): Hono<AppEnv> {
  const app = new Hono<AppEnv>();

  app.use('*', async (c, next) => {
    const requestId = requestIdFor(c.req.header('x-request-id'));
    c.set('requestId', requestId);
    c.header('X-Request-Id', requestId);
    c.header('Cache-Control', 'no-store');
    c.header('X-Content-Type-Options', 'nosniff');

    const origin = c.req.header('origin');
    const origins = allowedOrigins(c.env.ALLOWED_ORIGINS);
    if (origin && origins.includes(origin)) {
      c.header('Access-Control-Allow-Origin', origin);
      c.header('Vary', 'Origin');
      c.header(
        'Access-Control-Allow-Headers',
        'authorization, content-type, x-request-id',
      );
      c.header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
      c.header('Access-Control-Max-Age', '600');
      c.header('Access-Control-Expose-Headers', 'x-request-id');
    }
    if (c.req.method === 'OPTIONS') return c.body(null, 204);
    await next();
  });

  app.use('/api/v1/*', async (c, next) => {
    c.set('runtime', runtimeFor(c.env));
    await next();
  });

  app.use('/api/v1/*', async (c, next) => {
    if (c.req.path === '/api/v1/health' || c.req.path.startsWith('/api/v1/webhooks/')) {
      await next();
      return;
    }
    const runtime = c.get('runtime');
    const identity = await runtime.verifier(c.req.raw);
    c.set('user', await runtime.db.ensureUser(identity));
    await next();
  });

  app.get('/api/v1/health', async (c) => {
    const runtime = c.get('runtime');
    let dbOk = false;
    let dbLatency: number | undefined;
    try {
      dbLatency = await runtime.db.ping();
      dbOk = true;
    } catch {
      dbOk = false;
    }

    let r2Ok = false;
    try {
      // A HEAD for a key that does not exist still proves the binding answers.
      await runtime.media.head('__duckclean_healthcheck__');
      r2Ok = true;
    } catch {
      r2Ok = false;
    }

    const ping = async (url: string): Promise<boolean> => {
      if (!url) return false;
      try {
        const response = await runtime.fetcher(`${url.replace(/\/+$/, '')}/health`, {
          signal: AbortSignal.timeout(1_500),
        });
        return response.ok;
      } catch {
        return false;
      }
    };
    const [cpuOk, gpuOk] = await Promise.all([
      ping(c.env.CPU_WORKER_URL),
      ping(c.env.GPU_WORKER_URL),
    ]);

    const status = dbOk && r2Ok && cpuOk && gpuOk ? 'ok' : 'degraded';
    return c.json({
      status,
      version: c.env.API_VERSION,
      request_id: c.get('requestId'),
      time: new Date().toISOString(),
      checks: {
        db: { ok: dbOk, ...(dbLatency === undefined ? {} : { latency_ms: dbLatency }) },
        r2: { ok: r2Ok },
        cpu_worker: { ok: cpuOk },
        gpu_worker: { ok: gpuOk },
      },
    });
  });

  app.get('/api/v1/me', async (c) => {
    const user = c.get('user');
    const plan = planFor(user.plan);
    return c.json({
      id: user.id,
      email: user.email,
      display_name: user.displayName,
      avatar_url: user.avatarUrl,
      plan: user.plan,
      render_seconds_balance: user.renderSecondsBalance,
      storage_bytes_used: user.storageBytesUsed,
      storage_bytes_limit: plan.storage_bytes_limit,
      monthly_render_hours: plan.monthly_render_hours,
    });
  });

  app.post('/api/v1/uploads', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const body = uploadCreateRequestSchema.parse(await c.req.json());

    if (body.bytes > MAX_UPLOAD_BYTES) {
      throw new ApiError('too_large', 'Files are limited to 5 GB.', {
        detail: { max_bytes: MAX_UPLOAD_BYTES },
      });
    }
    const plan = planFor(user.plan);
    if (user.storageBytesUsed + body.bytes > plan.storage_bytes_limit) {
      throw new ApiError('quota', 'This upload would exceed your storage.', {
        detail: {
          storage_bytes_used: user.storageBytesUsed,
          storage_bytes_limit: plan.storage_bytes_limit,
        },
      });
    }

    const ext = CONTENT_TYPE_EXT[body.content_type];
    const itemId = crypto.randomUUID();
    const assetId = crypto.randomUUID();
    const key = keys.source(user.id, assetId, ext);
    const expiresAt = new Date(Date.now() + UPLOAD_TTL_SECONDS * 1000);
    const title = body.title ?? body.filename;

    await runtime.db.createUpload({
      userId: user.id,
      itemId,
      assetId,
      title: title.slice(0, 200),
      filename: body.filename,
      contentType: body.content_type,
      bytes: body.bytes,
      key,
      expiresAt,
    });

    const ticket = await runtime.signer.presignPut(
      key,
      UPLOAD_TTL_SECONDS,
      body.content_type,
    );
    return c.json(
      {
        upload_id: assetId,
        library_item_id: itemId,
        source_asset_id: assetId,
        method: 'PUT' as const,
        url: ticket.url,
        headers: { 'content-type': body.content_type },
        expires_at: ticket.expiresAt,
        max_bytes: body.bytes,
      },
      201,
    );
  });

  app.post('/api/v1/uploads/:uploadId/sign', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const assetId = c.req.param('uploadId');
    const expiresAt = new Date(Date.now() + UPLOAD_TTL_SECONDS * 1000);

    const target = await runtime.db.reSignUpload(user.id, assetId, expiresAt);
    if (!target) {
      const asset = await runtime.db.sourceByAsset(user.id, assetId);
      if (!asset) throw new ApiError('not_found', 'Upload not found.');
      throw new ApiError('conflict', 'This upload is already complete.', {
        detail: { upload_status: asset.uploadStatus },
      });
    }
    const ticket = await runtime.signer.presignPut(
      target.key,
      UPLOAD_TTL_SECONDS,
      target.contentType,
    );
    return c.json({
      upload_id: assetId,
      library_item_id: target.itemId,
      source_asset_id: assetId,
      method: 'PUT' as const,
      url: ticket.url,
      headers: { 'content-type': target.contentType },
      expires_at: ticket.expiresAt,
      max_bytes: target.bytes,
    });
  });

  app.post('/api/v1/uploads/:uploadId/complete', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const assetId = c.req.param('uploadId');
    const body = uploadCompleteRequestSchema.parse(await c.req.json());

    const asset = await runtime.db.sourceByAsset(user.id, assetId);
    if (!asset) throw new ApiError('not_found', 'Upload not found.');

    if (body.bytes !== asset.bytes) {
      throw new ApiError('validation', 'The reported size does not match the ticket.', {
        detail: { declared_bytes: asset.bytes, reported_bytes: body.bytes },
      });
    }

    const verdict = await verifyUpload(runtime.media, asset.r2Key, {
      bytes: asset.bytes,
      etag: body.etag,
    });
    if (!verdict.ok) {
      await runtime.db.setItemError(
        user.id,
        asset.libraryItemId,
        'source_unreadable',
        verdict.reason,
        'upload_incomplete',
      );
      throw new ApiError(
        'source_unreadable',
        'The uploaded file is missing or incomplete.',
        {
          detail: { reason: verdict.reason },
        },
      );
    }

    const completed = await runtime.db.completeUpload(user.id, assetId, {
      bytes: verdict.size,
      etag: verdict.etag,
    });
    if (!completed) throw new ApiError('not_found', 'Upload not found.');

    let probeQueued = false;
    try {
      const workerJobId = crypto.randomUUID();
      const job = await runtime.db.createJob({
        userId: user.id,
        itemId: completed.itemId,
        assetId,
        kind: 'probe',
        deviceClass: 'cpu',
        idempotencyKey: `probe:${assetId}`,
        workerJobId,
        request: { source_key: asset.r2Key },
      });
      await runtime.enqueue({ job_id: job.id });
      probeQueued = true;
    } catch {
      // The bytes are safe; only dispatch failed. Say so instead of failing the upload.
      await runtime.db.setItemError(
        user.id,
        completed.itemId,
        'worker_unavailable',
        'dispatch_failed',
      );
    }

    const row = await runtime.db.item(user.id, completed.itemId);
    if (!row) throw new ApiError('not_found', 'Library item not found.');
    return c.json(
      { library_item: await toWireItem(row, runtime.signer), probe_queued: probeQueued },
      202,
    );
  });

  app.get('/api/v1/library', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const limit = parseLimit(c.req.query('limit'));
    const statusRaw = c.req.query('status');
    const status = statusRaw ? libraryStatusSchema.parse(statusRaw) : undefined;
    const cursor = parseCursor(c.req.query('cursor'));

    const rows = await runtime.db.list(user.id, { limit, status, cursor });
    const page = rows.slice(0, limit);
    const items = await Promise.all(page.map((row) => toWireItem(row, runtime.signer)));
    return c.json({
      items,
      next_cursor:
        rows.length > limit ? cursorFor(page[page.length - 1] as LibraryRow) : null,
    });
  });

  app.get('/api/v1/library/:itemId', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const itemId = c.req.param('itemId');
    const row = await runtime.db.item(user.id, itemId);
    if (!row) throw new ApiError('not_found', 'Library item not found.');

    const [source, proxy, beats] = await Promise.all([
      runtime.db.source(user.id, itemId),
      runtime.db.proxy(user.id, itemId),
      runtime.db.beatSummary(user.id, itemId),
    ]);
    if (!source) throw new ApiError('not_found', 'Source not found.');

    return c.json({
      ...(await toWireItem(row, runtime.signer)),
      source: {
        id: source.id,
        filename: source.filename,
        content_type: source.contentType,
        bytes: source.bytes,
        etag: source.etag,
        sha256: source.sha256,
        upload_status: source.uploadStatus,
        probe_status: source.probeStatus,
        dissect_status: source.dissectStatus,
        beat_manifest_hash: source.beatManifestHash,
      },
      proxy: proxy
        ? {
            id: proxy.id,
            width: proxy.width,
            height: proxy.height,
            duration_ms: proxy.durationMs,
            fps: proxy.fpsNum / proxy.fpsDen,
            bytes: proxy.bytes,
          }
        : null,
      probe: probeWire(source.probeJson),
      beats: {
        total: beats.total,
        with_target: beats.withTarget,
        manifest_hash: source.beatManifestHash,
        items: [],
      },
      // M1 has no detection or render yet. Null is the truth, not an empty state.
      detection: null,
      render: null,
    });
  });

  app.delete('/api/v1/library/:itemId', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const deleted = await runtime.db.softDelete(user.id, c.req.param('itemId'));
    if (!deleted) throw new ApiError('not_found', 'Library item not found.');
    if (deleted.keys.length > 0) {
      try {
        await runtime.media.delete(deleted.keys);
      } catch (error) {
        // The row is already soft-deleted; a lifecycle sweep can retry the purge.
        console.error(
          JSON.stringify({
            level: 'error',
            message: 'media_purge_failed',
            request_id: c.get('requestId'),
            objects: deleted.keys.length,
            error: error instanceof Error ? error.message : String(error),
          }),
        );
      }
    }
    return c.body(null, 204);
  });

  app.get('/api/v1/library/:itemId/play', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const play = await runtime.db.play(user.id, c.req.param('itemId'));
    if (!play) {
      throw new ApiError('conflict', 'Playback is not ready yet.', {
        detail: { reason: 'proxy_missing' },
      });
    }
    const ticket = await runtime.signer.presignGet(play.r2Key, PLAY_TTL_SECONDS);
    return c.json({
      url: ticket.url,
      expires_at: ticket.expiresAt,
      duration_ms: play.durationMs,
      width: play.width,
      height: play.height,
    });
  });

  app.notFound((c) => c.json(errorEnvelope('not_found', 'Route not found.'), 404));

  app.onError((error, c) => {
    if (error instanceof ApiError) {
      return c.json({ error: error.toBody() }, error.status as 400);
    }
    if (error instanceof ZodError) {
      return c.json(
        errorEnvelope('validation', 'The request is invalid.', {
          detail: {
            issues: error.issues.map((issue) => ({
              path: issue.path.join('.'),
              code: issue.code,
            })),
          },
        }),
        400,
      );
    }
    if (error instanceof SyntaxError) {
      return c.json(
        errorEnvelope('validation', 'The request body is not valid JSON.'),
        400,
      );
    }
    if (error instanceof Error && error.name === 'HTTPException') {
      return c.json(errorEnvelope('validation', 'The request is invalid.'), 400);
    }
    console.error(
      JSON.stringify({
        level: 'error',
        message: 'unhandled_api_error',
        request_id: c.get('requestId') ?? null,
        error: error instanceof Error ? error.message : String(error),
      }),
    );
    return c.json(errorEnvelope('internal', 'Unexpected server error.'), 500);
  });

  return app;
}
