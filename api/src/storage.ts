import { AwsClient } from 'aws4fetch';
import { WORKER_INPUT_TTL_SECONDS } from './limits';

/** The subset of R2 the API uses. Tests provide an in-memory stand-in. */
export interface MediaBucket {
  head(key: string): Promise<{ size: number; etag: string } | null>;
  delete(key: string | string[]): Promise<void>;
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
}

/** S3 SigV4 presigner for R2. Credentials never leave the Worker. */
export function r2Signer(config: R2Config): Signer {
  const client = new AwsClient({
    accessKeyId: config.accessKeyId,
    secretAccessKey: config.secretAccessKey,
    service: 's3',
    region: 'auto',
  });

  async function presign(
    method: 'GET' | 'PUT',
    key: string,
    ttlSeconds: number,
    contentType?: string,
  ) {
    const encoded = key
      .split('/')
      .map((segment) => encodeURIComponent(segment))
      .join('/');
    const url = new URL(
      `https://${config.accountId}.r2.cloudflarestorage.com/${encodeURIComponent(
        config.bucket,
      )}/${encoded}`,
    );
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
