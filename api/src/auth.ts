import {
  createLocalJWKSet,
  createRemoteJWKSet,
  customFetch,
  jwtVerify,
  type JWTVerifyGetKey,
  type JWTPayload,
} from 'jose';
import { ApiError } from './errors';

/** The only thing taken from a verified token. */
export interface Identity {
  subject: string;
  email: string | null;
  displayName: string | null;
  avatarUrl: string | null;
}

export interface AuthOptions {
  issuer: string;
  audience: string;
  jwksUrl: string;
  /** Development only: a JWKS document, so local runs verify a real signature. */
  jwksJson?: string | undefined;
  allowedOrigins: readonly string[];
  fetcher?: typeof fetch;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * One cached key set per Worker isolate. `createRemoteJWKSet` caches keys,
 * coalesces concurrent fetches and refetches on an unknown `kid`, so a Clerk key
 * rotation does not require a deploy.
 */
const keySets = new Map<string, JWTVerifyGetKey>();

export function keySetFor(options: AuthOptions): JWTVerifyGetKey {
  if (options.jwksJson) {
    return createLocalJWKSet(
      JSON.parse(options.jwksJson) as unknown as Parameters<typeof createLocalJWKSet>[0],
    );
  }
  const cached = keySets.get(options.jwksUrl);
  if (cached) return cached;
  const keySet = createRemoteJWKSet(new URL(options.jwksUrl), {
    cacheMaxAge: 10 * 60 * 1000,
    cooldownDuration: 30 * 1000,
    timeoutDuration: 4_000,
    ...(options.fetcher ? { [customFetch]: options.fetcher } : {}),
  });
  keySets.set(options.jwksUrl, keySet);
  return keySet;
}

function claim(payload: JWTPayload, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' && value.length > 0 ? value : null;
}

export function identityFromPayload(payload: JWTPayload): Identity {
  const subject = payload.sub;
  if (typeof subject !== 'string' || subject.length === 0) {
    throw new ApiError('unauthorized', 'The session token has no subject.', {
      detail: { reason: 'missing_subject' },
    });
  }
  return {
    subject,
    email: claim(payload, 'email'),
    displayName: claim(payload, 'name') ?? claim(payload, 'full_name'),
    avatarUrl: claim(payload, 'image_url') ?? claim(payload, 'picture'),
  };
}

export type Verifier = (request: Request) => Promise<Identity>;

export function createVerifier(options: AuthOptions): Verifier {
  const keys = keySetFor(options);
  return async (request) => {
    const header = request.headers.get('authorization');
    if (!header?.startsWith('Bearer ')) {
      throw new ApiError('unauthorized', 'Sign in to continue.', {
        detail: { reason: 'missing_token' },
      });
    }
    const token = header.slice('Bearer '.length).trim();
    if (token.length === 0) {
      throw new ApiError('unauthorized', 'Sign in to continue.', {
        detail: { reason: 'missing_token' },
      });
    }

    let payload: JWTPayload;
    try {
      ({ payload } = await jwtVerify(token, keys, {
        issuer: options.issuer,
        audience: options.audience,
        algorithms: ['RS256'],
        clockTolerance: 5,
        requiredClaims: ['sub', 'exp', 'iat'],
      }));
    } catch (error) {
      const expired =
        error instanceof Error &&
        (error.name === 'JWTExpired' || /exp/i.test(error.message));
      throw new ApiError(
        'unauthorized',
        expired ? 'Your session expired.' : 'Sign in again.',
        {
          detail: { reason: expired ? 'expired' : 'invalid_token' },
        },
      );
    }

    // Clerk sets `azp` to the origin that obtained the token. When an allowlist
    // exists, a token minted for another origin is not accepted.
    if (options.allowedOrigins.length > 0 && typeof payload.azp === 'string') {
      if (!options.allowedOrigins.includes(payload.azp)) {
        throw new ApiError('unauthorized', 'Sign in again.', {
          detail: { reason: 'wrong_origin' },
        });
      }
    }

    return identityFromPayload(payload);
  };
}

export function authOptionsFromEnv(
  env: {
    CLERK_ISSUER: string;
    CLERK_AUDIENCE: string;
    CLERK_JWKS_URL?: string | undefined;
    AUTH_JWKS_JSON?: string | undefined;
    ALLOWED_ORIGINS: string;
    APP_ENV: string;
  },
  fetcher: typeof fetch = fetch,
): AuthOptions {
  const issuer = env.CLERK_ISSUER.replace(/\/+$/, '');
  // A dev JWKS document is honoured only outside production.
  const jwksJson = env.APP_ENV === 'development' ? env.AUTH_JWKS_JSON : undefined;
  return {
    issuer,
    audience: env.CLERK_AUDIENCE,
    jwksUrl: env.CLERK_JWKS_URL ?? `${issuer}/.well-known/jwks.json`,
    jwksJson,
    allowedOrigins: env.ALLOWED_ORIGINS.split(',')
      .map((origin) => origin.trim())
      .filter(Boolean),
    fetcher,
  };
}

export function isJwksDocument(value: unknown): value is { keys: unknown[] } {
  return isRecord(value) && Array.isArray(value.keys);
}
