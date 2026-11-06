/* Classic Clean: pure merge rules shared by the rail, the frame overlay and
 * the applied layer list. No DOM and no network, so the rules can be tested
 * with plain data.
 *
 * The rules mirror Studio's `clean.js`: one row per area and text, subtitles
 * in one area are one row, and only an exact duplicate saved layer merges.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ClassicCleanMerge = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function numberOr(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  /** IoU 0.3, or centres within 4% across and 3% down. */
  function sameArea(first, second) {
    if (!first || !second) return false;
    const left = Math.max(numberOr(first.x), numberOr(second.x));
    const top = Math.max(numberOr(first.y), numberOr(second.y));
    const right = Math.min(
      numberOr(first.x) + numberOr(first.w),
      numberOr(second.x) + numberOr(second.w),
    );
    const bottom = Math.min(
      numberOr(first.y) + numberOr(first.h),
      numberOr(second.y) + numberOr(second.h),
    );
    if (right > left && bottom > top) {
      const shared = (right - left) * (bottom - top);
      const union = numberOr(first.w) * numberOr(first.h)
        + numberOr(second.w) * numberOr(second.h) - shared;
      if (union > 0 && shared / union >= 0.3) return true;
    }
    const dx = Math.abs(
      numberOr(first.x) + numberOr(first.w) / 2
      - numberOr(second.x) - numberOr(second.w) / 2,
    );
    const dy = Math.abs(
      numberOr(first.y) + numberOr(first.h) / 2
      - numberOr(second.y) - numberOr(second.h) / 2,
    );
    return dx <= 0.04 && dy <= 0.03;
  }

  /** Lowercase letters and numbers only; OCR punctuation does not split a row. */
  function foundTextKey(value) {
    return String(value || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
  }

  /** Exact text, or a misread/partial reading when the shorter one has 4+ chars. */
  function sameFoundText(first, second) {
    if (first === second) return true;
    return Math.min(first.length, second.length) >= 4
      && (first.includes(second) || second.includes(first));
  }

  function joinBoxes(first, second) {
    if (!first || !second) return first || second || null;
    const x = Math.min(numberOr(first.x), numberOr(second.x));
    const y = Math.min(numberOr(first.y), numberOr(second.y));
    return {
      x,
      y,
      w: Math.max(
        numberOr(first.x) + numberOr(first.w),
        numberOr(second.x) + numberOr(second.w),
      ) - x,
      h: Math.max(
        numberOr(first.y) + numberOr(first.h),
        numberOr(second.y) + numberOr(second.h),
      ) - y,
    };
  }

  function mergeRanges(ranges) {
    const items = [];
    for (const item of ranges || []) {
      const start = Number(item?.start);
      const end = Number(item?.end);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) continue;
      items.push({
        start: Math.round(start * 1000) / 1000,
        end: Math.round(end * 1000) / 1000,
      });
    }
    items.sort((a, b) => a.start - b.start || a.end - b.end);
    const merged = [];
    for (const item of items) {
      const last = merged[merged.length - 1];
      if (last && item.start <= last.end + 1e-6) {
        last.end = Math.max(last.end, item.end);
      } else {
        merged.push({ ...item });
      }
    }
    return merged;
  }

  /** Same tracklet, same area and same text, or a real range overlap. */
  function sameScanText(layer, other) {
    if (!String(layer?.tracklet_id || "").trim()) return false;
    if (!sameArea(layer?.box, other?.box)) return false;
    if (layer?.text_key && layer.text_key === other?.text_key) return true;
    const first = Array.isArray(layer?.ranges) ? layer.ranges : [];
    const second = Array.isArray(other?.ranges) ? other.ranges : [];
    if (!first.length || !second.length) return true;
    return first.some((a) => second.some((b) => (
      Math.min(Number(a.end), Number(b.end))
      - Math.max(Number(a.start), Number(b.start)) > 0.05
    )));
  }

  /**
   * One row per area and text. Subtitle lines in one area always join; other
   * kinds join only on the same or a contained reading. The longest reading
   * names the row, and `ids`/`members` keep every tracklet for the clean pass.
   */
  function mergeFoundEntries(entries) {
    const rows = [];
    for (const entry of Array.isArray(entries) ? entries : []) {
      const id = String(entry?.tracklet_id || entry?.id || "");
      if (!id) continue;
      const kind = String(entry?.kind || "text");
      const text = String(entry?.text || entry?.text_key || "").trim();
      const key = foundTextKey(text);
      const home = rows.find((row) => row.ids.includes(id))
        || rows.find((row) => {
          if (row.kind !== kind || !sameArea(row.box, entry.box)) return false;
          return kind === "subtitle"
            || (key && sameFoundText(foundTextKey(row.text), key));
        });
      if (!home) {
        rows.push({
          ...entry,
          ids: [id],
          members: [entry],
          keys: new Set(key ? [key] : []),
          box: { ...(entry.box || {}) },
          text,
          text_key: String(entry.text_key || entry.text || ""),
          ranges: mergeRanges(entry.ranges || []),
          confidence: numberOr(entry.confidence),
        });
        continue;
      }
      if (!home.ids.includes(id)) {
        home.ids.push(id);
        home.members.push(entry);
      }
      if (key) home.keys.add(key);
      if (text.length > String(home.text || "").length) {
        home.text = text;
        if (String(entry.text_key || "").length >= String(home.text_key || "").length) {
          home.text_key = String(entry.text_key || entry.text || "");
        }
      }
      home.box = joinBoxes(home.box, entry.box);
      home.ranges = mergeRanges([...home.ranges, ...(entry.ranges || [])]);
      home.confidence = Math.max(numberOr(home.confidence), numberOr(entry.confidence));
      if (entry.action && !home.action) home.action = entry.action;
      if (entry.fill_keys !== undefined && home.fill_keys === undefined) {
        home.fill_keys = entry.fill_keys;
      }
      if (!home.reason && entry.reason) home.reason = entry.reason;
    }
    return rows.map(({ keys, ...row }) => ({
      ...row,
      tracklet_id: row.ids[0],
      lines: Math.max(1, keys.size),
    }));
  }

  /** The identity of one saved layer: its tracklet and box, or an exact box + text. */
  function exactLayerKey(layer) {
    if (!layer || typeof layer !== "object") return "";
    const box = layer.box || {};
    const rect = ["x", "y", "w", "h"]
      .map((axis) => Math.round(numberOr(box[axis]) * 10000) / 10000)
      .join(",");
    const tracklet = String(layer.tracklet_id || "").trim();
    if (tracklet) return `tracklet:${tracklet}:${rect}`;
    const kind = String(layer.tracklet_kind || layer.kind || "");
    const text = foundTextKey(layer.text_key || layer.label);
    return `box:${kind}:${text}:${rect}`;
  }

  /** Two saved layers that describe the same tracklet and the same box. */
  function sameExactLayer(first, second) {
    const key = exactLayerKey(first);
    return Boolean(key) && key === exactLayerKey(second);
  }

  /**
   * Merge only exact duplicate layers: the same tracklet, or the same box and
   * text when neither has a tracklet. Different subtitle lines in one area
   * keep their own tight box, range and fill keys; they are not one layer.
   */
  function dedupeCleanLayers(layers) {
    const source = Array.isArray(layers) ? layers : [];
    const groups = new Map();
    let changed = false;
    for (const layer of source) {
      if (!layer || typeof layer !== "object") {
        changed = true;
        continue;
      }
      if (String(layer.source || "").trim() === "manual") {
        groups.set(`manual:${layer.id || groups.size}`, [layer]);
        continue;
      }
      const key = exactLayerKey(layer);
      if (!key) {
        groups.set(`layer:${groups.size}`, [layer]);
        continue;
      }
      const home = groups.get(key);
      if (home) {
        home.push(layer);
        changed = true;
      } else {
        groups.set(key, [layer]);
      }
    }
    const merged = [];
    for (const group of groups.values()) {
      const first = group[0];
      if (group.length === 1) {
        merged.push(first);
        continue;
      }
      const longest = (field) => group
        .map((layer) => String(layer?.[field] || ""))
        .sort((a, b) => b.length - a.length)[0];
      const label = longest("label");
      const textKey = longest("text_key");
      // No ranges means the layer applies at every time. Joining it with a
      // bounded twin must not narrow it to that twin's windows.
      const unbounded = group.some((layer) => (
        !Array.isArray(layer.ranges) || layer.ranges.length === 0
      ));
      const fillKeys = group.find((layer) => layer.fill_keys !== undefined)?.fill_keys;
      merged.push({
        ...first,
        // The exact duplicate carries the same box. Keep the tight box; never
        // union different lines into one large layer.
        box: { ...(first.box || {}) },
        ranges: unbounded
          ? []
          : mergeRanges(group.flatMap((layer) => layer.ranges || [])),
        hidden: group.every((layer) => Boolean(layer.hidden)),
        ...(label ? { label } : {}),
        ...(textKey ? { text_key: textKey } : {}),
        ...(fillKeys !== undefined ? { fill_keys: fillKeys } : {}),
      });
    }
    return { layers: merged, changed: changed || merged.length !== source.length };
  }

  return {
    sameArea,
    foundTextKey,
    sameFoundText,
    joinBoxes,
    mergeRanges,
    sameScanText,
    mergeFoundEntries,
    exactLayerKey,
    sameExactLayer,
    dedupeCleanLayers,
  };
});
