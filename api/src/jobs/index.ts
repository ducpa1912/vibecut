import type { Bindings } from '../bindings';
import { handlers, type JobContext } from './handlers';
import {
  hasTarget,
  isRunnableKind,
  type DispatchRuntime,
  type JobOutcome,
  type RunnableJob,
} from './types';
import { DispatchError } from './worker';

export { DISSECT_PARAMS } from './types';
export type { DispatchRuntime, JobMessage, JobOutcome } from './types';

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled']);

/**
 * Records why a job stopped and puts the failure where the UI reads it. Returns
 * true when the attempt was the last one, so the message can be acknowledged.
 */
async function recordFailure(
  runtime: DispatchRuntime,
  job: RunnableJob,
  dispatch: DispatchError,
  attempts: number,
): Promise<boolean> {
  const terminal = await runtime.db.failJob(job.id, dispatch.code, dispatch.message, {
    retryable: dispatch.retryable,
    attempts,
    maxAttempts: job.maxAttempts,
  });
  if (!terminal) return false;

  if (job.kind === 'detect') {
    const runId = typeof job.request.run_id === 'string' ? job.request.run_id : '';
    if (runId) {
      await runtime.db.failDetectionRun(runId, dispatch.code, dispatch.message);
    }
  } else if (job.kind === 'dissect') {
    await runtime.db.failDissect(
      job.userId,
      job.libraryItemId,
      job.sourceAssetId,
      dispatch.code,
      dispatch.message,
    );
  } else {
    await runtime.db.setItemError(
      job.userId,
      job.libraryItemId,
      dispatch.code,
      dispatch.message,
      'failed',
    );
  }
  return true;
}

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
  if (TERMINAL.has(job.status)) return 'ack';

  if (!isRunnableKind(job.kind)) return 'ack';
  const handler = handlers[job.kind];

  if (!hasTarget(job)) {
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
      { retryable: false, attempts, maxAttempts: job.maxAttempts },
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

  const context: JobContext = { runtime, job, source };
  try {
    await handler(context);
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
    const terminal = await recordFailure(runtime, job, dispatch, attempts);
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
