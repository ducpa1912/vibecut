import type { Hono } from 'hono';
import { ApiError } from '../errors';
import {
  CONTENT_TYPE_EXT,
  MAX_UPLOAD_BYTES,
  UPLOAD_TTL_SECONDS,
  planFor,
} from '../limits';
import { uploadCompleteRequestSchema, uploadCreateRequestSchema } from '../schemas';
import { keys, verifyUpload } from '../storage';
import { toWireItem } from '../wire';
import type { AppEnv } from './shared';

/** Presign, re-sign, then verify the browser's direct PUT. */
export function registerUploadRoutes(app: Hono<AppEnv>): void {
  app.post('/api/v1/uploads', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const body = uploadCreateRequestSchema.parse(await c.req.json());

    if (body.bytes > MAX_UPLOAD_BYTES) {
      throw new ApiError('too_large', 'Files are limited to 5 GB.', {
        detail: { max_bytes: MAX_UPLOAD_BYTES },
      });
    }
    const plan = planFor(user.plan);
    if (user.storageBytesUsed + body.bytes > plan.storage_bytes_limit) {
      throw new ApiError('quota', 'This upload would exceed your storage.', {
        detail: {
          storage_bytes_used: user.storageBytesUsed,
          storage_bytes_limit: plan.storage_bytes_limit,
        },
      });
    }

    const ext = CONTENT_TYPE_EXT[body.content_type];
    const itemId = crypto.randomUUID();
    const assetId = crypto.randomUUID();
    const key = keys.source(user.id, assetId, ext);
    const expiresAt = new Date(Date.now() + UPLOAD_TTL_SECONDS * 1000);
    const title = body.title ?? body.filename;

    await runtime.db.createUpload({
      userId: user.id,
      itemId,
      assetId,
      title: title.slice(0, 200),
      filename: body.filename,
      contentType: body.content_type,
      bytes: body.bytes,
      key,
      expiresAt,
    });

    const ticket = await runtime.signer.presignPut(
      key,
      UPLOAD_TTL_SECONDS,
      body.content_type,
    );
    return c.json(
      {
        upload_id: assetId,
        library_item_id: itemId,
        source_asset_id: assetId,
        method: 'PUT' as const,
        url: ticket.url,
        headers: { 'content-type': body.content_type },
        expires_at: ticket.expiresAt,
        max_bytes: body.bytes,
      },
      201,
    );
  });

  app.post('/api/v1/uploads/:uploadId/sign', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const assetId = c.req.param('uploadId');
    const expiresAt = new Date(Date.now() + UPLOAD_TTL_SECONDS * 1000);

    const target = await runtime.db.reSignUpload(user.id, assetId, expiresAt);
    if (!target) {
      const asset = await runtime.db.sourceByAsset(user.id, assetId);
      if (!asset) throw new ApiError('not_found', 'Upload not found.');
      throw new ApiError('conflict', 'This upload is already complete.', {
        detail: { upload_status: asset.uploadStatus },
      });
    }
    const ticket = await runtime.signer.presignPut(
      target.key,
      UPLOAD_TTL_SECONDS,
      target.contentType,
    );
    return c.json({
      upload_id: assetId,
      library_item_id: target.itemId,
      source_asset_id: assetId,
      method: 'PUT' as const,
      url: ticket.url,
      headers: { 'content-type': target.contentType },
      expires_at: ticket.expiresAt,
      max_bytes: target.bytes,
    });
  });

  app.post('/api/v1/uploads/:uploadId/complete', async (c) => {
    const user = c.get('user');
    const runtime = c.get('runtime');
    const assetId = c.req.param('uploadId');
    const body = uploadCompleteRequestSchema.parse(await c.req.json());

    const asset = await runtime.db.sourceByAsset(user.id, assetId);
    if (!asset) throw new ApiError('not_found', 'Upload not found.');

    if (body.bytes !== asset.bytes) {
      throw new ApiError('validation', 'The reported size does not match the ticket.', {
        detail: { declared_bytes: asset.bytes, reported_bytes: body.bytes },
      });
    }

    const verdict = await verifyUpload(runtime.media, asset.r2Key, {
      bytes: asset.bytes,
      etag: body.etag,
    });
    if (!verdict.ok) {
      await runtime.db.setItemError(
        user.id,
        asset.libraryItemId,
        'source_unreadable',
        verdict.reason,
        'upload_incomplete',
      );
      throw new ApiError(
        'source_unreadable',
        'The uploaded file is missing or incomplete.',
        {
          detail: { reason: verdict.reason },
        },
      );
    }

    const completed = await runtime.db.completeUpload(user.id, assetId, {
      bytes: verdict.size,
      etag: verdict.etag,
    });
    if (!completed) throw new ApiError('not_found', 'Upload not found.');

    let probeQueued = false;
    try {
      const workerJobId = crypto.randomUUID();
      const job = await runtime.db.createJob({
        userId: user.id,
        itemId: completed.itemId,
        assetId,
        kind: 'probe',
        deviceClass: 'cpu',
        idempotencyKey: `probe:${assetId}`,
        workerJobId,
        request: { source_key: asset.r2Key },
      });
      await runtime.enqueue({ job_id: job.id });
      probeQueued = true;
    } catch {
      // The bytes are safe; only dispatch failed. Say so instead of failing the upload.
      await runtime.db.setItemError(
        user.id,
        completed.itemId,
        'worker_unavailable',
        'dispatch_failed',
      );
    }

    const row = await runtime.db.item(user.id, completed.itemId);
    if (!row) throw new ApiError('not_found', 'Library item not found.');
    return c.json(
      { library_item: await toWireItem(row, runtime.signer), probe_queued: probeQueued },
      202,
    );
  });
}
