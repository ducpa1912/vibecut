import { beatManifestHash, type BeatManifestPlan } from '../canonical';
import type { Db, SourceRow } from '../db';
import { MAX_DURATION_MS, MAX_DIMENSION_PX, WORKER_OUTPUT_TTL_SECONDS } from '../limits';
import { keys } from '../storage';
import {
  detectResponseSchema,
  dissectResponseSchema,
  probeResponseSchema,
  proxyResponseSchema,
} from '../worker-contract';
import {
  DISSECT_PARAMS,
  type DispatchRuntime,
  type RunnableJob,
  type RunnableJobKind,
} from './types';
import { callWorker, decodeBase64, DispatchError, sourceInput } from './worker';

/** Everything a handler needs: the queue row, its runtime and its verified source. */
export interface JobContext {
  runtime: DispatchRuntime;
  job: RunnableJob;
  source: SourceRow;
}

/** A handler either finishes the job or throws a `DispatchError`. */
export type JobHandler = (ctx: JobContext) => Promise<void>;

/** Frame -> integer milliseconds, floored so spans stay ordered and half-open. */
function startMs(frame: number, fpsNum: number, fpsDen: number): number {
  return Math.floor((frame * 1000 * fpsDen) / fpsNum);
}

function requireProbe(source: SourceRow): Record<string, unknown> {
  if (!source.probeJson) {
    throw new DispatchError('source_unreadable', 'probe facts are missing', false);
  }
  return source.probeJson;
}

/**
 * Probe decides the whole pipeline: it rejects unusable media, then queues the
 * proxy encode and the dissection side by side.
 */
async function runProbe({ runtime, job, source }: JobContext): Promise<void> {
  const body = {
    job_id: job.workerJobId,
    input: await sourceInput(runtime, source.r2Key),
    callback: null,
  };
  const parsed = probeResponseSchema.safeParse(
    await callWorker(runtime, '/v1/probe', body),
  );
  if (!parsed.success) {
    throw new DispatchError('payload_invalid', parsed.error.message, false);
  }
  const probe = parsed.data.probe;
  if (probe.duration_ms > MAX_DURATION_MS) {
    throw new DispatchError('too_large', 'The source is longer than 30 minutes.', false);
  }
  if (probe.display_width > MAX_DIMENSION_PX || probe.display_height > MAX_DIMENSION_PX) {
    throw new DispatchError('too_large', 'The source is larger than 4096 px.', false);
  }
  await runtime.db.applyProbe(
    { userId: job.userId, itemId: job.libraryItemId, assetId: job.sourceAssetId },
    probe,
    probe as unknown as Record<string, unknown>,
  );

  const proxyJobId = crypto.randomUUID();
  const created = await runtime.db.createJob({
    userId: job.userId,
    itemId: job.libraryItemId,
    assetId: job.sourceAssetId,
    kind: 'proxy',
    deviceClass: 'cpu',
    idempotencyKey: `proxy:${job.sourceAssetId}`,
    workerJobId: proxyJobId,
    request: { proxy_key: keys.proxy(job.userId, job.sourceAssetId) },
  });
  await runtime.enqueue({ job_id: created.id });

  // Dissection runs beside the proxy encode: both need the source, neither
  // needs the other, and the item becomes ready when both have landed.
  const dissectJobId = crypto.randomUUID();
  const dissect = await runtime.db.createJob({
    userId: job.userId,
    itemId: job.libraryItemId,
    assetId: job.sourceAssetId,
    kind: 'dissect',
    deviceClass: 'cpu',
    idempotencyKey: `dissect:${job.sourceAssetId}`,
    workerJobId: dissectJobId,
    request: { params: DISSECT_PARAMS },
  });
  await runtime.enqueue({ job_id: dissect.id });
  await runtime.db.markDissecting(job.userId, job.libraryItemId);
  await runtime.db.succeedJob(job.id, { probe }, parsed.data.usage.compute_seconds);
}

/** Dissect turns the probe into beats and freezes their manifest hash. */
async function runDissect({ runtime, job, source }: JobContext): Promise<void> {
  const probeRaw = requireProbe(source);
  const body = {
    job_id: job.workerJobId,
    input: await sourceInput(runtime, source.r2Key),
    probe: probeRaw,
    params: DISSECT_PARAMS,
    callback: null,
  };
  const parsed = dissectResponseSchema.safeParse(
    await callWorker(runtime, '/v1/dissect', body),
  );
  if (!parsed.success) {
    throw new DispatchError('payload_invalid', parsed.error.message, false);
  }
  const probe = probeRaw as {
    frame_count: number;
    display_width: number;
    display_height: number;
    fps_num: number;
    fps_den: number;
  };
  if (parsed.data.beats.at(-1)?.end_frame !== probe.frame_count) {
    throw new DispatchError(
      'payload_invalid',
      `beats end at frame ${parsed.data.beats.at(-1)?.end_frame}, source has ${probe.frame_count}`,
      false,
    );
  }
  const plan: BeatManifestPlan = {
    source: {
      sha256: parsed.data.source_sha256,
      bytes: source.bytes,
      frame_count: probe.frame_count,
      width: probe.display_width,
      height: probe.display_height,
    },
    params: {
      fps_num: probe.fps_num,
      fps_den: probe.fps_den,
      max_seconds_milli: DISSECT_PARAMS.max_seconds_milli,
      min_seconds_milli: DISSECT_PARAMS.min_seconds_milli,
      scene_threshold_milli: DISSECT_PARAMS.scene_threshold_milli,
    },
    beats: parsed.data.beats,
  };
  const manifestHash = await beatManifestHash(plan);
  await runtime.db.applyDissect(
    { userId: job.userId, itemId: job.libraryItemId, assetId: job.sourceAssetId },
    {
      beats: parsed.data.beats.map((beat) => ({
        index: beat.index,
        startFrame: beat.start_frame,
        endFrame: beat.end_frame,
        boundary: beat.boundary,
        startMs: startMs(beat.start_frame, probe.fps_num, probe.fps_den),
        endMs: startMs(beat.end_frame, probe.fps_num, probe.fps_den),
      })),
      manifestHash,
      manifest: plan as unknown as Record<string, unknown>,
      sourceSha256: parsed.data.source_sha256,
    },
  );
  await runtime.db.succeedJob(
    job.id,
    { beat_manifest_hash: manifestHash, beats: parsed.data.beats.length },
    parsed.data.usage.compute_seconds,
  );
}

/** Proxy: the worker downloads the verified source and writes both objects. */
async function runProxy({ runtime, job, source }: JobContext): Promise<void> {
  const probeRaw = requireProbe(source);
  const proxyKey = keys.proxy(job.userId, job.sourceAssetId);
  const posterKey = keys.poster(job.userId, job.sourceAssetId);
  const output = await runtime.signer.presignPut(
    proxyKey,
    WORKER_OUTPUT_TTL_SECONDS,
    'video/mp4',
  );
  const poster = await runtime.signer.presignPut(
    posterKey,
    WORKER_OUTPUT_TTL_SECONDS,
    'image/jpeg',
  );
  const body = {
    job_id: job.workerJobId,
    input: await sourceInput(runtime, source.r2Key),
    output: {
      url: output.url,
      method: 'PUT' as const,
      headers: { 'content-type': 'video/mp4' },
      expires_at: output.expiresAt,
    },
    poster: {
      url: poster.url,
      method: 'PUT' as const,
      headers: { 'content-type': 'image/jpeg' },
      expires_at: poster.expiresAt,
    },
    probe: probeRaw,
    options: { max_height: 720 },
    callback: null,
  };
  const parsed = proxyResponseSchema.safeParse(
    await callWorker(runtime, '/v1/proxy', body),
  );
  if (!parsed.success) {
    throw new DispatchError('payload_invalid', parsed.error.message, false);
  }
  const head = await runtime.media.head(proxyKey);
  if (!head || head.size !== parsed.data.proxy.bytes) {
    throw new DispatchError('storage_failed', 'proxy object is missing or short', true);
  }
  const posterHead = await runtime.media.head(posterKey);
  if (!posterHead || posterHead.size !== parsed.data.poster.bytes) {
    throw new DispatchError('storage_failed', 'poster object is missing or short', true);
  }
  await runtime.db.applyProxy(
    { userId: job.userId, itemId: job.libraryItemId, assetId: job.sourceAssetId },
    {
      proxyKey,
      posterKey,
      proxyId: crypto.randomUUID(),
      posterId: crypto.randomUUID(),
      width: parsed.data.proxy.width,
      height: parsed.data.proxy.height,
      fpsNum: parsed.data.proxy.fps_num,
      fpsDen: parsed.data.proxy.fps_den,
      durationMs: parsed.data.proxy.duration_ms,
      proxyBytes: parsed.data.proxy.bytes,
      posterBytes: parsed.data.poster.bytes,
      posterWidth: parsed.data.poster.width,
      posterHeight: parsed.data.poster.height,
      frameIndex: parsed.data.poster.frame_index ?? null,
      now: new Date(),
    },
  );
  await runtime.db.succeedJob(
    job.id,
    parsed.data as unknown as Record<string, unknown>,
    parsed.data.usage.compute_seconds,
  );
}

type DetectGroups = Parameters<Db['applyDetection']>[1]['groups'];
type DetectMasks = Parameters<Db['applyDetection']>[1]['masks'];

/**
 * Masks leave the worker inline; the API writes them and keeps only the keys.
 * Group and member rows are mapped in the same pass.
 */
async function storeGroups(
  runtime: DispatchRuntime,
  userId: string,
  runId: string,
  parsedGroups: Awaited<ReturnType<typeof detectResponseSchema.parse>>['groups'],
): Promise<{ groups: DetectGroups; masks: DetectMasks }> {
  const masks: DetectMasks = [];
  const groups: DetectGroups = [];
  for (const group of parsedGroups) {
    const members: DetectGroups[number]['members'] = [];
    for (const member of group.members) {
      let maskId: string | null = null;
      const mask = member.mask;
      if (mask?.png_base64) {
        const key = keys.mask(userId, runId, mask.mask_id);
        const written = await runtime.media.put(
          key,
          decodeBase64(mask.png_base64),
          'image/png',
        );
        masks.push({
          id: mask.mask_id,
          key,
          kind: mask.kind,
          bytes: written.size,
          groupId: group.group_id,
          memberId: member.member_id,
          format: mask.format,
          frameStart: mask.frame_start,
          frameEnd: mask.frame_end,
          provenance: mask.provenance,
          modelVersion: mask.model_version,
        });
        maskId = mask.mask_id;
      }
      members.push({
        id: member.member_id,
        orderIndex: member.order_index,
        text: member.text,
        rangeMode: member.range_mode,
        ranges: member.ranges,
        box: member.box,
        confidenceMilli: member.confidence_milli,
        provenance: member.provenance,
        includedDefault: member.included_default,
        lowConfidence: member.low_confidence,
        maskId,
      });
    }
    groups.push({
      id: group.group_id,
      kind: group.kind,
      lane: group.lane,
      orderIndex: group.order_index,
      sampleText: group.sample_text,
      box: group.box,
      confidenceMilli: group.confidence_milli,
      includedDefault: group.included_default,
      lowConfidence: group.low_confidence,
      members,
    });
  }
  return { groups, masks };
}

/** Detect scans every beat and stores the run, its groups, members and masks. */
async function runDetect({ runtime, job, source }: JobContext): Promise<void> {
  const runId = typeof job.request.run_id === 'string' ? job.request.run_id : '';
  const revision = typeof job.request.revision === 'string' ? job.request.revision : '';
  if (!runId || !revision) {
    throw new DispatchError('internal', 'detect job is missing its run', false);
  }
  const probeRaw = requireProbe(source);
  const beatRows = await runtime.db.beats(job.userId, job.libraryItemId);
  if (beatRows.length === 0) {
    throw new DispatchError('conflict', 'the source has no beats to scan', false);
  }
  const options =
    typeof job.request.options === 'object' && job.request.options !== null
      ? (job.request.options as Record<string, unknown>)
      : {};
  const scope = Array.isArray(options.scope_beat_indexes)
    ? options.scope_beat_indexes.filter(
        (value): value is number => typeof value === 'number' && Number.isInteger(value),
      )
    : null;
  const selected = scope
    ? beatRows.filter((beat) => scope.includes(beat.index))
    : beatRows;
  if (selected.length === 0) {
    throw new DispatchError('payload_invalid', 'no beats were selected', false);
  }
  await runtime.db.startDetectionRun(runId);
  const parsed = detectResponseSchema.safeParse(
    await callWorker(runtime, '/v1/detect', {
      job_id: job.workerJobId,
      input: await sourceInput(runtime, source.r2Key),
      probe: probeRaw,
      revision,
      beats: selected.map((beat) => ({
        id: beat.id,
        index: beat.index,
        start_frame: beat.startFrame,
        end_frame: beat.endFrame,
      })),
      detect: options,
      callback: null,
    }),
  );
  if (!parsed.success) {
    throw new DispatchError('payload_invalid', parsed.error.message, false);
  }
  if (parsed.data.revision !== revision) {
    throw new DispatchError(
      'payload_invalid',
      'the worker answered for a different revision',
      false,
    );
  }

  const { groups, masks } = await storeGroups(
    runtime,
    job.userId,
    runId,
    parsed.data.groups,
  );
  const applied = await runtime.db.applyDetection(runId, {
    truncated: parsed.data.coverage.truncated,
    framesRead: parsed.data.coverage.frames_read,
    framesTotal: parsed.data.coverage.frames_total,
    framesSkipped: parsed.data.coverage.frames_skipped,
    effectiveFpsMilli: parsed.data.coverage.effective_fps_milli,
    ocrAvailable: parsed.data.coverage.ocr_available,
    logoModelAvailable: parsed.data.coverage.logo_model_available,
    warnings: parsed.data.coverage.warnings,
    modelVersions: parsed.data.usage.model_versions,
    computeSeconds: parsed.data.usage.compute_seconds,
    deviceClass: parsed.data.usage.device_class,
    scopeBeatIndexes: scope,
    groups,
    masks,
  });
  await runtime.db.succeedJob(
    job.id,
    { revision, groups: groups.length, applied },
    parsed.data.usage.compute_seconds,
  );
}

/** The dispatch table. Kinds absent here are acknowledged without running. */
export const handlers: Record<RunnableJobKind, JobHandler> = {
  probe: runProbe,
  proxy: runProxy,
  dissect: runDissect,
  detect: runDetect,
};
