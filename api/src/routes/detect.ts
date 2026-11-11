import type { Hono } from 'hono';
import { detectionRevision } from '../canonical';
import { ApiError } from '../errors';
import { detectRequestSchema } from '../schemas';
import type { AppEnv } from './shared';
import { detectionFor, ownedItem } from './shared';

/** Below this, a candidate is kept but marked low confidence, never dropped. */
const MIN_CONFIDENCE_MILLI = 350;

type DetectRequest = ReturnType<typeof detectRequestSchema.parse>;

/** The revision covers only what changes the scan, so identical plans reuse a run. */
function revisionPlan(body: DetectRequest) {
  return {
    text: body.text,
    logos: body.logos,
    tile_small_text: body.tile_small_text,
    frame_policy: 'every_frame' as const,
    max_width: body.max_width,
    min_confidence_milli: MIN_CONFIDENCE_MILLI,
    regions: body.regions.map((region) => ({
      box: region.box,
      prompt: region.prompt ?? '',
    })),
    scope_beat_indexes: body.scope?.beat_indexes ?? null,
  };
}

/** What the worker is told to do; `tile_grid` only exists in the payload. */
function workerOptions(body: DetectRequest) {
  return {
    text: body.text,
    logos: body.logos,
    tile_small_text: body.tile_small_text,
    tile_grid: '2x2' as const,
    frame_policy: 'every_frame' as const,
    max_width: body.max_width,
    min_confidence_milli: MIN_CONFIDENCE_MILLI,
    regions: body.regions.map((region) => ({
      box: region.box,
      ...(region.prompt ? { prompt: region.prompt } : {}),
    })),
    scope_beat_indexes: body.scope?.beat_indexes ?? null,
  };
}

/** The M2 image ships RapidOCR only. Do not record an engine it cannot run. */
function resolvedEngine(value: DetectRequest['engine']): 'rapidocr' {
  if (value === 'paddleocr') {
    throw new ApiError(
      'validation',
      'PaddleOCR is not installed in this worker. Use auto or RapidOCR.',
      { detail: { engine: value } },
    );
  }
  return 'rapidocr';
}

export function registerDetectRoutes(app: Hono<AppEnv>): void {
  app.post('/api/v1/library/:itemId/detect', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const itemId = c.req.param('itemId');
    const raw = (await c.req.json().catch(() => ({}))) as Record<string, unknown>;
    const body = detectRequestSchema.parse({ text: true, logos: true, ...raw });

    const item = await ownedItem(runtime, user.id, itemId);
    const source = await runtime.db.source(user.id, itemId);
    if (!source) throw new ApiError('not_found', 'Source not found.');
    const beats = await runtime.db.beats(user.id, itemId);
    if (
      source.probeStatus !== 'succeeded' ||
      !source.probeJson ||
      source.dissectStatus !== 'succeeded' ||
      beats.length === 0
    ) {
      throw new ApiError('conflict', 'The source is still being prepared.', {
        detail: {
          reason: 'not_ready',
          probe_status: source.probeStatus,
          dissect_status: source.dissectStatus,
          beats: beats.length,
        },
      });
    }
    if (!source.sha256) {
      throw new ApiError('conflict', 'The source digest is unknown.', {
        detail: { reason: 'source_sha256_missing' },
      });
    }

    const scope = body.scope?.beat_indexes ?? null;
    if (scope && beats.every((beat) => !scope.includes(beat.index))) {
      throw new ApiError('validation', 'No beats were selected.', {
        detail: { reason: 'empty_scope' },
      });
    }
    const plan = revisionPlan(body);
    const revision = await detectionRevision({
      source_sha256: source.sha256,
      beat_manifest_hash: source.beatManifestHash ?? '',
      detect: plan,
      engine: { ocr: 'rapidocr', logo: 'none', segmentation: 'none' },
      models: {},
    });

    const existing = await runtime.db.latestDetectionRun(user.id, itemId);
    if (existing?.revision === revision) {
      if (existing.status === 'queued' || existing.status === 'running') {
        throw new ApiError('conflict', 'This detection plan is already running.', {
          detail: { reason: 'detection_running', run_id: existing.id },
        });
      }
      if (existing.status === 'succeeded') {
        return c.json(await detectionFor(runtime, user.id, itemId));
      }
    }

    const detectionWidth = Math.min(body.max_width, item.width ?? body.max_width);
    const detectionHeight =
      item.width && item.height
        ? Math.max(2, Math.round((item.height * detectionWidth) / item.width))
        : null;
    const engine = resolvedEngine(body.engine);
    const runId = crypto.randomUUID();
    const workerJobId = crypto.randomUUID();
    const created = await runtime.db.createOrRetryJob({
      userId: user.id,
      itemId,
      assetId: source.id,
      kind: 'detect',
      deviceClass: 'cpu',
      idempotencyKey: `detect:${source.id}:${revision}`,
      workerJobId,
      request: {
        run_id: runId,
        revision,
        options: {
          ...workerOptions(body),
          scope_beat_indexes: scope,
        },
      },
    });
    if (!created.created && !created.retried) {
      throw new ApiError('conflict', 'This detection plan already ran.', {
        detail: { reason: 'detection_exists', job_id: created.id },
      });
    }
    try {
      await runtime.db.createDetectionRun({
        id: runId,
        userId: user.id,
        assetId: source.id,
        revision,
        engine,
        detectionWidth,
        detectionHeight,
        workerJobId,
      });
    } catch (error) {
      await runtime.db.failJob(created.id, 'internal', 'could not create detection run', {
        retryable: false,
        attempts: 0,
        maxAttempts: 3,
      });
      throw error;
    }
    try {
      await runtime.enqueue({ job_id: created.id });
    } catch {
      await runtime.db.failDetectionRun(runId, 'worker_unavailable', 'dispatch_failed');
      await runtime.db.failJob(created.id, 'worker_unavailable', 'dispatch_failed', {
        retryable: false,
        attempts: 0,
        maxAttempts: 3,
      });
      throw new ApiError('worker_unavailable', 'Detection could not be dispatched.');
    }
    return c.json(await detectionFor(runtime, user.id, itemId), 202);
  });

  app.post('/api/v1/library/:itemId/detect/cancel', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const itemId = c.req.param('itemId');
    await ownedItem(runtime, user.id, itemId);
    if (!(await runtime.db.requestDetectionCancel(user.id, itemId))) {
      throw new ApiError('conflict', 'There is no detection run to cancel.', {
        detail: { reason: 'no_detection' },
      });
    }
    // A run already handed to the worker finishes its call; the API discards the
    // result instead of pretending the compute never happened. The state below
    // shows that: a queued run is cancelled, a running one stays running.
    return c.json(await detectionFor(runtime, user.id, itemId), 202);
  });
}
