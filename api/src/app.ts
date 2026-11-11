import { Hono } from 'hono';
import { ZodError } from 'zod';
import { ApiError, errorEnvelope } from './errors';
import { registerDetectRoutes } from './routes/detect';
import { registerHealthRoutes } from './routes/health';
import { registerLibraryRoutes } from './routes/library';
import type { AppEnv } from './routes/shared';
import { registerUploadRoutes } from './routes/uploads';
import type { RuntimeFactory } from './runtime';

export type { AppEnv } from './routes/shared';

function requestIdFor(header: string | undefined): string {
  if (header && /^[A-Za-z0-9_-]{8,64}$/.test(header)) return header;
  return crypto.randomUUID();
}

function allowedOrigins(value: string): string[] {
  return value
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
}

export function createApp(runtimeFor: RuntimeFactory): Hono<AppEnv> {
  const app = new Hono<AppEnv>();

  app.use('*', async (c, next) => {
    const requestId = requestIdFor(c.req.header('x-request-id'));
    c.set('requestId', requestId);
    c.header('X-Request-Id', requestId);
    c.header('Cache-Control', 'no-store');
    c.header('X-Content-Type-Options', 'nosniff');

    const origin = c.req.header('origin');
    const origins = allowedOrigins(c.env.ALLOWED_ORIGINS);
    if (origin && origins.includes(origin)) {
      c.header('Access-Control-Allow-Origin', origin);
      c.header('Vary', 'Origin');
      c.header(
        'Access-Control-Allow-Headers',
        'authorization, content-type, x-request-id',
      );
      c.header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
      c.header('Access-Control-Max-Age', '600');
      c.header('Access-Control-Expose-Headers', 'x-request-id');
    }
    if (c.req.method === 'OPTIONS') return c.body(null, 204);
    await next();
  });

  app.use('/api/v1/*', async (c, next) => {
    c.set('runtime', runtimeFor(c.env));
    await next();
  });

  app.use('/api/v1/*', async (c, next) => {
    if (c.req.path === '/api/v1/health' || c.req.path.startsWith('/api/v1/webhooks/')) {
      await next();
      return;
    }
    const runtime = c.get('runtime');
    const identity = await runtime.verifier(c.req.raw);
    c.set('user', await runtime.db.ensureUser(identity));
    await next();
  });

  registerHealthRoutes(app);
  registerUploadRoutes(app);
  registerLibraryRoutes(app);
  registerDetectRoutes(app);

  app.notFound((c) => c.json(errorEnvelope('not_found', 'Route not found.'), 404));

  app.onError((error, c) => {
    if (error instanceof ApiError) {
      return c.json({ error: error.toBody() }, error.status as 400);
    }
    if (error instanceof ZodError) {
      return c.json(
        errorEnvelope('validation', 'The request is invalid.', {
          detail: {
            issues: error.issues.map((issue) => ({
              path: issue.path.join('.'),
              code: issue.code,
            })),
          },
        }),
        400,
      );
    }
    if (error instanceof SyntaxError) {
      return c.json(
        errorEnvelope('validation', 'The request body is not valid JSON.'),
        400,
      );
    }
    if (error instanceof Error && error.name === 'HTTPException') {
      return c.json(errorEnvelope('validation', 'The request is invalid.'), 400);
    }
    console.error(
      JSON.stringify({
        level: 'error',
        message: 'unhandled_api_error',
        request_id: c.get('requestId') ?? null,
        error: error instanceof Error ? error.message : String(error),
      }),
    );
    // Local development gets the reason; production never does.
    const detail =
      c.env.APP_ENV === 'production'
        ? {}
        : { reason: error instanceof Error ? error.message : String(error) };
    return c.json(errorEnvelope('internal', 'Unexpected server error.', { detail }), 500);
  });

  return app;
}
