import type { Hono } from 'hono';
import type { LibraryRow } from '../db';
import { ApiError } from '../errors';
import { PLAY_TTL_SECONDS } from '../limits';
import { libraryStatusSchema } from '../schemas';
import { detectionWire, probeWire, toWireItem } from '../wire';
import { cursorFor, detectionFor, ownedItem, parseCursor, parseLimit } from './shared';
import type { AppEnv } from './shared';

export function registerLibraryRoutes(app: Hono<AppEnv>): void {
  app.get('/api/v1/library', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const limit = parseLimit(c.req.query('limit'));
    const statusRaw = c.req.query('status');
    const status = statusRaw ? libraryStatusSchema.parse(statusRaw) : undefined;
    const cursor = parseCursor(c.req.query('cursor'));

    const rows = await runtime.db.list(user.id, { limit, status, cursor });
    const page = rows.slice(0, limit);
    const items = await Promise.all(page.map((row) => toWireItem(row, runtime.signer)));
    return c.json({
      items,
      next_cursor:
        rows.length > limit ? cursorFor(page[page.length - 1] as LibraryRow) : null,
    });
  });

  app.get('/api/v1/library/:itemId', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const itemId = c.req.param('itemId');
    const row = await runtime.db.item(user.id, itemId);
    if (!row) throw new ApiError('not_found', 'Library item not found.');

    const [source, proxy, beats, beatRows] = await Promise.all([
      runtime.db.source(user.id, itemId),
      runtime.db.proxy(user.id, itemId),
      runtime.db.beatSummary(user.id, itemId),
      runtime.db.beats(user.id, itemId),
    ]);
    if (!source) throw new ApiError('not_found', 'Source not found.');

    const detectionState = await runtime.db.detectionState(user.id, itemId);
    const detection = await detectionWire(detectionState, runtime.signer);

    return c.json({
      ...(await toWireItem(row, runtime.signer)),
      source: {
        id: source.id,
        filename: source.filename,
        content_type: source.contentType,
        bytes: source.bytes,
        etag: source.etag,
        sha256: source.sha256,
        upload_status: source.uploadStatus,
        probe_status: source.probeStatus,
        dissect_status: source.dissectStatus,
        beat_manifest_hash: source.beatManifestHash,
      },
      proxy: proxy
        ? {
            id: proxy.id,
            width: proxy.width,
            height: proxy.height,
            duration_ms: proxy.durationMs,
            fps: proxy.fpsNum / proxy.fpsDen,
            bytes: proxy.bytes,
          }
        : null,
      probe: probeWire(source.probeJson),
      beats: {
        total: beats.total,
        with_target: beats.withTarget,
        manifest_hash: source.beatManifestHash,
        items: beatRows.map((beat) => ({
          beat_id: beat.id,
          index: beat.index,
          start_frame: beat.startFrame,
          end_frame: beat.endFrame,
          start_ms: beat.startMs,
          end_ms: beat.endMs,
          boundary: beat.boundary,
          status: beat.status,
          has_target: beat.hasTarget,
        })),
      },
      // Null until a run exists: an empty group list would claim a scan happened.
      detection:
        detection.run === null
          ? null
          : {
              run: detection.run,
              groups: detection.groups,
              beats: detection.beats,
              selection_counts: detection.selection_counts,
            },
      // Render is M4; null is the truth, not an empty state.
      render: null,
    });
  });

  app.delete('/api/v1/library/:itemId', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const deleted = await runtime.db.softDelete(user.id, c.req.param('itemId'));
    if (!deleted) throw new ApiError('not_found', 'Library item not found.');
    if (deleted.keys.length > 0) {
      try {
        await runtime.media.delete(deleted.keys);
      } catch (error) {
        // The row is already soft-deleted; a lifecycle sweep can retry the purge.
        console.error(
          JSON.stringify({
            level: 'error',
            message: 'media_purge_failed',
            request_id: c.get('requestId'),
            objects: deleted.keys.length,
            error: error instanceof Error ? error.message : String(error),
          }),
        );
      }
    }
    return c.body(null, 204);
  });

  app.get('/api/v1/library/:itemId/play', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const play = await runtime.db.play(user.id, c.req.param('itemId'));
    if (!play) {
      throw new ApiError('conflict', 'Playback is not ready yet.', {
        detail: { reason: 'proxy_missing' },
      });
    }
    const ticket = await runtime.signer.presignGet(play.r2Key, PLAY_TTL_SECONDS);
    return c.json({
      url: ticket.url,
      expires_at: ticket.expiresAt,
      duration_ms: play.durationMs,
      width: play.width,
      height: play.height,
    });
  });

  app.get('/api/v1/library/:itemId/detect', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const itemId = c.req.param('itemId');
    await ownedItem(runtime, user.id, itemId);
    return c.json(await detectionFor(runtime, user.id, itemId));
  });
}
