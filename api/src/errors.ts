import type { ApiErrorBody, ErrorAction, ErrorCode } from './schemas';

/**
 * One error envelope for every failure. Clients read `code` and `action`;
 * `detail` is structured and safe to log. Messages never contain OCR text,
 * filenames or signed URLs.
 */

const STATUS: Record<ErrorCode, number> = {
  unauthorized: 401,
  forbidden: 403,
  not_found: 404,
  validation: 400,
  conflict: 409,
  too_large: 413,
  unsupported_media: 415,
  quota: 402,
  rate_limited: 429,
  stale_detection: 409,
  worker_unavailable: 503,
  source_unreadable: 422,
  render_failed: 500,
  cancelled: 409,
  internal: 500,
};

const ACTION: Record<ErrorCode, ErrorAction> = {
  unauthorized: 'sign_in',
  forbidden: 'contact_support',
  not_found: 'none',
  validation: 'none',
  conflict: 'retry',
  too_large: 'upgrade_plan',
  unsupported_media: 'reupload',
  quota: 'upgrade_plan',
  rate_limited: 'retry',
  stale_detection: 'reload_detection',
  worker_unavailable: 'retry',
  source_unreadable: 'reupload',
  render_failed: 'retry',
  cancelled: 'retry',
  internal: 'retry',
};

const RETRYABLE = new Set<ErrorCode>(['rate_limited', 'worker_unavailable', 'internal']);

export interface ApiErrorOptions {
  detail?: Record<string, unknown>;
  retryable?: boolean;
  action?: ErrorAction;
}

export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly detail: Record<string, unknown>;
  readonly retryable: boolean;
  readonly action: ErrorAction;

  constructor(code: ErrorCode, message: string, options: ApiErrorOptions = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.detail = options.detail ?? {};
    this.retryable = options.retryable ?? RETRYABLE.has(code);
    this.action = options.action ?? ACTION[code];
  }

  get status(): number {
    return STATUS[this.code];
  }

  toBody(): ApiErrorBody {
    return {
      code: this.code,
      message: this.message,
      detail: this.detail,
      retryable: this.retryable,
      action: this.action,
    };
  }
}

/** Error payload for `c.json(...)` / `Response.json(...)`. */
export function errorEnvelope(
  code: ErrorCode,
  message: string,
  options: ApiErrorOptions = {},
): { error: ApiErrorBody } {
  return { error: new ApiError(code, message, options).toBody() };
}

export function httpStatusFor(code: ErrorCode): number {
  return STATUS[code];
}
