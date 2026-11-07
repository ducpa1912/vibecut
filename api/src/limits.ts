/** Limits and plan constants. Contract values live in docs/duckclean/contract.md §10. */

export const MAX_UPLOAD_BYTES = 5_000_000_000;
export const MAX_DURATION_MS = 1_800_000;
export const MAX_DIMENSION_PX = 4_096;
export const MAX_FPS = 60;

export const UPLOAD_TTL_SECONDS = 15 * 60;
export const PLAY_TTL_SECONDS = 10 * 60;
export const POSTER_TTL_SECONDS = 10 * 60;
export const WORKER_INPUT_TTL_SECONDS = 15 * 60;
export const WORKER_OUTPUT_TTL_SECONDS = 60 * 60;

/** Extension comes from the accepted content type, never from the filename. */
export const CONTENT_TYPE_EXT = {
  'video/mp4': 'mp4',
  'video/quicktime': 'mov',
  'video/webm': 'webm',
  'video/x-matroska': 'mkv',
} as const;

export type AllowedContentType = keyof typeof CONTENT_TYPE_EXT;

/**
 * Provisional plan limits. Billing is M6; these numbers exist so `GET /me` and
 * the upload quota check are concrete, not invented per request. They are not
 * a price and no charge is made from them.
 */
export const PLANS = {
  free: { storage_bytes_limit: 25_000_000_000, monthly_render_hours: 1 },
  pro: { storage_bytes_limit: 250_000_000_000, monthly_render_hours: 20 },
  studio: { storage_bytes_limit: 1_000_000_000_000, monthly_render_hours: 100 },
} as const;

export type PlanId = keyof typeof PLANS;

export function planFor(plan: string): (typeof PLANS)[PlanId] {
  return plan === 'pro' || plan === 'studio' ? PLANS[plan] : PLANS.free;
}
