import { z } from 'zod';

/**
 * Runtime mirror of api/openapi.yaml. The OpenAPI document is normative for the
 * wire shape; this file is what the Worker actually validates with, so a
 * mismatch is a bug in one of the two and is caught by api/test/contract.test.ts.
 *
 * Conventions: snake_case JSON, integer milliseconds, integer pixel boxes,
 * `range_mode` is `ranges` | `whole_source` and empty ranges are invalid.
 */

export const ERROR_CODES = [
  'unauthorized',
  'forbidden',
  'not_found',
  'validation',
  'conflict',
  'too_large',
  'unsupported_media',
  'quota',
  'rate_limited',
  'stale_detection',
  'worker_unavailable',
  'source_unreadable',
  'render_failed',
  'cancelled',
  'internal',
] as const;

export const ERROR_ACTIONS = [
  'none',
  'sign_in',
  'retry',
  'reload_detection',
  'upgrade_plan',
  'choose_engine',
  'reselect_range',
  'reupload',
  'contact_support',
] as const;

export const errorCodeSchema = z.enum(ERROR_CODES);
export const errorActionSchema = z.enum(ERROR_ACTIONS);
export type ErrorCode = (typeof ERROR_CODES)[number];
export type ErrorAction = (typeof ERROR_ACTIONS)[number];

export const apiErrorSchema = z
  .object({
    code: errorCodeSchema,
    message: z.string().min(1),
    detail: z.record(z.string(), z.unknown()),
    retryable: z.boolean(),
    action: errorActionSchema,
  })
  .strict();

export const errorEnvelopeSchema = z.object({ error: apiErrorSchema }).strict();

export type ApiErrorBody = z.infer<typeof apiErrorSchema>;
export type ErrorEnvelope = z.infer<typeof errorEnvelopeSchema>;

// ---------------------------------------------------------------- primitives

export const boxSchema = z
  .object({
    x: z.number().int().min(0),
    y: z.number().int().min(0),
    w: z.number().int().min(1),
    h: z.number().int().min(1),
  })
  .strict();

export const rangeSchema = z
  .object({
    beat_id: z.uuid(),
    beat_index: z.number().int().min(0),
    start_frame: z.number().int().min(0),
    end_frame: z.number().int().min(0),
    start_ms: z.number().int().min(0),
    end_ms: z.number().int().min(0),
  })
  .strict()
  .refine((r) => r.end_frame > r.start_frame, {
    message: 'range must be non-empty: end_frame > start_frame',
  });

export const rangeModeSchema = z.enum(['ranges', 'whole_source']);
export const fillEngineSchema = z.enum([
  'auto',
  'blur',
  'lama',
  'propainter',
  'generative',
  'cover',
]);
export const deviceClassSchema = z.enum(['cpu', 'gpu_standard', 'gpu_premium']);
export const provenanceSchema = z.enum(['ocr', 'logo', 'user_box', 'manual']);

export type Box = z.infer<typeof boxSchema>;
export type Range = z.infer<typeof rangeSchema>;
export type RangeMode = z.infer<typeof rangeModeSchema>;
export type FillEngine = z.infer<typeof fillEngineSchema>;
export type DeviceClass = z.infer<typeof deviceClassSchema>;
export type Provenance = z.infer<typeof provenanceSchema>;

/**
 * LaMa is the CPU clean path. GPU is reserved for ProPainter and generative
 * fill, where the model actually needs the device. The planner must call this
 * instead of trusting a client-supplied device for LaMa.
 */
export function deviceClassForEngine(
  engine: FillEngine | null | undefined,
  requested?: DeviceClass,
): DeviceClass {
  if (engine === 'lama') return 'cpu';
  return requested ?? 'gpu_standard';
}

// ------------------------------------------------------------------- uploads

export const uploadCreateRequestSchema = z
  .object({
    filename: z.string().min(1).max(200),
    content_type: z.enum([
      'video/mp4',
      'video/quicktime',
      'video/webm',
      'video/x-matroska',
    ]),
    bytes: z.number().int().min(1).max(5_000_000_000),
    title: z.string().min(1).max(200).optional(),
  })
  .strict();

export const uploadTicketSchema = z
  .object({
    upload_id: z.uuid(),
    library_item_id: z.uuid(),
    source_asset_id: z.uuid(),
    method: z.literal('PUT'),
    url: z.url(),
    headers: z.record(z.string(), z.string()),
    expires_at: z.iso.datetime(),
    max_bytes: z.number().int().min(1),
  })
  .strict();

export const uploadCompleteRequestSchema = z
  .object({
    bytes: z.number().int().min(1),
    etag: z.string().optional(),
    sha256: z
      .string()
      .regex(/^[a-f0-9]{64}$/)
      .optional(),
  })
  .strict();

// ------------------------------------------------------------------- library

export const libraryStatusSchema = z.enum([
  'uploading',
  'uploaded',
  'probing',
  'dissecting',
  'ready',
  'upload_incomplete',
  'failed',
  'deleting',
]);

export const libraryItemSchema = z
  .object({
    id: z.uuid(),
    title: z.string(),
    status: libraryStatusSchema,
    error: apiErrorSchema.nullable(),
    created_at: z.iso.datetime(),
    updated_at: z.iso.datetime(),
    duration_ms: z.number().int().min(0).nullable(),
    width: z.number().int().min(1).nullable(),
    height: z.number().int().min(1).nullable(),
    fps: z.number().nullable(),
    has_audio: z.boolean().nullable(),
    bytes: z.number().int().min(0).nullable(),
    poster_url: z.url().nullable(),
    poster_expires_at: z.iso.datetime().nullable(),
    detection_revision: z.string().nullable(),
    render_job_id: z.uuid().nullable(),
    render_status: z.string().nullable(),
  })
  .strict();

export const libraryPageSchema = z
  .object({
    items: z.array(libraryItemSchema),
    next_cursor: z.string().nullable(),
  })
  .strict();

export const playTicketSchema = z
  .object({
    url: z.url(),
    expires_at: z.iso.datetime(),
    duration_ms: z.number().int().min(1),
    width: z.number().int().min(1),
    height: z.number().int().min(1),
  })
  .strict();

// ----------------------------------------------------------------- detection

export const maskRefSchema = z
  .object({
    id: z.uuid(),
    kind: z.enum(['glyph', 'region', 'feather']),
    format: z.enum(['png', 'webp']),
    url: z.url().nullable(),
    expires_at: z.iso.datetime().nullable(),
    provenance: provenanceSchema,
    model_version: z.string(),
  })
  .strict();

export const detectionMemberSchema = z
  .object({
    id: z.uuid(),
    text: z.string().nullable(),
    range_mode: rangeModeSchema,
    ranges: z.array(rangeSchema),
    box: boxSchema,
    confidence: z.number().min(0).max(1),
    provenance: provenanceSchema,
    mask: maskRefSchema.nullable(),
    included_default: z.boolean(),
    low_confidence: z.boolean(),
    fill_keys: z.array(z.number().int().min(0)),
  })
  .strict()
  .refine((m) => m.range_mode === 'whole_source' || m.ranges.length > 0, {
    message:
      'range_mode=ranges requires at least one range; empty ranges never mean whole_source',
  });

export const detectionGroupSchema = z
  .object({
    id: z.uuid(),
    kind: z.enum(['text', 'logo', 'watermark', 'image', 'user_box']),
    lane: z.number().int().min(0),
    order_index: z.number().int().min(0),
    sample_text: z.string().nullable(),
    box: boxSchema,
    confidence: z.number().min(0).max(1),
    member_count: z.number().int().min(0),
    included_default: z.boolean(),
    low_confidence: z.boolean(),
    members: z.array(detectionMemberSchema),
  })
  .strict();

export const detectionRunSchema = z
  .object({
    id: z.uuid(),
    revision: z.string(),
    status: z.enum(['queued', 'running', 'succeeded', 'failed', 'cancelled']),
    progress: z.number().min(0).max(1),
    engine: z.enum(['auto', 'paddleocr', 'rapidocr']),
    model_versions: z.record(z.string(), z.string()),
    frames_read: z.number().int().min(0),
    frames_skipped: z.number().int().min(0),
    frames_total: z.number().int().min(0),
    effective_fps: z.number().nullable(),
    coverage: z.number().min(0).max(1).nullable(),
    truncated: z.boolean(),
    ocr_available: z.boolean(),
    logo_model_available: z.boolean(),
    warnings: z.array(
      z.enum([
        'scan_truncated',
        'ocr_unavailable',
        'logo_model_unavailable',
        'frame_cap',
        'low_confidence_only',
      ]),
    ),
    compute_seconds: z.number().min(0),
    device_class: deviceClassSchema.nullable(),
    error: apiErrorSchema.nullable(),
    started_at: z.iso.datetime().nullable(),
    finished_at: z.iso.datetime().nullable(),
  })
  .strict();

export const detectionBeatSchema = z
  .object({
    beat_id: z.uuid(),
    index: z.number().int().min(0),
    start_ms: z.number().int().min(0),
    end_ms: z.number().int().min(0),
    status: z.enum(['pending', 'ready', 'empty', 'failed']),
    has_target: z.boolean(),
  })
  .strict();

export const detectionStateSchema = z
  .object({
    run: detectionRunSchema.nullable(),
    groups: z.array(detectionGroupSchema),
    beats: z.array(detectionBeatSchema),
    selection_counts: z
      .object({
        groups: z.number().int().min(0),
        members: z.number().int().min(0),
        beats_with_target: z.number().int().min(0),
      })
      .strict(),
  })
  .strict();

export const detectRegionSchema = z
  .object({
    region_id: z.uuid().optional(),
    box: boxSchema,
    prompt: z.string().max(100).optional(),
  })
  .strict();

export const detectRequestSchema = z
  .object({
    engine: z.enum(['auto', 'paddleocr', 'rapidocr']).default('auto'),
    text: z.boolean(),
    logos: z.boolean(),
    tile_small_text: z.boolean().default(true),
    max_width: z.number().int().min(320).max(3840).default(1920),
    regions: z.array(detectRegionSchema).default([]),
    scope: z
      .object({ beat_indexes: z.array(z.number().int().min(0)) })
      .strict()
      .optional(),
  })
  .strict();

// -------------------------------------------------------------------- render

export const selectionOverrideSchema = z
  .object({
    member_id: z.uuid(),
    range_mode: rangeModeSchema,
    ranges: z.array(
      z
        .object({
          beat_id: z.uuid(),
          start_frame: z.number().int().min(0),
          end_frame: z.number().int().min(0),
        })
        .strict()
        .refine((r) => r.end_frame > r.start_frame, {
          message: 'override range must be non-empty',
        }),
    ),
  })
  .strict()
  .refine((o) => o.range_mode === 'whole_source' || o.ranges.length > 0, {
    message: 'range_mode=ranges requires at least one range',
  });

export const selectionGroupSchema = z
  .object({
    group_id: z.uuid(),
    member_ids: z.array(z.uuid()),
    engine: fillEngineSchema.nullable(),
    overrides: z.array(selectionOverrideSchema),
  })
  .strict();

export const manualRegionSchema = z
  .object({
    region_id: z.uuid(),
    box: boxSchema,
    range_mode: rangeModeSchema,
    ranges: z.array(rangeSchema),
    engine: fillEngineSchema.nullable(),
    prompt: z.string().max(100).nullable(),
  })
  .strict()
  .refine((r) => r.range_mode === 'whole_source' || r.ranges.length > 0, {
    message: 'range_mode=ranges requires at least one range',
  });

export const selectionSchema = z
  .object({
    groups: z.array(selectionGroupSchema),
    manual_regions: z.array(manualRegionSchema),
  })
  .strict();

export const renderRequestSchema = z
  .object({
    detection_revision: z.string().min(1),
    selection: selectionSchema,
    engine: fillEngineSchema.optional(),
    device_class: deviceClassSchema.optional(),
    idempotency_key: z.string().min(8).max(100).optional(),
  })
  .strict()
  .refine(
    (value) =>
      !(
        value.engine === 'lama' &&
        value.device_class !== undefined &&
        value.device_class !== 'cpu'
      ),
    {
      message: 'LaMa must run on CPU; use ProPainter or generative fill for GPU.',
      path: ['device_class'],
    },
  );

export const previewRequestSchema = z
  .object({
    detection_revision: z.string().min(1),
    selection: selectionSchema,
    engine: z.enum(['blur', 'lama']).default('blur'),
    device_class: deviceClassSchema.optional(),
  })
  .strict()
  .refine(
    (value) =>
      !(
        value.engine === 'lama' &&
        value.device_class !== undefined &&
        value.device_class !== 'cpu'
      ),
    {
      message: 'LaMa must run on CPU.',
      path: ['device_class'],
    },
  );

export const renderSegmentSchema = z
  .object({
    beat_index: z.number().int().min(0),
    beat_id: z.uuid(),
    mode: z.enum(['fill', 'passthrough']),
    status: z.enum(['pending', 'running', 'done', 'failed', 'lost', 'cancelled']),
    attempt: z.number().int().min(0),
    fill_engine: fillEngineSchema.nullable(),
    compute_seconds: z.number().min(0),
    error: apiErrorSchema.nullable(),
  })
  .strict();

export const renderOutputSchema = z
  .object({
    url: z.url(),
    expires_at: z.iso.datetime(),
    bytes: z.number().int().min(0),
    duration_ms: z.number().int().min(1),
    width: z.number().int().min(1),
    height: z.number().int().min(1),
    fps: z.number(),
    has_audio: z.boolean(),
    sha256: z.string().nullable(),
  })
  .strict();

export const renderStateSchema = z
  .object({
    job_id: z.uuid(),
    kind: z.enum(['render', 'preview']),
    status: z.enum(['queued', 'running', 'assembling', 'ready', 'failed', 'cancelled']),
    stage: z.enum([
      'queued',
      'planning',
      'rendering',
      'assembling',
      'finalizing',
      'done',
    ]),
    progress: z.number().min(0).max(1),
    detection_revision: z.string(),
    selection_revision: z.string(),
    engine: fillEngineSchema,
    device_class: deviceClassSchema,
    beats_total: z.number().int().min(0),
    beats_fill: z.number().int().min(0),
    beats_passthrough: z.number().int().min(0),
    estimate_seconds: z.number().min(0),
    compute_seconds: z.number().min(0),
    segments: z.array(renderSegmentSchema),
    output: renderOutputSchema.nullable(),
    error: apiErrorSchema.nullable(),
    created_at: z.iso.datetime(),
    finished_at: z.iso.datetime().nullable(),
  })
  .strict();

export const downloadTicketSchema = z
  .object({
    url: z.url(),
    expires_at: z.iso.datetime(),
    filename: z.string(),
    bytes: z.number().int().min(0),
  })
  .strict();

// ------------------------------------------------------------------- billing

export const estimateSchema = z
  .object({
    render_hours: z.number().min(0),
    compute_seconds: z.number().min(0),
    beats_fill: z.number().int().min(0),
    beats_passthrough: z.number().int().min(0),
    beats_total: z.number().int().min(0),
    engine: fillEngineSchema,
    device_class: deviceClassSchema,
    rate_table_version: z.string(),
    is_estimate: z.literal(true),
  })
  .strict();

export const ledgerRowSchema = z
  .object({
    id: z.uuid(),
    kind: z.enum(['detect', 'preview', 'render']),
    device_class: deviceClassSchema,
    compute_seconds: z.number().min(0),
    weight: z.number().min(0),
    render_hours: z.number().min(0),
    job_id: z.uuid().nullable(),
    stripe_meter_status: z.enum(['pending', 'sent', 'failed', 'skipped']),
    created_at: z.iso.datetime(),
  })
  .strict();

export const usageSchema = z
  .object({
    balance_render_hours: z.number(),
    used_render_hours_this_period: z.number().min(0),
    included_render_hours: z.number().min(0),
    storage_bytes_used: z.number().int().min(0),
    period_start: z.iso.datetime(),
    ledger: z.array(ledgerRowSchema),
    next_cursor: z.string().nullable(),
  })
  .strict();

// ------------------------------------------------------------------- workers

export const workerCallbackSchema = z
  .object({
    job_id: z.uuid(),
    seq: z.number().int().min(1),
    kind: z.enum(['probe', 'dissect', 'detect', 'render', 'preview']),
    status: z.enum(['running', 'succeeded', 'failed', 'cancelled']),
    stage: z.string().nullable(),
    progress: z.number().min(0).max(1),
    stage_detail: z.string().max(200).nullable(),
    compute_seconds: z.number().min(0),
    device_class: deviceClassSchema,
    model_versions: z.record(z.string(), z.string()),
    input_bytes: z.number().int().min(0),
    output_bytes: z.number().int().min(0),
    beats_done: z.number().int().min(0).optional(),
    beats_total: z.number().int().min(0).optional(),
    frames_read: z.number().int().min(0).optional(),
    error: z
      .object({
        code: z.string(),
        message: z.string(),
        retryable: z.boolean().optional(),
      })
      .strict()
      .nullable(),
  })
  .strict();

// ---------------------------------------------------------------------- misc

export const healthSchema = z
  .object({
    status: z.enum(['ok', 'degraded']),
    version: z.string(),
    request_id: z.string(),
    time: z.iso.datetime(),
    checks: z
      .object({
        db: z
          .object({ ok: z.boolean(), latency_ms: z.number().int().min(0).optional() })
          .strict(),
        r2: z.object({ ok: z.boolean() }).strict(),
        cpu_worker: z.object({ ok: z.boolean() }).strict(),
        gpu_worker: z.object({ ok: z.boolean() }).strict(),
      })
      .strict(),
  })
  .strict();

export const meSchema = z
  .object({
    id: z.uuid(),
    email: z.email().nullable(),
    display_name: z.string().nullable(),
    avatar_url: z.url().nullable(),
    plan: z.enum(['free', 'pro', 'studio']),
    render_seconds_balance: z.number().min(0),
    storage_bytes_used: z.number().int().min(0),
    storage_bytes_limit: z.number().int().min(0),
    monthly_render_hours: z.number().min(0),
  })
  .strict();
