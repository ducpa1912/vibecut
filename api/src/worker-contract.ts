import { z } from 'zod';

/**
 * The worker is the only producer of probe and proxy facts. These schemas are
 * the API side of `worker/duckclean_worker/contract.py`: a worker that changes
 * its answer without changing the contract fails here, at the boundary, instead
 * of writing a half-understood row.
 */

const usageSchema = z.object({
  compute_seconds: z.number().min(0),
  device_class: z.enum(['cpu', 'gpu_standard', 'gpu_premium']),
  model_versions: z.record(z.string(), z.string()).default({}),
  input_bytes: z.number().int().min(0).default(0),
  output_bytes: z.number().int().min(0).default(0),
});

export const probeResponseSchema = z.object({
  job_id: z.uuid(),
  status: z.literal('succeeded'),
  probe: z.object({
    duration_ms: z.number().int().positive(),
    display_width: z.number().int().positive(),
    display_height: z.number().int().positive(),
    coded_width: z.number().int().positive().nullable().optional(),
    coded_height: z.number().int().positive().nullable().optional(),
    rotation: z.union([z.literal(0), z.literal(90), z.literal(180), z.literal(270)]),
    fps_num: z.number().int().positive(),
    fps_den: z.number().int().positive(),
    frame_count: z.number().int().positive(),
    video_codec: z.string().min(1),
    pixel_format: z.string().min(1),
    audio_codec: z.string().nullable().optional(),
    has_audio: z.boolean(),
    bit_rate: z.number().int().nullable().optional(),
  }),
  usage: usageSchema,
});

export const proxyResponseSchema = z.object({
  job_id: z.uuid(),
  status: z.literal('succeeded'),
  proxy: z.object({
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    duration_ms: z.number().int().positive(),
    fps_num: z.number().int().positive(),
    fps_den: z.number().int().positive(),
    bytes: z.number().int().nonnegative(),
  }),
  poster: z.object({
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    bytes: z.number().int().nonnegative(),
    frame_index: z.number().int().nonnegative().nullable().optional(),
  }),
  usage: usageSchema,
});

export const dissectResponseSchema = z.object({
  job_id: z.uuid(),
  status: z.literal('succeeded'),
  beats: z
    .array(
      z.object({
        index: z.number().int().min(0),
        start_frame: z.number().int().min(0),
        end_frame: z.number().int().min(1),
        boundary: z.enum(['start', 'scene', 'cap', 'end']),
      }),
    )
    .min(1),
  // The worker is the only party that reads the bytes, so it reports the digest
  // the API hashes into the frozen manifest.
  source_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  usage: usageSchema,
});

const maskSchema = z.object({
  mask_id: z.uuid(),
  r2_key: z.string(),
  kind: z.enum(['glyph', 'region', 'feather']).default('glyph'),
  format: z.enum(['png', 'webp']),
  frame_start: z.number().int().min(0),
  frame_end: z.number().int().min(0),
  provenance: z.enum(['ocr', 'logo', 'user_box', 'manual']),
  model_version: z.string().min(1),
  bytes: z.number().int().min(0).default(0),
  // Inline until the contract has a presigned PUT for masks; the API uploads it.
  png_base64: z.string().nullable().optional(),
});

const frameRangeSchema = z.object({
  beat_id: z.uuid(),
  beat_index: z.number().int().min(0),
  start_frame: z.number().int().min(0),
  end_frame: z.number().int().min(1),
});

export const detectResponseSchema = z.object({
  job_id: z.uuid(),
  status: z.literal('succeeded'),
  revision: z.string().min(1),
  groups: z.array(
    z.object({
      group_id: z.uuid(),
      kind: z.enum(['text', 'logo', 'watermark', 'image', 'user_box']),
      lane: z.number().int().min(0),
      order_index: z.number().int().min(0),
      sample_text: z.string().nullable(),
      box: z.object({
        x: z.number().int().min(0),
        y: z.number().int().min(0),
        w: z.number().int().min(1),
        h: z.number().int().min(1),
      }),
      confidence_milli: z.number().int().min(0).max(1000),
      included_default: z.boolean(),
      low_confidence: z.boolean(),
      members: z
        .array(
          z.object({
            member_id: z.uuid(),
            order_index: z.number().int().min(0),
            text: z.string().nullable(),
            range_mode: z.enum(['ranges', 'whole_source']),
            ranges: z.array(frameRangeSchema),
            box: z.object({
              x: z.number().int().min(0),
              y: z.number().int().min(0),
              w: z.number().int().min(1),
              h: z.number().int().min(1),
            }),
            confidence_milli: z.number().int().min(0).max(1000),
            provenance: z.enum(['ocr', 'logo', 'user_box', 'manual']),
            mask: maskSchema.nullable().optional(),
            included_default: z.boolean(),
            low_confidence: z.boolean(),
          }),
        )
        .min(1),
    }),
  ),
  coverage: z.object({
    frames_total: z.number().int().min(0),
    frames_read: z.number().int().min(0),
    frames_skipped: z.number().int().min(0),
    effective_fps_milli: z.number().int().min(0),
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
  }),
  usage: usageSchema,
});

export type ProbeResponse = z.infer<typeof probeResponseSchema>;
export type ProxyResponse = z.infer<typeof proxyResponseSchema>;
export type DissectResponse = z.infer<typeof dissectResponseSchema>;
export type DetectResponse = z.infer<typeof detectResponseSchema>;
