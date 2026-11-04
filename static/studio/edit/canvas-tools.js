/**
 * Geometry and box tools for the Studio preview.
 *
 * Clean layers use source coordinates, before the crop. The preview uses
 * output coordinates, after the crop. Everything here is pure so the same
 * maths can be tested without a canvas and mirrored against the renderer's
 * `compose_render._base_crop` and `_scene_crop`.
 */

import { CANVAS, clamp, graphicRect, numberOr } from "./model.js";

export function sourceDimensions(source, aspect = "9:16") {
  const fallback = CANVAS[aspect] || CANVAS["9:16"];
  const width = numberOr(source?.width, fallback.width);
  const height = numberOr(source?.height, fallback.height);
  return {
    width: width > 1 ? width : fallback.width,
    height: height > 1 ? height : fallback.height,
  };
}

/** The story clip playing at output time `t`, with its cumulative offset. */
export function clipAt(story, time) {
  const clips = Array.isArray(story?.clips) ? story.clips : [];
  let cursor = 0;
  for (const clip of clips) {
    const duration = Math.max(
      0.01,
      numberOr(clip?.dur, numberOr(clip?.end) - numberOr(clip?.start)),
    );
    if (time < cursor + duration - 1e-6 || clip === clips[clips.length - 1]) {
      return { clip, offset: cursor, duration, sourceTime: numberOr(clip?.start) + Math.max(0, time - cursor) };
    }
    cursor += duration;
  }
  return { clip: null, offset: 0, duration: 0, sourceTime: Math.max(0, numberOr(time)) };
}

/** Output seconds -> source seconds through the story's ordered clips. */
export function sourceTimeAt(story, time) {
  return clipAt(story, time).sourceTime;
}

const SCENE_MAPS = new WeakMap();

function sceneMap(job) {
  if (job && typeof job === "object" && SCENE_MAPS.has(job)) {
    return SCENE_MAPS.get(job);
  }
  const scenes = job?.analysis?.scenes;
  const map = new Map();
  if (Array.isArray(scenes)) {
    scenes.forEach((scene, index) => {
      if (scene && scene.id !== undefined) map.set(String(scene.id), scene);
      if (scene) map.set(`#${index}`, scene);
    });
  } else if (scenes && typeof scenes === "object") {
    Object.entries(scenes).forEach(([key, scene]) => {
      if (scene && typeof scene === "object") map.set(String(key), scene);
    });
  }
  if (job && typeof job === "object") SCENE_MAPS.set(job, map);
  return map;
}

function sceneCrop(job, clip, aspect) {
  if (!clip) return null;
  const map = sceneMap(job);
  const scene = map.get(String(clip.scene));
  if (!scene) return null;
  const crops = scene.crops && typeof scene.crops === "object" ? scene.crops : {};
  let crop = crops[aspect];
  if (!crop && aspect === "9:16" && scene.crop && typeof scene.crop === "object") {
    crop = scene.crop;
  }
  if (!crop) return null;
  const cx = numberOr(crop.cx, 0.5);
  const cy = numberOr(crop.cy, 0.5);
  return { cx: clamp(cx, 0, 1), cy: clamp(cy, 0, 1) };
}

function baseCrop(width, height, aspect, cx, cy, zoom) {
  const canvas = CANVAS[aspect] || CANVAS["9:16"];
  const targetAr = canvas.width / canvas.height;
  const sourceAr = width / Math.max(1, height);
  let cropW;
  let cropH;
  if (sourceAr > targetAr) {
    cropH = height;
    cropW = Math.min(height * targetAr, width);
  } else {
    cropW = width;
    cropH = Math.min(width / targetAr, height);
  }
  if (zoom > 1) {
    cropW = Math.min(cropW, cropW / zoom);
    cropH = Math.min(cropH, cropH / zoom);
  }
  cropW = Math.max(2, Math.min(cropW, width));
  cropH = Math.max(2, Math.min(cropH, height));
  return {
    x: clamp(cx * width - cropW / 2, 0, Math.max(0, width - cropW)) / width,
    y: clamp(cy * height - cropH / 2, 0, Math.max(0, height - cropH)) / height,
    w: cropW / width,
    h: cropH / height,
  };
}

/**
 * The crop window at output time `t`, as fractions of the source frame.
 * Mirrors `compose_render`: center mode ignores scenes, auto mode prefers the
 * scene crop, and the Edit's overrides win over both.
 */
export function cropAt({ edit, job, story, time = 0, aspect = "9:16" } = {}) {
  const { width, height } = sourceDimensions(job?.source, aspect);
  const reframe = edit?.reframe || {};
  const mode = String(reframe.mode || "auto").toLowerCase();
  const active = clipAt(story, time);
  let cx = numberOr(reframe.cx, 0.5);
  let cy = numberOr(reframe.cy, 0.5);
  if (mode === "center") {
    cx = 0.5;
    cy = 0.5;
  } else if (mode === "auto") {
    const scene = sceneCrop(job, active.clip, aspect);
    if (scene) {
      cx = scene.cx;
      cy = scene.cy;
    }
  }
  const overrides = reframe.overrides && typeof reframe.overrides === "object"
    ? reframe.overrides
    : {};
  cx = numberOr(overrides.cx, cx);
  cy = numberOr(overrides.cy, cy);
  const zoom = clamp(numberOr(overrides.zoom, reframe.zoom ?? 1), 1, 2);
  return baseCrop(width, height, aspect, clamp(cx, 0, 1), clamp(cy, 0, 1), zoom);
}

function validBox(box) {
  return box && typeof box === "object"
    && Number.isFinite(Number(box.x))
    && Number.isFinite(Number(box.y))
    && Number.isFinite(Number(box.w))
    && Number.isFinite(Number(box.h));
}

/** Source box -> output frame fractions. May fall outside 0..1. */
export function boxToFrame(box, crop) {
  const safe = validBox(box) ? box : { x: 0.08, y: 0.72, w: 0.84, h: 0.16 };
  const width = Math.max(1e-6, numberOr(crop?.w, 1));
  const height = Math.max(1e-6, numberOr(crop?.h, 1));
  return {
    x: (numberOr(safe.x) - numberOr(crop?.x)) / width,
    y: (numberOr(safe.y) - numberOr(crop?.y)) / height,
    w: numberOr(safe.w) / width,
    h: numberOr(safe.h) / height,
  };
}

/** Output frame fractions -> source box, clamped to the source frame. */
export function frameToBox(rect, crop) {
  const x = numberOr(rect?.x) * numberOr(crop?.w, 1) + numberOr(crop?.x);
  const y = numberOr(rect?.y) * numberOr(crop?.h, 1) + numberOr(crop?.y);
  const w = numberOr(rect?.w) * numberOr(crop?.w, 1);
  const h = numberOr(rect?.h) * numberOr(crop?.h, 1);
  const left = clamp(x, 0, 1);
  const top = clamp(y, 0, 1);
  return {
    x: left,
    y: top,
    w: clamp(w, 0.004, 1 - left),
    h: clamp(h, 0.004, 1 - top),
  };
}

/**
 * A layer's place on the video, from where it shows in this crop. Unlike
 * `frameToBox` it is not clamped, so the layer keeps its size at the frame edge.
 */
export function stuckPosition(rect, crop) {
  const round = (value) => Math.round(value * 1e6) / 1e6;
  return {
    box: {
      x: round(numberOr(rect?.x) * numberOr(crop?.w, 1) + numberOr(crop?.x)),
      y: round(numberOr(rect?.y) * numberOr(crop?.h, 1) + numberOr(crop?.y)),
      w: round(numberOr(rect?.w) * numberOr(crop?.w, 1)),
      h: round(numberOr(rect?.h) * numberOr(crop?.h, 1)),
    },
    crop_h: round(numberOr(crop?.h, 1)),
  };
}

/** How much bigger a stuck layer is in this crop. Mirrors `compose_render`. */
export function stuckScale(layer, crop) {
  return numberOr(layer?.video?.crop_h, 1) / Math.max(1e-6, numberOr(crop?.h, 1));
}

/** Where a graphic layer shows in this crop: on the video, or on the screen. */
export function layerFrameRect(layer, crop) {
  return layer?.video && crop ? boxToFrame(layer.video.box, crop) : graphicRect(layer);
}

/** Clean ranges are source seconds; no ranges means the whole story. */
export function layerActive(layer, sourceTime) {
  const ranges = Array.isArray(layer?.ranges) ? layer.ranges : [];
  if (!ranges.length) return true;
  return ranges.some((range) => (
    sourceTime >= numberOr(range?.start) - 1e-6
    && sourceTime < numberOr(range?.end) + 1e-6
  ));
}

/** Move a source box by a source-fraction delta and keep it inside the frame. */
export function moveBox(box, dx, dy) {
  const source = validBox(box) ? box : { x: 0.08, y: 0.72, w: 0.84, h: 0.16 };
  const w = clamp(numberOr(source.w), 0.004, 1);
  const h = clamp(numberOr(source.h), 0.004, 1);
  return {
    x: clamp(numberOr(source.x) + numberOr(dx), 0, 1 - w),
    y: clamp(numberOr(source.y) + numberOr(dy), 0, 1 - h),
    w,
    h,
  };
}

/** Resize one or more edges of a source box, keeping a minimum size. */
export function resizeBox(box, handle, dx, dy, minimum = 0.004) {
  const source = validBox(box) ? box : { x: 0.08, y: 0.72, w: 0.84, h: 0.16 };
  const min = clamp(numberOr(minimum, 0.004), 0.001, 0.2);
  let left = numberOr(source.x);
  let top = numberOr(source.y);
  let right = left + numberOr(source.w);
  let bottom = top + numberOr(source.h);
  const value = String(handle || "");
  if (value.includes("w")) left = clamp(left + numberOr(dx), 0, right - min);
  if (value.includes("e")) right = clamp(right + numberOr(dx), left + min, 1);
  if (value.includes("n")) top = clamp(top + numberOr(dy), 0, bottom - min);
  if (value.includes("s")) bottom = clamp(bottom + numberOr(dy), top + min, 1);
  return { x: left, y: top, w: right - left, h: bottom - top };
}

/** Which resize handle (if any) is under a point in the same units as rect. */
export function handleAt(rect, point, tolerance = 0) {
  const x = numberOr(rect?.x);
  const y = numberOr(rect?.y);
  const w = numberOr(rect?.w);
  const h = numberOr(rect?.h);
  const px = numberOr(point?.x);
  const py = numberOr(point?.y);
  const t = Math.max(0, numberOr(tolerance));
  const nearLeft = Math.abs(px - x) <= t;
  const nearRight = Math.abs(px - (x + w)) <= t;
  const nearTop = Math.abs(py - y) <= t;
  const nearBottom = Math.abs(py - (y + h)) <= t;
  const insideX = px >= x - t && px <= x + w + t;
  const insideY = py >= y - t && py <= y + h + t;
  if (!insideX || !insideY) return "";
  if (nearLeft && nearTop) return "nw";
  if (nearRight && nearTop) return "ne";
  if (nearLeft && nearBottom) return "sw";
  if (nearRight && nearBottom) return "se";
  if (nearLeft) return "w";
  if (nearRight) return "e";
  if (nearTop) return "n";
  if (nearBottom) return "s";
  return "";
}

/** Whether a point is inside a rect, in the same units. */
export function insideRect(rect, point) {
  return numberOr(point?.x) >= numberOr(rect?.x)
    && numberOr(point?.x) <= numberOr(rect?.x) + numberOr(rect?.w)
    && numberOr(point?.y) >= numberOr(rect?.y)
    && numberOr(point?.y) <= numberOr(rect?.y) + numberOr(rect?.h);
}

/** Intersection of a frame rect with the visible 0..1 frame, or null. */
export function visibleRect(rect) {
  const left = Math.max(0, numberOr(rect?.x));
  const top = Math.max(0, numberOr(rect?.y));
  const right = Math.min(1, numberOr(rect?.x) + numberOr(rect?.w));
  const bottom = Math.min(1, numberOr(rect?.y) + numberOr(rect?.h));
  if (right <= left + 1e-6 || bottom <= top + 1e-6) return null;
  return { x: left, y: top, w: right - left, h: bottom - top };
}
