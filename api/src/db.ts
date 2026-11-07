import type { Identity } from './auth';
import type { Sql } from './sql';

export type LibraryStatus =
  | 'uploading'
  | 'uploaded'
  | 'probing'
  | 'dissecting'
  | 'ready'
  | 'upload_incomplete'
  | 'failed'
  | 'deleting';

export type JobKind = 'probe' | 'proxy' | 'dissect' | 'detect' | 'render' | 'preview';
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type DeviceClass = 'cpu' | 'gpu_standard' | 'gpu_premium';

export interface UserRecord {
  id: string;
  email: string | null;
  displayName: string | null;
  avatarUrl: string | null;
  plan: string;
  renderSecondsBalance: number;
  storageBytesUsed: number;
}

export interface LibraryRow {
  id: string;
  title: string;
  status: LibraryStatus;
  statusErrorCode: string | null;
  statusErrorDetail: string | null;
  createdAt: string;
  updatedAt: string;
  durationMs: number | null;
  width: number | null;
  height: number | null;
  fpsNum: number | null;
  fpsDen: number | null;
  hasAudio: boolean | null;
  bytes: number | null;
  posterKey: string | null;
  detectionRevision: string | null;
  renderJobId: string | null;
  renderStatus: string | null;
}

export interface SourceRow {
  id: string;
  filename: string;
  contentType: string;
  bytes: number;
  etag: string | null;
  sha256: string | null;
  uploadStatus: 'pending' | 'completed' | 'abandoned';
  probeStatus: 'pending' | 'running' | 'succeeded' | 'failed';
  dissectStatus: 'pending' | 'running' | 'succeeded' | 'failed';
  beatManifestHash: string | null;
  r2Key: string;
  probeJson: Record<string, unknown> | null;
}

export interface ProxyRow {
  id: string;
  width: number;
  height: number;
  durationMs: number;
  fpsNum: number;
  fpsDen: number;
  bytes: number;
}

export interface PlayRow {
  r2Key: string;
  width: number;
  height: number;
  durationMs: number;
}

export interface WorkerJobRow {
  id: string;
  kind: JobKind;
  status: JobStatus;
  attempts: number;
  maxAttempts: number;
  workerJobId: string | null;
  libraryItemId: string | null;
  sourceAssetId: string | null;
  userId: string;
  deviceClass: DeviceClass;
  request: Record<string, unknown>;
}

interface RawUser {
  id: string;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
  plan: string;
  render_seconds_balance: string | number | null;
  storage_bytes_used: string | number | null;
}

interface RawLibrary extends Record<string, unknown> {
  id: string;
  title: string;
  status: LibraryStatus;
  status_error_code: string | null;
  status_error_detail: string | null;
  created_at: Date | string;
  updated_at: Date | string;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  fps_num: number | null;
  fps_den: number | null;
  has_audio: boolean | null;
  bytes: string | number | null;
  poster_key: string | null;
  detection_revision: string | null;
  render_job_id: string | null;
  render_status: string | null;
}

export function iso(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

export function num(value: string | number | null | undefined): number | null {
  return value === null || value === undefined ? null : Number(value);
}

export function mapUser(row: RawUser): UserRecord {
  return {
    id: row.id,
    email: row.email,
    displayName: row.display_name,
    avatarUrl: row.avatar_url,
    plan: row.plan,
    renderSecondsBalance: num(row.render_seconds_balance) ?? 0,
    storageBytesUsed: num(row.storage_bytes_used) ?? 0,
  };
}

export function mapLibrary(row: RawLibrary): LibraryRow {
  return {
    id: row.id,
    title: row.title,
    status: row.status,
    statusErrorCode: row.status_error_code,
    statusErrorDetail: row.status_error_detail,
    createdAt: iso(row.created_at),
    updatedAt: iso(row.updated_at),
    durationMs: row.duration_ms,
    width: row.width,
    height: row.height,
    fpsNum: row.fps_num,
    fpsDen: row.fps_den,
    hasAudio: row.has_audio,
    bytes: num(row.bytes),
    posterKey: row.poster_key,
    detectionRevision: row.detection_revision,
    renderJobId: row.render_job_id,
    renderStatus: row.render_status,
  };
}

const LIBRARY_SELECT = `
  select li.id, li.title, li.status, li.status_error_code, li.status_error_detail,
         li.created_at, li.updated_at, li.duration_ms, li.width, li.height,
         li.fps_num, li.fps_den, li.has_audio, li.bytes,
         po.r2_key as poster_key,
         (select d.revision from detection_runs d
            where d.source_asset_id = li.source_asset_id and d.status = 'succeeded'
            order by d.created_at desc limit 1) as detection_revision,
         (select r.id from render_jobs r where r.library_item_id = li.id
            order by r.created_at desc limit 1) as render_job_id,
         (select r.status from render_jobs r where r.library_item_id = li.id
            order by r.created_at desc limit 1) as render_status
    from library_items li
    left join poster_assets po on po.id = li.poster_asset_id`;

export class Db {
  constructor(private readonly sql: Sql) {}

  async ping(): Promise<number> {
    const started = Date.now();
    await this.sql.query('select 1 as ok');
    return Date.now() - started;
  }

  /** First authenticated call creates the row; later calls refresh mutable profile fields. */
  async ensureUser(identity: Identity): Promise<UserRecord> {
    const { rows } = await this.sql.query<RawUser>(
      `insert into users (oauth_subject, email, display_name, avatar_url)
       values ($1, $2, $3, $4)
       on conflict (oauth_subject) do update
         set email = coalesce(excluded.email, users.email),
             display_name = coalesce(excluded.display_name, users.display_name),
             avatar_url = coalesce(excluded.avatar_url, users.avatar_url)
       returning id, email, display_name, avatar_url, plan,
                 render_seconds_balance, storage_bytes_used`,
      [identity.subject, identity.email, identity.displayName, identity.avatarUrl],
    );
    const row = rows[0];
    if (!row) throw new Error('users upsert returned no row');
    return mapUser(row);
  }

  async createUpload(input: {
    userId: string;
    itemId: string;
    assetId: string;
    title: string;
    filename: string;
    contentType: string;
    bytes: number;
    key: string;
    expiresAt: Date;
  }): Promise<void> {
    await this.sql.transaction(async (tx) => {
      await tx.query(
        `insert into library_items
           (id, user_id, title, status, source_asset_id, bytes)
         values ($1, $2, $3, 'uploading', $4, $5)`,
        [input.itemId, input.userId, input.title, input.assetId, input.bytes],
      );
      await tx.query(
        `insert into source_assets
           (id, user_id, library_item_id, r2_key, filename, content_type, bytes, upload_expires_at)
         values ($1, $2, $3, $4, $5, $6, $7, $8)`,
        [
          input.assetId,
          input.userId,
          input.itemId,
          input.key,
          input.filename,
          input.contentType,
          input.bytes,
          input.expiresAt,
        ],
      );
    });
  }

  /** A retry gets the same object key with a fresh deadline. */
  async reSignUpload(
    userId: string,
    assetId: string,
    expiresAt: Date,
  ): Promise<{ itemId: string; key: string; bytes: number; contentType: string } | null> {
    const { rows } = await this.sql.query<{
      library_item_id: string;
      r2_key: string;
      bytes: string | number;
      content_type: string;
    }>(
      `update source_assets
          set upload_expires_at = $3
        where id = $1 and user_id = $2 and upload_status = 'pending'
      returning library_item_id, r2_key, bytes, content_type`,
      [assetId, userId, expiresAt],
    );
    const row = rows[0];
    if (!row) return null;
    return {
      itemId: row.library_item_id,
      key: row.r2_key,
      bytes: Number(row.bytes),
      contentType: row.content_type,
    };
  }

  /**
   * Marks a verified object complete exactly once. The guarded update is what
   * makes a duplicate `complete` call idempotent and prevents double-counting
   * storage.
   */
  async completeUpload(
    userId: string,
    assetId: string,
    verified: { bytes: number; etag: string },
  ): Promise<{ itemId: string; first: boolean } | null> {
    return this.sql.transaction(async (tx) => {
      const { rows } = await tx.query<{
        library_item_id: string;
        size: string | number;
      }>(
        `update source_assets
            set upload_status = 'completed', bytes = $3, etag = $4
          where id = $1 and user_id = $2 and upload_status = 'pending'
        returning library_item_id, bytes as size`,
        [assetId, userId, verified.bytes, verified.etag],
      );
      const row = rows[0];
      if (!row) {
        const existing = await tx.query<{ library_item_id: string }>(
          `select library_item_id from source_assets where id = $1 and user_id = $2`,
          [assetId, userId],
        );
        const found = existing.rows[0];
        return found ? { itemId: found.library_item_id, first: false } : null;
      }
      await tx.query(
        `update library_items
            set status = case when status = 'uploading' then 'uploaded' else status end,
                bytes = $3,
                status_error_code = null,
                status_error_detail = null
          where id = $1 and user_id = $2`,
        [row.library_item_id, userId, verified.bytes],
      );
      await tx.query(
        `update users set storage_bytes_used = storage_bytes_used + $2 where id = $1`,
        [userId, Number(row.size)],
      );
      return { itemId: row.library_item_id, first: true };
    });
  }

  async list(
    userId: string,
    options: {
      limit: number;
      status?: string | undefined;
      cursor?: { createdAt: string; id: string } | undefined;
    },
  ): Promise<LibraryRow[]> {
    const values: unknown[] = [userId];
    const where = ['li.user_id = $1', 'li.deleted_at is null'];
    if (options.status) {
      values.push(options.status);
      where.push(`li.status = $${values.length}`);
    }
    if (options.cursor) {
      values.push(options.cursor.createdAt, options.cursor.id);
      where.push(
        `(li.created_at, li.id) < ($${values.length - 1}::timestamptz, $${values.length}::uuid)`,
      );
    }
    values.push(options.limit + 1);
    const { rows } = await this.sql.query<RawLibrary>(
      `${LIBRARY_SELECT} where ${where.join(' and ')}
       order by li.created_at desc, li.id desc
       limit $${values.length}`,
      values,
    );
    return rows.map(mapLibrary);
  }

  async item(userId: string, itemId: string): Promise<LibraryRow | null> {
    const { rows } = await this.sql.query<RawLibrary>(
      `${LIBRARY_SELECT} where li.user_id = $1 and li.id = $2 and li.deleted_at is null`,
      [userId, itemId],
    );
    const row = rows[0];
    return row ? mapLibrary(row) : null;
  }

  /** Looks up an upload by asset id, scoped to the caller. */
  async sourceByAsset(
    userId: string,
    assetId: string,
  ): Promise<{
    id: string;
    libraryItemId: string;
    r2Key: string;
    bytes: number;
    contentType: string;
    uploadStatus: 'pending' | 'completed' | 'abandoned';
    probeJson: Record<string, unknown> | null;
  } | null> {
    const { rows } = await this.sql.query<{
      id: string;
      library_item_id: string;
      r2_key: string;
      bytes: string | number;
      content_type: string;
      upload_status: 'pending' | 'completed' | 'abandoned';
      probe_json: Record<string, unknown> | null;
    }>(
      `select id, library_item_id, r2_key, bytes, content_type, upload_status, probe_json
         from source_assets where id = $1 and user_id = $2`,
      [assetId, userId],
    );
    const row = rows[0];
    return row
      ? {
          id: row.id,
          libraryItemId: row.library_item_id,
          r2Key: row.r2_key,
          bytes: Number(row.bytes),
          contentType: row.content_type,
          uploadStatus: row.upload_status,
          probeJson: row.probe_json,
        }
      : null;
  }

  async source(userId: string, itemId: string): Promise<SourceRow | null> {
    const { rows } = await this.sql.query<{
      id: string;
      filename: string;
      content_type: string;
      bytes: string | number;
      etag: string | null;
      sha256: string | null;
      upload_status: SourceRow['uploadStatus'];
      probe_status: SourceRow['probeStatus'];
      dissect_status: SourceRow['dissectStatus'];
      beat_manifest_hash: string | null;
      r2_key: string;
      probe_json: Record<string, unknown> | null;
    }>(
      `select id, filename, content_type, bytes, etag, sha256, upload_status,
              probe_status, dissect_status, beat_manifest_hash, r2_key, probe_json
         from source_assets
        where library_item_id = $1 and user_id = $2
        order by created_at desc limit 1`,
      [itemId, userId],
    );
    const row = rows[0];
    return row
      ? {
          id: row.id,
          filename: row.filename,
          contentType: row.content_type,
          bytes: Number(row.bytes),
          etag: row.etag,
          sha256: row.sha256,
          uploadStatus: row.upload_status,
          probeStatus: row.probe_status,
          dissectStatus: row.dissect_status,
          beatManifestHash: row.beat_manifest_hash,
          r2Key: row.r2_key,
          probeJson: row.probe_json,
        }
      : null;
  }

  async proxy(userId: string, itemId: string): Promise<ProxyRow | null> {
    const { rows } = await this.sql.query<{
      id: string;
      width: number;
      height: number;
      duration_ms: number;
      fps_num: number;
      fps_den: number;
      bytes: string | number;
    }>(
      `select p.id, p.width, p.height, p.duration_ms, p.fps_num, p.fps_den, p.bytes
         from library_items li
         join proxy_assets p on p.id = li.proxy_asset_id
        where li.id = $1 and li.user_id = $2 and li.deleted_at is null`,
      [itemId, userId],
    );
    const row = rows[0];
    return row
      ? {
          id: row.id,
          width: row.width,
          height: row.height,
          durationMs: row.duration_ms,
          fpsNum: row.fps_num,
          fpsDen: row.fps_den,
          bytes: Number(row.bytes),
        }
      : null;
  }

  async play(userId: string, itemId: string): Promise<PlayRow | null> {
    const { rows } = await this.sql.query<{
      r2_key: string;
      width: number;
      height: number;
      duration_ms: number;
    }>(
      `select p.r2_key, p.width, p.height, p.duration_ms
         from library_items li
         join proxy_assets p on p.id = li.proxy_asset_id
        where li.id = $1 and li.user_id = $2 and li.deleted_at is null`,
      [itemId, userId],
    );
    const row = rows[0];
    return row
      ? {
          r2Key: row.r2_key,
          width: row.width,
          height: row.height,
          durationMs: row.duration_ms,
        }
      : null;
  }

  async beatSummary(
    userId: string,
    itemId: string,
  ): Promise<{ total: number; withTarget: number }> {
    const { rows } = await this.sql.query<{ total: number; with_target: number }>(
      `select count(*)::int as total,
              count(*) filter (where b.has_target)::int as with_target
         from beats b
         join library_items li on li.source_asset_id = b.source_asset_id
        where li.id = $1 and li.user_id = $2`,
      [itemId, userId],
    );
    const row = rows[0];
    return { total: row?.total ?? 0, withTarget: row?.with_target ?? 0 };
  }

  async softDelete(
    userId: string,
    itemId: string,
  ): Promise<{ keys: string[]; bytes: number } | null> {
    return this.sql.transaction(async (tx) => {
      const { rows } = await tx.query<{
        source_key: string | null;
        proxy_key: string | null;
        poster_key: string | null;
        bytes: string | number | null;
      }>(
        `select sa.r2_key as source_key, pa.r2_key as proxy_key, po.r2_key as poster_key,
                sa.bytes
           from library_items li
           left join source_assets sa on sa.id = li.source_asset_id
           left join proxy_assets pa on pa.id = li.proxy_asset_id
           left join poster_assets po on po.id = li.poster_asset_id
          where li.id = $1 and li.user_id = $2 and li.deleted_at is null
          for update of li`,
        [itemId, userId],
      );
      const row = rows[0];
      if (!row) return null;
      const keys = [row.source_key, row.proxy_key, row.poster_key].filter(
        (key): key is string => typeof key === 'string',
      );
      const bytes = Number(row.bytes ?? 0);
      await tx.query(
        `update library_items
            set deleted_at = now(), status = 'deleting',
                proxy_asset_id = null, poster_asset_id = null
          where id = $1 and user_id = $2`,
        [itemId, userId],
      );
      if (bytes > 0) {
        await tx.query(
          `update users set storage_bytes_used = greatest(0, storage_bytes_used - $2)
            where id = $1`,
          [userId, bytes],
        );
      }
      return { keys, bytes };
    });
  }

  async createJob(input: {
    userId: string;
    itemId: string;
    assetId: string;
    kind: JobKind;
    deviceClass: DeviceClass;
    idempotencyKey: string;
    request?: Record<string, unknown>;
    workerJobId: string;
  }): Promise<{ id: string; created: boolean }> {
    const { rows } = await this.sql.query<{ id: string }>(
      `insert into worker_jobs
         (user_id, library_item_id, source_asset_id, kind, device_class,
          idempotency_key, request_json, worker_job_id)
       values ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
       on conflict (kind, idempotency_key) do nothing
       returning id`,
      [
        input.userId,
        input.itemId,
        input.assetId,
        input.kind,
        input.deviceClass,
        input.idempotencyKey,
        JSON.stringify(input.request ?? {}),
        input.workerJobId,
      ],
    );
    const created = rows[0];
    if (created) return { id: created.id, created: true };
    const existing = await this.sql.query<{ id: string }>(
      `select id from worker_jobs where kind = $1 and idempotency_key = $2`,
      [input.kind, input.idempotencyKey],
    );
    const row = existing.rows[0];
    if (!row) throw new Error('worker_jobs insert conflicted but no row exists');
    return { id: row.id, created: false };
  }

  async job(jobId: string): Promise<WorkerJobRow | null> {
    const { rows } = await this.sql.query<{
      id: string;
      kind: JobKind;
      status: JobStatus;
      attempts: number;
      max_attempts: number;
      worker_job_id: string | null;
      library_item_id: string | null;
      source_asset_id: string | null;
      user_id: string;
      device_class: DeviceClass;
      request_json: Record<string, unknown>;
    }>(
      `select id, kind, status, attempts, max_attempts, worker_job_id,
              library_item_id, source_asset_id, user_id, device_class, request_json
         from worker_jobs where id = $1`,
      [jobId],
    );
    const row = rows[0];
    return row
      ? {
          id: row.id,
          kind: row.kind,
          status: row.status,
          attempts: row.attempts,
          maxAttempts: row.max_attempts,
          workerJobId: row.worker_job_id,
          libraryItemId: row.library_item_id,
          sourceAssetId: row.source_asset_id,
          userId: row.user_id,
          deviceClass: row.device_class,
          request: row.request_json,
        }
      : null;
  }

  async startJob(jobId: string): Promise<boolean> {
    const { rows } = await this.sql.query(
      `update worker_jobs
          set status = 'running', attempts = attempts + 1,
              started_at = coalesce(started_at, now()),
              lease_expires_at = now() + interval '30 minutes'
        where id = $1 and status in ('queued', 'failed') and attempts < max_attempts
      returning id`,
      [jobId],
    );
    return rows.length > 0;
  }

  async succeedJob(
    jobId: string,
    result: Record<string, unknown>,
    computeSeconds: number,
  ) {
    await this.sql.query(
      `update worker_jobs
          set status = 'succeeded', result_json = $2::jsonb,
              compute_seconds = $3, finished_at = now(), error_code = null,
              error_detail = null
        where id = $1`,
      [jobId, JSON.stringify(result), computeSeconds],
    );
  }

  async failJob(
    jobId: string,
    code: string,
    detail: string,
    options: { retryable: boolean; attempts: number; maxAttempts: number },
  ) {
    const exhausted = options.attempts >= options.maxAttempts;
    await this.sql.query(
      `update worker_jobs
          set status = $3, error_code = $2, error_detail = $4,
              finished_at = case when $3 = 'failed' then now() else null end
        where id = $1`,
      [jobId, code, exhausted || !options.retryable ? 'failed' : 'queued', detail],
    );
    return exhausted || !options.retryable;
  }

  async applyProbe(
    job: { userId: string; itemId: string; assetId: string },
    probe: {
      duration_ms: number;
      display_width: number;
      display_height: number;
      rotation: number;
      fps_num: number;
      fps_den: number;
      has_audio: boolean;
      video_codec: string;
    },
    raw: Record<string, unknown>,
  ): Promise<void> {
    await this.sql.transaction(async (tx) => {
      await tx.query(
        `update source_assets
            set probe_status = 'succeeded', probe_json = $2::jsonb,
                error_code = null, error_detail = null
          where id = $1`,
        [job.assetId, JSON.stringify(raw)],
      );
      await tx.query(
        `update library_items
            set duration_ms = $3, width = $4, height = $5, fps_num = $6,
                fps_den = $7, rotation = $8, has_audio = $9, codec = $10,
                status_error_code = null, status_error_detail = null
          where id = $1 and user_id = $2`,
        [
          job.itemId,
          job.userId,
          probe.duration_ms,
          probe.display_width,
          probe.display_height,
          probe.fps_num,
          probe.fps_den,
          probe.rotation,
          probe.has_audio,
          probe.video_codec,
        ],
      );
    });
  }

  async applyProxy(
    job: { userId: string; itemId: string; assetId: string },
    input: {
      proxyKey: string;
      posterKey: string;
      width: number;
      height: number;
      fpsNum: number;
      fpsDen: number;
      durationMs: number;
      proxyBytes: number;
      posterBytes: number;
      posterWidth: number;
      posterHeight: number;
      frameIndex: number | null;
      proxyId: string;
      posterId: string;
      now: Date;
    },
  ): Promise<void> {
    await this.sql.transaction(async (tx) => {
      await tx.query(
        `insert into proxy_assets
           (id, user_id, source_asset_id, r2_key, width, height, fps_num, fps_den,
            duration_ms, bytes)
         values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
         on conflict (r2_key) do update
           set bytes = excluded.bytes, updated_at = now()`,
        [
          input.proxyId,
          job.userId,
          job.assetId,
          input.proxyKey,
          input.width,
          input.height,
          input.fpsNum,
          input.fpsDen,
          input.durationMs,
          input.proxyBytes,
        ],
      );
      await tx.query(
        `insert into poster_assets
           (id, user_id, source_asset_id, r2_key, width, height, bytes, frame_index)
         values ($1, $2, $3, $4, $5, $6, $7, $8)
         on conflict (r2_key) do update
           set bytes = excluded.bytes, updated_at = now()`,
        [
          input.posterId,
          job.userId,
          job.assetId,
          input.posterKey,
          input.posterWidth,
          input.posterHeight,
          input.posterBytes,
          input.frameIndex,
        ],
      );
      await tx.query(
        `update library_items
            set proxy_asset_id = (select id from proxy_assets where r2_key = $3),
                poster_asset_id = (select id from poster_assets where r2_key = $4),
                status_error_code = null, status_error_detail = null
          where id = $1 and user_id = $2`,
        [job.itemId, job.userId, input.proxyKey, input.posterKey],
      );
    });
  }

  async setItemError(
    userId: string,
    itemId: string,
    code: string,
    detail: string,
    status?: 'failed' | 'upload_incomplete',
  ): Promise<void> {
    await this.sql.query(
      `update library_items
          set status = coalesce($4, status),
              status_error_code = $3, status_error_detail = $5
        where id = $1 and user_id = $2`,
      [itemId, userId, code, status ?? null, detail],
    );
  }

  async clearItemError(userId: string, itemId: string): Promise<void> {
    await this.sql.query(
      `update library_items
          set status_error_code = null, status_error_detail = null
        where id = $1 and user_id = $2`,
      [itemId, userId],
    );
  }
}
