/**
 * Studio editor timeline.
 *
 * One sentence lane plus the fixed layer lanes. Bars are buttons, the ruler
 * and empty space seek, and the playhead is a percentage so the timeline never
 * needs horizontal scrolling.
 */

import { el } from "../ui.js";
import {
  formatSpan,
  formatTime,
  layerSpans,
  numberOr,
  sentenceSegments,
} from "./model.js";

const LANE_LABELS = {
  clean: "Clean",
  text: "Text",
  captions: "Captions",
  effects: "Effects",
  color: "Color",
  audio: "Audio",
};

const EMPTY_COPY = {
  clean: "No old text marked",
  text: "No text yet",
  captions: "No captions yet",
  effects: "No motion or effects",
  color: "Original colour",
  audio: "Original sound",
};

function niceStep(duration) {
  const target = Math.max(0.5, duration / 6);
  const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
  return steps.find((step) => step >= target) || 600;
}

export function mountTimeline(root, options = {}) {
  const handlers = {
    onSeek: options.onSeek || (() => {}),
    onSelect: options.onSelect || (() => {}),
  };
  let disposed = false;
  let duration = 10;
  let selected = null;
  let seeking = false;
  let state = { edit: null, captions: null, story: null, aspect: "9:16" };

  root.innerHTML = `
    <section class="st-timeline" aria-labelledby="st-timeline-title">
      <header class="st-timeline-head">
        <div>
          <h2 id="st-timeline-title">Timeline</h2>
          <p class="st-hint">Click a sentence or a layer to jump to it.</p>
        </div>
        <div class="st-timeline-meta">
          <span id="st-timeline-span" class="st-mono st-timeline-span">0:00.0</span>
          <span id="st-timeline-count" class="st-chip st-chip-quiet">0 layers</span>
        </div>
      </header>
      <div class="st-timeline-scroll" tabindex="0" role="group" aria-label="Story timeline">
        <div id="st-timeline-grid" class="st-timeline-grid"></div>
      </div>
    </section>
  `;

  const $ = (selector) => root.querySelector(selector);
  const dom = {
    grid: $("#st-timeline-grid"),
    span: $("#st-timeline-span"),
    count: $("#st-timeline-count"),
    scroll: $(".st-timeline-scroll"),
  };

  function position(item) {
    const total = Math.max(0.1, duration);
    const start = Math.max(0, Math.min(total, numberOr(item.start)));
    const end = Math.max(start + 0.05, Math.min(total, numberOr(item.end, start + 0.1)));
    return {
      left: (start / total) * 100,
      width: Math.max(0.35, ((end - start) / total) * 100),
    };
  }

  function timeFromEvent(event) {
    const track = event.currentTarget;
    const box = track.getBoundingClientRect();
    if (!box.width) return 0;
    const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
    return ratio * duration;
  }

  function makePlayhead() {
    return el("i", { class: "st-tl-playhead", "aria-hidden": "true" });
  }

  function setPlayhead(track) {
    const line = track.querySelector(".st-tl-playhead");
    if (!line) return;
    line.style.left = `${(Math.max(0, Math.min(duration, numberOr(state.time))) / Math.max(0.1, duration)) * 100}%`;
  }

  function paintPlayheads() {
    for (const track of dom.grid.querySelectorAll(".st-tl-track")) setPlayhead(track);
  }

  function makeBar(item, kind) {
    const geometry = position(item);
    const label = String(item.label || "").trim();
    const button = el("button", {
      class: `st-tl-bar st-tl-bar-${kind}${item.muted ? " is-muted" : ""}${item.dashed ? " is-dashed" : ""}${selected?.kind === kind && selected?.id === item.layerId ? " is-selected" : ""}`,
      type: "button",
      title: `${label || LANE_LABELS[kind] || "Layer"} · ${formatSpan(item.start, item.end)}`,
      "aria-label": `${label || LANE_LABELS[kind] || "Layer"}, ${formatSpan(item.start, item.end)}`,
      style: `left:${geometry.left}%;width:${geometry.width}%`,
      dataset: {
        kind,
        layer: item.layerId || item.id,
        start: String(numberOr(item.start)),
      },
    }, [
      geometry.width > 5 ? el("span", { text: label }) : null,
    ]);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      handlers.onSelect(kind, item.layerId || item.id);
      handlers.onSeek(numberOr(item.start));
    });
    return button;
  }

  function makeTrack(row) {
    const track = el("div", {
      class: `st-tl-track st-tl-track-${row.kind}`,
      dataset: { kind: row.kind },
      role: "group",
      "aria-label": `${LANE_LABELS[row.kind] || row.label} track`,
    });
    track.append(makePlayhead());
    for (const item of row.items) track.append(makeBar(item, row.kind));
    if (!row.items.length) {
      track.append(el("span", { class: "st-tl-empty", text: EMPTY_COPY[row.kind] || "Empty" }));
    }
    track.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".st-tl-bar")) return;
      seeking = true;
      track.setPointerCapture?.(event.pointerId);
      handlers.onSeek(timeFromEvent(event));
    });
    track.addEventListener("pointermove", (event) => {
      if (!seeking) return;
      handlers.onSeek(timeFromEvent(event));
    });
    track.addEventListener("pointerup", () => { seeking = false; });
    track.addEventListener("pointercancel", () => { seeking = false; });
    return track;
  }

  function makeRuler() {
    const ruler = el("div", { class: "st-tl-ruler", role: "group", "aria-label": "Timeline ruler" });
    const step = niceStep(duration);
    const count = Math.floor(duration / step) + 1;
    for (let index = 0; index < count; index += 1) {
      const time = index * step;
      const ratio = Math.min(1, time / Math.max(0.1, duration));
      const tick = el("button", {
        class: "st-tl-tick",
        type: "button",
        style: `left:${ratio * 100}%`,
        title: `Jump to ${formatTime(time)}`,
        "aria-label": `Jump to ${formatTime(time)}`,
        dataset: { time: String(time) },
      }, [el("span", { text: formatTime(time) })]);
      tick.addEventListener("click", (event) => {
        event.stopPropagation();
        handlers.onSeek(time);
      });
      ruler.append(tick);
    }
    ruler.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".st-tl-tick")) return;
      const box = ruler.getBoundingClientRect();
      if (!box.width) return;
      const ratio = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
      handlers.onSeek(ratio * duration);
    });
    return ruler;
  }

  function render() {
    if (disposed) return;
    const rows = [];
    const sentences = sentenceSegments(state.story);
    rows.push({
      id: "sentences",
      label: "Sentences",
      kind: "sentences",
      items: sentences.map((sentence) => ({
        id: sentence.id,
        label: sentence.text,
        start: sentence.start,
        end: sentence.end,
        sentence: true,
      })),
    });
    const layers = layerSpans(state.edit, state.captions, duration);
    for (const row of layers) rows.push(row);

    dom.grid.replaceChildren();
    dom.grid.append(el("div", { class: "st-tl-corner", text: "Track" }), makeRuler());

    for (const row of rows) {
      const label = el("div", { class: `st-tl-label st-tl-label-${row.kind}` }, [
        el("span", { text: row.label || LANE_LABELS[row.kind] || "Layer" }),
        row.kind !== "sentences" ? el("small", {
          text: String(row.items.length),
        }) : null,
      ]);
      if (row.kind !== "sentences") {
        label.setAttribute("role", "button");
        label.setAttribute("tabindex", "0");
        label.addEventListener("click", () => handlers.onSelect(row.kind, ""));
        label.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            handlers.onSelect(row.kind, "");
          }
        });
      }
      dom.grid.append(label, makeTrack(row));
    }

    const layerCount = rows.reduce((total, row) => total + (row.kind === "sentences" ? 0 : row.items.length), 0);
    dom.count.textContent = `${layerCount} ${layerCount === 1 ? "layer" : "layers"}`;
    dom.span.textContent = `${formatTime(0)} – ${formatTime(duration)}`;
    paintPlayheads();
  }

  function updateTime(time) {
    state.time = Math.max(0, Math.min(duration, numberOr(time)));
    paintPlayheads();
  }

  function updateSelected(value) {
    selected = value || null;
    for (const bar of dom.grid.querySelectorAll(".st-tl-bar")) {
      const match = selected
        && bar.dataset.kind === selected.kind
        && bar.dataset.layer === selected.id;
      bar.classList.toggle("is-selected", Boolean(match));
    }
  }

  dom.scroll.addEventListener("keydown", (event) => {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const delta = event.shiftKey ? 1 : 0.1;
      handlers.onSeek(numberOr(state.time) + (event.key === "ArrowRight" ? delta : -delta));
    } else if (event.key === "Home") {
      event.preventDefault();
      handlers.onSeek(0);
    } else if (event.key === "End") {
      event.preventDefault();
      handlers.onSeek(duration);
    }
  });

  return {
    setData({ edit, captions, story, duration: nextDuration, aspect } = {}) {
      state = {
        edit: edit === undefined ? state.edit : edit,
        captions: captions === undefined ? state.captions : captions,
        story: story === undefined ? state.story : story,
        aspect: aspect || state.aspect,
        time: state.time,
      };
      if (typeof nextDuration === "number" && Number.isFinite(nextDuration)) {
        duration = Math.max(0.1, nextDuration);
      }
      render();
      updateSelected(selected);
    },
    setTime(time) {
      updateTime(time);
    },
    setSelected(value) {
      updateSelected(value);
    },
    setCaptionData(captions) {
      state.captions = captions;
      render();
      updateSelected(selected);
    },
    destroy() {
      disposed = true;
      root.replaceChildren();
    },
  };
}
