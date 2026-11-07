import type { Box, DeviceClass, FillEngine, RangeMode } from './schemas';

/**
 * Revision hashing (contract.md §Revisions).
 *
 * Every hash input is canonical JSON: objects with sorted keys, no whitespace,
 * UTF-8, and integer numbers only. Floats are rejected at runtime rather than
 * rounded, because a rounded time silently changes which frames a render
 * covers. Times are integer milliseconds or frame indices, never seconds.
 */

export const BEAT_MANIFEST_VERSION = 1;
export const DETECTION_PLAN_VERSION = 1;
export const SELECTION_PLAN_VERSION = 1;

export type CanonicalValue =
  string | number | boolean | null | CanonicalValue[] | { [key: string]: CanonicalValue };

export class CanonicalJsonError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CanonicalJsonError';
  }
}

export function canonicalJson(value: unknown): string {
  if (value === null) return 'null';

  switch (typeof value) {
    case 'boolean':
      return value ? 'true' : 'false';
    case 'number':
      if (!Number.isSafeInteger(value)) {
        throw new CanonicalJsonError(
          `canonical JSON accepts integers only, received ${String(value)}`,
        );
      }
      return JSON.stringify(value === 0 ? 0 : value);
    case 'string':
      return JSON.stringify(value);
    case 'object':
      break;
    default:
      throw new CanonicalJsonError(`canonical JSON cannot encode ${typeof value}`);
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(',')}]`;
  }

  const prototype = Object.getPrototypeOf(value) as object | null;
  if (prototype !== Object.prototype && prototype !== null) {
    throw new CanonicalJsonError('canonical JSON accepts plain objects only');
  }

  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  const parts: string[] = [];
  for (const key of keys) {
    const entry = record[key];
    if (entry === undefined) {
      throw new CanonicalJsonError(
        `canonical JSON cannot encode undefined (key "${key}")`,
      );
    }
    parts.push(`${JSON.stringify(key)}:${canonicalJson(entry)}`);
  }
  return `{${parts.join(',')}}`;
}

export async function sha256Hex(input: string): Promise<string> {
  const bytes = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export async function sha256OfCanonical(value: unknown): Promise<string> {
  return sha256Hex(canonicalJson(value));
}

// ------------------------------------------------------------ beat manifest

export type BeatBoundary = 'start' | 'scene' | 'cap' | 'end';

export interface BeatManifestPlan {
  source: {
    sha256: string;
    bytes: number;
    frame_count: number;
    width: number;
    height: number;
  };
  params: {
    fps_num: number;
    fps_den: number;
    max_seconds_milli: number;
    min_seconds_milli: number;
    scene_threshold_milli: number;
  };
  beats: Array<{
    index: number;
    start_frame: number;
    end_frame: number;
    boundary: BeatBoundary;
  }>;
}

/**
 * Deterministic: same source bytes, same frame count and same params produce
 * the same hash, so a re-dissect can prove it changed nothing.
 */
export async function beatManifestHash(plan: BeatManifestPlan): Promise<string> {
  assertManifestContiguous(plan);
  return sha256OfCanonical({ v: BEAT_MANIFEST_VERSION, ...plan });
}

export function assertManifestContiguous(plan: BeatManifestPlan): void {
  if (plan.beats.length === 0) {
    throw new CanonicalJsonError('beat manifest must contain at least one beat');
  }
  let expectedStart = 0;
  plan.beats.forEach((beat, position) => {
    if (beat.index !== position) {
      throw new CanonicalJsonError(
        `beat at position ${position} has index ${beat.index}`,
      );
    }
    if (beat.start_frame !== expectedStart) {
      throw new CanonicalJsonError(
        `beat ${beat.index} starts at frame ${beat.start_frame}, expected ${expectedStart}`,
      );
    }
    if (beat.end_frame <= beat.start_frame) {
      throw new CanonicalJsonError(`beat ${beat.index} is empty`);
    }
    expectedStart = beat.end_frame;
  });
  if (expectedStart !== plan.source.frame_count) {
    throw new CanonicalJsonError(
      `beats end at frame ${expectedStart}, source has ${plan.source.frame_count}`,
    );
  }
}

// ------------------------------------------------------- detection revision

export interface DetectionPlan {
  source_sha256: string;
  beat_manifest_hash: string;
  detect: {
    text: boolean;
    logos: boolean;
    tile_small_text: boolean;
    frame_policy: 'every_frame';
    max_width: number;
    min_confidence_milli: number;
    regions: Array<{ box: Box; prompt: string }>;
    scope_beat_indexes: number[] | null;
  };
  engine: {
    ocr: 'paddleocr' | 'rapidocr';
    logo: 'grounding_dino' | 'owlv2' | 'none';
    segmentation: 'sam2' | 'none';
  };
  models: Record<string, string>;
}

export async function detectionRevision(plan: DetectionPlan): Promise<string> {
  return sha256OfCanonical({
    v: DETECTION_PLAN_VERSION,
    source_sha256: plan.source_sha256,
    beat_manifest_hash: plan.beat_manifest_hash,
    detect: plan.detect,
    engine: plan.engine,
    models: plan.models,
  });
}

// -------------------------------------------------------- selection revision

export interface SelectionRange {
  beat_index: number;
  start_frame: number;
  end_frame: number;
}

export interface SelectionMemberPlan {
  member_id: string;
  range_mode: RangeMode;
  ranges: SelectionRange[];
}

export interface SelectionGroupPlan {
  group_id: string;
  engine: Exclude<FillEngine, 'auto'>;
  device_class: DeviceClass;
  members: SelectionMemberPlan[];
}

export interface SelectionRegionPlan {
  region_id: string;
  box: Box;
  range_mode: RangeMode;
  ranges: SelectionRange[];
  engine: Exclude<FillEngine, 'auto'>;
  device_class: DeviceClass;
}

export interface RenderParamsPlan {
  kind: 'render' | 'preview';
  codec: 'h264';
  pixel_format: 'yuv420p';
  crf: number;
  preset: string;
  width: number;
  height: number;
  fps: 'source';
  audio: 'source';
  resolution_scale_milli: number;
  time_limit_s: number | null;
}

export interface SelectionPlan {
  detection_revision: string;
  groups: SelectionGroupPlan[];
  manual_regions: SelectionRegionPlan[];
  render: RenderParamsPlan;
}

/**
 * Normalises before hashing so argument order can never change the revision:
 * groups and regions sort by id, members sort by id, ranges sort by
 * (beat_index, start_frame) and overlap-merge per beat, and anything that
 * contributes no frames is dropped.
 *
 * `whole_source` is kept as a marker and expanded against the beat manifest by
 * the render planner, not here.
 */
export async function selectionRevision(plan: SelectionPlan): Promise<string> {
  const groups = plan.groups
    .map((group) => ({
      group_id: group.group_id,
      engine: group.engine,
      device_class: group.device_class,
      members: group.members
        .map((member) => ({
          member_id: member.member_id,
          range_mode: member.range_mode,
          ranges: normaliseRanges(member.ranges),
        }))
        .filter(
          (member) => member.range_mode === 'whole_source' || member.ranges.length > 0,
        )
        .sort((a, b) =>
          a.member_id < b.member_id ? -1 : a.member_id > b.member_id ? 1 : 0,
        ),
    }))
    .filter((group) => group.members.length > 0)
    .sort((a, b) => (a.group_id < b.group_id ? -1 : a.group_id > b.group_id ? 1 : 0));

  const manualRegions = plan.manual_regions
    .map((region) => ({ ...region, ranges: normaliseRanges(region.ranges) }))
    .filter((region) => region.range_mode === 'whole_source' || region.ranges.length > 0)
    .sort((a, b) => (a.region_id < b.region_id ? -1 : a.region_id > b.region_id ? 1 : 0));

  return sha256OfCanonical({
    v: SELECTION_PLAN_VERSION,
    detection_revision: plan.detection_revision,
    groups,
    manual_regions: manualRegions,
    render: plan.render,
  });
}

export function normaliseRanges(ranges: SelectionRange[]): SelectionRange[] {
  const byBeat = new Map<number, SelectionRange[]>();
  for (const range of ranges) {
    if (range.end_frame <= range.start_frame) continue;
    const list = byBeat.get(range.beat_index) ?? [];
    list.push(range);
    byBeat.set(range.beat_index, list);
  }

  const merged: SelectionRange[] = [];
  for (const beatIndex of [...byBeat.keys()].sort((a, b) => a - b)) {
    const sorted = (byBeat.get(beatIndex) ?? []).sort(
      (a, b) => a.start_frame - b.start_frame || a.end_frame - b.end_frame,
    );
    let current: SelectionRange | null = null;
    for (const range of sorted) {
      if (current && range.start_frame <= current.end_frame) {
        current = {
          beat_index: current.beat_index,
          start_frame: current.start_frame,
          end_frame: Math.max(current.end_frame, range.end_frame),
        };
      } else {
        if (current) merged.push(current);
        current = {
          beat_index: range.beat_index,
          start_frame: range.start_frame,
          end_frame: range.end_frame,
        };
      }
    }
    if (current) merged.push(current);
  }
  return merged;
}
