import type {
  ApiErrorBody,
  ApiErrorEnvelope,
  DetectionView,
  LibraryDetail,
  LibraryPage,
  Me,
  PlayTicket,
  UploadTicket,
} from './types';

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/+$/, '');

export class ApiError extends Error {
  readonly code: string;
  readonly action: ApiErrorBody['action'];
  readonly status: number;
  readonly detail: Record<string, unknown>;
  readonly retryable: boolean;

  constructor(body: ApiErrorBody, status: number) {
    super(body.message);
    this.name = 'ApiError';
    this.code = body.code;
    this.action = body.action;
    this.status = status;
    this.detail = body.detail;
    this.retryable = body.retryable;
  }
}

function isEnvelope(value: unknown): value is ApiErrorEnvelope {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as { error?: unknown }).error === 'object'
  );
}

type TokenSource = () => Promise<string | null>;

export class Api {
  constructor(private readonly token: TokenSource) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await this.token();
    if (!token) {
      throw new ApiError(
        {
          code: 'unauthorized',
          message: 'Sign in to continue.',
          detail: {},
          retryable: false,
          action: 'sign_in',
        },
        401,
      );
    }
    const headers = new Headers(init.headers);
    headers.set('authorization', `Bearer ${token}`);
    if (init.body && !headers.has('content-type')) {
      headers.set('content-type', 'application/json');
    }

    const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
    if (response.status === 204) return undefined as T;

    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      if (isEnvelope(body)) throw new ApiError(body.error, response.status);
      throw new ApiError(
        {
          code: 'internal',
          message: `Request failed (${response.status}).`,
          detail: {},
          retryable: response.status >= 500,
          action: 'retry',
        },
        response.status,
      );
    }
    return body as T;
  }

  me(): Promise<Me> {
    return this.request<Me>('/me');
  }

  library(cursor?: string): Promise<LibraryPage> {
    const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : '';
    return this.request<LibraryPage>(`/library${query}`);
  }

  item(id: string): Promise<LibraryDetail> {
    return this.request<LibraryDetail>(`/library/${encodeURIComponent(id)}`);
  }

  detection(id: string): Promise<DetectionView> {
    return this.request<DetectionView>(`/library/${encodeURIComponent(id)}/detect`);
  }

  startDetection(id: string): Promise<DetectionView> {
    return this.request<DetectionView>(`/library/${encodeURIComponent(id)}/detect`, {
      method: 'POST',
      body: JSON.stringify({ text: true, logos: true }),
    });
  }

  play(id: string): Promise<PlayTicket> {
    return this.request<PlayTicket>(`/library/${encodeURIComponent(id)}/play`);
  }

  createUpload(input: {
    filename: string;
    content_type: string;
    bytes: number;
    title?: string;
  }): Promise<UploadTicket> {
    return this.request<UploadTicket>('/uploads', {
      method: 'POST',
      body: JSON.stringify(input),
    });
  }

  signUpload(uploadId: string): Promise<UploadTicket> {
    return this.request<UploadTicket>(`/uploads/${encodeURIComponent(uploadId)}/sign`, {
      method: 'POST',
    });
  }

  completeUpload(uploadId: string, bytes: number): Promise<unknown> {
    return this.request(`/uploads/${encodeURIComponent(uploadId)}/complete`, {
      method: 'POST',
      body: JSON.stringify({ bytes }),
    });
  }
}

export interface UploadProgress {
  loaded: number;
  total: number;
}

/**
 * Browser-to-R2 PUT with real byte progress. The API never sees these bytes,
 * and the only progress shown is `loaded / total` reported by the browser.
 */
export function putToStorage(
  ticket: UploadTicket,
  file: File,
  onProgress: (progress: UploadProgress) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(ticket.method, ticket.url, true);
    for (const [name, value] of Object.entries(ticket.headers)) {
      request.setRequestHeader(name, value);
    }
    request.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress({ loaded: event.loaded, total: event.total });
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        resolve();
      } else {
        reject(
          new Error(
            request.status === 0
              ? 'Upload blocked by the storage origin.'
              : `Storage rejected the upload (${request.status}).`,
          ),
        );
      }
    };
    request.onerror = () => reject(new Error('Upload failed before it reached storage.'));
    request.onabort = () => reject(new DOMException('Upload cancelled.', 'AbortError'));
    signal?.addEventListener('abort', () => request.abort(), { once: true });
    request.send(file);
  });
}

export function contentTypeFor(file: File): string | null {
  const allowed = ['video/mp4', 'video/quicktime', 'video/webm', 'video/x-matroska'];
  if (allowed.includes(file.type)) return file.type;
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (extension === 'mp4') return 'video/mp4';
  if (extension === 'mov') return 'video/quicktime';
  if (extension === 'webm') return 'video/webm';
  if (extension === 'mkv') return 'video/x-matroska';
  return null;
}
