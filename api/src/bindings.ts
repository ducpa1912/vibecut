/** Cloudflare bindings. Secrets are set with `wrangler secret put`; no key is committed. */
export interface Bindings {
  HYPERDRIVE: Hyperdrive;
  MEDIA: R2Bucket;
  JOBS: Queue<unknown>;
  APP_ENV: string;
  API_VERSION: string;
  CLERK_ISSUER: string;
  CLERK_AUDIENCE: string;
  CLERK_JWKS_URL?: string;
  /** Development only: a JWKS document so local tests verify a real signature. */
  AUTH_JWKS_JSON?: string;
  CPU_WORKER_URL: string;
  GPU_WORKER_URL: string;
  ALLOWED_ORIGINS: string;
  WORKER_HMAC_SECRET: string;
  WORKER_HMAC_KEY_ID?: string;
  R2_ACCOUNT_ID: string;
  R2_BUCKET: string;
  R2_ACCESS_KEY_ID: string;
  R2_SECRET_ACCESS_KEY: string;
  STRIPE_SECRET_KEY?: string;
  STRIPE_METER_EVENT_NAME?: string;
}
