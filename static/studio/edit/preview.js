/**
 * Studio editor preview.
 *
 * The canvas is the single place the creator judges a story. It draws the
 * exact frame from `GET …/frame?t=&quality=draft` when that route is live.
 * While the route is not available it falls back to the 540p proxy, then to a
 * quiet placeholder; the timeline and controls keep working in every state.
 */

import { el } from "../ui.js";
import {
  CANVAS,
  CLEAN_LABELS,
  LAYER_COLOURS,
  TEXT_KINDS,
  clamp,
  colorFilter,
  formatTime,
  graphicRect,
  numberOr,
  round,
  safeZoneRects,
} from "./model.js";
import {
  boxToFrame,
  cropAt,
  frameToBox,
  handleAt,
  insideRect,
  layerActive,
  moveBox,
  resizeBox,
  sourceTimeAt,
  visibleRect,
} from "./canvas-tools.js";
import { fetchFrame, framePath, proxyPath, syncMediaCookie } from "./api.js";
import { drawOverlay } from "./overlay.js";
import { icon } from "./icons.js";

const FADE_IN_SKIP = 0.15;

export function mountPreview(root, options = {}) {
  const callbacks = {
    onTime: options.onTime || (() => {}),
    onStatus: options.onStatus || (() => {}),
    onStale: options.onStale || (() => {}),
    onSelect: options.onSelect || (() => {}),
    onBoxChange: options.onBoxChange || (() => {}),
    onBoxCreate: options.onBoxCreate || (() => {}),
    onAspect: options.onAspect || (() => {}),
    onOutput: options.onOutput || (() => {}),
    onPaint: options.onPaint || (() => {}),
    onPaintRequest: options.onPaintRequest || (() => ""),
    onPaintEnd: options.onPaintEnd || (() => {}),
    onCleanMethod: options.onCleanMethod || (() => {}),
    fillAvailable: options.fillAvailable || (() => false),
    onStory: options.onStory || (() => {}),
    onSceneStep: options.onSceneStep || (() => {}),
    onSpan: options.onSpan || (() => {}),
  };
  const state = {
    aspect: "9:16",
    edit: null,
    captions: null,
    job: null,
    story: null,
    duration: 10,
    time: 0,
    showSafeZones: true,
    platform: "auto",
    loop: false,
    selected: null,
    hiddenLayers: new Set(),
    foundText: [],
    foundFocus: "",
    tool: "select",
    paintLayerId: "",
    paintRadius: 0.025,
    paintPoints: [],
    viewZoom: 1,
    viewPan: { x: 0, y: 0 },
    jobId: options.jobId || "",
  };

  let disposed = false;
  let frameImage = null;
  let frameReady = false;
  let frameAvailable = true;
  let frameState = "idle";
  let frameTimer = 0;
  let frameController = null;
  let frameSeq = 0;
  let proxyVideo = null;
  let proxyReady = false;
  let proxyFailed = false;
  let proxyRequested = false;
  // The Edit id changed (a trim or a rebind). The proxy and the exact frame
  // still show the previous cut until the server answers, so say so.
  let rebuilding = false;
  // The parent's duration wins once it passes one; an Edit's story_ref is
  // only the fallback for a direct caller.
  let durationOwned = false;
  let playing = false;
  let videoPlaying = false;
  // Play was pressed before the proxy finished building; start it on ready.
  let pendingPlay = false;
  let raf = 0;
  let lastTick = 0;
  let lastFrameAt = 0;
  let keyHandler = null;
  // Clean-box editing on the canvas.
  let drag = null;
  let drawPreview = null;
  let suppressClick = false;

  root.innerHTML = `
    <section class="st-preview" aria-label="Story preview">
      <div class="st-preview-head">
        <div class="st-preview-head-left">
          <div class="st-preview-story">
            <button id="st-preview-story-btn" class="st-preview-story-btn" type="button" aria-haspopup="menu" aria-expanded="false" title="Switch moment">
              <span id="st-preview-story-num" class="st-mono">01</span>
              <span id="st-preview-story-title">Moment</span>
              <span class="st-moment-caret" aria-hidden="true">▾</span>
            </button>
            <div id="st-preview-story-menu" class="st-preview-story-menu" role="menu" hidden></div>
          </div>
          <div class="st-preview-tools">
            <div class="st-preview-toolgroup" role="group" aria-label="Canvas tool">
              <button id="st-preview-tool-select" class="st-preview-tool is-active" type="button" data-tool="select" aria-pressed="true" title="Select and move boxes (V)" aria-label="Select tool"></button>
              <button id="st-preview-tool-box" class="st-preview-tool" type="button" data-tool="box" aria-pressed="false" title="Draw a Remove-text box (B)" aria-label="Draw box"></button>
              <button id="st-preview-tool-paint" class="st-preview-tool" type="button" data-tool="paint" aria-pressed="false" title="Paint a cleanup mask" aria-label="Paint mask"></button>
            </div>
          </div>
        </div>
        <div class="st-preview-scene" aria-live="polite">
          <span id="st-preview-scene-num" class="st-mono">01</span>
          <span id="st-preview-scene-role" class="st-preview-role">Scene</span>
        </div>
        <div class="st-preview-head-right">
          <span id="st-preview-source" class="st-visually-hidden" role="status">Loading preview…</span>
          <div class="st-preview-viewgroup" role="group" aria-label="Preview zoom">
            <button id="st-preview-zoom-out" class="st-preview-chip" type="button" title="Zoom out" aria-label="Zoom out">−</button>
            <button id="st-preview-zoom-level" class="st-preview-chip" type="button" title="Fit the preview" aria-label="Fit the preview">100%</button>
            <button id="st-preview-zoom-in" class="st-preview-chip" type="button" title="Zoom in" aria-label="Zoom in">+</button>
          </div>
          <div class="st-preview-spangroup" role="group" aria-label="Span">
            <button id="st-preview-span-in" class="st-preview-chip" type="button" title="Set span in at the playhead" aria-label="Set span in">In</button>
            <button id="st-preview-span-out" class="st-preview-chip" type="button" title="Set span out at the playhead" aria-label="Set span out">Out</button>
            <span id="st-preview-span" class="st-mono st-preview-span">Full</span>
          </div>
          <button id="st-preview-focus" class="st-icon-btn" type="button" title="Focus the preview (F)" aria-label="Focus the preview" aria-pressed="false"></button>
        </div>
      </div>
      <div class="st-preview-stage">
        <canvas id="st-preview-canvas" class="st-preview-canvas" width="1080" height="1920" aria-label="Story preview with safe zones and editable boxes"></canvas>
        <div id="st-box-method" class="st-box-method" role="group" aria-label="Clean method for this box" hidden>
          <button type="button" data-kind="fill">AI fill</button>
          <button type="button" data-kind="blur">Blur</button>
        </div>
        <div id="st-preview-compare" class="st-preview-compare" hidden>
          <img class="st-compare-before" alt="Before the Clean layer">
          <img class="st-compare-after" alt="After the Clean layer">
          <i class="st-compare-divider" aria-hidden="true"></i>
          <video class="st-compare-video" loop muted playsinline hidden></video>
          <div class="st-compare-head">
            <strong id="st-compare-title">Before / After</strong>
            <span id="st-compare-note">Selected Clean layer · this scene</span>
            <button id="st-compare-play" class="st-btn st-btn-ghost st-btn-small" type="button" hidden>Play</button>
            <button id="st-compare-close" class="st-icon-btn" type="button" title="Close comparison" aria-label="Close comparison">×</button>
          </div>
          <input id="st-compare-slider" class="st-compare-slider" type="range" min="0" max="100" value="50" aria-label="Compare before and after the Clean layer">
        </div>
      </div>
      <div class="st-preview-transport">
        <div class="st-preview-left">
          <span id="st-preview-time" class="st-mono st-preview-time">0:00.0</span>
          <label class="st-preview-select">
            <span class="st-visually-hidden">Safe-zone platform</span>
            <select id="st-preview-platform" aria-label="Safe-zone platform">
              <option value="auto">This shape</option>
              <option value="tiktok">TikTok</option>
              <option value="rednote">RedNote</option>
              <option value="facebook">Facebook</option>
              <option value="youtube">YouTube</option>
            </select>
          </label>
          <button id="st-preview-safe-toggle" class="st-icon-btn is-on" type="button" title="Safe zones" aria-label="Safe zones" aria-pressed="true"></button>
          <input id="st-preview-safe" type="checkbox" checked class="st-visually-hidden" tabindex="-1">
        </div>
        <div class="st-preview-center">
          <button id="st-preview-back" class="st-icon-btn" type="button" title="Back 1 second (J)" aria-label="Back 1 second"></button>
          <button id="st-preview-play" class="st-icon-btn st-preview-play" type="button" aria-label="Play preview" title="Play / pause (Space)"></button>
          <button id="st-preview-forward" class="st-icon-btn" type="button" title="Forward 1 second (L)" aria-label="Forward 1 second"></button>
        </div>
        <div class="st-preview-right">
          <button id="st-preview-aspect" class="st-preview-chip" type="button" title="Aspect ratio" aria-haspopup="menu">9:16</button>
          <button id="st-preview-resolution" class="st-preview-chip" type="button" title="Output resolution" aria-haspopup="menu">1080p</button>
          <button id="st-preview-frame" class="st-icon-btn" type="button" title="Save this frame" aria-label="Save this frame"></button>
          <button id="st-preview-hdr" class="st-preview-chip" type="button" disabled title="HDR output is not available in this build">HDR</button>
          <button id="st-preview-fps" class="st-preview-chip" type="button" title="Preview frame rate">30</button>
        </div>
        <input id="st-preview-scrub" class="st-visually-hidden" type="range" min="0" max="10" step="0.01" value="0" aria-label="Preview position" tabindex="-1">
      </div>
      <div id="st-preview-aspect-menu" class="st-preview-menu" hidden role="menu" aria-label="Aspect ratio">
        <button type="button" data-aspect="9:16">9:16</button>
        <button type="button" data-aspect="4:5">4:5</button>
        <button type="button" data-aspect="1:1">1:1</button>
        <button type="button" data-aspect="16:9">16:9</button>
        <button type="button" data-aspect="16:10">16:10</button>
      </div>
      <div id="st-preview-res-menu" class="st-preview-menu is-res" hidden role="menu" aria-label="Output resolution">
        <button type="button" data-res="720p">720p</button>
        <button type="button" data-res="1080p">1080p</button>
        <button type="button" data-res="1440p">1440p</button>
        <button type="button" data-res="4K">4K</button>
        <div class="st-preview-custom">
          <input id="st-preview-width" type="number" min="240" max="4096" step="2" aria-label="Custom width" placeholder="Width">
          <span>×</span>
          <input id="st-preview-height" type="number" min="240" max="4096" step="2" aria-label="Custom height" placeholder="Height">
          <button id="st-preview-res-apply" class="st-btn st-btn-ghost st-btn-small" type="button">Use</button>
        </div>
        <div class="st-preview-quality">
          <label><input id="st-preview-optical" type="checkbox"> Optical flow</label>
          <label><input id="st-preview-stabilize" type="checkbox"> Stabilize</label>
          <label class="st-preview-strength">Strength
            <input id="st-preview-strength" type="range" min="0" max="1" step="0.1" value="0.5">
          </label>
        </div>
      </div>
      <p id="st-preview-note" class="st-preview-note" role="status">Opening the preview…</p>
    </section>
    `;

  const $ = (selector) => root.querySelector(selector);
  const dom = {
    canvas: $("#st-preview-canvas"),
    aspect: $("#st-preview-aspect"),
    aspectMenu: $("#st-preview-aspect-menu"),
    safe: $("#st-preview-safe"),
    safeToggle: $("#st-preview-safe-toggle"),
    play: $("#st-preview-play"),
    back: $("#st-preview-back"),
    forward: $("#st-preview-forward"),
    time: $("#st-preview-time"),
    scrub: $("#st-preview-scrub"),
    note: $("#st-preview-note"),
    source: $("#st-preview-source"),
    storyBtn: $("#st-preview-story-btn"),
    storyMenu: $("#st-preview-story-menu"),
    storyNum: $("#st-preview-story-num"),
    storyTitle: $("#st-preview-story-title"),
    zoomOut: $("#st-preview-zoom-out"),
    zoomIn: $("#st-preview-zoom-in"),
    zoomLevel: $("#st-preview-zoom-level"),
    spanIn: $("#st-preview-span-in"),
    spanOut: $("#st-preview-span-out"),
    spanText: $("#st-preview-span"),
    compare: $("#st-preview-compare"),
    compareBefore: $("#st-preview-compare .st-compare-before"),
    compareAfter: $("#st-preview-compare .st-compare-after"),
    compareVideo: $("#st-preview-compare .st-compare-video"),
    compareTitle: $("#st-compare-title"),
    compareNote: $("#st-compare-note"),
    comparePlay: $("#st-compare-play"),
    compareSlider: $("#st-compare-slider"),
    compareClose: $("#st-compare-close"),
    sceneNum: $("#st-preview-scene-num"),
    sceneRole: $("#st-preview-scene-role"),
    platform: $("#st-preview-platform"),
    focus: $("#st-preview-focus"),
    resolution: $("#st-preview-resolution"),
    resMenu: $("#st-preview-res-menu"),
    width: $("#st-preview-width"),
    height: $("#st-preview-height"),
    resApply: $("#st-preview-res-apply"),
    frame: $("#st-preview-frame"),
    fps: $("#st-preview-fps"),
    optical: $("#st-preview-optical"),
    stabilize: $("#st-preview-stabilize"),
    strength: $("#st-preview-strength"),
    tools: Array.from(root.querySelectorAll(".st-preview-tool")),
    boxMethod: root.querySelector("#st-box-method"),
  };
  const ctx = dom.canvas.getContext("2d");

  for (const button of dom.tools) {
    button.prepend(icon(
      button.dataset.tool === "select" ? "cursor"
        : button.dataset.tool === "paint" ? "brush" : "square",
      { size: 13 },
    ));
  }
  dom.focus?.prepend(icon("expand", { size: 15 }));
  dom.back?.append(icon("arrow-left", { size: 15 }));
  dom.forward?.append(icon("arrow-right", { size: 15 }));
  dom.safeToggle?.prepend(icon("eye", { size: 14 }));
  dom.frame?.prepend(icon("scissors", { size: 14 }));

  function setNote(message, tone = "") {
    dom.note.textContent = message || "";
    dom.note.dataset.tone = tone;
  }

  function sourceLabel() {
    if (rebuilding) return "Rebuilding preview…";
    if (frameState === "loading") return "Loading frame…";
    if (frameState === "stale") return "Refreshing frame…";
    if (frameState === "bad-time") return "No frame at this time";
    if (frameState === "locked") return "Preview needs sign-in";
    if (frameState === "error") return "Preview failed";
    if (pendingPlay && !proxyReady) return "Preparing playback…";
    if (videoPlaying && proxyReady) return "Fast preview";
    if (frameReady) return "Exact frame";
    if (proxyReady) return "Fast preview";
    if (frameAvailable === false && proxyFailed) return "Preview not ready";
    return "Loading preview…";
  }

  function updateSource() {
    dom.source.textContent = sourceLabel();
    dom.source.dataset.tone = frameReady ? "ok"
      : frameState === "error" || frameState === "locked" ? "bad"
        : proxyReady ? "ok" : "quiet";

    if (rebuilding) {
      setNote("Rebuilding preview for the new cut. The old frame stays up until the new one is ready.");
    } else if (pendingPlay && !proxyReady) {
      setNote("Building the playback copy with sound. This takes a few seconds the first time.");
    } else if (videoPlaying) {
      setNote("Playing a 540p copy with sound. Pause to see the exact frame.");
    } else if (frameReady) {
      setNote("Exact frame from the current edit. Pause or scrub to refresh it.");
    } else if (proxyReady) {
      setNote("Fast 540p preview. Pause to load the exact frame.");
    } else if (!frameAvailable && proxyFailed) {
      setNote("Preview is not ready in this build yet. Edits save as you go.");
    } else if (frameState === "bad-time") {
      setNote("There is no frame at this position. Move the playhead and try again.");
    } else if (frameState === "locked") {
      setNote("The server refused the preview. Open Settings to check the access token.");
    } else if (frameState === "error") {
      setNote("The preview could not load. Edits still save.");
    } else {
      setNote("Loading the first frame…");
    }
  }

  function drawCover(source, width, height) {
    const sw = source.videoWidth || source.naturalWidth || source.width;
    const sh = source.videoHeight || source.naturalHeight || source.height;
    if (!sw || !sh) return;
    const scale = Math.max(width / sw, height / sh);
    const dw = sw * scale;
    const dh = sh * scale;
    ctx.drawImage(source, (width - dw) / 2, (height - dh) / 2, dw, dh);
  }

  function drawPlaceholder(width, height) {
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "#19191d");
    gradient.addColorStop(1, "#0b0b0d");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    ctx.fillStyle = "rgba(232, 162, 102, 0.14)";
    ctx.beginPath();
    ctx.arc(width / 2, height * 0.42, width * 0.16, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(232, 162, 102, 0.55)";
    ctx.lineWidth = 5;
    ctx.stroke();

    ctx.textAlign = "center";
    ctx.fillStyle = "#f1efe9";
    ctx.font = "600 42px ui-sans-serif, -apple-system, sans-serif";
    ctx.fillText("Preview appears here", width / 2, height * 0.56);
    ctx.fillStyle = "#a3a1a6";
    ctx.font = "400 30px ui-sans-serif, -apple-system, sans-serif";
    ctx.fillText("Edits save while you work.", width / 2, height * 0.56 + 52);
  }

  function drawSafeZones(width, height) {
    if (!state.showSafeZones) return;
    const zones = safeZoneRects(state.aspect, state.platform);
    const px = (zone) => ({
      x: zone.x * width, y: zone.y * height, w: zone.w * width, h: zone.h * height,
    });
    const safe = px(zones.safe);
    ctx.save();
    // One rule on screen: shaded means the app covers it, keep text off it.
    ctx.fillStyle = "rgba(5, 5, 6, 0.46)";
    ctx.beginPath();
    ctx.rect(0, 0, width, height);
    ctx.rect(safe.x, safe.y, safe.w, safe.h);
    ctx.fill("evenodd");
    for (const zone of zones.reserved) {
      const area = px(zone);
      const x = Math.max(area.x, safe.x);
      const y = Math.max(area.y, safe.y);
      const right = Math.min(area.x + area.w, safe.x + safe.w);
      const bottom = Math.min(area.y + area.h, safe.y + safe.h);
      if (right > x && bottom > y) ctx.fillRect(x, y, right - x, bottom - y);
    }

    ctx.setLineDash([18, 12]);
    ctx.lineWidth = 4;
    ctx.strokeStyle = "rgba(241, 239, 233, 0.55)";
    ctx.strokeRect(safe.x, safe.y, safe.w, safe.h);
    ctx.setLineDash([]);

    ctx.font = "600 42px ui-sans-serif, -apple-system, sans-serif";
    ctx.textBaseline = "top";
    ctx.textAlign = "left";
    ctx.fillStyle = "rgba(241, 239, 233, 0.78)";
    ctx.fillText("Text safe area", safe.x + 16, safe.y + 14);
    const buttons = zones.reserved.find((zone) => zone.name === "Buttons");
    if (buttons) {
      const area = px(buttons);
      ctx.textAlign = "right";
      ctx.fillStyle = "rgba(241, 239, 233, 0.6)";
      ctx.font = "600 30px ui-sans-serif, -apple-system, sans-serif";
      ctx.fillText("App", width - 12, area.y + 14);
      ctx.fillText("buttons", width - 12, area.y + 50);
    }
    ctx.restore();
  }

  /**
   * A trim keeps layers that fell fully outside with `hidden: true` and their
   * old times. The renderer skips them; the preview must too, or a removed
   * hook would draw over the new first sentence.
   */
  function visibleEdit(edit) {
    if (!edit) return edit;
    const graphics = Array.isArray(edit.graphics) ? edit.graphics : [];
    const pins = new Set(["source", "story_start", "story_end"]);
    const visible = graphics
      .filter((layer) => {
        if (!layer || layer.hidden) return false;
        const kind = layer.type === "text" ? "text" : "effects";
        return !state.hiddenLayers.has(`${kind}:${layer.id}`);
      })
      .map((layer) => {
        // "story_start" is a pin (the R2 schema stores it under `pin`). If a
        // freshly added hook still carries it in `anchor`, draw the kind's
        // usual position rather than the fallback centre.
        if (!pins.has(String(layer?.anchor || ""))) return layer;
        return {
          ...layer,
          anchor: TEXT_KINDS[layer.kind]?.anchor || "center",
        };
      });
    if (visible.length === graphics.length
      && visible.every((layer, index) => layer === graphics[index])) {
      return edit;
    }
    return { ...edit, graphics: visible };
  }

  function visibleCaptions(captions) {
    if (!captions || !Array.isArray(captions.cues)) return captions;
    const cues = captions.cues.filter((cue) => !state.hiddenLayers.has(`captions:${cue.id}`));
    if (cues.length === captions.cues.length) return captions;
    return { ...captions, cues };
  }

  function currentCrop() {
    return cropAt({
      edit: state.edit,
      job: state.job,
      story: state.story,
      time: state.time,
      aspect: state.aspect,
    });
  }

  function cleanLayers() {
    return (state.edit?.clean || []).filter((layer) => layer && layer.id);
  }

  function hiddenKey(kind, id) {
    return `${kind}:${id}`;
  }

  function sourceTime() {
    return sourceTimeAt(state.story, state.time);
  }

  function cleanRects() {
    const crop = currentCrop();
    const time = sourceTime();
    const selected = state.selected?.kind === "clean" ? state.selected.id : "";
    return cleanLayers().map((layer) => {
      const frame = boxToFrame(layer.box, crop);
      return {
        layer,
        frame,
        active: layerActive(layer, time),
        selected: layer.id === selected,
        hidden: state.hiddenLayers.has(hiddenKey("clean", layer.id)),
      };
    });
  }

  function pxRect(frame, width, height) {
    return {
      x: frame.x * width,
      y: frame.y * height,
      w: frame.w * width,
      h: frame.h * height,
    };
  }

  function cleanAt(frame, width, height) {
    const rects = cleanRects().filter((item) => !item.hidden);
    for (let index = rects.length - 1; index >= 0; index -= 1) {
      const item = rects[index];
      const clipped = visibleRect(item.frame);
      if (!clipped) continue;
      if (insideRect(clipped, frame)) return item;
    }
    return null;
  }

  function selectedClean() {
    if (state.selected?.kind !== "clean") return null;
    return cleanRects().find((item) => item.selected && !item.hidden) || null;
  }

  function drawEdgeMarkers(frame, width, height) {
    const size = Math.max(8, Math.round(width * 0.012));
    const colour = "#e8a266";
    const centerX = clamp((frame.x + frame.w / 2) * width, 0, width);
    const centerY = clamp((frame.y + frame.h / 2) * height, 0, height);
    const marks = [];
    if (frame.x < 0) marks.push([0, centerY, 1, 0]);
    if (frame.x + frame.w > 1) marks.push([width, centerY, -1, 0]);
    if (frame.y < 0) marks.push([centerX, 0, 0, 1]);
    if (frame.y + frame.h > 1) marks.push([centerX, height, 0, -1]);
    ctx.save();
    ctx.fillStyle = colour;
    for (const [x, y, dx, dy] of marks) {
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + dx * size + (dy ? size / 2 : 0), y + dy * size + (dx ? size / 2 : 0));
      ctx.lineTo(x + dx * size - (dy ? size / 2 : 0), y + dy * size - (dx ? size / 2 : 0));
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  function foundRects() {
    if (!state.foundText.length) return [];
    const added = new Set(
      (state.edit?.clean || [])
        .map((layer) => String(layer?.tracklet_id || ""))
        .filter(Boolean),
    );
    const crop = currentCrop();
    const time = sourceTime();
    return state.foundText
      .filter((row) => row?.box && !added.has(String(row.id || "")))
      .map((row) => ({
        row,
        frame: boxToFrame(row.box, crop),
        active: layerActive({ ranges: row.ranges || [] }, time),
      }));
  }

  function drawFoundBoxes(width, height) {
    for (const item of foundRects()) {
      if (!item.active) continue;
      const clipped = visibleRect(item.frame);
      if (!clipped) continue;
      const rect = pxRect(clipped, width, height);
      const colour = item.row.blocked
        ? "#77777f"
        : item.row.ticked ? "#e8a266" : "#7b9bb8";
      ctx.save();
      const focused = String(item.row.id || "") === String(state.foundFocus || "");
      ctx.globalAlpha = focused ? 1 : item.row.blocked ? 0.5 : item.row.ticked ? 0.95 : 0.7;
      ctx.strokeStyle = colour;
      ctx.lineWidth = focused ? Math.max(4, width * 0.004) : Math.max(2, width * 0.0024);
      ctx.setLineDash([Math.max(5, width * 0.007), Math.max(4, width * 0.005)]);
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
      if (item.row.ticked && !item.row.blocked) {
        const label = String(item.row.text || "Text").slice(0, 34);
        ctx.font = `600 ${Math.max(16, Math.round(width * 0.022))}px ui-sans-serif, -apple-system, sans-serif`;
        const labelWidth = Math.min(rect.w, ctx.measureText(label).width + 16);
        const labelY = Math.max(0, rect.y - Math.max(22, width * 0.034));
        ctx.fillStyle = "rgba(10, 10, 12, 0.8)";
        ctx.fillRect(rect.x, labelY, labelWidth, Math.max(20, width * 0.032));
        ctx.fillStyle = "#f1efe9";
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(label, rect.x + 8, labelY + 4);
      }
      ctx.restore();
    }
  }

  function drawCleanBoxes(width, height) {
    const rects = cleanRects();
    const handle = Math.max(18, Math.round(width * 0.02));
    for (const item of rects) {
      if (item.hidden) continue;
      const clipped = visibleRect(item.frame);
      if (!clipped) {
        if (item.selected) drawEdgeMarkers(item.frame, width, height);
        continue;
      }
      const rect = pxRect(clipped, width, height);
      const colour = LAYER_COLOURS.clean;
      ctx.save();
      ctx.globalAlpha = item.active ? 1 : 0.34;
      ctx.strokeStyle = colour;
      ctx.lineWidth = item.selected ? Math.max(3, width * 0.004) : Math.max(2, width * 0.0022);
      ctx.setLineDash(item.selected ? [] : [Math.max(6, width * 0.008), Math.max(4, width * 0.006)]);
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
      const mask = item.layer?.mask;
      const strokes = mask && !Array.isArray(mask) ? (mask.strokes || []) : (mask ? [{ r: mask[0]?.r || 0.025, points: mask }] : []);
      const onVideo = mask && !Array.isArray(mask) && mask.space === "source";
      const crop = currentCrop();
      const points = strokes.flatMap((stroke) => (
        (stroke.points || []).map((point) => (onVideo
          ? {
            x: (point.x - crop.x) / crop.w,
            y: (point.y - crop.y) / crop.h,
            r: (stroke.r || 0.025) / crop.w,
          }
          : { ...point, r: stroke.r || 0.025 }))
      ));
      if (points.length) {
        ctx.globalAlpha = item.active ? 0.5 : 0.22;
        ctx.fillStyle = colour;
        for (const point of points) {
          ctx.beginPath();
          ctx.arc(
            point.x * width,
            point.y * height,
            Math.max(2, point.r * width),
            0,
            Math.PI * 2,
          );
          ctx.fill();
        }
        ctx.globalAlpha = item.active ? 1 : 0.34;
      }
      if (item.active) {
        const tag = item.layer.kind === "fill" ? "AI fill" : item.layer.kind === "blur" ? "Blur" : "Old";
        const size = Math.max(16, Math.round(width * 0.02));
        ctx.setLineDash([]);
        ctx.font = `600 ${size}px ui-sans-serif, -apple-system, sans-serif`;
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        const tagWidth = ctx.measureText(tag).width + size;
        ctx.fillStyle = "rgba(10, 10, 12, 0.82)";
        ctx.fillRect(rect.x, rect.y, tagWidth, size * 1.5);
        ctx.fillStyle = colour;
        ctx.fillText(tag, rect.x + size / 2, rect.y + size * 0.25);
      }
      if (item.selected) {
        const points = [
          [rect.x, rect.y], [rect.x + rect.w / 2, rect.y], [rect.x + rect.w, rect.y],
          [rect.x + rect.w, rect.y + rect.h / 2], [rect.x + rect.w, rect.y + rect.h],
          [rect.x + rect.w / 2, rect.y + rect.h], [rect.x, rect.y + rect.h],
          [rect.x, rect.y + rect.h / 2],
        ];
        ctx.setLineDash([]);
        ctx.fillStyle = colour;
        for (const [hx, hy] of points) {
          ctx.fillRect(hx - handle / 2, hy - handle / 2, handle, handle);
        }
        const label = String(item.layer.label || CLEAN_LABELS[item.layer.kind] || "Remove text").slice(0, 42);
        ctx.font = `600 ${Math.max(18, Math.round(width * 0.026))}px ui-sans-serif, -apple-system, sans-serif`;
        const textWidth = Math.min(rect.w, ctx.measureText(label).width + 24);
        const labelY = Math.max(0, rect.y - Math.max(26, width * 0.04));
        ctx.fillStyle = "rgba(10, 10, 12, 0.86)";
        ctx.fillRect(rect.x, labelY, textWidth, Math.max(24, width * 0.038));
        ctx.fillStyle = "#f1efe9";
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(label, rect.x + 10, labelY + 5);
      }
      ctx.restore();
      if (item.selected) drawEdgeMarkers(item.frame, width, height);
    }
  }

  function drawDrawPreview(width, height) {
    if (!drawPreview) return;
    const rect = pxRect(drawPreview, width, height);
    ctx.save();
    ctx.fillStyle = "rgba(232, 162, 102, 0.16)";
    ctx.strokeStyle = "#e8a266";
    ctx.lineWidth = Math.max(2, width * 0.003);
    ctx.setLineDash([Math.max(6, width * 0.008), Math.max(4, width * 0.006)]);
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
    ctx.restore();
  }

  function drawSelection(width, height) {
    if (!state.selected || !state.edit) return;
    if (state.selected.kind === "clean") return;
    let rect = null;
    let label = "Selected";
    if (state.selected.kind === "text") {
      const layer = (state.edit.graphics || [])
        .find((item) => item.id === state.selected.id && !item.hidden);
      if (!layer) return;
      rect = graphicRect(layer);
      label = layer.text || "Text";
    } else if (state.selected.kind === "captions") {
      const style = state.captions?.style || {};
      const zone = style.safe_zone || { bottom: 0.16, left: 0.08, right: 0.08 };
      const bottom = numberOr(zone.bottom, 0.16);
      rect = {
        x: numberOr(zone.left, 0.08),
        y: 1 - bottom - 0.06,
        w: 1 - numberOr(zone.left, 0.08) - numberOr(zone.right, 0.08),
        h: Math.max(0.04, bottom + 0.02),
      };
      label = "Captions";
    } else {
      return;
    }

    const x = rect.x * width;
    const y = rect.y * height;
    const w = rect.w * width;
    const h = rect.h * height;
    const colour = state.selected.kind === "captions"
      ? LAYER_COLOURS.captions
      : LAYER_COLOURS.text;
    ctx.save();
    ctx.strokeStyle = colour;
    ctx.lineWidth = 6;
    ctx.strokeRect(x, y, w, h);
    const handle = 14;
    ctx.fillStyle = colour;
    const points = [
      [x, y], [x + w / 2, y], [x + w, y],
      [x + w, y + h / 2], [x + w, y + h],
      [x + w / 2, y + h], [x, y + h], [x, y + h / 2],
    ];
    for (const [hx, hy] of points) {
      ctx.fillRect(hx - handle / 2, hy - handle / 2, handle, handle);
    }
    ctx.font = "600 28px ui-sans-serif, -apple-system, sans-serif";
    const text = String(label).slice(0, 42);
    const textWidth = Math.min(w, ctx.measureText(text).width + 28);
    ctx.fillStyle = "rgba(10, 10, 12, 0.82)";
    ctx.fillRect(x, Math.max(0, y - 44), textWidth, 38);
    ctx.fillStyle = "#f1efe9";
    ctx.textAlign = "left";
    ctx.fillText(text, x + 12, Math.max(28, y - 16));
    ctx.restore();
  }

  function draw() {
    if (!ctx) return;
    const width = dom.canvas.width;
    const height = dom.canvas.height;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#050506";
    ctx.fillRect(0, 0, width, height);

    let source = null;
    if (videoPlaying && proxyReady && proxyVideo && proxyVideo.readyState >= 2) source = proxyVideo;
    else if (frameReady && frameImage?.complete) source = frameImage;
    else if (proxyReady && proxyVideo && proxyVideo.readyState >= 2) source = proxyVideo;

    if (source) {
      ctx.save();
      if (source === proxyVideo) {
        ctx.filter = state.hiddenLayers.has("color:color")
          ? "none"
          : colorFilter(state.edit?.color);
      }
      drawCover(source, width, height);
      ctx.restore();
      // The proxy is the raw story range; the exact frame already has every
      // layer burned in, so only the proxy gets the live overlay.
      if (source === proxyVideo) {
        drawOverlay(
          ctx, visibleEdit(state.edit), visibleCaptions(state.captions),
          state.time, width, height,
        );
      }
    } else {
      drawPlaceholder(width, height);
    }

    drawSafeZones(width, height);
    drawFoundBoxes(width, height);
    drawCleanBoxes(width, height);
    placeMethodSwitch();
    drawSelection(width, height);
    drawDrawPreview(width, height);
    drawPaintPreview(width, height);
    drawBorder(width, height);
  }

  function drawPaintPreview(width, height) {
    if (!state.paintPoints.length) return;
    ctx.save();
    ctx.globalAlpha = 0.55;
    ctx.fillStyle = LAYER_COLOURS.clean;
    for (const point of state.paintPoints) {
      ctx.beginPath();
      ctx.arc(point.x * width, point.y * height, Math.max(2, point.r * width), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawBorder(width, height) {
    const border = state.edit?.border;
    const size = Math.max(0, Number(border?.width) || 0);
    if (!size) return;
    const scale = Math.min(width, height) / 1080;
    const line = Math.max(1, size * scale);
    const radius = Math.max(0, (Number(border?.radius) || 0) * scale);
    ctx.save();
    ctx.strokeStyle = border?.color || "#f1efe9";
    ctx.lineWidth = line;
    const inset = line / 2;
    if (radius > 0 && ctx.roundRect) {
      ctx.beginPath();
      ctx.roundRect(inset, inset, width - line, height - line, radius);
      ctx.stroke();
    } else {
      ctx.strokeRect(inset, inset, width - line, height - line);
    }
    ctx.restore();
  }

  function applyAspect(aspect) {
    const next = CANVAS[aspect] ? aspect : "9:16";
    if (state.aspect === next && dom.canvas.width === CANVAS[next].width) return;
    state.aspect = next;
    const size = CANVAS[next];
    dom.canvas.width = size.width;
    dom.canvas.height = size.height;
    dom.aspect.textContent = next;
    for (const item of root.querySelectorAll("#st-preview-aspect-menu [data-aspect]")) {
      item.classList.toggle("is-active", item.dataset.aspect === next);
      item.setAttribute("aria-checked", item.dataset.aspect === next ? "true" : "false");
    }
    draw();
  }

  function updateTransport() {
    const duration = Math.max(0.1, numberOr(state.duration, 0.1));
    dom.scrub.max = String(duration);
    dom.scrub.value = String(clamp(state.time, 0, duration));
    dom.time.textContent = formatTime(state.time);
    dom.play.textContent = playing ? "❚❚" : "▶";
    dom.play.setAttribute("aria-label", playing ? "Pause preview" : "Play preview");
  }

  function setTime(value, { notify = false } = {}) {
    const duration = Math.max(0.1, numberOr(state.duration, 0.1));
    state.time = clamp(numberOr(value), 0, duration);
    updateTransport();
    draw();
    if (notify) callbacks.onTime(state.time);
  }

  function clearFrame() {
    frameReady = false;
    if (frameImage?.src?.startsWith("blob:")) URL.revokeObjectURL(frameImage.src);
    frameImage = null;
    if (frameController) {
      frameController.abort();
      frameController = null;
    }
  }

  function resetProxy() {
    if (proxyVideo) {
      proxyVideo.pause();
      proxyVideo.removeAttribute("src");
      proxyVideo.load();
      proxyVideo = null;
    }
    proxyReady = false;
    proxyFailed = false;
    proxyRequested = false;
    videoPlaying = false;
  }

  function ensureProxy() {
    if (disposed || !state.edit || !state.jobId || proxyRequested) return;
    proxyRequested = true;
    const video = document.createElement("video");
    // Sound on: the creator judges music, voice and ducking here.
    video.muted = false;
    video.volume = 1;
    video.playsInline = true;
    video.preload = "auto";
    video.src = proxyPath(state.jobId, state.edit.id);
    video.addEventListener("loadedmetadata", () => {
      if (disposed) return;
      proxyReady = true;
      proxyFailed = false;
      rebuilding = false;
      video.currentTime = Math.min(state.time, Math.max(0, (video.duration || state.duration) - 0.05));
      if (pendingPlay && playing) {
        pendingPlay = false;
        startVideo();
      }
      updateSource();
      draw();
    });
    video.addEventListener("seeked", () => {
      if (!disposed && !frameReady) draw();
    });
    video.addEventListener("timeupdate", () => {
      if (disposed || !videoPlaying) return;
      const duration = Math.max(0.1, numberOr(state.duration, 0.1));
      state.time = clamp(video.currentTime, 0, duration);
      updateTransport();
      draw();
      callbacks.onTime(state.time);
      if (state.time >= duration - 0.03) {
        if (state.loop) {
          state.time = 0;
          video.currentTime = 0;
          video.play().catch(() => {});
          updateTransport();
          scheduleFrame(0);
          return;
        }
        videoPlaying = false;
        playing = false;
        video.pause();
        updateTransport();
        scheduleFrame(0);
      }
    });
    video.addEventListener("error", () => {
      if (disposed) return;
      proxyFailed = true;
      proxyReady = false;
      rebuilding = false;
      if (pendingPlay && playing) {
        // No playable copy: fall back to stepping exact frames, silently.
        pendingPlay = false;
        startClock();
      }
      updateSource();
      draw();
    });
    proxyVideo = video;
  }

  function scheduleFrame(delay = 160) {
    if (disposed || !state.edit || !frameAvailable) return;
    if (frameTimer) window.clearTimeout(frameTimer);
    frameTimer = window.setTimeout(() => {
      frameTimer = 0;
      void loadFrame(state.time);
    }, delay);
  }

  // Renders open with a 0.12 s fade from black, so the true first frame is
  // black. The still preview shows the first visible frame instead.
  function frameTime(time) {
    const lead = Math.min(FADE_IN_SKIP, Math.max(0, numberOr(state.duration, 0) / 2));
    return Math.max(numberOr(time, 0), lead);
  }

  async function loadFrame(time) {
    if (disposed || !state.edit || !state.jobId || !frameAvailable) return;
    if (frameController) frameController.abort();
    const seq = ++frameSeq;
    const controller = new AbortController();
    frameController = controller;
    frameState = "loading";
    updateSource();
    try {
      const response = await fetchFrame(
        framePath(state.jobId, state.edit.id, frameTime(time), "draft"),
        { signal: controller.signal },
      );
      if (disposed || seq !== frameSeq) return;

      if (response.ok) {
        const blob = await response.blob();
        if (disposed || seq !== frameSeq) return;
        const url = URL.createObjectURL(blob);
        const image = new Image();
        image.onload = () => {
          if (disposed || seq !== frameSeq) {
            URL.revokeObjectURL(url);
            return;
          }
          if (frameImage && frameImage.src?.startsWith("blob:")) {
            URL.revokeObjectURL(frameImage.src);
          }
          frameImage = image;
          frameReady = true;
          frameAvailable = true;
          frameState = "ready";
          rebuilding = false;
          updateSource();
          draw();
        };
        image.onerror = () => {
          URL.revokeObjectURL(url);
          if (disposed || seq !== frameSeq) return;
          frameState = "error";
          rebuilding = false;
          updateSource();
        };
        image.src = url;
        return;
      }

      if (response.status === 409) {
        frameState = "stale";
        frameReady = false;
        rebuilding = false;
        updateSource();
        callbacks.onStale();
        return;
      }
      if (response.status === 404 || response.status === 405 || response.status === 501) {
        frameAvailable = false;
        frameReady = false;
        frameState = "unavailable";
        rebuilding = false;
        updateSource();
        ensureProxy();
        draw();
        return;
      }
      if (response.status === 422) {
        frameState = "bad-time";
        rebuilding = false;
        updateSource();
        return;
      }
      if (response.status === 401 || response.status === 403) {
        frameState = "locked";
        rebuilding = false;
        updateSource();
        return;
      }
      frameState = "error";
      rebuilding = false;
      updateSource();
    } catch (error) {
      if (error?.name === "AbortError" || disposed) return;
      frameState = "error";
      updateSource();
    } finally {
      if (frameController === controller) frameController = null;
    }
  }

  function startClock() {
    lastTick = performance.now();
    lastFrameAt = 0;
    const tick = (now) => {
      if (!playing || disposed) return;
      const delta = Math.min(0.12, Math.max(0, (now - lastTick) / 1000));
      lastTick = now;
      const duration = Math.max(0.1, numberOr(state.duration, 0.1));
      const next = state.time + delta;
      if (next >= duration) {
        if (state.loop) {
          setTime(0, { notify: true });
          lastTick = now;
          raf = window.requestAnimationFrame(tick);
          return;
        }
        setTime(duration, { notify: true });
        pause();
        return;
      }
      setTime(next, { notify: true });
      if (frameAvailable && now - lastFrameAt > 220) {
        lastFrameAt = now;
        void loadFrame(state.time);
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
  }

  function play() {
    if (disposed) return;
    ensureProxy();
    if (playing) {
      pause();
      return;
    }
    playing = true;
    if (proxyReady && proxyVideo) {
      startVideo();
    } else if (proxyFailed) {
      startClock();
    } else {
      pendingPlay = true;
    }
    updateTransport();
    updateSource();
  }

  function startVideo() {
    if (!proxyVideo) return;
    if (state.time >= state.duration - 0.05) setTime(0);
    proxyVideo.currentTime = state.time;
    videoPlaying = true;
    updateSource();
    proxyVideo.play().catch(() => {
      videoPlaying = false;
      updateSource();
      startClock();
    });
  }

  function pause() {
    playing = false;
    pendingPlay = false;
    if (raf) window.cancelAnimationFrame(raf);
    raf = 0;
    if (videoPlaying && proxyVideo) proxyVideo.pause();
    videoPlaying = false;
    updateTransport();
    updateSource();
    if (frameAvailable) scheduleFrame(0);
  }

  function togglePlay() {
    if (playing || videoPlaying) pause();
    else play();
  }

  // The parent owns the duration; an Edit's `story_ref.duration` is only a
  // fallback for direct callers. A trim updates both together.
  function setEdit(edit, { keepTime = false } = {}) {
    const previous = state.edit;
    const previousId = previous?.id || "";
    const nextId = edit?.id || "";
    // A normal autosave returns a new Edit version for the same cut. Keeping
    // the proxy alive is what lets layers save without stopping playback.
    const sameCut = Boolean(previousId && nextId)
      && String(previous?.story_ref?.clip_hash || "") === String(edit?.story_ref?.clip_hash || "")
      && String(previous?.aspect || "") === String(edit?.aspect || "");
    state.edit = edit || null;
    if (!durationOwned) {
      const fallback = numberOr(edit?.story_ref?.duration);
      if (fallback > 0) state.duration = Math.max(0.1, fallback);
    }
    if (!keepTime) setTime(state.time);
    if (previousId !== nextId && !sameCut) {
      rebuilding = Boolean(state.edit);
      clearFrame();
      resetProxy();
      frameAvailable = true;
      frameState = "idle";
      frameReady = false;
      if (state.edit) {
        void loadFrame(state.time);
        // Build the playable copy now so Play starts with sound right away.
        ensureProxy();
      }
    } else {
      scheduleFrame(80);
    }
    updateTransport();
    updateSource();
    draw();
  }

  function invalidate() {
    if (!state.edit) return;
    frameReady = false;
    frameImage = null;
    frameState = "idle";
    scheduleFrame(120);
    draw();
  }

  function setData({
    aspect, edit, captions, duration, selected, jobId, job, story, hiddenLayers, foundText,
  } = {}) {
    if (jobId && jobId !== state.jobId) {
      state.jobId = jobId;
      rebuilding = false;
      clearFrame();
      resetProxy();
    }
    if (aspect) applyAspect(aspect);
    if (edit?.output?.width && edit?.output?.height) {
      output = {
        resolution: `${edit.output.width}×${edit.output.height}`,
        width: Number(edit.output.width),
        height: Number(edit.output.height),
        fps: Number(edit.output.fps) || 30,
        optical_flow: Boolean(edit.output.optical_flow),
        stabilize: Boolean(edit.output.stabilize),
        strength: Number(edit.output.strength ?? 0.5),
      };
      paintOutput();
    }
    if (job !== undefined) state.job = job;
    if (story !== undefined) state.story = story;
    if (hiddenLayers !== undefined) {
      state.hiddenLayers = hiddenLayers instanceof Set ? hiddenLayers : new Set(hiddenLayers || []);
    }
    if (foundText !== undefined) {
      state.foundText = Array.isArray(foundText) ? foundText : [];
    }
    if (captions !== undefined) state.captions = captions;
    if (selected !== undefined) state.selected = selected;
    if (edit !== undefined) setEdit(edit);
    // Apply the parent's duration after the Edit so the scrubber, the frame
    // time and the playhead all read the same source.
    if (typeof duration === "number" && Number.isFinite(duration)) {
      durationOwned = true;
      state.duration = Math.max(0.1, duration);
      const clamped = clamp(state.time, 0, state.duration);
      if (clamped !== state.time) {
        state.time = clamped;
        // The new cut is shorter than the old playhead: ask for its frame.
        scheduleFrame(0);
      }
    }
    if (edit === undefined) draw();
    updateSource();
    updateTransport();
  }

  function seek(value) {
    pauseClockOnly();
    const duration = Math.max(0.1, numberOr(state.duration, 0.1));
    const target = clamp(numberOr(value), 0, duration);
    state.time = target;
    updateTransport();
    if (proxyReady && proxyVideo) {
      proxyVideo.currentTime = Math.min(target, Math.max(0, (proxyVideo.duration || duration) - 0.05));
    }
    draw();
    scheduleFrame(140);
    callbacks.onTime(state.time);
  }

  function pauseClockOnly() {
    if (!playing) return;
    playing = false;
    if (raf) window.cancelAnimationFrame(raf);
    raf = 0;
    if (videoPlaying && proxyVideo) proxyVideo.pause();
    videoPlaying = false;
    updateTransport();
  }

  function step(delta) {
    pauseClockOnly();
    seek(state.time + delta);
  }

  function canvasPoint(event) {
    const box = dom.canvas.getBoundingClientRect();
    return {
      x: (event.clientX - box.left) * (dom.canvas.width / Math.max(1, box.width)),
      y: (event.clientY - box.top) * (dom.canvas.height / Math.max(1, box.height)),
    };
  }

  function framePoint(event) {
    const point = canvasPoint(event);
    return { x: point.x / dom.canvas.width, y: point.y / dom.canvas.height };
  }

  function applyViewTransform() {
    const zoom = state.viewZoom || 1;
    if (zoom <= 1.001) {
      state.viewPan = { x: 0, y: 0 };
      dom.canvas.style.transform = "";
    } else {
      dom.canvas.style.transform = `translate(${state.viewPan.x}px, ${state.viewPan.y}px) scale(${zoom})`;
    }
    if (dom.zoomLevel) dom.zoomLevel.textContent = `${Math.round(zoom * 100)}%`;
    dom.canvas.style.cursor = zoom > 1.001 ? "grab" : "";
  }

  function applyViewZoom(value) {
    state.viewZoom = Math.max(1, Math.min(3, Number(value) || 1));
    const limit = Math.max(0, (state.viewZoom - 1) * (dom.canvas.clientWidth || 300) * 0.5);
    state.viewPan = {
      x: Math.max(-limit, Math.min(limit, state.viewPan.x || 0)),
      y: Math.max(-limit, Math.min(limit, state.viewPan.y || 0)),
    };
    applyViewTransform();
  }

  dom.zoomOut?.addEventListener("click", () => applyViewZoom((state.viewZoom || 1) - 0.1));
  dom.zoomIn?.addEventListener("click", () => applyViewZoom((state.viewZoom || 1) + 0.1));
  dom.zoomLevel?.addEventListener("click", () => applyViewZoom(1));

  dom.storyBtn?.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = dom.storyMenu?.hidden !== false;
    if (dom.storyMenu) dom.storyMenu.hidden = !open;
    dom.storyBtn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  dom.storyMenu?.addEventListener("click", (event) => event.stopPropagation());
  document.addEventListener("click", () => {
    if (dom.storyMenu) dom.storyMenu.hidden = true;
    dom.storyBtn?.setAttribute("aria-expanded", "false");
  });

  function applyCompare(value) {
    const position = Math.max(0, Math.min(100, Number(value) || 0));
    if (dom.compareAfter) dom.compareAfter.style.clipPath = `inset(0 0 0 ${position}%)`;
    const divider = dom.compare?.querySelector(".st-compare-divider");
    if (divider) divider.style.left = `${position}%`;
  }

  function stopCompareVideo() {
    if (!dom.compareVideo) return;
    dom.compareVideo.pause();
    dom.compareVideo.removeAttribute("src");
    dom.compareVideo.hidden = true;
    if (dom.comparePlay) dom.comparePlay.textContent = "Play";
  }

  dom.comparePlay?.addEventListener("click", () => {
    const video = dom.compareVideo;
    if (!video) return;
    video.hidden = !video.hidden;
    if (video.hidden) video.pause();
    else void video.play().catch(() => {});
    dom.comparePlay.textContent = video.hidden ? "Play" : "Compare";
  });
  dom.compareSlider?.addEventListener("input", () => applyCompare(dom.compareSlider.value));
  dom.compareClose?.addEventListener("click", () => {
    stopCompareVideo();
    dom.compare.hidden = true;
    placeMethodSwitch();
    dom.compareBefore.removeAttribute("src");
    dom.compareAfter.removeAttribute("src");
  });

  /** The AI fill or Blur switch sits on the selected box. */
  function placeMethodSwitch() {
    const node = dom.boxMethod;
    if (!node) return;
    const item = cleanRects().find((row) => row.selected && !row.hidden);
    const clipped = item ? visibleRect(item.frame) : null;
    if (!clipped || !dom.canvas.width || !dom.compare.hidden) {
      node.hidden = true;
      return;
    }
    const canvas = dom.canvas.getBoundingClientRect();
    const stage = node.parentElement.getBoundingClientRect();
    const rect = pxRect(clipped, dom.canvas.width, dom.canvas.height);
    const scale = canvas.width / dom.canvas.width;
    node.hidden = false;
    node.style.left = `${Math.max(0, canvas.left - stage.left + rect.x * scale)}px`;
    node.style.top = `${Math.max(0, canvas.top - stage.top + (rect.y + rect.h) * scale + 4)}px`;
    for (const button of node.querySelectorAll("button")) {
      const active = button.dataset.kind === item.layer.kind;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.disabled = button.dataset.kind === "fill" && !callbacks.fillAvailable();
    }
    node.dataset.layer = item.layer.id;
  }

  function setTool(tool) {
    const wasPaint = state.tool === "paint";
    state.tool = ["box", "paint"].includes(tool) ? tool : "select";
    if (state.tool !== "paint") state.paintPoints = [];
    if (wasPaint && state.tool !== "paint") callbacks.onPaintEnd();
    for (const button of dom.tools) {
      const active = button.dataset.tool === state.tool;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
    dom.canvas.dataset.tool = state.tool;
    dom.canvas.style.cursor = ["box", "paint"].includes(state.tool) ? "crosshair" : "default";
  }

  function textAt(frame) {
    const layers = (state.edit?.graphics || [])
      .filter((layer) => layer?.type === "text" && !layer.hidden)
      .filter((layer) => !state.hiddenLayers.has(`text:${layer.id}`))
      .filter((layer) => state.time >= numberOr(layer.start, 0) && state.time < numberOr(layer.end, 0));
    for (let index = layers.length - 1; index >= 0; index -= 1) {
      if (insideRect(graphicRect(layers[index]), frame)) return layers[index];
    }
    return null;
  }

  function dragRect(start, current) {
    const left = clamp(Math.min(start.x, current.x), 0, 1);
    const top = clamp(Math.min(start.y, current.y), 0, 1);
    const right = clamp(Math.max(start.x, current.x), 0, 1);
    const bottom = clamp(Math.max(start.y, current.y), 0, 1);
    return { x: left, y: top, w: right - left, h: bottom - top };
  }

  function beginPointer(event) {
    if (disposed || event.button !== 0 || !state.edit) return;
    const point = canvasPoint(event);
    const frame = framePoint(event);
    const crop = currentCrop();
    if (state.tool === "paint" && state.paintLayerId) {
      pauseClockOnly();
      state.paintPoints = [{
        x: round(frame.x, 4), y: round(frame.y, 4), r: state.paintRadius,
      }];
      drag = { mode: "paint", layerId: state.paintLayerId, last: frame };
      dom.canvas.setPointerCapture?.(event.pointerId);
      draw();
      event.preventDefault();
      return;
    }
    if (state.tool === "box") {
      pauseClockOnly();
      drag = { mode: "draw", crop, startFrame: frame };
      drawPreview = { x: frame.x, y: frame.y, w: 0, h: 0 };
      dom.canvas.setPointerCapture?.(event.pointerId);
      draw();
      event.preventDefault();
      return;
    }
    const selected = selectedClean();
    if (selected) {
      const handle = handleAt(
        pxRect(selected.frame, dom.canvas.width, dom.canvas.height),
        point,
        Math.max(24, dom.canvas.width * 0.028),
      );
      if (handle) {
        pauseClockOnly();
        drag = {
          mode: "resize",
          id: selected.layer.id,
          handle,
          crop,
          startFrame: frame,
          startBox: { ...selected.layer.box },
        };
        dom.canvas.setPointerCapture?.(event.pointerId);
        event.preventDefault();
        return;
      }
    }
    const hit = cleanAt(frame, dom.canvas.width, dom.canvas.height);
    if (hit) {
      pauseClockOnly();
      callbacks.onSelect("clean", hit.layer.id);
      drag = {
        mode: "move",
        id: hit.layer.id,
        crop,
        startFrame: frame,
        startBox: { ...hit.layer.box },
      };
      dom.canvas.setPointerCapture?.(event.pointerId);
      event.preventDefault();
      return;
    }
    const text = textAt(frame);
    if (text) {
      callbacks.onSelect("text", text.id);
      return;
    }
    if (state.viewZoom > 1.001) {
      drag = {
        mode: "pan",
        clientX: event.clientX,
        clientY: event.clientY,
        startPan: { ...state.viewPan },
      };
      dom.canvas.setPointerCapture?.(event.pointerId);
      dom.canvas.style.cursor = "grabbing";
      event.preventDefault();
    }
  }

  function movePointer(event) {
    if (!drag) return;
    if (drag.mode === "pan") {
      const limit = Math.max(0, (state.viewZoom - 1) * (dom.canvas.clientWidth || 300) * 0.5);
      state.viewPan = {
        x: Math.max(-limit, Math.min(limit, drag.startPan.x + event.clientX - drag.clientX)),
        y: Math.max(-limit, Math.min(limit, drag.startPan.y + event.clientY - drag.clientY)),
      };
      applyViewTransform();
      event.preventDefault();
      return;
    }
    const frame = framePoint(event);
    if (drag.mode === "paint") {
      const last = drag.last || frame;
      if (Math.hypot(frame.x - last.x, frame.y - last.y) >= 0.008) {
        state.paintPoints.push({
          x: round(frame.x, 4), y: round(frame.y, 4), r: state.paintRadius,
        });
        drag.last = frame;
      }
      draw();
      event.preventDefault();
      return;
    }
    if (drag.mode === "draw") {
      drawPreview = dragRect(drag.startFrame, frame);
      draw();
      event.preventDefault();
      return;
    }
    const dx = (frame.x - drag.startFrame.x) * drag.crop.w;
    const dy = (frame.y - drag.startFrame.y) * drag.crop.h;
    const box = drag.mode === "move"
      ? moveBox(drag.startBox, dx, dy)
      : resizeBox(drag.startBox, drag.handle, dx, dy);
    drag.box = box;
    callbacks.onBoxChange(drag.id, box, { commit: false });
    draw();
    event.preventDefault();
  }

  function endPointer(event) {
    if (!drag) return;
    if (drag.mode === "pan") {
      drag = null;
      dom.canvas.style.cursor = "";
      dom.canvas.releasePointerCapture?.(event.pointerId);
      event.preventDefault();
      return;
    }
    const current = drag;
    drag = null;
    if (current.mode === "paint") {
      const points = state.paintPoints.slice(0, 120);
      state.paintPoints = [];
      callbacks.onPaint(current.layerId, points, currentCrop());
      setTool("select");
    } else if (current.mode === "draw") {
      const rect = drawPreview;
      drawPreview = null;
      if (rect && rect.w * current.crop.w > 0.006 && rect.h * current.crop.h > 0.006) {
        callbacks.onBoxCreate(frameToBox(rect, current.crop));
      }
      setTool("select");
    } else if (current.box) {
      callbacks.onBoxChange(current.id, current.box, { commit: true });
    }
    dom.canvas.releasePointerCapture?.(event.pointerId);
    draw();
    event.preventDefault();
  }

  function cancelPointer(event) {
    drag = null;
    drawPreview = null;
    state.paintPoints = [];
    dom.canvas.releasePointerCapture?.(event.pointerId);
    draw();
  }

  dom.boxMethod?.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-kind]");
    if (button && !button.disabled && dom.boxMethod.dataset.layer) {
      callbacks.onCleanMethod(dom.boxMethod.dataset.layer, button.dataset.kind);
    }
  });
  dom.canvas.addEventListener("pointerdown", beginPointer);
  dom.canvas.addEventListener("pointermove", movePointer);
  dom.canvas.addEventListener("pointerup", endPointer);
  dom.canvas.addEventListener("pointercancel", cancelPointer);
  for (const button of dom.tools) {
    button.addEventListener("click", () => {
      if (button.dataset.tool === "paint" && !state.paintLayerId) {
        const id = callbacks.onPaintRequest?.();
        if (id) state.paintLayerId = String(id);
      }
      setTool(button.dataset.tool);
    });
  }

  const OUTPUT_KEY = "vibecut.studio.edit.output";
  function readOutput() {
    try {
      const value = JSON.parse(localStorage.getItem(OUTPUT_KEY) || "null");
      if (!value || typeof value !== "object") return null;
      return value;
    } catch (_) {
      return null;
    }
  }
  function writeOutput(value) {
    try { localStorage.setItem(OUTPUT_KEY, JSON.stringify(value)); } catch (_) { /* private window */ }
    callbacks.onOutput(value);
  }
  function resolutionSize(aspect, label) {
    const table = {
      "16:9": { "720p": [1280, 720], "1080p": [1920, 1080], "1440p": [2560, 1440], "4K": [3840, 2160] },
      "16:10": { "720p": [1280, 800], "1080p": [1920, 1200], "1440p": [2560, 1600], "4K": [3840, 2400] },
      "1:1": { "720p": [720, 720], "1080p": [1080, 1080], "1440p": [1440, 1440], "4K": [2160, 2160] },
      "4:5": { "720p": [720, 900], "1080p": [1080, 1350], "1440p": [1440, 1800], "4K": [2160, 2700] },
      "9:16": { "720p": [720, 1280], "1080p": [1080, 1920], "1440p": [1440, 2560], "4K": [2160, 3840] },
    };
    return (table[aspect] || table["9:16"])[label] || null;
  }
  let output = readOutput() || {
    resolution: "1080p", width: 0, height: 0, fps: 30,
    optical_flow: false, stabilize: false, strength: 0.5,
  };
  function paintOutput() {
    if (dom.resolution) dom.resolution.textContent = output.resolution || "1080p";
    if (dom.fps) dom.fps.textContent = String(output.fps || 30);
    if (dom.width) dom.width.value = String(output.width || "");
    if (dom.height) dom.height.value = String(output.height || "");
    if (dom.optical) dom.optical.checked = Boolean(output.optical_flow);
    if (dom.stabilize) dom.stabilize.checked = Boolean(output.stabilize);
    if (dom.strength) dom.strength.value = String(Number(output.strength ?? 0.5));
  }
  paintOutput();

  function closeMenus() {
    if (dom.aspectMenu) dom.aspectMenu.hidden = true;
    if (dom.resMenu) dom.resMenu.hidden = true;
  }

  function toggleFocus() {
    const target = root.querySelector(".st-preview");
    if (!target) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
      return;
    }
    if (document.fullscreenEnabled && target.requestFullscreen) {
      target.requestFullscreen().catch(() => {
        target.classList.add("is-focus");
        updateFocus();
      });
    } else {
      target.classList.toggle("is-focus");
      updateFocus();
    }
  }
  function updateFocus() {
    const on = document.fullscreenElement === root.querySelector(".st-preview")
      || root.querySelector(".st-preview")?.classList.contains("is-focus");
    dom.focus?.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function captureFrame() {
    const canvas = dom.canvas;
    if (!canvas) return;
    const stamp = formatTime(state.time).replace(/[:.]/g, "-");
    const name = `vibecut-frame-${state.jobId || "moment"}-${stamp}.png`;
    const done = (url) => {
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      if (String(url).startsWith("blob:")) setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNote(`Frame saved: ${name}`, "ok");
    };
    if (canvas.toBlob) canvas.toBlob((blob) => { if (blob) done(URL.createObjectURL(blob)); }, "image/png");
    else done(canvas.toDataURL("image/png"));
  }

  dom.safe.addEventListener("change", () => {
    state.showSafeZones = Boolean(dom.safe.checked);
    dom.safeToggle?.classList.toggle("is-on", state.showSafeZones);
    dom.safeToggle?.setAttribute("aria-pressed", state.showSafeZones ? "true" : "false");
    draw();
  });
  dom.safeToggle?.addEventListener("click", () => {
    dom.safe.checked = !dom.safe.checked;
    dom.safe.dispatchEvent(new Event("change"));
  });
  dom.platform?.addEventListener("change", () => {
    state.platform = dom.platform.value || "auto";
    draw();
  });
  dom.play.addEventListener("click", play);
  dom.back?.addEventListener("click", () => callbacks.onSceneStep(-1));
  dom.forward?.addEventListener("click", () => callbacks.onSceneStep(1));
  dom.spanIn?.addEventListener("click", () => callbacks.onSpan("in"));
  dom.spanOut?.addEventListener("click", () => callbacks.onSpan("out"));
  dom.focus?.addEventListener("click", toggleFocus);
  dom.frame?.addEventListener("click", captureFrame);
  dom.aspect?.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = dom.aspectMenu?.hidden !== false;
    closeMenus();
    if (dom.aspectMenu && open) dom.aspectMenu.hidden = false;
  });
  for (const item of root.querySelectorAll("#st-preview-aspect-menu [data-aspect]")) {
    item.addEventListener("click", () => {
      callbacks.onAspect(item.dataset.aspect);
      closeMenus();
    });
  }
  dom.resolution?.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = dom.resMenu?.hidden !== false;
    closeMenus();
    if (dom.resMenu && open) dom.resMenu.hidden = false;
  });
  for (const item of root.querySelectorAll("#st-preview-res-menu [data-res]")) {
    item.addEventListener("click", () => {
      const size = resolutionSize(state.aspect, item.dataset.res);
      output = {
        ...output,
        resolution: item.dataset.res,
        width: size ? size[0] : 0,
        height: size ? size[1] : 0,
      };
      paintOutput();
      writeOutput(output);
      closeMenus();
    });
  }
  dom.resApply?.addEventListener("click", () => {
    const width = Math.max(240, Math.min(4096, Number(dom.width?.value) || 0));
    const height = Math.max(240, Math.min(4096, Number(dom.height?.value) || 0));
    if (!width || !height) return;
    output = { ...output, resolution: "Custom", width, height };
    paintOutput();
    writeOutput(output);
    closeMenus();
  });
  for (const input of [dom.optical, dom.stabilize, dom.strength]) {
    input?.addEventListener("input", () => {
      output = {
        ...output,
        optical_flow: Boolean(dom.optical?.checked),
        stabilize: Boolean(dom.stabilize?.checked),
        strength: Number(dom.strength?.value ?? 0.5),
      };
      writeOutput(output);
    });
  }
  dom.fps?.addEventListener("click", () => {
    const steps = [15, 24, 30, 60];
    const index = steps.indexOf(Number(output.fps));
    output = { ...output, fps: steps[(index + 1) % steps.length] };
    paintOutput();
    writeOutput(output);
  });
  document.addEventListener("click", (event) => {
    if (!root.querySelector(".st-preview")?.contains(event.target)) return;
    if (event.target.closest("#st-preview-aspect, #st-preview-resolution, .st-preview-menu")) return;
    closeMenus();
  });
  document.addEventListener("fullscreenchange", updateFocus);
  dom.scrub.addEventListener("input", () => {
    pauseClockOnly();
    seek(Number(dom.scrub.value));
  });
  dom.scrub.addEventListener("change", () => {
    if (frameAvailable) scheduleFrame(0);
  });

  keyHandler = (event) => {
    if (disposed) return;
    const target = event.target;
    if (target instanceof HTMLElement
      && (/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(target.tagName) || target.isContentEditable)) {
      return;
    }
    if (event.key === "Escape") {
      if (document.fullscreenElement) {
        document.exitFullscreen?.().catch(() => {});
        return;
      }
      if (drag || state.tool === "box") {
        drag = null;
        drawPreview = null;
        setTool("select");
        draw();
      }
    }
  };
  window.addEventListener("keydown", keyHandler);

  syncMediaCookie();
  applyAspect(state.aspect);
  updateTransport();
  updateSource();
  draw();

  return {
    setData,
    setEdit,
    setCaptions(captions) {
      state.captions = captions;
      draw();
    },
    setSelected(selected) {
      state.selected = selected;
      if (selected?.kind !== "clean" || String(selected.id || "") !== state.paintLayerId) {
        state.paintLayerId = "";
      }
      draw();
    },
    setTool,
    startPaint(layerId, radius = 0.025) {
      state.paintLayerId = String(layerId || "");
      state.paintRadius = Math.max(0.005, Math.min(0.2, Number(radius) || 0.025));
      setTool("paint");
    },
    setHiddenLayers(hidden) {
      state.hiddenLayers = hidden instanceof Set ? hidden : new Set(hidden || []);
      draw();
    },
    setFoundText(found) {
      state.foundText = Array.isArray(found) ? found : [];
      draw();
    },
    setStories(stories, currentId) {
      const rows = Array.isArray(stories) ? stories : [];
      const current = rows.find((row) => String(row.id) === String(currentId));
      if (dom.storyNum) dom.storyNum.textContent = String(current?.num || "01").padStart(2, "0");
      if (dom.storyTitle) dom.storyTitle.textContent = String(current?.title || "Moment");
      if (!dom.storyMenu) return;
      dom.storyMenu.replaceChildren();
      for (const row of rows) {
        const active = String(row.id) === String(currentId);
        const button = el("button", {
          class: `st-moment-item${active ? " is-active" : ""}`,
          type: "button",
          role: "menuitemradio",
          "aria-checked": active ? "true" : "false",
        }, [
          el("span", { class: "st-mono", text: String(row.num || "").padStart(2, "0") }),
          el("span", { class: "st-moment-item-copy" }, [
            el("strong", { text: String(row.title || "Moment").slice(0, 70) }),
            el("small", { text: String(row.time || "") }),
          ]),
        ]);
        button.addEventListener("click", () => {
          dom.storyMenu.hidden = true;
          dom.storyBtn?.setAttribute("aria-expanded", "false");
          if (!active) callbacks.onStory(row.id);
        });
        dom.storyMenu.append(button);
      }
    },
    setSpan(text) {
      if (dom.spanText) dom.spanText.textContent = String(text || "Full");
    },
    setViewZoom(value) {
      applyViewZoom(value);
    },
    setFoundFocus(id) {
      state.foundFocus = String(id || "");
      draw();
    },
    showCompare(data) {
      if (!data?.before || !data?.after) return;
      dom.compareBefore.src = String(data.before);
      dom.compareAfter.src = String(data.after);
      stopCompareVideo();
      if (dom.compareTitle) dom.compareTitle.textContent = data.title || "Before / After";
      if (dom.compareNote) dom.compareNote.textContent = data.note || "Selected Clean layer · this scene";
      if (dom.comparePlay) dom.comparePlay.hidden = !data.video;
      if (data.video && dom.compareVideo) dom.compareVideo.src = String(data.video);
      dom.compare.hidden = false;
      if (dom.boxMethod) dom.boxMethod.hidden = true;
      applyCompare(dom.compareSlider?.value ?? 50);
    },
    hideCompare() {
      stopCompareVideo();
      dom.compare.hidden = true;
      dom.compareBefore.removeAttribute("src");
      dom.compareAfter.removeAttribute("src");
    },
    setTime,
    setScene(value, role = "Scene") {
      if (dom.sceneNum) dom.sceneNum.textContent = String(value || "01").padStart(2, "0");
      if (dom.sceneRole) dom.sceneRole.textContent = role || "Scene";
    },
    setPlatform(value, { safe = true } = {}) {
      state.platform = value || "auto";
      if (dom.platform) dom.platform.value = state.platform;
      dom.safe.checked = Boolean(safe);
      state.showSafeZones = Boolean(safe);
      draw();
    },
    setLoop(value) {
      state.loop = Boolean(value);
    },
    getOutput() {
      return { ...output };
    },
    toggleFocus,
    captureFrame,
    rebuildProxy() {
      clearFrame();
      resetProxy();
      frameAvailable = true;
      frameState = "idle";
      frameReady = false;
      if (state.edit) {
        void loadFrame(state.time);
        ensureProxy();
      }
      draw();
    },
    seek,
    step,
    play,
    pause,
    togglePlay,
    invalidate,
    refresh: draw,
    destroy() {
      disposed = true;
      if (keyHandler) window.removeEventListener("keydown", keyHandler);
      pause();
      clearFrame();
      resetProxy();
      if (frameTimer) window.clearTimeout(frameTimer);
      if (raf) window.cancelAnimationFrame(raf);
      root.replaceChildren(el("p", { class: "st-hint", text: "Preview closed." }));
    },
  };
}
