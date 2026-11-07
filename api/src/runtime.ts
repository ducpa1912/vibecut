import { authOptionsFromEnv, createVerifier, type Verifier } from './auth';
import type { Bindings } from './bindings';
import { Db } from './db';
import type { JobMessage } from './jobs';
import { pgSql } from './sql';
import type { MediaBucket, Signer } from './storage';
import { r2Signer } from './storage';

export interface Runtime {
  db: Db;
  media: MediaBucket;
  signer: Signer;
  enqueue: (message: JobMessage) => Promise<void>;
  verifier: Verifier;
  fetcher: typeof fetch;
  cpuWorkerUrl: string;
  secret: string;
  keyId: string;
}

export type RuntimeFactory = (env: Bindings) => Runtime;

/** Production wiring. Tests pass their own factory with PGlite and a fake bucket. */
export const runtimeFor: RuntimeFactory = (env) => ({
  db: new Db(pgSql(env.HYPERDRIVE.connectionString)),
  media: env.MEDIA,
  signer: r2Signer({
    accountId: env.R2_ACCOUNT_ID,
    bucket: env.R2_BUCKET,
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  }),
  enqueue: async (message) => {
    await env.JOBS.send(message);
  },
  verifier: createVerifier(authOptionsFromEnv(env)),
  fetcher: fetch,
  cpuWorkerUrl: env.CPU_WORKER_URL,
  secret: env.WORKER_HMAC_SECRET,
  keyId: env.WORKER_HMAC_KEY_ID ?? 'v1',
});
