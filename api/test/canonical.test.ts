import { describe, expect, it } from 'vitest';
import {
  CanonicalJsonError,
  beatManifestHash,
  canonicalJson,
  detectionRevision,
  normaliseRanges,
  selectionRevision,
  type BeatManifestPlan,
  type SelectionPlan,
} from '../src/canonical';

const UUID_A = '11111111-1111-4111-8111-111111111111';
const UUID_B = '22222222-2222-4222-8222-222222222222';
const UUID_C = '33333333-3333-4333-8333-333333333333';

describe('canonicalJson', () => {
  it('sorts keys at every depth and drops no data', () => {
    expect(canonicalJson({ b: 1, a: [{ d: true, c: null }] })).toBe(
      '{"a":[{"c":null,"d":true}],"b":1}',
    );
  });

  it('rejects floats so times cannot drift through rounding', () => {
    expect(() => canonicalJson({ start_s: 1.5 })).toThrow(CanonicalJsonError);
    expect(() => canonicalJson({ start_ms: 1500 })).not.toThrow();
  });

  it('rejects undefined, NaN, Infinity and non-plain objects', () => {
    expect(() => canonicalJson({ a: undefined })).toThrow(/undefined/);
    expect(() => canonicalJson(Number.NaN)).toThrow(CanonicalJsonError);
    expect(() => canonicalJson(Number.POSITIVE_INFINITY)).toThrow(CanonicalJsonError);
    expect(() => canonicalJson(new Date())).toThrow(/plain objects/);
  });
});

describe('beatManifestHash', () => {
  const plan: BeatManifestPlan = {
    source: {
      sha256: 'a'.repeat(64),
      bytes: 13_810_783,
      frame_count: 120,
      width: 1440,
      height: 2560,
    },
    params: {
      fps_num: 30,
      fps_den: 1,
      max_seconds_milli: 4000,
      min_seconds_milli: 1000,
      scene_threshold_milli: 300,
    },
    beats: [
      { index: 0, start_frame: 0, end_frame: 60, boundary: 'start' },
      { index: 1, start_frame: 60, end_frame: 120, boundary: 'end' },
    ],
  };

  it('is deterministic', async () => {
    const first = await beatManifestHash(plan);
    const second = await beatManifestHash(structuredClone(plan));
    expect(first).toBe(second);
    expect(first).toMatch(/^[a-f0-9]{64}$/);
  });

  it('changes when the source or params change', async () => {
    const changedParams = await beatManifestHash({
      ...plan,
      params: { ...plan.params, max_seconds_milli: 3000 },
    });
    expect(changedParams).not.toBe(await beatManifestHash(plan));
  });

  it('rejects a manifest with gaps, empty beats or the wrong frame count', async () => {
    await expect(
      beatManifestHash({
        ...plan,
        beats: [
          { index: 0, start_frame: 0, end_frame: 60, boundary: 'start' },
          { index: 1, start_frame: 61, end_frame: 120, boundary: 'end' },
        ],
      }),
    ).rejects.toThrow(/starts at frame 61/);

    await expect(
      beatManifestHash({
        ...plan,
        beats: [{ index: 0, start_frame: 0, end_frame: 60, boundary: 'start' }],
      }),
    ).rejects.toThrow(/beats end at frame 60/);
  });
});

describe('normaliseRanges', () => {
  it('merges overlaps and touching ranges inside one beat', () => {
    expect(
      normaliseRanges([
        { beat_index: 0, start_frame: 30, end_frame: 50 },
        { beat_index: 0, start_frame: 10, end_frame: 30 },
        { beat_index: 1, start_frame: 0, end_frame: 5 },
      ]),
    ).toEqual([
      { beat_index: 0, start_frame: 10, end_frame: 50 },
      { beat_index: 1, start_frame: 0, end_frame: 5 },
    ]);
  });

  it('drops empty ranges', () => {
    expect(normaliseRanges([{ beat_index: 0, start_frame: 10, end_frame: 10 }])).toEqual(
      [],
    );
  });
});

function selectionPlan(): SelectionPlan {
  return {
    detection_revision: 'rev-1',
    groups: [
      {
        group_id: UUID_A,
        engine: 'lama',
        device_class: 'gpu_standard',
        members: [
          {
            member_id: UUID_B,
            range_mode: 'ranges',
            ranges: [
              { beat_index: 1, start_frame: 30, end_frame: 45 },
              { beat_index: 0, start_frame: 0, end_frame: 15 },
            ],
          },
          { member_id: UUID_C, range_mode: 'whole_source', ranges: [] },
        ],
      },
    ],
    manual_regions: [],
    render: {
      kind: 'render',
      codec: 'h264',
      pixel_format: 'yuv420p',
      crf: 18,
      preset: 'medium',
      width: 1440,
      height: 2560,
      fps: 'source',
      audio: 'source',
      resolution_scale_milli: 1000,
      time_limit_s: null,
    },
  };
}

describe('selectionRevision', () => {
  it('is independent of group, member and range order', async () => {
    const plan = selectionPlan();
    const shuffled = selectionPlan();
    shuffled.groups[0]?.members.reverse();
    shuffled.groups[0]?.members[0]?.ranges.reverse();

    expect(await selectionRevision(shuffled)).toBe(await selectionRevision(plan));
  });

  it('ignores members that contribute no frames', async () => {
    const plan = selectionPlan();
    const withEmptyMember = selectionPlan();
    withEmptyMember.groups[0]?.members.push({
      member_id: '44444444-4444-4444-8444-444444444444',
      range_mode: 'ranges',
      ranges: [{ beat_index: 0, start_frame: 5, end_frame: 5 }],
    });

    expect(await selectionRevision(withEmptyMember)).toBe(await selectionRevision(plan));
  });

  it('changes with the engine, a removed member or a different detection revision', async () => {
    const base = await selectionRevision(selectionPlan());

    const otherEngine = selectionPlan();
    otherEngine.groups[0]!.engine = 'propainter';
    expect(await selectionRevision(otherEngine)).not.toBe(base);

    const fewerMembers = selectionPlan();
    fewerMembers.groups[0]!.members.pop();
    expect(await selectionRevision(fewerMembers)).not.toBe(base);

    const otherRevision = selectionPlan();
    otherRevision.detection_revision = 'rev-2';
    expect(await selectionRevision(otherRevision)).not.toBe(base);
  });

  it('changes when a preview is asked for instead of a render', async () => {
    const preview = selectionPlan();
    preview.render = {
      ...preview.render,
      kind: 'preview',
      crf: 28,
      resolution_scale_milli: 500,
    };
    expect(await selectionRevision(preview)).not.toBe(
      await selectionRevision(selectionPlan()),
    );
  });
});

describe('detectionRevision', () => {
  it('changes when a model version changes', async () => {
    const plan = {
      source_sha256: 'f'.repeat(64),
      beat_manifest_hash: 'b'.repeat(64),
      detect: {
        text: true,
        logos: true,
        tile_small_text: true,
        frame_policy: 'every_frame' as const,
        max_width: 1920,
        min_confidence_milli: 350,
        regions: [],
        scope_beat_indexes: null,
      },
      engine: {
        ocr: 'paddleocr' as const,
        logo: 'grounding_dino' as const,
        segmentation: 'sam2' as const,
      },
      models: { ocr: 'ppocrv5-2026.1' },
    };

    const first = await detectionRevision(plan);
    expect(first).toMatch(/^[a-f0-9]{64}$/);
    expect(
      await detectionRevision({ ...plan, models: { ocr: 'ppocrv5-2026.2' } }),
    ).not.toBe(first);
  });
});
