import { describe, expect, it } from 'vitest';
import {
  detectRequestSchema,
  detectionMemberSchema,
  detectionStateSchema,
  deviceClassForEngine,
  errorEnvelopeSchema,
  renderRequestSchema,
  uploadTicketSchema,
} from '../src/schemas';

const BEAT = '11111111-1111-4111-8111-111111111111';
const MIRROR_GROUP = '22222222-2222-4222-8222-222222222222';
const MIRROR_MEMBER = '33333333-3333-4333-8333-333333333333';
const MASK = '44444444-4444-4444-8444-444444444444';
const RUN = '55555555-5555-4555-8555-555555555555';

const member = {
  id: MIRROR_MEMBER,
  text: 'HELLO',
  range_mode: 'ranges',
  ranges: [
    {
      beat_id: BEAT,
      beat_index: 0,
      start_frame: 10,
      end_frame: 40,
      start_ms: 333,
      end_ms: 1333,
    },
  ],
  box: { x: 120, y: 1600, w: 800, h: 90 },
  confidence: 0.94,
  provenance: 'ocr',
  mask: {
    id: MASK,
    kind: 'glyph',
    format: 'png',
    url: 'https://example.test/mask.png',
    expires_at: '2026-11-07T12:00:00.000Z',
    provenance: 'ocr',
    model_version: 'ppocrv5-2026.1',
  },
  included_default: true,
  low_confidence: false,
  fill_keys: [10, 11, 12],
};

const detectionState = {
  run: {
    id: RUN,
    revision: 'a'.repeat(64),
    status: 'succeeded',
    progress: 1,
    engine: 'paddleocr',
    model_versions: { ocr: 'ppocrv5-2026.1', logo: 'grounding-dino-1.0' },
    frames_read: 120,
    frames_skipped: 0,
    frames_total: 120,
    effective_fps: 30,
    coverage: 1,
    truncated: false,
    ocr_available: true,
    logo_model_available: true,
    warnings: [],
    compute_seconds: 41.2,
    device_class: 'cpu',
    error: null,
    started_at: '2026-11-07T10:00:00.000Z',
    finished_at: '2026-11-07T10:00:45.000Z',
  },
  groups: [
    {
      id: MIRROR_GROUP,
      kind: 'text',
      lane: 0,
      order_index: 0,
      sample_text: 'HELLO',
      box: { x: 120, y: 1600, w: 800, h: 90 },
      confidence: 0.94,
      member_count: 1,
      included_default: true,
      low_confidence: false,
      members: [member],
    },
  ],
  beats: [
    {
      beat_id: BEAT,
      index: 0,
      start_ms: 0,
      end_ms: 4000,
      status: 'ready',
      has_target: true,
    },
  ],
  selection_counts: { groups: 1, members: 1, beats_with_target: 1 },
};

describe('detection state', () => {
  it('accepts a real detection payload', () => {
    const parsed = detectionStateSchema.parse(detectionState);
    expect(parsed.groups[0]?.members[0]?.ranges).toHaveLength(1);
  });

  it('accepts a succeeded run with no groups as an empty result', () => {
    const empty = {
      ...detectionState,
      groups: [],
      beats: detectionState.beats.map((beat) => ({
        ...beat,
        has_target: false,
        status: 'empty',
      })),
      selection_counts: { groups: 0, members: 0, beats_with_target: 0 },
    };
    expect(detectionStateSchema.parse(empty).groups).toEqual([]);
  });

  it('rejects ranges mode with an empty range list', () => {
    expect(() => detectionMemberSchema.parse({ ...member, ranges: [] })).toThrow(
      /empty ranges never mean whole_source/,
    );
  });

  it('rejects a reversed or empty frame range', () => {
    expect(() =>
      detectionMemberSchema.parse({
        ...member,
        ranges: [{ ...member.ranges[0], start_frame: 40, end_frame: 40 }],
      }),
    ).toThrow(/non-empty/);
  });
});

describe('requests', () => {
  it('fills detection defaults without inventing targets', () => {
    const parsed = detectRequestSchema.parse({ text: true, logos: false });
    expect(parsed).toMatchObject({
      engine: 'auto',
      tile_small_text: true,
      max_width: 1920,
      regions: [],
    });
  });

  it('requires an explicit detection revision to render', () => {
    expect(() =>
      renderRequestSchema.parse({
        selection: { groups: [], manual_regions: [] },
      }),
    ).toThrow();
  });

  it('accepts a minimal render selection', () => {
    const parsed = renderRequestSchema.parse({
      detection_revision: 'a'.repeat(64),
      selection: {
        groups: [
          {
            group_id: MIRROR_GROUP,
            member_ids: [MIRROR_MEMBER],
            engine: null,
            overrides: [],
          },
        ],
        manual_regions: [],
      },
    });
    expect(parsed.selection.groups).toHaveLength(1);
  });

  it('forces LaMa to CPU and keeps GPU for video models', () => {
    expect(deviceClassForEngine('lama', 'gpu_standard')).toBe('cpu');
    expect(deviceClassForEngine('propainter', 'gpu_standard')).toBe('gpu_standard');
    expect(deviceClassForEngine('generative', 'gpu_premium')).toBe('gpu_premium');
    expect(() =>
      renderRequestSchema.parse({
        detection_revision: 'a'.repeat(64),
        selection: { groups: [], manual_regions: [] },
        engine: 'lama',
        device_class: 'gpu_standard',
      }),
    ).toThrow(/LaMa must run on CPU/);
  });

  it('rejects an override with empty ranges', () => {
    expect(() =>
      renderRequestSchema.parse({
        detection_revision: 'a'.repeat(64),
        selection: {
          groups: [
            {
              group_id: MIRROR_GROUP,
              member_ids: [MIRROR_MEMBER],
              engine: null,
              overrides: [{ member_id: MIRROR_MEMBER, range_mode: 'ranges', ranges: [] }],
            },
          ],
          manual_regions: [],
        },
      }),
    ).toThrow(/requires at least one range/);
  });

  it('validates upload tickets', () => {
    const ticket = {
      upload_id: BEAT,
      library_item_id: MIRROR_GROUP,
      source_asset_id: BEAT,
      method: 'PUT',
      url: 'https://account.r2.cloudflarestorage.com/bucket/key?X-Amz-Signature=abc',
      headers: { 'content-type': 'video/mp4' },
      expires_at: '2026-11-07T12:15:00.000Z',
      max_bytes: 5_000_000_000,
    };
    expect(uploadTicketSchema.parse(ticket).method).toBe('PUT');
  });
});

describe('error envelope', () => {
  it('accepts the documented shape', () => {
    const parsed = errorEnvelopeSchema.parse({
      error: {
        code: 'stale_detection',
        message: 'Detection changed. Review the new ranges.',
        detail: {},
        retryable: false,
        action: 'reload_detection',
      },
    });
    expect(parsed.error.code).toBe('stale_detection');
  });

  it('rejects unknown codes and missing retryability', () => {
    expect(() =>
      errorEnvelopeSchema.parse({
        error: {
          code: 'whoops',
          message: 'x',
          detail: {},
          retryable: false,
          action: 'none',
        },
      }),
    ).toThrow();
    expect(() =>
      errorEnvelopeSchema.parse({
        error: { code: 'not_found', message: 'x', detail: {}, action: 'none' },
      }),
    ).toThrow();
  });
});
