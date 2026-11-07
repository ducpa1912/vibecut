-- DuckClean — initial schema (M0 contract).
--
-- Conventions
--   * UUID primary keys, `gen_random_uuid()` (core Postgres >= 13).
--   * Every row that belongs to a person carries `user_id`; every API query
--     filters on it. No client-supplied user id is ever trusted.
--   * Times are stored as integer milliseconds and integer frame indices.
--     Milliseconds are derived from frames (`frame * 1000 / fps`) and never
--     re-derived from float seconds, so the contract has no float drift.
--   * Boxes are integers in pixels of the source *display* frame (rotation
--     applied). Normalised boxes are computed by the API for the UI only.
--   * `range_mode` is `ranges` or `whole_source`; an empty `ranges` array is
--     rejected by a CHECK constraint and never means "the whole video".
--   * Job state lives in Postgres. R2 holds bytes, never truth.
--
-- Hash-bearing columns (revision, manifest hash, segment key) use the canonical
-- JSON rules in docs/duckclean/contract.md: integers and strings only, sorted
-- keys, no whitespace.

begin;

-- ---------------------------------------------------------------------------
-- Identity
-- ---------------------------------------------------------------------------

create table users (
  id uuid primary key default gen_random_uuid(),
  -- Clerk JWT `sub`. The only identity join; email is mutable metadata.
  oauth_subject text not null unique,
  email text,
  display_name text,
  avatar_url text,
  plan text not null default 'free'
    check (plan in ('free', 'pro', 'studio')),
  render_seconds_balance numeric(14, 3) not null default 0
    check (render_seconds_balance >= 0),
  storage_bytes_used bigint not null default 0
    check (storage_bytes_used >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table oauth_accounts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  provider text not null
    check (provider in ('clerk', 'google', 'apple', 'email_link')),
  subject text not null,
  email text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (provider, subject)
);

create index oauth_accounts_user_id_idx on oauth_accounts (user_id);

-- ---------------------------------------------------------------------------
-- Library and assets
-- ---------------------------------------------------------------------------

create table library_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  title text not null check (length(title) between 1 and 200),
  -- uploading -> uploaded -> probing -> dissecting -> ready
  -- any state -> failed; uploading -> upload_incomplete (lifecycle reaper)
  status text not null default 'uploading'
    check (status in (
      'uploading', 'uploaded', 'probing', 'dissecting', 'ready',
      'upload_incomplete', 'failed', 'deleting'
    )),
  status_error_code text,
  status_error_detail text,
  -- Populated by probe. NULL until the source is readable.
  duration_ms integer check (duration_ms is null or duration_ms > 0),
  width integer check (width is null or width > 0),
  height integer check (height is null or height > 0),
  fps_num integer check (fps_num is null or fps_num > 0),
  fps_den integer check (fps_den is null or fps_den > 0),
  rotation integer not null default 0,
  has_audio boolean,
  codec text,
  bytes bigint check (bytes is null or bytes >= 0),
  source_asset_id uuid,
  proxy_asset_id uuid,
  poster_asset_id uuid,
  retention_expires_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index library_items_user_created_idx
  on library_items (user_id, created_at desc)
  where deleted_at is null;

create table source_assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  library_item_id uuid not null,
  -- Object key from docs/duckclean/contract.md §Storage layout.
  r2_key text not null unique,
  filename text not null,
  content_type text not null,
  bytes bigint not null check (bytes >= 0),
  etag text,
  sha256 text,
  -- pending: presigned PUT issued, object not verified.
  -- completed: R2 HEAD agreed on bytes (and etag when present).
  upload_status text not null default 'pending'
    check (upload_status in ('pending', 'completed', 'abandoned')),
  upload_expires_at timestamptz not null,
  probe_status text not null default 'pending'
    check (probe_status in ('pending', 'running', 'succeeded', 'failed')),
  probe_json jsonb,
  beat_manifest_hash text,
  beat_manifest_json jsonb,
  dissect_status text not null default 'pending'
    check (dissect_status in ('pending', 'running', 'succeeded', 'failed')),
  error_code text,
  error_detail text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index source_assets_user_idx on source_assets (user_id);
create index source_assets_library_item_idx on source_assets (library_item_id);

-- library_items <-> source_assets reference each other; the deferred FK keeps
-- "create item + asset in one transaction" possible.
alter table source_assets
  add constraint source_assets_library_item_fk
  foreign key (library_item_id) references library_items (id)
  on delete cascade
  deferrable initially deferred;

alter table library_items
  add constraint library_items_source_asset_fk
  foreign key (source_asset_id) references source_assets (id)
  on delete set null
  deferrable initially deferred;

create table proxy_assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  source_asset_id uuid not null references source_assets (id) on delete cascade,
  r2_key text not null unique,
  width integer not null check (width > 0),
  height integer not null check (height > 0),
  fps_num integer not null check (fps_num > 0),
  fps_den integer not null check (fps_den > 0),
  duration_ms integer not null check (duration_ms > 0),
  bytes bigint not null check (bytes >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index proxy_assets_source_idx on proxy_assets (source_asset_id);

alter table library_items
  add constraint library_items_proxy_asset_fk
  foreign key (proxy_asset_id) references proxy_assets (id)
  on delete set null
  deferrable initially deferred;

alter table library_items
  add constraint library_items_poster_asset_fk
  foreign key (poster_asset_id) references proxy_assets (id)
  on delete set null
  deferrable initially deferred;

-- ---------------------------------------------------------------------------
-- Beats
-- ---------------------------------------------------------------------------

-- A beat is the unit of detection and render. Ranges are half-open:
-- [start_frame, end_frame). Beat 0 starts at frame 0; the last beat ends at
-- frame_count; every beat's end_frame equals the next beat's start_frame.
create table beats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  source_asset_id uuid not null references source_assets (id) on delete cascade,
  beat_manifest_hash text not null,
  "index" integer not null check ("index" >= 0),
  start_frame integer not null check (start_frame >= 0),
  end_frame integer not null check (end_frame > start_frame),
  start_ms integer not null check (start_ms >= 0),
  end_ms integer not null check (end_ms > start_ms),
  -- start: frame 0. scene: ffmpeg scene cut. cap: max-length split. end: last frame.
  boundary text not null check (boundary in ('start', 'scene', 'cap', 'end')),
  status text not null default 'pending'
    check (status in ('pending', 'ready', 'empty', 'failed')),
  has_target boolean not null default false,
  confidence_milli integer check (
    confidence_milli is null or (confidence_milli between 0 and 1000)
  ),
  detection_run_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_asset_id, "index")
);

create index beats_source_index_idx on beats (source_asset_id, "index");

-- ---------------------------------------------------------------------------
-- Detection
-- ---------------------------------------------------------------------------

create table detection_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  source_asset_id uuid not null references source_assets (id) on delete cascade,
  -- sha256 over the canonical detection plan; see contract.md §Revisions.
  revision text not null,
  engine text not null default 'auto'
    check (engine in ('auto', 'paddleocr', 'rapidocr')),
  model_versions_json jsonb not null default '{}'::jsonb,
  -- Detection frame space: every box is reported in source display pixels, so
  -- this is informational (the capped width models were actually run at).
  detection_width integer check (detection_width is null or detection_width > 0),
  detection_height integer check (detection_height is null or detection_height > 0),
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  progress_milli integer not null default 0
    check (progress_milli between 0 and 1000),
  frames_read integer not null default 0 check (frames_read >= 0),
  frames_skipped integer not null default 0 check (frames_skipped >= 0),
  frames_total integer not null default 0 check (frames_total >= 0),
  -- 0..1, integer parts per thousand so no float is stored or hashed.
  coverage_milli integer check (coverage_milli is null or coverage_milli between 0 and 1000),
  -- A truncated scan is not "no text"; it is reported separately.
  truncated boolean not null default false,
  ocr_available boolean not null default false,
  logo_model_available boolean not null default false,
  warnings_json jsonb not null default '[]'::jsonb,
  compute_seconds numeric(12, 3) not null default 0 check (compute_seconds >= 0),
  device_class text check (
    device_class is null or device_class in ('cpu', 'gpu_standard', 'gpu_premium')
  ),
  worker_job_id uuid,
  error_code text,
  error_detail text,
  cancel_requested_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index detection_runs_source_created_idx
  on detection_runs (source_asset_id, created_at desc);

alter table beats
  add constraint beats_detection_run_fk
  foreign key (detection_run_id) references detection_runs (id)
  on delete set null
  deferrable initially deferred;

-- One group per visual text area or logo cluster. Groups span beats; the
-- per-beat detail lives on each member's ranges. `lane` keeps timeline rows
-- from overlapping; `order_index` is stable for a revision.
create table detection_groups (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  run_id uuid not null references detection_runs (id) on delete cascade,
  kind text not null check (kind in ('text', 'logo', 'watermark', 'image', 'user_box')),
  lane integer not null default 0 check (lane >= 0),
  order_index integer not null check (order_index >= 0),
  sample_text text,
  box_x integer not null check (box_x >= 0),
  box_y integer not null check (box_y >= 0),
  box_w integer not null check (box_w > 0),
  box_h integer not null check (box_h > 0),
  confidence_milli integer not null check (confidence_milli between 0 and 1000),
  member_count integer not null default 0 check (member_count >= 0),
  included_default boolean not null default true,
  low_confidence boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (run_id, order_index)
);

create index detection_groups_run_lane_idx
  on detection_groups (run_id, lane, order_index);

create table mask_assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  run_id uuid not null references detection_runs (id) on delete cascade,
  group_id uuid references detection_groups (id) on delete cascade,
  member_id uuid,
  kind text not null check (kind in ('glyph', 'region', 'feather')),
  r2_key text not null unique,
  format text not null check (format in ('png', 'webp')),
  bytes bigint not null default 0 check (bytes >= 0),
  frame_start integer not null default 0 check (frame_start >= 0),
  frame_end integer not null default 0 check (frame_end >= 0),
  -- Provenance is never inferred: ocr, logo, user_box or manual.
  provenance text not null check (provenance in ('ocr', 'logo', 'user_box', 'manual')),
  model_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index mask_assets_run_idx on mask_assets (run_id);
create index mask_assets_member_idx on mask_assets (member_id);

-- A member is one text line, logo instance or user region. Its ranges carry the
-- beat they belong to so render planning is a direct group-by.
create table detection_members (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  group_id uuid not null references detection_groups (id) on delete cascade,
  order_index integer not null default 0 check (order_index >= 0),
  text text,
  range_mode text not null default 'ranges'
    check (range_mode in ('ranges', 'whole_source')),
  -- Array of {beat_id, beat_index, start_frame, end_frame}. Non-empty when
  -- range_mode = 'ranges'. Empty ranges are an error, never "whole video".
  ranges_json jsonb not null default '[]'::jsonb,
  box_x integer not null check (box_x >= 0),
  box_y integer not null check (box_y >= 0),
  box_w integer not null check (box_w > 0),
  box_h integer not null check (box_h > 0),
  confidence_milli integer not null check (confidence_milli between 0 and 1000),
  provenance text not null check (provenance in ('ocr', 'logo', 'user_box', 'manual')),
  mask_asset_id uuid references mask_assets (id) on delete set null,
  included_default boolean not null default true,
  low_confidence boolean not null default false,
  fill_keys_json jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (group_id, order_index),
  constraint detection_members_ranges_is_array
    check (jsonb_typeof(ranges_json) = 'array'),
  constraint detection_members_ranges_not_empty
    check (
      range_mode = 'whole_source' or jsonb_array_length(ranges_json) > 0
    )
);

create index detection_members_group_idx on detection_members (group_id, order_index);

alter table mask_assets
  add constraint mask_assets_member_fk
  foreign key (member_id) references detection_members (id)
  on delete cascade
  deferrable initially deferred;

-- ---------------------------------------------------------------------------
-- Rendering
-- ---------------------------------------------------------------------------

-- A preview is a render job with kind = 'preview' (blur or cheap fill, 0.5
-- scale, short hard limit). One state machine, one segment table.
create table render_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  library_item_id uuid not null references library_items (id) on delete cascade,
  detection_run_id uuid references detection_runs (id) on delete set null,
  kind text not null default 'render' check (kind in ('render', 'preview')),
  -- sha256 of the detection run the user reviewed.
  revision text not null,
  -- sha256 over the normalised selection; stable across retries.
  selection_revision text not null,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'assembling', 'ready', 'failed', 'cancelled')),
  stage text not null default 'queued'
    check (stage in (
      'queued', 'planning', 'rendering', 'assembling', 'finalizing', 'done'
    )),
  progress_milli integer not null default 0
    check (progress_milli between 0 and 1000),
  engine text not null default 'auto'
    check (engine in ('auto', 'blur', 'lama', 'propainter', 'generative', 'cover')),
  device_class text not null default 'gpu_standard'
    check (device_class in ('cpu', 'gpu_standard', 'gpu_premium')),
  -- Resolved render parameters: codec, crf, preset, scale, time limit.
  params_json jsonb not null default '{}'::jsonb,
  -- The normalised, sorted selection that was hashed into selection_revision.
  selection_json jsonb not null default '{}'::jsonb,
  model_versions_json jsonb not null default '{}'::jsonb,
  beats_total integer not null default 0 check (beats_total >= 0),
  beats_fill integer not null default 0 check (beats_fill >= 0),
  beats_passthrough integer not null default 0 check (beats_passthrough >= 0),
  estimate_seconds numeric(12, 3) not null default 0 check (estimate_seconds >= 0),
  compute_seconds numeric(12, 3) not null default 0 check (compute_seconds >= 0),
  output_asset_id uuid,
  error_code text,
  error_detail text,
  idempotency_key text,
  worker_job_id uuid,
  worker_id text,
  parent_job_id uuid references render_jobs (id) on delete set null,
  cancel_requested_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index render_jobs_user_idempotency_idx
  on render_jobs (user_id, idempotency_key)
  where idempotency_key is not null;

create index render_jobs_user_status_created_idx
  on render_jobs (user_id, status, created_at desc);
create index render_jobs_library_item_idx on render_jobs (library_item_id, created_at desc);

create table render_segments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  render_job_id uuid not null references render_jobs (id) on delete cascade,
  beat_id uuid not null references beats (id) on delete cascade,
  beat_index integer not null check (beat_index >= 0),
  -- fill: a model runs. passthrough: identical encode parameters, no model.
  mode text not null check (mode in ('fill', 'passthrough')),
  status text not null default 'pending'
    check (status in ('pending', 'running', 'done', 'failed', 'lost', 'cancelled')),
  attempt integer not null default 0 check (attempt >= 0),
  -- (selection_revision, beat_index, engine, params_hash). A retry may reuse a
  -- done segment whose key and object still exist.
  segment_key text not null,
  fill_engine text check (
    fill_engine is null or fill_engine in ('blur', 'lama', 'propainter', 'generative', 'cover')
  ),
  input_r2_key text,
  output_r2_key text,
  fill_seconds numeric(9, 3) not null default 0 check (fill_seconds >= 0),
  encode_seconds numeric(9, 3) not null default 0 check (encode_seconds >= 0),
  compute_seconds numeric(9, 3) not null default 0 check (compute_seconds >= 0),
  error_code text,
  error_detail text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (render_job_id, beat_index)
);

create index render_segments_job_idx on render_segments (render_job_id, beat_index);
create index render_segments_reusable_idx
  on render_segments (segment_key)
  where status = 'done';

create table output_assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  render_job_id uuid not null references render_jobs (id) on delete cascade,
  kind text not null check (kind in ('render', 'preview')),
  r2_key text not null unique,
  bytes bigint not null check (bytes >= 0),
  duration_ms integer not null check (duration_ms > 0),
  width integer not null check (width > 0),
  height integer not null check (height > 0),
  fps_num integer not null check (fps_num > 0),
  fps_den integer not null check (fps_den > 0),
  has_audio boolean not null,
  video_codec text not null default 'h264',
  pixel_format text not null default 'yuv420p',
  sha256 text,
  engine text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index output_assets_job_idx on output_assets (render_job_id);

alter table render_jobs
  add constraint render_jobs_output_asset_fk
  foreign key (output_asset_id) references output_assets (id)
  on delete set null
  deferrable initially deferred;

-- ---------------------------------------------------------------------------
-- Billing and audit
-- ---------------------------------------------------------------------------

-- One row per metered job. `render_hours` is generated, so the ledger cannot
-- disagree with the formula in HANDOFF/contract.md.
create table usage_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete restrict,
  render_job_id uuid references render_jobs (id) on delete set null,
  detection_run_id uuid references detection_runs (id) on delete set null,
  kind text not null check (kind in ('detect', 'preview', 'render')),
  device_class text not null check (device_class in ('cpu', 'gpu_standard', 'gpu_premium')),
  model_tier text,
  compute_seconds numeric(12, 3) not null check (compute_seconds >= 0),
  weight numeric(6, 3) not null check (weight > 0),
  render_hours numeric(14, 6) generated always as
    (compute_seconds * weight / 3600.0) stored,
  stripe_meter_event_id text unique,
  stripe_meter_status text not null default 'pending'
    check (stripe_meter_status in ('pending', 'sent', 'failed', 'skipped')),
  -- Idempotency across worker retries, queue redelivery and Stripe replays.
  idempotency_key text not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index usage_ledger_user_created_idx on usage_ledger (user_id, created_at desc);
create index usage_ledger_job_idx on usage_ledger (render_job_id);

create table events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users (id) on delete cascade,
  job_id uuid,
  type text not null,
  payload_json jsonb not null default '{}'::jsonb,
  -- Webhook and callback dedupe key (Stripe event id, worker callback seq).
  idempotency_key text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (type, idempotency_key)
);

create index events_job_idx on events (job_id);
create index events_user_created_idx on events (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- updated_at
-- ---------------------------------------------------------------------------

create or replace function set_updated_at() returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger users_set_updated_at before update on users
  for each row execute function set_updated_at();
create trigger oauth_accounts_set_updated_at before update on oauth_accounts
  for each row execute function set_updated_at();
create trigger library_items_set_updated_at before update on library_items
  for each row execute function set_updated_at();
create trigger source_assets_set_updated_at before update on source_assets
  for each row execute function set_updated_at();
create trigger proxy_assets_set_updated_at before update on proxy_assets
  for each row execute function set_updated_at();
create trigger beats_set_updated_at before update on beats
  for each row execute function set_updated_at();
create trigger detection_runs_set_updated_at before update on detection_runs
  for each row execute function set_updated_at();
create trigger detection_groups_set_updated_at before update on detection_groups
  for each row execute function set_updated_at();
create trigger detection_members_set_updated_at before update on detection_members
  for each row execute function set_updated_at();
create trigger mask_assets_set_updated_at before update on mask_assets
  for each row execute function set_updated_at();
create trigger render_jobs_set_updated_at before update on render_jobs
  for each row execute function set_updated_at();
create trigger render_segments_set_updated_at before update on render_segments
  for each row execute function set_updated_at();
create trigger output_assets_set_updated_at before update on output_assets
  for each row execute function set_updated_at();
create trigger usage_ledger_set_updated_at before update on usage_ledger
  for each row execute function set_updated_at();
create trigger events_set_updated_at before update on events
  for each row execute function set_updated_at();

commit;
