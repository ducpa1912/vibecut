import { PGlite } from '@electric-sql/pglite';
import { exportJWK, generateKeyPair, SignJWT } from 'jose';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createApp } from '../src/app';
import { createVerifier } from '../src/auth';
import type { Bindings } from '../src/bindings';
import { Db } from '../src/db';
import { runJob } from '../src/jobs';
import { pgliteSql } from '../src/sql';
import type { MediaBucket, Signer } from '../src/storage';
import { migrate } from './helpers/migrate';

/**
 * The whole M1 path against real Postgres semantics (PGlite), a real RS256
 * signature verified through a JWKS document, and an in-memory R2 stand-in.
 * Nothing here fakes a status: HEAD decides completion, and the queue tests run
 * the same dispatch code production runs.
 */

const ISSUER = 'https://clerk.test';
const AUDIENCE = 'duckclean';

let db: PGlite;
let privateKey: CryptoKey;
let jwksJson: string;
let kid: string;

class MemoryBucket implements MediaBucket {
  readonly objects = new Map<string, { size: number; etag: string }>();

  async head(key: string) {
    return this.objects.get(key) ?? null;
  }

  async delete(key: string | string[]) {
    for (const item of Array.isArray(key) ? key : [key]) this.objects.delete(item);
  }
}

function fakeSigner(): Signer {
  const expires = (ttl: number) => new Date(Date.now() + ttl * 1000).toISOString();
  return {
    async presignGet(key, ttl) {
      return { url: `https://r2.test/${key}?get=1`, expiresAt: expires(ttl) };
    },
    async presignPut(key, ttl) {
      return { url: `https://r2.test/${key}?put=1`, expiresAt: expires(ttl) };
    },
  };
}

function keyFromUrl(url: string): string {
  return new URL(url).pathname.slice(1);
}

async function tokenFor(
  subject: string,
  email = `${subject}@example.test`,
): Promise<string> {
  return new SignJWT({ email, name: 'Test Person' })
    .setProtectedHeader({ alg: 'RS256', kid })
    .setIssuer(ISSUER)
    .setAudience(AUDIENCE)
    .setSubject(subject)
    .setIssuedAt()
    .setExpirationTime('10m')
    .sign(privateKey);
}

function env(overrides: Partial<Bindings> = {}): Bindings {
  return {
    APP_ENV: 'test',
    API_VERSION: 'v1',
    CLERK_ISSUER: ISSUER,
    CLERK_AUDIENCE: AUDIENCE,
    AUTH_JWKS_JSON: jwksJson,
    ALLOWED_ORIGINS: 'http://localhost:5173',
    CPU_WORKER_URL: '',
    GPU_WORKER_URL: '',
    WORKER_HMAC_SECRET: 'test-secret',
    R2_ACCOUNT_ID: 'account',
    R2_BUCKET: 'bucket',
    R2_ACCESS_KEY_ID: 'key',
    R2_SECRET_ACCESS_KEY: 'secret',
    HYPERDRIVE: {} as Hyperdrive,
    MEDIA: {} as R2Bucket,
    JOBS: {} as Queue,
    ...overrides,
  } as Bindings;
}

beforeAll(async () => {
  db = new PGlite();
  await migrate(db);
  const pair = await generateKeyPair('RS256');
  privateKey = pair.privateKey;
  kid = `test-${crypto.randomUUID()}`;
  const publicJwk = await exportJWK(pair.publicKey);
  jwksJson = JSON.stringify({ keys: [{ ...publicJwk, kid, alg: 'RS256', use: 'sig' }] });
});

afterAll(async () => {
  await db?.close();
});

beforeEach(async () => {
  await db.exec('truncate users cascade');
});

interface Harness {
  app: ReturnType<typeof createApp>;
  media: MemoryBucket;
  signer: Signer;
  enqueued: { job_id: string }[];
  fetcher: typeof fetch;
  calls: { path: string; body: Record<string, unknown> }[];
}

function harness(options: { worker?: boolean } = {}): Harness {
  const media = new MemoryBucket();
  const signer = fakeSigner();
  const enqueued: { job_id: string }[] = [];
  const calls: { path: string; body: Record<string, unknown> }[] = [];

  const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const body = JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>;
    calls.push({ path: new URL(url).pathname, body });
    if (url.endsWith('/v1/probe')) {
      return Response.json({
        job_id: body.job_id,
        status: 'succeeded',
        probe: {
          duration_ms: 12_000,
          display_width: 720,
          display_height: 1280,
          rotation: 90,
          fps_num: 30,
          fps_den: 1,
          frame_count: 360,
          video_codec: 'hevc',
          pixel_format: 'yuv420p',
          audio_codec: 'aac',
          has_audio: true,
        },
        usage: {
          compute_seconds: 2.5,
          device_class: 'cpu',
          input_bytes: 1000,
          output_bytes: 0,
        },
      });
    }
    if (url.endsWith('/v1/proxy')) {
      return Response.json({
        job_id: body.job_id,
        status: 'succeeded',
        proxy: {
          width: 720,
          height: 1280,
          duration_ms: 12_000,
          fps_num: 30,
          fps_den: 1,
          bytes: 12_345,
        },
        poster: { width: 720, height: 1280, bytes: 2_000, frame_index: 36 },
        usage: { compute_seconds: 4.5, device_class: 'cpu' },
      });
    }
    return new Response('unexpected path', { status: 404 });
  }) as unknown as typeof fetch;

  const dam = new Db(pgliteSql(db));
  const verifier = createVerifier({
    issuer: ISSUER,
    audience: AUDIENCE,
    jwksUrl: `${ISSUER}/.well-known/jwks.json`,
    jwksJson,
    allowedOrigins: [],
  });
  const app = createApp(() => ({
    db: dam,
    media,
    signer,
    enqueue: async (message) => {
      enqueued.push(message);
    },
    verifier,
    fetcher,
    cpuWorkerUrl: 'https://worker.test',
    secret: 'test-secret',
    keyId: 'v1',
  }));
  void options;
  return { app, media, signer, enqueued, fetcher, calls };
}

async function createUpload(
  h: Harness,
  overrides: { bytes?: number; filename?: string; contentType?: string } = {},
) {
  const response = await h.app.request(
    '/api/v1/uploads',
    {
      method: 'POST',
      headers: {
        authorization: `Bearer ${await tokenFor('user_one')}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        filename: overrides.filename ?? 'clip.mp4',
        content_type: overrides.contentType ?? 'video/mp4',
        bytes: overrides.bytes ?? 1000,
        title: 'Test clip',
      }),
    },
    env(),
  );
  const body = (await response.clone().json()) as {
    upload_id: string;
    library_item_id: string;
    url: string;
    headers: Record<string, string>;
    expires_at: string;
  };
  return { response, body };
}

describe('GET /api/v1/health', () => {
  it('reports degraded when no worker is configured, and never claims ok', async () => {
    const h = harness();
    const response = await h.app.request('/api/v1/health', {}, env());
    expect(response.status).toBe(200);
    const body = (await response.clone().json()) as {
      status: string;
      checks: Record<string, { ok: boolean }>;
      request_id: string;
    };
    expect(body.status).toBe('degraded');
    expect(body.checks.db?.ok).toBe(true);
    expect(body.checks.r2?.ok).toBe(true);
    expect(body.checks.cpu_worker?.ok).toBe(false);
    expect(body.request_id).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe('auth', () => {
  it('rejects a request with no token using the one error envelope', async () => {
    const h = harness();
    const response = await h.app.request('/api/v1/me', {}, env());
    expect(response.status).toBe(401);
    const body = (await response.clone().json()) as {
      error: { code: string; action: string; retryable: boolean };
    };
    expect(body.error).toMatchObject({
      code: 'unauthorized',
      action: 'sign_in',
      retryable: false,
    });
  });

  it('rejects a token signed by another key', async () => {
    const h = harness();
    const other = await generateKeyPair('RS256');
    const forged = await new SignJWT({})
      .setProtectedHeader({ alg: 'RS256', kid })
      .setIssuer(ISSUER)
      .setAudience(AUDIENCE)
      .setSubject('user_one')
      .setIssuedAt()
      .setExpirationTime('10m')
      .sign(other.privateKey);
    const response = await h.app.request(
      '/api/v1/me',
      { headers: { authorization: `Bearer ${forged}` } },
      env(),
    );
    expect(response.status).toBe(401);
  });

  it('creates the user on first call and returns the same id after', async () => {
    const h = harness();
    const token = await tokenFor('user_one');
    const first = await h.app.request(
      '/api/v1/me',
      { headers: { authorization: `Bearer ${token}` } },
      env(),
    );
    expect(first.status).toBe(200);
    const firstBody = (await first.json()) as {
      id: string;
      plan: string;
      storage_bytes_limit: number;
    };
    expect(firstBody.plan).toBe('free');
    expect(firstBody.storage_bytes_limit).toBe(25_000_000_000);

    const second = await h.app.request(
      '/api/v1/me',
      { headers: { authorization: `Bearer ${token}` } },
      env(),
    );
    const secondBody = (await second.json()) as { id: string };
    expect(secondBody.id).toBe(firstBody.id);
  });
});

describe('uploads', () => {
  it('issues a ticket for the contract key and leaves the asset pending', async () => {
    const h = harness();
    const { response, body } = await createUpload(h);
    expect(response.status).toBe(201);
    expect(body.upload_id).toBeDefined();
    const key = keyFromUrl(body.url);
    expect(key).toMatch(/^u\/[0-9a-f-]+\/src\/[0-9a-f-]+\/source\.mp4$/);
    expect(body.headers['content-type']).toBe('video/mp4');
    expect(Date.parse(body.expires_at)).toBeGreaterThan(Date.now());

    const rows = await db.query<{ upload_status: string }>(
      'select upload_status from source_assets where id = $1',
      [body.upload_id],
    );
    expect(rows.rows[0]?.upload_status).toBe('pending');
  });

  it('rejects an upload that would exceed storage', async () => {
    const h = harness();
    await h.app.request(
      '/api/v1/me',
      { headers: { authorization: `Bearer ${await tokenFor('user_one')}` } },
      env(),
    );
    await db.query(`update users set storage_bytes_used = 24_999_999_500`);
    const { response } = await createUpload(h, { bytes: 1000 });
    expect(response.status).toBe(402);
    const body = (await response.clone().json()) as {
      error: { code: string; action: string };
    };
    expect(body.error.code).toBe('quota');
  });

  it('refuses completion when HEAD finds no object, and marks the item incomplete', async () => {
    const h = harness();
    const { body } = await createUpload(h);
    const response = await h.app.request(
      `/api/v1/uploads/${body.upload_id}/complete`,
      {
        method: 'POST',
        headers: {
          authorization: `Bearer ${await tokenFor('user_one')}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify({ bytes: 1000 }),
      },
      env(),
    );
    expect(response.status).toBe(422);
    const error = (await response.json()) as {
      error: { code: string; detail: { reason: string }; action: string };
    };
    expect(error.error.code).toBe('source_unreadable');
    expect(error.error.detail.reason).toBe('missing_object');
    expect(error.error.action).toBe('reupload');

    const item = await db.query<{ status: string; status_error_code: string }>(
      'select status, status_error_code from library_items where id = $1',
      [body.library_item_id],
    );
    expect(item.rows[0]).toMatchObject({
      status: 'upload_incomplete',
      status_error_code: 'source_unreadable',
    });
  });

  it('marks a completed upload exactly once and queues one probe', async () => {
    const h = harness();
    const { body } = await createUpload(h);
    h.media.objects.set(keyFromUrl(body.url), { size: 1000, etag: 'abc123' });

    const complete = async () =>
      h.app.request(
        `/api/v1/uploads/${body.upload_id}/complete`,
        {
          method: 'POST',
          headers: {
            authorization: `Bearer ${await tokenFor('user_one')}`,
            'content-type': 'application/json',
          },
          body: JSON.stringify({ bytes: 1000 }),
        },
        env(),
      );

    const first = await complete();
    expect(first.status).toBe(202);
    const firstBody = (await first.json()) as {
      probe_queued: boolean;
      library_item: { status: string; bytes: number };
    };
    expect(firstBody.probe_queued).toBe(true);
    expect(firstBody.library_item.status).toBe('uploaded');
    expect(h.enqueued).toHaveLength(1);

    const second = await complete();
    expect(second.status).toBe(202);

    const user = await db.query<{ storage_bytes_used: string }>(
      'select storage_bytes_used from users',
    );
    expect(Number(user.rows[0]?.storage_bytes_used)).toBe(1000);
    const jobs = await db.query<{ count: number }>(
      `select count(*)::int as count from worker_jobs where kind = 'probe'`,
    );
    expect(jobs.rows[0]?.count).toBe(1);
  });

  it('re-signs a pending upload but refuses a completed one', async () => {
    const h = harness();
    const { body } = await createUpload(h);
    const auth = {
      authorization: `Bearer ${await tokenFor('user_one')}`,
      'content-type': 'application/json',
    };

    const resigned = await h.app.request(
      `/api/v1/uploads/${body.upload_id}/sign`,
      { method: 'POST', headers: auth },
      env(),
    );
    expect(resigned.status).toBe(200);
    const ticket = (await resigned.json()) as { url: string; upload_id: string };
    expect(ticket.upload_id).toBe(body.upload_id);
    expect(keyFromUrl(ticket.url)).toBe(keyFromUrl(body.url));

    h.media.objects.set(keyFromUrl(body.url), { size: 1000, etag: 'abc123' });
    await h.app.request(
      `/api/v1/uploads/${body.upload_id}/complete`,
      { method: 'POST', headers: auth, body: JSON.stringify({ bytes: 1000 }) },
      env(),
    );
    const refused = await h.app.request(
      `/api/v1/uploads/${body.upload_id}/sign`,
      { method: 'POST', headers: auth },
      env(),
    );
    expect(refused.status).toBe(409);
  });
});

describe('library', () => {
  async function seeded(h: Harness, count: number) {
    const ids: string[] = [];
    for (let index = 0; index < count; index += 1) {
      const { body } = await createUpload(h, { filename: `clip-${index}.mp4` });
      ids.push(body.library_item_id);
      await db.query(
        `update library_items set created_at = now() - ($2 || ' minutes')::interval where id = $1`,
        [body.library_item_id, String(index * 5)],
      );
    }
    return ids;
  }

  it('paginates newest first with a cursor that survives the round trip', async () => {
    const h = harness();
    await seeded(h, 3);
    const auth = { authorization: `Bearer ${await tokenFor('user_one')}` };

    const first = await h.app.request(
      '/api/v1/library?limit=2',
      { headers: auth },
      env(),
    );
    const firstBody = (await first.json()) as {
      items: { id: string; title: string }[];
      next_cursor: string | null;
    };
    expect(firstBody.items).toHaveLength(2);
    expect(firstBody.next_cursor).toBeTruthy();

    const second = await h.app.request(
      `/api/v1/library?limit=2&cursor=${encodeURIComponent(firstBody.next_cursor ?? '')}`,
      { headers: auth },
      env(),
    );
    const secondBody = (await second.json()) as {
      items: { id: string }[];
      next_cursor: string | null;
    };
    expect(secondBody.items).toHaveLength(1);
    expect(secondBody.next_cursor).toBeNull();
    const seen = new Set(
      [...firstBody.items, ...secondBody.items].map((item) => item.id),
    );
    expect(seen.size).toBe(3);
  });

  it('never shows another user an item', async () => {
    const h = harness();
    const { body } = await createUpload(h);
    const other = await tokenFor('user_two');
    const detail = await h.app.request(
      `/api/v1/library/${body.library_item_id}`,
      { headers: { authorization: `Bearer ${other}` } },
      env(),
    );
    expect(detail.status).toBe(404);

    const list = await h.app.request(
      '/api/v1/library',
      { headers: { authorization: `Bearer ${other}` } },
      env(),
    );
    const listBody = (await list.json()) as { items: unknown[] };
    expect(listBody.items).toEqual([]);
  });

  it('returns real source facts and no invented detection state', async () => {
    const h = harness();
    const { body } = await createUpload(h);
    h.media.objects.set(keyFromUrl(body.url), { size: 1000, etag: 'abc123' });
    const auth = {
      authorization: `Bearer ${await tokenFor('user_one')}`,
      'content-type': 'application/json',
    };
    await h.app.request(
      `/api/v1/uploads/${body.upload_id}/complete`,
      { method: 'POST', headers: auth, body: JSON.stringify({ bytes: 1000 }) },
      env(),
    );

    const detail = await h.app.request(
      `/api/v1/library/${body.library_item_id}`,
      { headers: auth },
      env(),
    );
    const detailBody = (await detail.json()) as {
      source: { bytes: number; upload_status: string; probe_status: string };
      proxy: unknown;
      probe: unknown;
      detection: unknown;
      render: unknown;
      beats: { total: number };
    };
    expect(detailBody.source).toMatchObject({ bytes: 1000, upload_status: 'completed' });
    expect(detailBody.proxy).toBeNull();
    expect(detailBody.probe).toBeNull();
    expect(detailBody.detection).toBeNull();
    expect(detailBody.render).toBeNull();
    expect(detailBody.beats.total).toBe(0);
  });

  it('refuses playback until a proxy exists', async () => {
    const h = harness();
    const { body } = await createUpload(h);
    const response = await h.app.request(
      `/api/v1/library/${body.library_item_id}/play`,
      { headers: { authorization: `Bearer ${await tokenFor('user_one')}` } },
      env(),
    );
    expect(response.status).toBe(409);
    const error = (await response.json()) as { error: { detail: { reason: string } } };
    expect(error.error.detail.reason).toBe('proxy_missing');
  });

  it('soft-deletes the item, purges its objects and returns storage', async () => {
    const h = harness();
    const { body } = await createUpload(h);
    const key = keyFromUrl(body.url);
    h.media.objects.set(key, { size: 1000, etag: 'abc123' });
    const auth = {
      authorization: `Bearer ${await tokenFor('user_one')}`,
      'content-type': 'application/json',
    };
    await h.app.request(
      `/api/v1/uploads/${body.upload_id}/complete`,
      { method: 'POST', headers: auth, body: JSON.stringify({ bytes: 1000 }) },
      env(),
    );

    const deleted = await h.app.request(
      `/api/v1/library/${body.library_item_id}`,
      { method: 'DELETE', headers: auth },
      env(),
    );
    expect(deleted.status).toBe(204);
    expect(h.media.objects.has(key)).toBe(false);

    const list = await h.app.request('/api/v1/library', { headers: auth }, env());
    expect(((await list.json()) as { items: unknown[] }).items).toEqual([]);
    const user = await db.query<{ storage_bytes_used: string }>(
      'select storage_bytes_used from users',
    );
    expect(Number(user.rows[0]?.storage_bytes_used)).toBe(0);
  });
});

describe('probe and proxy jobs', () => {
  async function uploaded(h: Harness) {
    const { body } = await createUpload(h);
    h.media.objects.set(keyFromUrl(body.url), { size: 1000, etag: 'abc123' });
    await h.app.request(
      `/api/v1/uploads/${body.upload_id}/complete`,
      {
        method: 'POST',
        headers: {
          authorization: `Bearer ${await tokenFor('user_one')}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify({ bytes: 1000 }),
      },
      env(),
    );
    return body;
  }

  it('applies probe facts, then a proxy, and only then serves playback', async () => {
    const h = harness();
    const upload = await uploaded(h);
    const runtime = {
      db: new Db(pgliteSql(db)),
      signer: h.signer,
      media: h.media,
      enqueue: async (message: { job_id: string }) => {
        h.enqueued.push(message);
      },
      fetcher: h.fetcher,
      cpuWorkerUrl: 'https://worker.test',
      secret: 'test-secret',
      keyId: 'v1',
    };

    const probeRow = await db.query<{ id: string; worker_job_id: string }>(
      `select id, worker_job_id from worker_jobs where kind = 'probe'`,
    );
    const probeJobId = probeRow.rows[0]?.id;
    expect(probeJobId).toBeDefined();
    expect(await runJob(runtime, probeJobId as string)).toBe('ack');

    const afterProbe = await db.query<{
      duration_ms: number;
      width: number;
      height: number;
      fps_num: number;
      has_audio: boolean;
      probe_status: string;
    }>(
      `select li.duration_ms, li.width, li.height, li.fps_num, li.has_audio,
              sa.probe_status
         from library_items li join source_assets sa on sa.library_item_id = li.id
        where li.id = $1`,
      [upload.library_item_id],
    );
    expect(afterProbe.rows[0]).toMatchObject({
      duration_ms: 12_000,
      width: 720,
      height: 1280,
      fps_num: 30,
      has_audio: true,
      probe_status: 'succeeded',
    });
    expect(h.enqueued).toHaveLength(2);

    const proxyRow = await db.query<{ id: string }>(
      `select id from worker_jobs where kind = 'proxy'`,
    );
    const proxyJobId = proxyRow.rows[0]?.id as string;
    const proxyKey = `u/${upload.upload_id.split('/')[0]}`;
    void proxyKey;
    // The worker uploads the proxy with a presigned PUT; the API verifies its size.
    const asset = await db.query<{ user_id: string; id: string }>(
      'select user_id, id from source_assets where library_item_id = $1',
      [upload.library_item_id],
    );
    const userId = asset.rows[0]?.user_id as string;
    const assetId = asset.rows[0]?.id as string;
    h.media.objects.set(`u/${userId}/src/${assetId}/proxy.mp4`, {
      size: 12_345,
      etag: 'proxy',
    });

    expect(await runJob(runtime, proxyJobId)).toBe('ack');

    const play = await h.app.request(
      `/api/v1/library/${upload.library_item_id}/play`,
      { headers: { authorization: `Bearer ${await tokenFor('user_one')}` } },
      env(),
    );
    expect(play.status).toBe(200);
    const ticket = (await play.json()) as {
      url: string;
      duration_ms: number;
      width: number;
    };
    expect(ticket.duration_ms).toBe(12_000);
    expect(ticket.width).toBe(720);
    expect(ticket.url).toContain('/proxy.mp4');
  });

  it('records worker_unavailable and leaves the upload usable when dispatch fails', async () => {
    const h = harness();
    const upload = await uploaded(h);
    const runtime = {
      db: new Db(pgliteSql(db)),
      signer: h.signer,
      media: h.media,
      enqueue: async () => undefined,
      fetcher: h.fetcher,
      cpuWorkerUrl: '',
      secret: 'test-secret',
      keyId: 'v1',
    };
    const probeRow = await db.query<{ id: string }>(
      `select id from worker_jobs where kind = 'probe'`,
    );
    const outcome = await runJob(runtime, probeRow.rows[0]?.id as string);
    expect(outcome).toBe('retry');
    const job = await db.query<{ status: string; error_code: string; attempts: number }>(
      `select status, error_code, attempts from worker_jobs where kind = 'probe'`,
    );
    expect(job.rows[0]).toMatchObject({
      status: 'queued',
      error_code: 'worker_unavailable',
      attempts: 1,
    });
    const item = await db.query<{ status: string; status_error_code: string }>(
      'select status, status_error_code from library_items where id = $1',
      [upload.library_item_id],
    );
    expect(item.rows[0]).toMatchObject({ status: 'uploaded' });
  });
});
