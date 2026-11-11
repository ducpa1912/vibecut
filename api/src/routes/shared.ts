import type { LibraryRow, UserRecord } from '../db';
import { ApiError } from '../errors';
import type { Runtime } from '../runtime';
import { detectionWire } from '../wire';
import type { Bindings } from '../bindings';

export type AppEnv = {
  Bindings: Bindings;
  Variables: {
    requestId: string;
    runtime: Runtime;
    user: UserRecord;
  };
};

/** Item routes start the same way: the row must exist and belong to this user. */
export async function ownedItem(runtime: Runtime, userId: string, itemId: string) {
  const item = await runtime.db.item(userId, itemId);
  if (!item) throw new ApiError('not_found', 'Library item not found.');
  return item;
}

/** The one detection envelope, so every route answers with the same shape. */
export async function detectionFor(runtime: Runtime, userId: string, itemId: string) {
  return detectionWire(await runtime.db.detectionState(userId, itemId), runtime.signer);
}

export function cursorFor(row: LibraryRow): string {
  return btoa(`${row.createdAt}|${row.id}`);
}

export function parseCursor(
  raw: string | undefined,
): { createdAt: string; id: string } | undefined {
  if (!raw) return undefined;
  try {
    const [createdAt, id] = atob(raw).split('|');
    if (
      createdAt &&
      id &&
      /^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(createdAt) &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) &&
      !Number.isNaN(Date.parse(createdAt))
    ) {
      return { createdAt: new Date(createdAt).toISOString(), id };
    }
  } catch {
    // fall through
  }
  throw new ApiError('validation', 'The cursor is invalid.');
}

export function parseLimit(raw: string | undefined): number {
  if (raw === undefined) return 25;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1 || value > 100) {
    throw new ApiError('validation', 'limit must be an integer between 1 and 100.');
  }
  return value;
}
