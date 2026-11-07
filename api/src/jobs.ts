import type { Bindings } from './bindings';
import type { Db } from './db';
import { MAX_DURATION_MS, MAX_DIMENSION_PX, WORKER_OUTPUT_TTL_SECONDS } from './limits';
import type { MediaBucket, Signer } from './storage';
import { keys } from './storage';
import { probeResponseSchema, proxyResponseSchema } from './worker-contract';

export interface JobMessage {
  job_id: string;
}

export interface DispatchRuntime {
  db: Db;
  signer: Signer;
  media: MediaBucket;
  enqueue: (message: JobMessage) => Promise<void>;
  fetcher: typeof fetch;
  cpuWorkerUrl: string;
  secret: string;
  keyId: string;
}

class DispatchError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = 'DispatchError';
  }
}

const encoder = new TextEncoder();

async function hmacHex(
  secret: string,
  body: string,
): Promise<{ signature: string; timestamp: number }> {
  const timestamp = Math.floor(Date.now() / 1000);
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const prefix = encoder.encode(`${timestamp}.`);
  const payload = encoder.encode(body);
  const bytes = new Uint8Array(prefix.length + payload.length);
  bytes.set(prefix);
  bytes.set(payload, prefix.length);
  const digest = await crypto.subtle.sign('HMAC', key, bytes);
  const hex = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
  return { signature: hex, timestamp };
}

/** Signed POST to the worker fleet. The body is the exact bytes that were signed. */
async function callWorker(
  runtime: DispatchRuntime,
  path: string,
  body: unknown,
): Promise<unknown> {
  if (!runtime.cpuWorkerUrl) {
    throw new DispatchError('worker_unavailable', 'No worker is configured.', true);
  }
  const raw = JSON.stringify(body);
  const { signature, timestamp } = await hmacHex(runtime.secret, raw);
  let response: Response;
  try {
    response = await runtime.fetcher(
      `${runtime.cpuWorkerUrl.replace(/\/+$/, '')}${path}`,
      {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'X-DuckClean-Signature': `t=${timestamp},v1=${signature}`,
          'X-DuckClean-Key-Id': runtime.keyId,
        },
        body: raw,
        signal: AbortSignal.timeout(240_000),
      },
    );
  } catch {
    throw new DispatchError('worker_unavailable', 'The worker did not answer.', true);
  }

  const text = await response.text();
  if (!response.ok) {
    const retryable = response.status >= 500 || response.status === 429;
    const code =
      response.status === 401 || response.status === 403
        ? 'invalid_signature'
        : response.status >= 500
          ? 'worker_unavailable'
          : 'payload_invalid';
    throw new DispatchError(
      code,
      text.slice(0, 300) || `worker status ${response.status}`,
      retryable,
    );
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new DispatchError(
      'worker_unavailable',
      'The worker returned invalid JSON.',
      true,
    );
  }
}

function sourceUrl(expiresAt: string, url: string) {
  return { url, method: 'GET' as const, headers: {}, expires_at: expiresAt };
}

export type JobOutcome = 'ack' | 'retry';

/**
 * Runs one queue message. Every non-terminal failure is written to
 * `worker_jobs` before the message is retried, so a queue redelivery never
 * hides why a job stopped, and a succeeded job is never re-run.
 */
export async function runJob(
  runtime: DispatchRuntime,
  jobId: string,
): Promise<JobOutcome> {
  const job = await runtime.db.job(jobId);
  if (!job) return 'ack';
  if (
    job.status === 'succeeded' ||
    job.status === 'failed' ||
    job.status === 'cancelled'
  ) {
    return 'ack';
  }
  if (job.kind !== 'probe' && job.kind !== 'proxy') return 'ack';
  if (!job.libraryItemId || !job.sourceAssetId || !job.workerJobId) {
    await runtime.db.failJob(job.id, 'internal', 'job row is missing its target', {
      retryable: false,
      attempts: job.attempts,
      maxAttempts: job.maxAttempts,
    });
    return 'ack';
  }

  const started = await runtime.db.startJob(job.id);
  if (!started) {
    const current = await runtime.db.job(job.id);
    return current?.status === 'running' ? 'retry' : 'ack';
  }
  const attempts = job.attempts + 1;

  const source = await runtime.db.source(job.userId, job.libraryItemId);
  if (!source) {
    await runtime.db.failJob(
      job.id,
      'source_unreadable',
      'source object row is missing',
      {
        retryable: false,
        attempts,
        maxAttempts: job.maxAttempts,
      },
    );
    await runtime.db.setItemError(
      job.userId,
      job.libraryItemId,
      'source_unreadable',
      'source missing',
      'failed',
    );
    return 'ack';
  }

  try {
    if (job.kind === 'probe') {
      const input = await runtime.signer.presignGet(source.r2Key, 15 * 60);
      const body = {
        job_id: job.workerJobId,
        input: sourceUrl(input.expiresAt, input.url),
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
        throw new DispatchError(
          'too_large',
          'The source is longer than 30 minutes.',
          false,
        );
      }
      if (
        probe.display_width > MAX_DIMENSION_PX ||
        probe.display_height > MAX_DIMENSION_PX
      ) {
        throw new DispatchError('too_large', 'The source is larger than 4096 px.', false);
      }
      await runtime.db.applyProbe(
        { userId: job.userId, itemId: job.libraryItemId, assetId: job.sourceAssetId },
        probe,
        probe as unknown as Record<string, unknown>,
      );

      const proxyKey = keys.proxy(job.userId, job.sourceAssetId);
      const proxyJobId = crypto.randomUUID();
      const created = await runtime.db.createJob({
        userId: job.userId,
        itemId: job.libraryItemId,
        assetId: job.sourceAssetId,
        kind: 'proxy',
        deviceClass: 'cpu',
        idempotencyKey: `proxy:${job.sourceAssetId}`,
        workerJobId: proxyJobId,
        request: { proxy_key: proxyKey },
      });
      await runtime.enqueue({ job_id: created.id });
      await runtime.db.succeedJob(job.id, { probe }, parsed.data.usage.compute_seconds);
      return 'ack';
    }

    // Proxy: the worker downloads the verified source and writes both objects.
    const probeRaw = source.probeJson;
    if (!probeRaw) {
      throw new DispatchError('source_unreadable', 'probe facts are missing', false);
    }
    const proxyKey = keys.proxy(job.userId, job.sourceAssetId);
    const posterKey = keys.poster(job.userId, job.sourceAssetId);
    const input = await runtime.signer.presignGet(source.r2Key, 15 * 60);
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
      input: sourceUrl(input.expiresAt, input.url),
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
    return 'ack';
  } catch (error) {
    const dispatch =
      error instanceof DispatchError
        ? error
        : new DispatchError(
            'internal',
            error instanceof Error ? error.message : 'unexpected dispatch failure',
            true,
          );
    const terminal = await runtime.db.failJob(job.id, dispatch.code, dispatch.message, {
      retryable: dispatch.retryable,
      attempts,
      maxAttempts: job.maxAttempts,
    });
    if (terminal) {
      const status = dispatch.code === 'too_large' ? 'failed' : 'failed';
      await runtime.db.setItemError(
        job.userId,
        job.libraryItemId,
        dispatch.code,
        dispatch.message,
        status,
      );
    }
    return terminal ? 'ack' : 'retry';
  }
}

export function createQueueHandler(runtimeFor: (env: Bindings) => DispatchRuntime) {
  return async (batch: MessageBatch<unknown>, env: Bindings): Promise<void> => {
    const runtime = runtimeFor(env);
    for (const message of batch.messages) {
      let outcome: JobOutcome;
      try {
        const body = message.body as { job_id?: unknown } | null;
        const jobId = body?.job_id;
        outcome = typeof jobId === 'string' ? await runJob(runtime, jobId) : 'ack';
      } catch {
        outcome = 'retry';
      }
      if (outcome === 'retry') {
        message.retry({ delaySeconds: 20 });
      } else {
        message.ack();
      }
    }
  };
}
