import { authOptionsFromEnv, createVerifier, type Verifier } from './auth';
import type { Bindings } from './bindings';
import { Db } from './db';
import type { JobMessage } from './jobs';
import { pgSql } from './sql';
import type { MediaBucket, R2Config, Signer } from './storage';
import { r2MediaBucket, r2Signer, s3MediaBucket } from './storage';

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

/**
 * A local S3 endpoint is a development tool. Production always talks to R2 and
 * always uses the binding for reads and deletes, so this cannot silently point
 * a deployed API at another store.
 */
function localEndpoint(env: Bindings): string | undefined {
  const raw = env.R2_ENDPOINT?.trim();
  if (!raw) return undefined;
  if (env.APP_ENV === 'production') {
    console.warn(
      JSON.stringify({
        level: 'warn',
        message: 'r2_endpoint_ignored',
        reason: 'R2_ENDPOINT is development only',
      }),
    );
    return undefined;
  }
  const parsed = new URL(raw);
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('R2_ENDPOINT must be an http(s) URL');
  }
  return raw.replace(/\/+$/, '');
}

/** Production wiring. Tests pass their own factory with PGlite and a fake bucket. */
export const runtimeFor: RuntimeFactory = (env) => {
  const endpoint = localEndpoint(env);
  const config: R2Config = {
    accountId: env.R2_ACCOUNT_ID,
    bucket: env.R2_BUCKET,
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    endpoint,
    region: endpoint ? env.R2_REGION?.trim() || 'us-east-1' : undefined,
  };

  return {
    db: new Db(
      pgSql(env.HYPERDRIVE.connectionString, {
        perCallConnection: env.APP_ENV !== 'production',
      }),
    ),
    media: endpoint ? s3MediaBucket(config) : r2MediaBucket(env.MEDIA),
    signer: r2Signer(config),
    enqueue: async (message) => {
      await env.JOBS.send(message);
    },
    verifier: createVerifier(authOptionsFromEnv(env)),
    // `fetch` must be called without a receiver: storing it directly and
    // invoking `runtime.fetcher(...)` throws "Illegal invocation" in Workers.
    fetcher: (input, init) => fetch(input, init),
    cpuWorkerUrl: env.CPU_WORKER_URL,
    secret: env.WORKER_HMAC_SECRET,
    keyId: env.WORKER_HMAC_KEY_ID ?? 'v1',
  };
};
