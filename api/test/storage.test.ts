import { describe, expect, it } from 'vitest';
import { r2Signer, verifyUpload, type MediaBucket } from '../src/storage';

describe('r2Signer', () => {
  const signer = r2Signer({
    accountId: '0123456789abcdef',
    bucket: 'duckclean-media',
    accessKeyId: 'AKIAIOSFODNN7EXAMPLE',
    secretAccessKey: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
  });

  it('signs a PUT with a TTL, the exact key and a bound content type', async () => {
    const ticket = await signer.presignPut(
      'u/user/src/asset/source.mp4',
      900,
      'video/mp4',
    );
    const url = new URL(ticket.url);
    expect(url.host).toBe('0123456789abcdef.r2.cloudflarestorage.com');
    expect(url.pathname).toBe('/duckclean-media/u/user/src/asset/source.mp4');
    expect(url.searchParams.get('X-Amz-Expires')).toBe('900');
    expect(url.searchParams.get('X-Amz-Signature')).toMatch(/^[0-9a-f]{64}$/);
    expect(url.searchParams.get('X-Amz-SignedHeaders')).toBe('content-type;host');
    expect(url.searchParams.get('X-Amz-Algorithm')).toBe('AWS4-HMAC-SHA256');
    // The signature changes with the key: no shared ticket for another object.
    const other = await signer.presignPut('u/user/src/asset/other.mp4', 900, 'video/mp4');
    expect(new URL(other.url).searchParams.get('X-Amz-Signature')).not.toBe(
      url.searchParams.get('X-Amz-Signature'),
    );
  });

  it('signs a GET without a body type', async () => {
    const ticket = await signer.presignGet('u/user/src/asset/proxy.mp4', 600);
    const url = new URL(ticket.url);
    expect(url.searchParams.get('X-Amz-Expires')).toBe('600');
    expect(url.searchParams.get('X-Amz-SignedHeaders')).toBe('host');
  });

  it('uses a local endpoint and path-style bucket when one is configured', async () => {
    const local = r2Signer({
      accountId: 'local',
      bucket: 'duckclean-media',
      accessKeyId: 'duckclean',
      secretAccessKey: 'duckclean-dev-secret',
      endpoint: 'http://127.0.0.1:9000/',
    });
    const ticket = await local.presignPut('u/user/src/a/source.mp4', 900, 'video/mp4');
    const url = new URL(ticket.url);
    expect(url.origin).toBe('http://127.0.0.1:9000');
    expect(url.pathname).toBe('/duckclean-media/u/user/src/a/source.mp4');
    // MinIO signs a concrete region; `auto` is an R2-only value.
    expect(url.searchParams.get('X-Amz-Credential')).toContain('/us-east-1/s3/');
  });
});

describe('verifyUpload', () => {
  const bucket: MediaBucket = {
    async head(key) {
      if (key === 'missing') return null;
      if (key === 'short') return { size: 10, etag: 'abc' };
      return { size: 1000, etag: '"abc123"' };
    },
    async delete() {
      return undefined;
    },
    async put(_key, bytes) {
      return { size: bytes.byteLength };
    },
  };

  it('accepts only the declared size and a matching etag', async () => {
    expect(
      await verifyUpload(bucket, 'ok', { bytes: 1000, etag: 'abc123' }),
    ).toMatchObject({
      ok: true,
      size: 1000,
    });
    expect(await verifyUpload(bucket, 'missing', { bytes: 1000 })).toEqual({
      ok: false,
      reason: 'missing_object',
    });
    expect(await verifyUpload(bucket, 'short', { bytes: 1000 })).toMatchObject({
      ok: false,
      reason: 'size_mismatch',
      size: 10,
    });
    expect(
      await verifyUpload(bucket, 'ok', { bytes: 1000, etag: 'different' }),
    ).toMatchObject({ ok: false, reason: 'etag_mismatch' });
  });
});
