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

export interface DetectionRunRow {
  id: string;
  revision: string;
  engine: 'auto' | 'paddleocr' | 'rapidocr';
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  progressMilli: number;
  framesRead: number;
  framesSkipped: number;
  framesTotal: number;
  coverageMilli: number | null;
  effectiveFpsMilli: number | null;
  truncated: boolean;
  ocrAvailable: boolean;
  logoModelAvailable: boolean;
  warnings: string[];
  modelVersions: Record<string, string>;
  detectionWidth: number | null;
  detectionHeight: number | null;
  computeSeconds: number;
  deviceClass: DeviceClass | null;
  errorCode: string | null;
  errorDetail: string | null;
  cancelRequestedAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface DetectionGroupRow {
  id: string;
  kind: 'text' | 'logo' | 'watermark' | 'image' | 'user_box';
  lane: number;
  orderIndex: number;
  sampleText: string | null;
  box: { x: number; y: number; w: number; h: number };
  confidenceMilli: number;
  includedDefault: boolean;
  lowConfidence: boolean;
  members: DetectionMemberRow[];
}

export interface DetectionMemberRow {
  id: string;
  orderIndex: number;
  text: string | null;
  rangeMode: 'ranges' | 'whole_source';
  ranges: Array<{
    beat_id: string;
    beat_index: number;
    start_frame: number;
    end_frame: number;
  }>;
  box: { x: number; y: number; w: number; h: number };
  confidenceMilli: number;
  provenance: 'ocr' | 'logo' | 'user_box' | 'manual';
  maskId: string | null;
  maskKey: string | null;
  maskKind: 'glyph' | 'region' | 'feather' | null;
  maskFormat: 'png' | 'webp' | null;
  maskProvenance: 'ocr' | 'logo' | 'user_box' | 'manual' | null;
  maskModelVersion: string | null;
  includedDefault: boolean;
  lowConfidence: boolean;
}

export interface BeatRow {
  id: string;
  index: number;
  startFrame: number;
  endFrame: number;
  startMs: number;
  endMs: number;
  boundary: 'start' | 'scene' | 'cap' | 'end';
  status: 'pending' | 'ready' | 'empty' | 'failed';
  hasTarget: boolean;
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

  /**
   * Create a job, or return a failed/cancelled one to the queue.
   *
   * A failed detection used to leave its idempotency key occupied, so a retry
   * inserted a new detection run and then collided with the old job. Resetting
   * the job keeps one row and one attempt history slot.
   */
  async createOrRetryJob(input: {
    userId: string;
    itemId: string;
    assetId: string;
    kind: JobKind;
    deviceClass: DeviceClass;
    idempotencyKey: string;
    request?: Record<string, unknown>;
    workerJobId: string;
  }): Promise<{ id: string; created: boolean; retried: boolean }> {
    const created = await this.createJob(input);
    if (created.created) return { ...created, retried: false };

    const { rows } = await this.sql.query<{ id: string }>(
      `update worker_jobs
          set status = 'queued', attempts = 0, worker_job_id = $3,
              request_json = $4::jsonb, device_class = $5,
              error_code = null, error_detail = null,
              started_at = null, finished_at = null, lease_expires_at = null,
              updated_at = now()
        where kind = $1 and idempotency_key = $2
          and status in ('failed', 'cancelled')
        returning id`,
      [
        input.kind,
        input.idempotencyKey,
        input.workerJobId,
        JSON.stringify(input.request ?? {}),
        input.deviceClass,
      ],
    );
    const row = rows[0];
    return row
      ? { id: row.id, created: false, retried: true }
      : { ...created, retried: false };
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
                status = case when status = 'uploaded' then 'probing' else status end,
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

  /**
   * Beats are only usable once the proxy exists and dissection succeeded; the
   * item is `ready` exactly then, whichever job finishes second.
   */
  private static readinessSql = `
    update library_items li
       set status = 'ready', status_error_code = null, status_error_detail = null
     where li.id = $1 and li.user_id = $2
       and li.status in ('uploading', 'uploaded', 'probing', 'dissecting')
       and li.proxy_asset_id is not null
       and exists (
         select 1 from source_assets sa
          where sa.id = li.source_asset_id and sa.dissect_status = 'succeeded'
       )`;

  async markDissecting(userId: string, itemId: string): Promise<void> {
    await this.sql.query(
      `update library_items set status = 'dissecting'
        where id = $1 and user_id = $2 and status in ('uploaded', 'probing')`,
      [itemId, userId],
    );
  }

  async applyDissect(
    job: { userId: string; itemId: string; assetId: string },
    input: {
      beats: Array<{
        index: number;
        startFrame: number;
        endFrame: number;
        startMs: number;
        endMs: number;
        boundary: 'start' | 'scene' | 'cap' | 'end';
      }>;
      manifestHash: string;
      manifest: Record<string, unknown>;
      sourceSha256: string;
    },
  ): Promise<void> {
    await this.sql.transaction(async (tx) => {
      await tx.query(`delete from beats where source_asset_id = $1`, [job.assetId]);
      await tx.query(
        `update source_assets
            set dissect_status = 'succeeded', beat_manifest_hash = $2,
                beat_manifest_json = $3::jsonb, sha256 = coalesce(sha256, $4),
                error_code = null, error_detail = null
          where id = $1`,
        [
          job.assetId,
          input.manifestHash,
          JSON.stringify(input.manifest),
          input.sourceSha256,
        ],
      );
      for (const beat of input.beats) {
        await tx.query(
          `insert into beats
             (user_id, source_asset_id, beat_manifest_hash, "index", start_frame,
              end_frame, start_ms, end_ms, boundary, status)
           values ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending')`,
          [
            job.userId,
            job.assetId,
            input.manifestHash,
            beat.index,
            beat.startFrame,
            beat.endFrame,
            beat.startMs,
            beat.endMs,
            beat.boundary,
          ],
        );
      }
      await tx.query(Db.readinessSql, [job.itemId, job.userId]);
    });
  }

  /**
   * Dissection failed for good. The proxy still plays, so the item is marked
   * ready with an explicit error instead of being reported as unusable.
   */
  async failDissect(
    userId: string,
    itemId: string,
    assetId: string,
    code: string,
    detail: string,
  ): Promise<void> {
    await this.sql.transaction(async (tx) => {
      await tx.query(
        `update source_assets
            set dissect_status = 'failed', error_code = $2, error_detail = $3
          where id = $1`,
        [assetId, code, detail],
      );
      await tx.query(
        `update library_items
            set status = case when proxy_asset_id is not null then 'ready' else 'failed' end,
                status_error_code = 'dissect_failed', status_error_detail = $3
          where id = $1 and user_id = $2`,
        [itemId, userId, detail],
      );
    });
  }

  async beats(userId: string, itemId: string): Promise<BeatRow[]> {
    const { rows } = await this.sql.query<{
      id: string;
      index: number;
      start_frame: number;
      end_frame: number;
      start_ms: number;
      end_ms: number;
      boundary: BeatRow['boundary'];
      status: BeatRow['status'];
      has_target: boolean;
    }>(
      `select b.id, b."index", b.start_frame, b.end_frame, b.start_ms, b.end_ms,
              b.boundary, b.status, b.has_target
         from beats b
         join library_items li on li.source_asset_id = b.source_asset_id
        where li.id = $1 and li.user_id = $2 and li.deleted_at is null
        order by b."index"`,
      [itemId, userId],
    );
    return rows.map((row) => ({
      id: row.id,
      index: row.index,
      startFrame: row.start_frame,
      endFrame: row.end_frame,
      startMs: row.start_ms,
      endMs: row.end_ms,
      boundary: row.boundary,
      status: row.status,
      hasTarget: row.has_target,
    }));
  }

  async createDetectionRun(input: {
    id: string;
    userId: string;
    assetId: string;
    revision: string;
    engine: 'auto' | 'paddleocr' | 'rapidocr';
    detectionWidth: number | null;
    detectionHeight: number | null;
    workerJobId: string;
  }): Promise<string> {
    const { rows } = await this.sql.query<{ id: string }>(
      `insert into detection_runs
         (id, user_id, source_asset_id, revision, engine, detection_width,
          detection_height, status, worker_job_id)
       values ($1, $2, $3, $4, $5, $6, $7, 'queued', $8)
       returning id`,
      [
        input.id,
        input.userId,
        input.assetId,
        input.revision,
        input.engine,
        input.detectionWidth,
        input.detectionHeight,
        input.workerJobId,
      ],
    );
    const row = rows[0];
    if (!row) throw new Error('detection_runs insert returned no row');
    return row.id;
  }

  async startDetectionRun(runId: string): Promise<void> {
    await this.sql.query(
      `update detection_runs
          set status = 'running', started_at = coalesce(started_at, now())
        where id = $1 and status = 'queued'`,
      [runId],
    );
  }

  async detectionRun(runId: string): Promise<DetectionRunRow | null> {
    const { rows } = await this.sql.query<Record<string, unknown>>(
      `${DETECTION_RUN_SELECT} where r.id = $1`,
      [runId],
    );
    return rows[0] ? toDetectionRun(rows[0]) : null;
  }

  async latestDetectionRun(
    userId: string,
    itemId: string,
  ): Promise<DetectionRunRow | null> {
    const { rows } = await this.sql.query<Record<string, unknown>>(
      `${DETECTION_RUN_SELECT}
        join library_items li on li.source_asset_id = r.source_asset_id
       where li.id = $1 and li.user_id = $2 and li.deleted_at is null
       order by r.created_at desc limit 1`,
      [itemId, userId],
    );
    return rows[0] ? toDetectionRun(rows[0]) : null;
  }

  async detectionState(
    userId: string,
    itemId: string,
  ): Promise<{
    run: DetectionRunRow | null;
    groups: DetectionGroupRow[];
    beats: BeatRow[];
  }> {
    const run = await this.latestDetectionRun(userId, itemId);
    if (!run) return { run: null, groups: [], beats: await this.beats(userId, itemId) };
    const { rows } = await this.sql.query<{
      id: string;
      kind: DetectionGroupRow['kind'];
      lane: number;
      order_index: number;
      sample_text: string | null;
      box_x: number;
      box_y: number;
      box_w: number;
      box_h: number;
      confidence_milli: number;
      included_default: boolean;
      low_confidence: boolean;
    }>(
      `select id, kind, lane, order_index, sample_text, box_x, box_y, box_w, box_h,
              confidence_milli, included_default, low_confidence
         from detection_groups where run_id = $1 order by order_index`,
      [run.id],
    );
    const members = await this.sql.query<{
      id: string;
      group_id: string;
      order_index: number;
      text: string | null;
      range_mode: 'ranges' | 'whole_source';
      ranges_json: DetectionMemberRow['ranges'];
      box_x: number;
      box_y: number;
      box_w: number;
      box_h: number;
      confidence_milli: number;
      provenance: DetectionMemberRow['provenance'];
      mask_id: string | null;
      r2_key: string | null;
      mask_kind: DetectionMemberRow['maskKind'];
      mask_format: 'png' | 'webp' | null;
      mask_provenance: DetectionMemberRow['maskProvenance'];
      mask_model_version: string | null;
      included_default: boolean;
      low_confidence: boolean;
    }>(
      `select m.id, m.group_id, m.order_index, m.text, m.range_mode, m.ranges_json,
              m.box_x, m.box_y, m.box_w, m.box_h, m.confidence_milli, m.provenance,
              ma.id as mask_id, ma.r2_key, ma.kind as mask_kind,
              ma.format as mask_format,
              ma.provenance as mask_provenance,
              ma.model_version as mask_model_version,
              m.included_default, m.low_confidence
         from detection_members m
         left join mask_assets ma on ma.id = m.mask_asset_id
        where m.group_id in (select id from detection_groups where run_id = $1)
        order by m.group_id, m.order_index`,
      [run.id],
    );
    const byGroup = new Map<string, DetectionMemberRow[]>();
    for (const row of members.rows) {
      const list = byGroup.get(row.group_id) ?? [];
      list.push({
        id: row.id,
        orderIndex: row.order_index,
        text: row.text,
        rangeMode: row.range_mode,
        ranges: row.ranges_json ?? [],
        box: { x: row.box_x, y: row.box_y, w: row.box_w, h: row.box_h },
        confidenceMilli: row.confidence_milli,
        provenance: row.provenance,
        maskId: row.mask_id,
        maskKey: row.r2_key,
        maskKind: row.mask_kind,
        maskFormat: row.mask_format,
        maskProvenance: row.mask_provenance,
        maskModelVersion: row.mask_model_version,
        includedDefault: row.included_default,
        lowConfidence: row.low_confidence,
      });
      byGroup.set(row.group_id, list);
    }
    return {
      run,
      groups: rows.map((row) => ({
        id: row.id,
        kind: row.kind,
        lane: row.lane,
        orderIndex: row.order_index,
        sampleText: row.sample_text,
        box: { x: row.box_x, y: row.box_y, w: row.box_w, h: row.box_h },
        confidenceMilli: row.confidence_milli,
        includedDefault: row.included_default,
        lowConfidence: row.low_confidence,
        members: byGroup.get(row.id) ?? [],
      })),
      beats: await this.beats(userId, itemId),
    };
  }

  async requestDetectionCancel(
    userId: string,
    itemId: string,
  ): Promise<DetectionRunRow | null> {
    const run = await this.latestDetectionRun(userId, itemId);
    if (!run) return null;
    if (run.status !== 'queued' && run.status !== 'running') return run;
    await this.sql.query(
      `update detection_runs
          set cancel_requested_at = now(),
              status = case when status = 'queued' then 'cancelled' else status end,
              finished_at = case when status = 'queued' then now() else finished_at end
        where id = $1`,
      [run.id],
    );
    return this.detectionRun(run.id);
  }

  async applyDetection(
    runId: string,
    payload: {
      truncated: boolean;
      framesRead: number;
      framesTotal: number;
      framesSkipped: number;
      effectiveFpsMilli: number;
      ocrAvailable: boolean;
      logoModelAvailable: boolean;
      warnings: string[];
      modelVersions: Record<string, string>;
      computeSeconds: number;
      deviceClass: DeviceClass;
      /** null means every beat was in scope. */
      scopeBeatIndexes: number[] | null;
      groups: Array<{
        id: string;
        kind: DetectionGroupRow['kind'];
        lane: number;
        orderIndex: number;
        sampleText: string | null;
        box: { x: number; y: number; w: number; h: number };
        confidenceMilli: number;
        includedDefault: boolean;
        lowConfidence: boolean;
        members: Array<
          Omit<
            DetectionMemberRow,
            | 'maskKey'
            | 'maskId'
            | 'maskKind'
            | 'maskFormat'
            | 'maskProvenance'
            | 'maskModelVersion'
          > & { maskId: string | null }
        >;
      }>;
      masks: Array<{
        id: string;
        key: string;
        kind: 'glyph' | 'region' | 'feather';
        bytes: number;
        groupId: string;
        memberId: string;
        format: 'png' | 'webp';
        frameStart: number;
        frameEnd: number;
        provenance: DetectionMemberRow['provenance'];
        modelVersion: string;
      }>;
    },
  ): Promise<boolean> {
    return this.sql.transaction(async (tx) => {
      const { rows } = await tx.query<{ cancel_requested_at: string | null }>(
        `select cancel_requested_at from detection_runs where id = $1 for update`,
        [runId],
      );
      const run = rows[0];
      if (!run) return false;
      if (run.cancel_requested_at) {
        await tx.query(
          `update detection_runs set status = 'cancelled', finished_at = now()
            where id = $1`,
          [runId],
        );
        return false;
      }
      // A new revision replaces the previous scan's beat truth. Without this
      // reset, beats from the old run stay `ready`/`has_target`.
      await tx.query(
        `update beats
            set has_target = false, status = 'pending', detection_run_id = null
          where source_asset_id = (
            select source_asset_id from detection_runs where id = $1
          )`,
        [runId],
      );
      const coverageMilli = payload.framesTotal
        ? Math.round((payload.framesRead * 1000) / payload.framesTotal)
        : 0;
      await tx.query(
        `update detection_runs
            set status = 'succeeded', progress_milli = 1000,
                frames_read = $2, frames_skipped = $3, frames_total = $4,
                coverage_milli = $5, effective_fps_milli = $13, truncated = $6,
                ocr_available = $7,
                logo_model_available = $8, warnings_json = $9::jsonb,
                model_versions_json = $10::jsonb, compute_seconds = $11,
                device_class = $12, finished_at = now(),
                error_code = null, error_detail = null
          where id = $1`,
        [
          runId,
          payload.framesRead,
          payload.framesSkipped,
          payload.framesTotal,
          coverageMilli,
          payload.truncated,
          payload.ocrAvailable,
          payload.logoModelAvailable,
          JSON.stringify(payload.warnings),
          JSON.stringify(payload.modelVersions),
          payload.computeSeconds,
          payload.deviceClass,
          payload.effectiveFpsMilli,
        ],
      );
      for (const group of payload.groups) {
        await tx.query(
          `insert into detection_groups
             (id, user_id, run_id, kind, lane, order_index, sample_text,
              box_x, box_y, box_w, box_h, confidence_milli, member_count,
              included_default, low_confidence)
           select $1, r.user_id, r.id, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
             from detection_runs r where r.id = $2`,
          [
            group.id,
            runId,
            group.kind,
            group.lane,
            group.orderIndex,
            group.sampleText,
            group.box.x,
            group.box.y,
            group.box.w,
            group.box.h,
            group.confidenceMilli,
            group.members.length,
            group.includedDefault,
            group.lowConfidence,
          ],
        );
        for (const member of group.members) {
          await tx.query(
            `insert into detection_members
               (id, user_id, group_id, order_index, text, range_mode, ranges_json,
                box_x, box_y, box_w, box_h, confidence_milli, provenance,
                mask_asset_id, included_default, low_confidence)
             select $1, g.user_id, g.id, $3, $4, $5, $6::jsonb, $7, $8, $9, $10,
                    $11, $12, null, $13, $14
               from detection_groups g where g.id = $2`,
            [
              member.id,
              group.id,
              member.orderIndex,
              member.text,
              member.rangeMode,
              JSON.stringify(member.ranges),
              member.box.x,
              member.box.y,
              member.box.w,
              member.box.h,
              member.confidenceMilli,
              member.provenance,
              member.includedDefault,
              member.lowConfidence,
            ],
          );
        }
      }

      // Masks reference both the group and the member, so they land last.
      for (const mask of payload.masks) {
        await tx.query(
          `insert into mask_assets
             (id, user_id, run_id, group_id, member_id, kind, r2_key, format, bytes,
              frame_start, frame_end, provenance, model_version)
           select $1, r.user_id, r.id, $3, $4, $5, $2, $6, $7, $8, $9, $10, $11
             from detection_runs r where r.id = $12`,
          [
            mask.id,
            mask.key,
            mask.groupId,
            mask.memberId,
            mask.kind,
            mask.format,
            mask.bytes,
            mask.frameStart,
            mask.frameEnd,
            mask.provenance,
            mask.modelVersion,
            runId,
          ],
        );
        await tx.query('update detection_members set mask_asset_id = $2 where id = $1', [
          mask.memberId,
          mask.id,
        ]);
      }

      // has_target comes from the members that actually exist, never from a plan.
      await tx.query(
        `update beats b
            set has_target = true, status = 'ready', detection_run_id = $1
          where b.source_asset_id = (select source_asset_id from detection_runs where id = $1)
            and exists (
              select 1
                from detection_members m
                join detection_groups g on g.id = m.group_id
               where g.run_id = $1
                 and (m.range_mode = 'whole_source'
                      or exists (
                        select 1 from jsonb_array_elements(m.ranges_json) r
                         where (r ->> 'beat_id')::uuid = b.id
                      ))
            )`,
        [runId],
      );
      // A complete scan proves the selected beats have nothing. A scoped scan
      // never claims anything about beats it did not read.
      await tx.query(
        `update beats b
            set status = 'empty', detection_run_id = $1
          where b.source_asset_id = (select source_asset_id from detection_runs where id = $1)
            and b.status = 'pending' and $2 = false
            and ($3::int[] is null or b."index" = any($3::int[]))`,
        [runId, payload.truncated, payload.scopeBeatIndexes],
      );
      // `library_items.detection_revision` is a projection of the latest run,
      // not a stored column, so nothing to keep in sync here.
      return true;
    });
  }

  async failDetectionRun(runId: string, code: string, detail: string): Promise<void> {
    await this.sql.query(
      `update detection_runs
          set status = 'failed', error_code = $2, error_detail = $3, finished_at = now()
        where id = $1 and status in ('queued', 'running')`,
      [runId, code, detail],
    );
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
                status = case
                  when status in ('uploading', 'uploaded', 'probing') then 'dissecting'
                  when status = 'dissecting' then 'dissecting'
                  else status
                end,
                status_error_code = null, status_error_detail = null
          where id = $1 and user_id = $2`,
        [job.itemId, job.userId, input.proxyKey, input.posterKey],
      );
      await tx.query(Db.readinessSql, [job.itemId, job.userId]);
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

const DETECTION_RUN_SELECT = `
  select r.id, r.revision, r.engine, r.status, r.progress_milli, r.frames_read,
         r.frames_skipped, r.frames_total, r.coverage_milli, r.effective_fps_milli,
         r.truncated,
         r.ocr_available, r.logo_model_available, r.warnings_json,
         r.model_versions_json, r.detection_width, r.detection_height,
         r.compute_seconds, r.device_class, r.error_code, r.error_detail,
         r.cancel_requested_at, r.started_at, r.finished_at
    from detection_runs r`;

function toDetectionRun(row: Record<string, unknown>): DetectionRunRow {
  return {
    id: String(row.id),
    revision: String(row.revision),
    engine: row.engine as DetectionRunRow['engine'],
    status: row.status as DetectionRunRow['status'],
    progressMilli: Number(row.progress_milli),
    framesRead: Number(row.frames_read),
    framesSkipped: Number(row.frames_skipped),
    framesTotal: Number(row.frames_total),
    coverageMilli: row.coverage_milli === null ? null : Number(row.coverage_milli),
    effectiveFpsMilli:
      row.effective_fps_milli === null ? null : Number(row.effective_fps_milli),
    truncated: Boolean(row.truncated),
    ocrAvailable: Boolean(row.ocr_available),
    logoModelAvailable: Boolean(row.logo_model_available),
    warnings: (row.warnings_json as string[] | null) ?? [],
    modelVersions: (row.model_versions_json as Record<string, string> | null) ?? {},
    detectionWidth: row.detection_width === null ? null : Number(row.detection_width),
    detectionHeight: row.detection_height === null ? null : Number(row.detection_height),
    computeSeconds: Number(row.compute_seconds ?? 0),
    deviceClass: (row.device_class as DetectionRunRow['deviceClass']) ?? null,
    errorCode: (row.error_code as string | null) ?? null,
    errorDetail: (row.error_detail as string | null) ?? null,
    cancelRequestedAt: row.cancel_requested_at
      ? new Date(row.cancel_requested_at as string).toISOString()
      : null,
    startedAt: row.started_at ? new Date(row.started_at as string).toISOString() : null,
    finishedAt: row.finished_at
      ? new Date(row.finished_at as string).toISOString()
      : null,
  };
}
