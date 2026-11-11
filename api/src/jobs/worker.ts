import type { DispatchRuntime } from './types';

/** A dispatch failure the caller may retry, with the code the UI shows. */
export class DispatchError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = 'DispatchError';
  }
}

const encoder = new TextEncoder();

async function hmacHex(
  secret: string,
  body: string,
): Promise<{ signature: string; timestamp: number }> {
  const timestamp = Math.floor(Date.now() / 1000);
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const prefix = encoder.encode(`${timestamp}.`);
  const payload = encoder.encode(body);
  const bytes = new Uint8Array(prefix.length + payload.length);
  bytes.set(prefix);
  bytes.set(payload, prefix.length);
  const digest = await crypto.subtle.sign('HMAC', key, bytes);
  const hex = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
  return { signature: hex, timestamp };
}

/** Signed POST to the worker fleet. The body is the exact bytes that were signed. */
export async function callWorker(
  runtime: DispatchRuntime,
  path: string,
  body: unknown,
): Promise<unknown> {
  if (!runtime.cpuWorkerUrl) {
    throw new DispatchError('worker_unavailable', 'No worker is configured.', true);
  }
  const raw = JSON.stringify(body);
  const { signature, timestamp } = await hmacHex(runtime.secret, raw);
  let response: Response;
  try {
    response = await runtime.fetcher(
      `${runtime.cpuWorkerUrl.replace(/\/+$/, '')}${path}`,
      {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'X-DuckClean-Signature': `t=${timestamp},v1=${signature}`,
          'X-DuckClean-Key-Id': runtime.keyId,
        },
        body: raw,
        signal: AbortSignal.timeout(240_000),
      },
    );
  } catch {
    throw new DispatchError('worker_unavailable', 'The worker did not answer.', true);
  }

  const text = await response.text();
  if (!response.ok) {
    const retryable = response.status >= 500 || response.status === 429;
    const code =
      response.status === 401 || response.status === 403
        ? 'invalid_signature'
        : response.status >= 500
          ? 'worker_unavailable'
          : 'payload_invalid';
    throw new DispatchError(
      code,
      text.slice(0, 300) || `worker status ${response.status}`,
      retryable,
    );
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new DispatchError(
      'worker_unavailable',
      'The worker returned invalid JSON.',
      true,
    );
  }
}

export function decodeBase64(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function sourceUrl(expiresAt: string, url: string) {
  return { url, method: 'GET' as const, headers: {}, expires_at: expiresAt };
}

const SOURCE_TTL_SECONDS = 15 * 60;

/** Every worker call reads the source through one short-lived signed GET. */
export async function sourceInput(runtime: DispatchRuntime, r2Key: string) {
  const ticket = await runtime.signer.presignGet(r2Key, SOURCE_TTL_SECONDS);
  return sourceUrl(ticket.expiresAt, ticket.url);
}
