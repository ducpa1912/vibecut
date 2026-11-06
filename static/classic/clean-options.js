/* Classic Clean: how AI fill runs, and the cheaper way to clean a big drawn box.
 * Pure rules, plus one remembered choice. The same rules as Studio's Render step
 * and `clean.js`, so they can be tested with plain data.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ClassicCleanOptions = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const STORE_KEY = "vibecut.classic.fillChoice";
  const ENGINES = ["lama", "migan", "telea", "ns"];
  const KEYED = ["lama", "migan"];
  const BIG_BOX_SHARE = 5;

  /** An unknown or missing choice falls back to the defaults. */
  function normalChoice(value) {
    const raw = value && typeof value === "object" ? value : {};
    return {
      engine: ENGINES.includes(raw.engine) ? raw.engine : "lama",
      // Empty is the default: the GPU when this Mac can run the fill.
      device: raw.device === "cpu" ? "cpu" : "",
      follow: raw.follow === true,
    };
  }

  function loadChoice(storage) {
    try {
      return normalChoice(JSON.parse(storage.getItem(STORE_KEY) || "{}"));
    } catch (_) {
      return normalChoice({});
    }
  }

  function saveChoice(storage, choice) {
    try {
      storage.setItem(STORE_KEY, JSON.stringify(normalChoice(choice)));
    } catch (_) {
      // A private window keeps the choice for this page only.
    }
  }

  /** What a render or estimate sends. OpenCV has no chip or camera choice. */
  function requestFields(choice) {
    const normal = normalChoice(choice);
    if (!KEYED.includes(normal.engine)) return { fill_device: "", fill_follow: false };
    return { fill_device: normal.device, fill_follow: normal.follow };
  }

  /** Lines the scan found mostly inside a box, while the box is on screen. */
  function linesInsideBox(layer, tracklets) {
    const box = layer && layer.box;
    if (!box) return [];
    const ranges = Array.isArray(layer.ranges) ? layer.ranges : [];
    return (Array.isArray(tracklets) ? tracklets : []).filter((tracklet) => {
      const line = tracklet && tracklet.box;
      if (!line || tracklet.minor === true || !tracklet.id) return false;
      const width = Math.min(box.x + box.w, line.x + line.w) - Math.max(box.x, line.x);
      const height = Math.min(box.y + box.h, line.y + line.h) - Math.max(box.y, line.y);
      if (width <= 0 || height <= 0) return false;
      if ((width * height) / Math.max(1e-6, line.w * line.h) < 0.6) return false;
      if (!ranges.length) return true;
      return (Array.isArray(tracklet.ranges) ? tracklet.ranges : []).some((seen) => ranges.some((range) => (
        Number(seen.start) < Number(range.end) && Number(range.start) < Number(seen.end)
      )));
    });
  }

  /** A line's times inside the times the box was on. An empty list means always. */
  function rangesWithin(lineRanges, boxRanges) {
    if (!Array.isArray(boxRanges) || !boxRanges.length) return lineRanges;
    const kept = [];
    for (const line of Array.isArray(lineRanges) ? lineRanges : []) {
      for (const box of boxRanges) {
        const start = Math.max(Number(line.start), Number(box.start));
        const end = Math.min(Number(line.end), Number(box.end));
        if (end > start) kept.push({ start, end });
      }
    }
    return kept;
  }

  /** The picture share of a drawn AI fill box big enough to warn about, or 0. */
  function bigBoxShare(layer) {
    const box = layer && layer.box;
    if (!box || layer.method !== "fill" || String(layer.tracklet_id || "").trim()) return 0;
    const share = Math.round((Number(box.w) || 0) * (Number(box.h) || 0) * 100);
    return share >= BIG_BOX_SHARE ? share : 0;
  }

  return {
    ENGINES, normalChoice, loadChoice, saveChoice, requestFields,
    linesInsideBox, rangesWithin, bigBoxShare,
  };
});
