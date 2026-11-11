import { AwsClient } from 'aws4fetch';
import { WORKER_INPUT_TTL_SECONDS } from './limits';

/** The subset of R2 the API uses. Tests provide an in-memory stand-in. */
export interface MediaBucket {
  head(key: string): Promise<{ size: number; etag: string } | null>;
  delete(key: string | string[]): Promise<void>;
  /**
   * Small server-produced objects only (masks). Video bytes never travel
   * through the API: the browser uploads those with a presigned PUT.
   */
  put(key: string, bytes: Uint8Array, contentType: string): Promise<{ size: number }>;
}

export interface SignedUrl {
  url: string;
  expiresAt: string;
}

export interface Signer {
  presignGet(key: string, ttlSeconds: number): Promise<SignedUrl>;
  presignPut(key: string, ttlSeconds: number, contentType: string): Promise<SignedUrl>;
}

/** Keys are fixed by contract.md §5. The extension comes from content type. */
export const keys = {
  source: (userId: string, assetId: string, ext: string) =>
    `u/${userId}/src/${assetId}/source.${ext}`,
  proxy: (userId: string, assetId: string) => `u/${userId}/src/${assetId}/proxy.mp4`,
  poster: (userId: string, assetId: string) => `u/${userId}/src/${assetId}/poster.jpg`,
  mask: (userId: string, runId: string, maskId: string) =>
    `u/${userId}/detect/${runId}/${maskId}.png`,
  segment: (userId: string, jobId: string, index: number) =>
    `u/${userId}/render/${jobId}/beat/${String(index).padStart(5, '0')}.mp4`,
  final: (userId: string, jobId: string) => `u/${userId}/render/${jobId}/final.mp4`,
  preview: (userId: string, jobId: string) => `u/${userId}/preview/${jobId}.mp4`,
};

export interface R2Config {
  accountId: string;
  bucket: string;
  accessKeyId: string;
  secretAccessKey: string;
  /**
   * Development only: a local S3-compatible endpoint such as MinIO. Production
   * never sets this; the signer then uses the R2 endpoint for `accountId`.
   */
  endpoint?: string | undefined;
  /** SigV4 region. R2 accepts `auto`; local S3 servers need a concrete one. */
  region?: string | undefined;
}

function objectUrl(config: R2Config, key: string): URL {
  const encoded = key
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  const bucket = encodeURIComponent(config.bucket);
  const endpoint = config.endpoint?.replace(/\/+$/, '');
  if (endpoint) return new URL(`${endpoint}/${bucket}/${encoded}`);
  return new URL(
    `https://${config.accountId}.r2.cloudflarestorage.com/${bucket}/${encoded}`,
  );
}

function s3Client(config: R2Config): AwsClient {
  return new AwsClient({
    accessKeyId: config.accessKeyId,
    secretAccessKey: config.secretAccessKey,
    service: 's3',
    region: config.region ?? (config.endpoint ? 'us-east-1' : 'auto'),
  });
}

/** S3 SigV4 presigner for R2. Credentials never leave the Worker. */
export function r2Signer(config: R2Config): Signer {
  const client = s3Client(config);

  async function presign(
    method: 'GET' | 'PUT',
    key: string,
    ttlSeconds: number,
    contentType?: string,
  ) {
    const url = objectUrl(config, key);
    // aws4fetch reads the expiry from the query string for S3 presigns.
    url.searchParams.set('X-Amz-Expires', String(ttlSeconds));
    const headers: Record<string, string> = {};
    if (contentType) headers['content-type'] = contentType;
    const signed = await client.sign(
      new Request(url, { method, headers }),
      // `allHeaders` signs content-type as well, so the PUT is bound to the
      // type the ticket was issued for; a browser sending another type gets 403.
      { aws: { signQuery: true, allHeaders: true } },
    );
    return {
      url: signed.url,
      expiresAt: new Date(Date.now() + ttlSeconds * 1000).toISOString(),
    };
  }

  return {
    presignGet: (key, ttlSeconds) => presign('GET', key, ttlSeconds),
    presignPut: (key, ttlSeconds, contentType) =>
      presign('PUT', key, ttlSeconds, contentType),
  };
}

/** The R2 binding is authoritative in production: same surface, bound object. */
export function r2MediaBucket(bucket: R2Bucket): MediaBucket {
  return {
    async head(key) {
      const object = await bucket.head(key);
      return object ? { size: object.size, etag: object.etag } : null;
    },
    async delete(key) {
      await bucket.delete(Array.isArray(key) ? key : key);
    },
    async put(key, bytes, contentType) {
      const object = await bucket.put(key, bytes, {
        httpMetadata: { contentType },
      });
      return { size: object?.size ?? bytes.byteLength };
    },
  };
}

/**
 * The R2 binding is authoritative in production. A local S3 server has no
 * binding, so development reads and deletes through the same SigV4 client the
 * presigner uses. Selected by `runtimeFor` only when `APP_ENV` is not production
 * and `R2_ENDPOINT` is set.
 */
export function s3MediaBucket(config: R2Config): MediaBucket {
  const client = s3Client(config);
  return {
    async head(key) {
      const response = await client.fetch(objectUrl(config, key), { method: 'HEAD' });
      if (response.status === 404) return null;
      if (!response.ok) {
        throw new Error(`s3 head failed with status ${response.status}`);
      }
      return {
        size: Number(response.headers.get('content-length') ?? '0'),
        etag: response.headers.get('etag') ?? '',
      };
    },
    async delete(keys) {
      for (const key of Array.isArray(keys) ? keys : [keys]) {
        const response = await client.fetch(objectUrl(config, key), { method: 'DELETE' });
        if (!response.ok && response.status !== 404) {
          throw new Error(`s3 delete failed with status ${response.status}`);
        }
      }
    },
    async put(key, bytes, contentType) {
      const response = await client.fetch(objectUrl(config, key), {
        method: 'PUT',
        headers: { 'content-type': contentType },
        body: bytes,
      });
      if (!response.ok) {
        throw new Error(`s3 put failed with status ${response.status}`);
      }
      return { size: bytes.byteLength };
    },
  };
}

export function workerInputUrl(signer: Signer, key: string): Promise<SignedUrl> {
  return signer.presignGet(key, WORKER_INPUT_TTL_SECONDS);
}

export type HeadVerdict =
  | { ok: true; size: number; etag: string }
  | {
      ok: false;
      reason: 'missing_object' | 'size_mismatch' | 'etag_mismatch';
      size?: number;
    };

function normaliseEtag(value: string): string {
  return value.replace(/^"|"$/g, '').toLowerCase();
}

/**
 * HEAD is the only proof that the bytes arrived. The client's reported numbers
 * are a hint; R2 wins. A mismatch never marks the source complete.
 */
export async function verifyUpload(
  media: MediaBucket,
  key: string,
  expected: { bytes: number; etag?: string | undefined },
): Promise<HeadVerdict> {
  const object = await media.head(key);
  if (!object) return { ok: false, reason: 'missing_object' };
  if (object.size !== expected.bytes) {
    return { ok: false, reason: 'size_mismatch', size: object.size };
  }
  if (expected.etag && normaliseEtag(expected.etag) !== normaliseEtag(object.etag)) {
    return { ok: false, reason: 'etag_mismatch', size: object.size };
  }
  return { ok: true, size: object.size, etag: object.etag };
}
