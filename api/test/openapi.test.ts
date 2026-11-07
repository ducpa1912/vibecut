import { readFileSync } from 'node:fs';
import { parse } from 'yaml';
import { describe, expect, it } from 'vitest';

/**
 * Structural checks on the normative contract. This is not a full OpenAPI
 * validator: it proves every reference resolves, every operation is named, the
 * documented surface matches HANDOFF, and the hard rules are expressed in the
 * schema itself.
 */

// Vitest runs with the api workspace as cwd.
const raw = readFileSync('openapi.yaml', 'utf8');
const spec = parse(raw) as Record<string, never>;
const pkg = JSON.parse(readFileSync('package.json', 'utf8')) as { version: string };

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

function walk(node: Json, visit: (value: Json, path: string) => void, path = '#'): void {
  visit(node, path);
  if (Array.isArray(node)) {
    node.forEach((item, index) => walk(item, visit, `${path}/${index}`));
  } else if (node && typeof node === 'object') {
    for (const [key, value] of Object.entries(node)) {
      walk(value, visit, `${path}/${key}`);
    }
  }
}

function resolvePointer(pointer: string): Json {
  const parts = pointer.replace(/^#\//, '').split('/');
  let node: Json = spec as unknown as Json;
  for (const part of parts) {
    if (node === null || typeof node !== 'object' || Array.isArray(node)) {
      throw new Error(`cannot resolve ${pointer}`);
    }
    node = node[part] as Json;
    if (node === undefined) throw new Error(`cannot resolve ${pointer}`);
  }
  return node;
}

const document = spec as unknown as Json;

describe('openapi.yaml', () => {
  it('is OpenAPI 3.1 and matches the package version', () => {
    expect((spec as unknown as { openapi: string }).openapi).toBe('3.1.0');
    expect((spec as unknown as { info: { version: string } }).info.version).toBe(
      pkg.version,
    );
  });

  it('resolves every $ref', () => {
    const missing: string[] = [];
    walk(document, (value, path) => {
      if (
        value &&
        typeof value === 'object' &&
        !Array.isArray(value) &&
        '$ref' in value
      ) {
        const ref = String((value as { $ref: string }).$ref);
        if (!ref.startsWith('#/')) {
          missing.push(`${path}: external ref ${ref}`);
          return;
        }
        try {
          resolvePointer(ref);
        } catch {
          missing.push(`${path}: ${ref}`);
        }
      }
    });
    expect(missing).toEqual([]);
  });

  it('names every operation uniquely and documents every HANDOFF route', () => {
    const paths = (spec as unknown as { paths: Record<string, Record<string, Json>> })
      .paths;
    const operationIds = new Set<string>();
    const found: string[] = [];

    for (const [route, item] of Object.entries(paths)) {
      for (const method of ['get', 'post', 'delete', 'put', 'patch']) {
        const operation = item[method];
        if (!operation) continue;
        const op = operation as {
          operationId?: string;
          responses?: Record<string, Json>;
        };
        expect(op.operationId, `${method.toUpperCase()} ${route}`).toBeTruthy();
        expect(operationIds.has(op.operationId ?? '')).toBe(false);
        operationIds.add(op.operationId ?? '');
        expect(op.responses, `${method.toUpperCase()} ${route}`).toBeTruthy();
        found.push(`${method.toUpperCase()} ${route}`);
      }
    }

    expect(found.sort()).toEqual(
      [
        'GET /health',
        'GET /me',
        'POST /uploads',
        'POST /uploads/{upload_id}/complete',
        'POST /uploads/{upload_id}/sign',
        'GET /library',
        'GET /library/{library_item_id}',
        'DELETE /library/{library_item_id}',
        'GET /library/{library_item_id}/play',
        'POST /library/{library_item_id}/detect',
        'GET /library/{library_item_id}/detect',
        'POST /library/{library_item_id}/detect/cancel',
        'POST /library/{library_item_id}/render',
        'GET /library/{library_item_id}/render',
        'POST /library/{library_item_id}/render/cancel',
        'POST /library/{library_item_id}/preview',
        'GET /previews/{preview_id}',
        'GET /library/{library_item_id}/download',
        'GET /billing/estimate',
        'GET /billing/usage',
        'POST /webhooks/stripe',
        'POST /webhooks/worker',
      ].sort(),
    );
  });

  it('requires auth everywhere except health and webhooks', () => {
    const paths = (spec as unknown as { paths: Record<string, Record<string, Json>> })
      .paths;
    for (const [route, item] of Object.entries(paths)) {
      for (const method of ['get', 'post', 'delete']) {
        const operation = item[method] as { security?: unknown[] } | undefined;
        if (!operation) continue;
        const isPublic = route === '/health' || route.startsWith('/webhooks/');
        if (isPublic) {
          expect(operation.security, `${route} should be public`).toEqual([]);
        } else {
          expect(operation.security, `${route} should require a session`).toBeUndefined();
        }
      }
    }
  });

  it('uses one error envelope for every failure path', () => {
    const paths = (spec as unknown as { paths: Record<string, Record<string, Json>> })
      .paths;
    for (const [route, item] of Object.entries(paths)) {
      for (const method of ['get', 'post', 'delete']) {
        const operation = item[method] as
          { responses?: Record<string, { $ref?: string }> } | undefined;
        if (!operation?.responses) continue;
        const fallback = operation.responses['default'];
        expect(fallback?.$ref, `${method.toUpperCase()} ${route}`).toBe(
          '#/components/responses/Error',
        );
      }
    }
  });

  it('encodes the range_mode hard rule', () => {
    const rangeMode = (
      spec as unknown as { components: { schemas: Record<string, Json> } }
    ).components.schemas.RangeMode as { enum: string[] };
    expect(rangeMode.enum).toEqual(['ranges', 'whole_source']);

    const group = (spec as unknown as { components: { schemas: Record<string, Json> } })
      .components.schemas.SelectionGroup as { required: string[] };
    expect(group.required).toContain('member_ids');
  });
});
