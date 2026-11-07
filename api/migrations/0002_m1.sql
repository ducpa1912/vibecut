-- DuckClean — M1 schema additions.
--
-- Two corrections the M1 build needs, both additive:
--
--   1. `poster_assets`. M0 pointed `library_items.poster_asset_id` at
--      `proxy_assets`, which requires a positive fps and duration. A still
--      poster has neither, so the constraint forced fake values into a row.
--      Posters now have their own table and the FK is repointed.
--   2. `worker_jobs`. One row per dispatched worker call: attempts, lease,
--      idempotency key and the worker's own job id. Domain truth stays in
--      `source_assets` / `beats` / `detection_runs` / `render_jobs`; this table
--      is only dispatch and retry state, so a redelivered queue message can
--      never double-charge or double-write a result.

begin;

-- ---------------------------------------------------------------------------
-- Posters
-- ---------------------------------------------------------------------------

create table poster_assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  source_asset_id uuid not null references source_assets (id) on delete cascade,
  r2_key text not null unique,
  width integer not null check (width > 0),
  height integer not null check (height > 0),
  bytes bigint not null check (bytes >= 0),
  frame_index integer check (frame_index is null or frame_index >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index poster_assets_source_idx on poster_assets (source_asset_id);
create index poster_assets_user_idx on poster_assets (user_id);

alter table library_items
  drop constraint library_items_poster_asset_fk;

alter table library_items
  add constraint library_items_poster_asset_fk
  foreign key (poster_asset_id) references poster_assets (id)
  on delete set null
  deferrable initially deferred;

create trigger poster_assets_set_updated_at before update on poster_assets
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Worker dispatch
-- ---------------------------------------------------------------------------

create table worker_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users (id) on delete cascade,
  library_item_id uuid references library_items (id) on delete cascade,
  source_asset_id uuid references source_assets (id) on delete cascade,
  kind text not null
    check (kind in ('probe', 'proxy', 'dissect', 'detect', 'render', 'preview')),
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  attempts integer not null default 0,
  constraint worker_jobs_attempts_bounds
    check (attempts >= 0 and attempts <= max_attempts),
  max_attempts integer not null default 3
    check (max_attempts between 1 and 10),
  -- Sent to the worker as its idempotency key. Distinct from this row's id so a
  -- retry can keep the same worker-side result when the call actually landed.
  worker_job_id uuid,
  -- The device class the job was planned for; usage is billed from the worker's
  -- report, never from this column.
  device_class text not null default 'cpu'
    check (device_class in ('cpu', 'gpu_standard', 'gpu_premium')),
  request_json jsonb not null default '{}'::jsonb,
  result_json jsonb,
  compute_seconds numeric(12, 3) check (compute_seconds is null or compute_seconds >= 0),
  lease_expires_at timestamptz,
  error_code text,
  error_detail text,
  -- Stable across queue redelivery. `probe:<source_id>` is one probe.
  idempotency_key text not null,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (kind, idempotency_key)
);

create index worker_jobs_status_created_idx
  on worker_jobs (status, created_at);
create index worker_jobs_library_item_idx
  on worker_jobs (library_item_id, created_at desc);
create index worker_jobs_source_idx
  on worker_jobs (source_asset_id, kind, created_at desc);

create trigger worker_jobs_set_updated_at before update on worker_jobs
  for each row execute function set_updated_at();

commit;
