import type { Hono } from 'hono';
import { planFor } from '../limits';
import type { AppEnv } from './shared';

/** Liveness plus one check per dependency the request path needs. */
export function registerHealthRoutes(app: Hono<AppEnv>): void {
  app.get('/api/v1/health', async (c) => {
    const runtime = c.get('runtime');
    let dbOk = false;
    let dbLatency: number | undefined;
    try {
      dbLatency = await runtime.db.ping();
      dbOk = true;
    } catch {
      dbOk = false;
    }

    let r2Ok = false;
    let r2Reason: string | undefined;
    try {
      // A HEAD for a key that does not exist still proves the binding answers.
      await runtime.media.head('__duckclean_healthcheck__');
      r2Ok = true;
    } catch (error) {
      r2Ok = false;
      r2Reason = error instanceof Error ? error.message : String(error);
    }

    const ping = async (url: string): Promise<boolean> => {
      if (!url) return false;
      try {
        const response = await runtime.fetcher(`${url.replace(/\/+$/, '')}/health`, {
          signal: AbortSignal.timeout(1_500),
        });
        return response.ok;
      } catch {
        return false;
      }
    };
    const [cpuOk, gpuOk] = await Promise.all([
      ping(c.env.CPU_WORKER_URL),
      ping(c.env.GPU_WORKER_URL),
    ]);

    const status = dbOk && r2Ok && cpuOk && gpuOk ? 'ok' : 'degraded';
    return c.json({
      status,
      version: c.env.API_VERSION,
      request_id: c.get('requestId'),
      time: new Date().toISOString(),
      checks: {
        db: { ok: dbOk, ...(dbLatency === undefined ? {} : { latency_ms: dbLatency }) },
        r2: {
          ok: r2Ok,
          ...(r2Ok || c.env.APP_ENV === 'production' ? {} : { reason: r2Reason }),
        },
        cpu_worker: { ok: cpuOk },
        gpu_worker: { ok: gpuOk },
      },
    });
  });

  app.get('/api/v1/me', async (c) => {
    const user = c.get('user');
    const plan = planFor(user.plan);
    return c.json({
      id: user.id,
      email: user.email,
      display_name: user.displayName,
      avatar_url: user.avatarUrl,
      plan: user.plan,
      render_seconds_balance: user.renderSecondsBalance,
      storage_bytes_used: user.storageBytesUsed,
      storage_bytes_limit: plan.storage_bytes_limit,
      monthly_render_hours: plan.monthly_render_hours,
    });
  });
}
