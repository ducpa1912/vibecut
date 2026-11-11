import type { Db, JobKind, WorkerJobRow } from '../db';
import type { MediaBucket, Signer } from '../storage';

/** M2 defaults: 4 s beats, 1 s minimum, scene score 0.3 at 480 px. */
export const DISSECT_PARAMS = {
  max_seconds_milli: 4000,
  min_seconds_milli: 1000,
  scene_threshold_milli: 300,
  scene_analysis_height: 480,
} as const;

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

/** Kinds this dispatcher runs. `render` and `preview` are acknowledged elsewhere. */
export type RunnableJobKind = Extract<JobKind, 'probe' | 'proxy' | 'dissect' | 'detect'>;

/** A job row whose target columns are known to be present. */
export type RunnableJob = WorkerJobRow & {
  libraryItemId: string;
  sourceAssetId: string;
  workerJobId: string;
};

export function hasTarget(job: WorkerJobRow): job is RunnableJob {
  return Boolean(job.libraryItemId && job.sourceAssetId && job.workerJobId);
}

export function isRunnableKind(kind: JobKind): kind is RunnableJobKind {
  return kind === 'probe' || kind === 'proxy' || kind === 'dissect' || kind === 'detect';
}

export type JobOutcome = 'ack' | 'retry';
