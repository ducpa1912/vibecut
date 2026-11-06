/* Classic Clean: pure timeline rules shared by the timeline panel, the
 * detection overlay and the apply step. No DOM and no network, so the mapping
 * can be tested with plain data.
 *
 * One bar is one tight box at one time. A grouped row (subtitle lines in one
 * area) stays one timeline row, and each member keeps its own bar, box and
 * range. The scan can only describe source time; the app passes a mapper when
 * the timeline shows cut time.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ClassicCleanTimeline = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const MIN_BAR_SECONDS = 0.05;

  function numberOr(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  }

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, Number(value)));
  }

  function round(value) {
    return Math.round(Number(value) * 1000) / 1000;
  }

  /** One line, short enough for a 12px bar label. */
  function shortSample(value, max = 28) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!text) return "";
    if (text.length <= max) return text;
    return `${text.slice(0, Math.max(1, max - 1)).trimEnd()}…`;
  }

  /** A short text sample, or the fallback name the founder can point at. */
  function barLabel(value, index, max = 28) {
    return shortSample(value, max) || `Remove Box ${Math.max(1, Math.round(numberOr(index)) + 1)}`;
  }

  function normalizeRanges(ranges) {
    const items = [];
    for (const item of Array.isArray(ranges) ? ranges : []) {
      const start = Number(item?.start);
      const end = Number(item?.end);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) continue;
      items.push({ start: round(start), end: round(end) });
    }
    items.sort((a, b) => a.start - b.start || a.end - b.end);
    return items;
  }

  /** The member ranges an apply step should use: override, else the scan. */
  function rangesFor(row, member, override) {
    const own = override && typeof override === "object" ? override : null;
    if (own) {
      const stored = normalizeRanges(own);
      if (stored.length) return stored;
    }
    return normalizeRanges(member?.ranges || row?.ranges || []);
  }

  function moveRange(range, delta, total) {
    const limit = Math.max(MIN_BAR_SECONDS, numberOr(total));
    const start = clamp(numberOr(range?.start), 0, limit);
    const end = clamp(Math.max(start + MIN_BAR_SECONDS, numberOr(range?.end)), 0, limit);
    const span = Math.max(MIN_BAR_SECONDS, end - start);
    const next = clamp(start + numberOr(delta), 0, Math.max(0, limit - span));
    return { start: round(next), end: round(next + span) };
  }

  function moveRanges(ranges, delta, total) {
    return normalizeRanges(ranges).map((range) => moveRange(range, delta, total));
  }

  function trimRange(range, side, value, total, minDuration = MIN_BAR_SECONDS) {
    const limit = Math.max(minDuration, numberOr(total));
    const min = Math.max(MIN_BAR_SECONDS, numberOr(minDuration));
    const start = clamp(numberOr(range?.start), 0, limit);
    const end = clamp(Math.max(start + min, numberOr(range?.end)), 0, limit);
    if (side === "start") {
      return { start: round(clamp(numberOr(value), 0, end - min)), end: round(end) };
    }
    return { start: round(start), end: round(clamp(numberOr(value), start + min, limit)) };
  }

  function rangeAt(ranges, t) {
    const time = numberOr(t);
    return normalizeRanges(ranges).some((range) => time + 1 / 30 > range.start && time < range.end);
  }

  function rulerTicks(total, count = 6) {
    const limit = Math.max(0.01, numberOr(total));
    const steps = Math.max(1, Math.round(numberOr(count) || 6));
    const ticks = [];
    for (let index = 0; index <= steps; index += 1) {
      const time = (limit * index) / steps;
      ticks.push({ time, left: (time / limit) * 100, first: index === 0, last: index === steps });
    }
    return ticks;
  }

  /**
   * One bar per tight member range.
   *
   * `rows` are the scan rows from `cleanScanRows`: a grouped row keeps
   * `entryRows` (its members), a drawn row is `manual`. `mapRanges` converts
   * source ranges to the timeline the workspace shows; `overrideFor` returns a
   * stored range override for one member.
   */
  function buildBars(rows, options = {}) {
    const total = Math.max(MIN_BAR_SECONDS, numberOr(options.total));
    const mapRanges = typeof options.mapRanges === "function"
      ? options.mapRanges
      : (ranges) => normalizeRanges(ranges);
    const overrideFor = typeof options.overrideFor === "function"
      ? options.overrideFor
      : () => null;
    const identity = typeof options.identity === "function"
      ? options.identity
      : (row) => String(row?.identity || row?.key || "");
    const labelFor = typeof options.labelFor === "function"
      ? options.labelFor
      : (member, index) => barLabel(member?.text || member?.text_key, index);
    const bars = [];
    const list = Array.isArray(rows) ? rows : [];
    list.forEach((row, rowIndex) => {
      if (!row) return;
      const rowIdentity = identity(row);
      const members = row.manual
        ? [{ ...row, tracklet_id: "" }]
        : (Array.isArray(row.entryRows) && row.entryRows.length ? row.entryRows : [row]);
      for (const member of members) {
        const memberId = String(member?.tracklet_id || "");
        const overrideKey = `${rowIdentity}|${memberId}`;
        const raw = rangesFor(row, member, overrideFor(row, member, overrideKey));
        const mapped = normalizeRanges(mapRanges(raw, row, member));
        // A row whose ranges map outside the cut has nothing to show here.
        if (raw.length && !mapped.length && options.hideOutside !== false) continue;
        const spans = mapped.length ? mapped : [{ start: 0, end: total }];
        spans.forEach((span, rangeIndex) => {
          const start = clamp(numberOr(span.start), 0, total);
          const end = clamp(numberOr(span.end), 0, total);
          if (end - start < 0.001) return;
          bars.push({
            id: `${rowIdentity}|${memberId}|${rangeIndex}`,
            rowIdentity,
            rowIndex,
            memberId,
            overrideKey,
            rangeIndex,
            start: round(start),
            end: round(end),
            left: (start / total) * 100,
            width: Math.max(0.35, ((end - start) / total) * 100),
            label: labelFor(member, bars.length, row),
            lane: Math.max(0, Math.round(numberOr(row.lane))),
            manual: Boolean(row.manual),
          });
        });
      }
    });
    return bars;
  }

  return {
    MIN_BAR_SECONDS,
    shortSample,
    barLabel,
    normalizeRanges,
    rangesFor,
    moveRange,
    moveRanges,
    trimRange,
    rangeAt,
    rulerTicks,
    buildBars,
  };
});
