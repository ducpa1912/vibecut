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

export type ProbeResponse = z.infer<typeof probeResponseSchema>;
export type ProxyResponse = z.infer<typeof proxyResponseSchema>;
