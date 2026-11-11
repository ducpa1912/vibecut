import { ApiError } from './api';

/** Any thrown value becomes the error shape the banners already know how to show. */
export function asApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause;
  return new ApiError(
    {
      code: 'internal',
      message: cause instanceof Error ? cause.message : 'Something went wrong.',
      detail: {},
      retryable: true,
      action: 'retry',
    },
    0,
  );
}
