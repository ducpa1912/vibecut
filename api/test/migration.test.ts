import { PGlite } from '@electric-sql/pglite';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { migrate } from './helpers/migrate';

/**
 * Applies the frozen migration to a real Postgres (PGlite) and proves the hard
 * rules are enforced by the database, not just by application code.
 */

// Vitest runs with the api workspace as cwd.
let db: PGlite;

beforeAll(async () => {
  db = new PGlite();
  await migrate(db);
});

afterAll(async () => {
  await db?.close();
});

async function createUser(): Promise<string> {
  const id = crypto.randomUUID();
  await db.query(`insert into users (id, oauth_subject, email) values ($1, $2, $3)`, [
    id,
    `clerk_${id}`,
    `u_${id}@example.test`,
  ]);
  return id;
}

async function createItemAndSource(
  ownerId: string,
): Promise<{ itemId: string; sourceId: string }> {
  const itemId = crypto.randomUUID();
  const sourceId = crypto.randomUUID();
  // The two tables reference each other; the deferred FKs allow one transaction.
  await db.transaction(async (tx) => {
    await tx.query(
      `insert into library_items (id, user_id, title, source_asset_id)
       values ($1, $2, 'clip.mp4', $3)`,
      [itemId, ownerId, sourceId],
    );
    await tx.query(
      `insert into source_assets
         (id, user_id, library_item_id, r2_key, filename, content_type, bytes, upload_expires_at)
       values ($1, $2, $3, $4, 'clip.mp4', 'video/mp4', 1048576, now() + interval '15 minutes')`,
      [sourceId, ownerId, itemId, `u/${ownerId}/src/${sourceId}/source.mp4`],
    );
  });
  return { itemId, sourceId };
}

async function createRunAndGroup(
  ownerId: string,
  sourceId: string,
): Promise<{ runId: string; groupId: string }> {
  const runId = crypto.randomUUID();
  const groupId = crypto.randomUUID();
  await db.query(
    `insert into detection_runs (id, user_id, source_asset_id, revision)
     values ($1, $2, $3, 'rev-1')`,
    [runId, ownerId, sourceId],
  );
  await db.query(
    `insert into detection_groups
       (id, user_id, run_id, kind, lane, order_index, box_x, box_y, box_w, box_h, confidence_milli)
     values ($1, $2, $3, 'text', 0, 0, 100, 900, 600, 80, 940)`,
    [groupId, ownerId, runId],
  );
  return { runId, groupId };
}

describe('migrations', () => {
  it('applies to an empty database', async () => {
    const { rows } = await db.query<{ count: number }>(
      `select count(*)::int as count from information_schema.tables
       where table_schema = 'public'`,
    );
    expect(rows[0]?.count).toBe(17);
  });

  it('creates the required tables', async () => {
    const { rows } = await db.query<{ table_name: string }>(
      `select table_name from information_schema.tables where table_schema = 'public'`,
    );
    const names = rows.map((row) => row.table_name).sort();
    expect(names).toEqual(
      [
        'beats',
        'detection_groups',
        'detection_members',
        'detection_runs',
        'events',
        'library_items',
        'mask_assets',
        'oauth_accounts',
        'output_assets',
        'poster_assets',
        'proxy_assets',
        'render_jobs',
        'render_segments',
        'source_assets',
        'usage_ledger',
        'users',
        'worker_jobs',
      ].sort(),
    );
  });

  it('links an item and its source in one transaction', async () => {
    const userId = await createUser();
    const { itemId, sourceId } = await createItemAndSource(userId);
    const { rows } = await db.query<{ source_asset_id: string }>(
      `select source_asset_id from library_items where id = $1`,
      [itemId],
    );
    expect(rows[0]?.source_asset_id).toBe(sourceId);
  });

  it('rejects range_mode=ranges with an empty range list', async () => {
    const owner = await createUser();
    const { sourceId } = await createItemAndSource(owner);
    const { groupId } = await createRunAndGroup(owner, sourceId);
    await expect(
      db.query(
        `insert into detection_members
           (user_id, group_id, ranges_json, box_x, box_y, box_w, box_h,
            confidence_milli, provenance)
         values ($1, $2, '[]'::jsonb, 100, 900, 600, 80, 900, 'ocr')`,
        [owner, groupId],
      ),
    ).rejects.toThrow(/detection_members_ranges_not_empty/);
  });

  it('allows whole_source with an empty range list, but never empty ranges mode', async () => {
    const owner = await createUser();
    const { sourceId } = await createItemAndSource(owner);
    const { groupId } = await createRunAndGroup(owner, sourceId);
    const { rows } = await db.query<{ range_mode: string }>(
      `insert into detection_members
         (user_id, group_id, range_mode, ranges_json, box_x, box_y, box_w, box_h,
          confidence_milli, provenance)
       values ($1, $2, 'whole_source', '[]'::jsonb, 100, 900, 600, 80, 900, 'user_box')
       returning range_mode`,
      [owner, groupId],
    );
    expect(rows[0]?.range_mode).toBe('whole_source');
  });

  it('keeps beat indices and frame spans unique per source', async () => {
    const owner = await createUser();
    const { sourceId } = await createItemAndSource(owner);
    const insert = (id: string) =>
      db.query(
        `insert into beats
           (id, user_id, source_asset_id, beat_manifest_hash, "index",
            start_frame, end_frame, start_ms, end_ms, boundary)
         values ($1, $2, $3, 'manifest', 0, 0, 30, 0, 1000, 'start')`,
        [id, owner, sourceId],
      );
    await insert(crypto.randomUUID());
    await expect(insert(crypto.randomUUID())).rejects.toThrow(
      /beats_source_asset_id_index_key/,
    );
  });

  it('computes ledger render_hours from compute seconds and weight', async () => {
    const { rows } = await db.query<{ render_hours: string }>(
      `insert into usage_ledger
         (user_id, kind, device_class, compute_seconds, weight, idempotency_key)
       values ($1, 'render', 'gpu_standard', 1800, 1.0, $2)
       returning render_hours`,
      [await createUser(), `ledger_${crypto.randomUUID()}`],
    );
    // 1800 s * 1.00 / 3600 = 0.5 render-hours.
    expect(Number(rows[0]?.render_hours)).toBe(0.5);
  });

  it('rejects a weight that would make billing free or negative', async () => {
    await expect(
      db.query(
        `insert into usage_ledger
           (user_id, kind, device_class, compute_seconds, weight, idempotency_key)
         values ($1, 'render', 'gpu_standard', 10, 0, $2)`,
        [await createUser(), `ledger_${crypto.randomUUID()}`],
      ),
    ).rejects.toThrow(/usage_ledger_weight_check/);
  });

  it('dedupes metered usage by idempotency key', async () => {
    const owner = await createUser();
    const key = `meter_${crypto.randomUUID()}`;
    const insert = () =>
      db.query(
        `insert into usage_ledger
           (user_id, kind, device_class, compute_seconds, weight, idempotency_key)
         values ($1, 'render', 'gpu_standard', 10, 1.0, $2)`,
        [owner, key],
      );
    await insert();
    await expect(insert()).rejects.toThrow(/usage_ledger_idempotency_key_key/);
  });

  it('allows one render segment per beat per job', async () => {
    const owner = await createUser();
    const { itemId, sourceId } = await createItemAndSource(owner);
    const { runId } = await createRunAndGroup(owner, sourceId);
    const beatId = crypto.randomUUID();
    await db.query(
      `insert into beats
         (id, user_id, source_asset_id, beat_manifest_hash, "index",
          start_frame, end_frame, start_ms, end_ms, boundary)
       values ($1, $2, $3, 'manifest', 0, 0, 30, 0, 1000, 'start')`,
      [beatId, owner, sourceId],
    );
    const jobId = crypto.randomUUID();
    await db.query(
      `insert into render_jobs
         (id, user_id, library_item_id, detection_run_id, revision, selection_revision)
       values ($1, $2, $3, $4, 'rev-1', 'sel-1')`,
      [jobId, owner, itemId, runId],
    );
    const insertSegment = (id: string) =>
      db.query(
        `insert into render_segments
           (id, user_id, render_job_id, beat_id, beat_index, mode, segment_key)
         values ($1, $2, $3, $4, 0, 'fill', 'seg-key')`,
        [id, owner, jobId, beatId],
      );
    await insertSegment(crypto.randomUUID());
    await expect(insertSegment(crypto.randomUUID())).rejects.toThrow(
      /render_segments_render_job_id_beat_index_key/,
    );
  });

  it('accepts a poster without inventing a frame rate or duration', async () => {
    const owner = await createUser();
    const { itemId, sourceId } = await createItemAndSource(owner);
    const posterId = crypto.randomUUID();
    await db.query(
      `insert into poster_assets
         (id, user_id, source_asset_id, r2_key, width, height, bytes)
       values ($1, $2, $3, $4, 720, 1280, 24000)`,
      [posterId, owner, sourceId, `u/${owner}/src/${sourceId}/poster.jpg`],
    );
    await db.query(`update library_items set poster_asset_id = $2 where id = $1`, [
      itemId,
      posterId,
    ]);
    const { rows } = await db.query<{ poster_asset_id: string }>(
      `select poster_asset_id from library_items where id = $1`,
      [itemId],
    );
    expect(rows[0]?.poster_asset_id).toBe(posterId);
  });

  it('dedupes a worker job by kind and idempotency key', async () => {
    const owner = await createUser();
    const { itemId, sourceId } = await createItemAndSource(owner);
    const insert = () =>
      db.query(
        `insert into worker_jobs
           (user_id, library_item_id, source_asset_id, kind, idempotency_key, worker_job_id)
         values ($1, $2, $3, 'probe', $4, $5)`,
        [owner, itemId, sourceId, `probe:${sourceId}`, crypto.randomUUID()],
      );
    await insert();
    await expect(insert()).rejects.toThrow(/worker_jobs_kind_idempotency_key_key/);
  });

  it('never stores more attempts than the job allows', async () => {
    const owner = await createUser();
    const { itemId, sourceId } = await createItemAndSource(owner);
    await expect(
      db.query(
        `insert into worker_jobs
           (user_id, library_item_id, source_asset_id, kind, idempotency_key,
            attempts, max_attempts)
         values ($1, $2, $3, 'proxy', $4, 4, 3)`,
        [owner, itemId, sourceId, `proxy:${sourceId}`],
      ),
    ).rejects.toThrow(/worker_jobs_attempts_bounds/);
  });

  it('bumps updated_at on update', async () => {
    const owner = await createUser();
    await db.query(`update users set display_name = 'Duck' where id = $1`, [owner]);
    const { rows } = await db.query<{ newer: boolean }>(
      `select (updated_at >= created_at + interval '0 seconds') as newer
       from users where id = $1`,
      [owner],
    );
    expect(rows[0]?.newer).toBe(true);
  });
});
