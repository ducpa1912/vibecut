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
  clamp,
  colorFilter,
  formatTime,
  graphicRect,
  numberOr,
  safeZoneRects,
} from "./model.js";
import { fetchFrame, framePath, proxyPath, syncMediaCookie } from "./api.js";

const FADE_IN_SKIP = 0.15;

export function mountPreview(root, options = {}) {
  const callbacks = {
    onTime: options.onTime || (() => {}),
    onStatus: options.onStatus || (() => {}),
    onStale: options.onStale || (() => {}),
  };
  const state = {
    aspect: "9:16",
    edit: null,
    captions: null,
    duration: 10,
    time: 0,
    showSafeZones: true,
    selected: null,
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
  let playing = false;
  let videoPlaying = false;
  // Play was pressed before the proxy finished building; start it on ready.
  let pendingPlay = false;
  let raf = 0;
  let lastTick = 0;
  let lastFrameAt = 0;
  let keyHandler = null;

  root.innerHTML = `
    <section class="st-preview" aria-label="Story preview">
      <div class="st-preview-head">
        <div class="st-preview-heading">
          <h2>Preview</h2>
          <span id="st-preview-aspect" class="st-chip st-chip-quiet">9:16</span>
        </div>
        <div class="st-preview-tools">
          <label class="st-switch">
            <input id="st-preview-safe" type="checkbox" checked>
            <span>Safe zones</span>
          </label>
          <span id="st-preview-source" class="st-preview-source">Loading preview…</span>
        </div>
      </div>
      <div class="st-preview-stage">
        <canvas id="st-preview-canvas" class="st-preview-canvas" width="1080" height="1920" aria-label="Story preview with safe zones"></canvas>
      </div>
      <div class="st-preview-transport">
        <button id="st-preview-play" class="st-icon-btn st-preview-play" type="button" aria-label="Play preview">▶</button>
        <span id="st-preview-time" class="st-mono st-preview-time">0:00.0 / 0:00.0</span>
        <input id="st-preview-scrub" class="st-preview-scrub" type="range" min="0" max="10" step="0.01" value="0" aria-label="Preview position">
      </div>
      <p id="st-preview-note" class="st-preview-note" role="status">Opening the preview…</p>
    </section>
  `;

  const $ = (selector) => root.querySelector(selector);
  const dom = {
    canvas: $("#st-preview-canvas"),
    aspect: $("#st-preview-aspect"),
    safe: $("#st-preview-safe"),
    source: $("#st-preview-source"),
    play: $("#st-preview-play"),
    time: $("#st-preview-time"),
    scrub: $("#st-preview-scrub"),
    note: $("#st-preview-note"),
  };
  const ctx = dom.canvas.getContext("2d");

  function setNote(message, tone = "") {
    dom.note.textContent = message || "";
    dom.note.dataset.tone = tone;
  }

  function sourceLabel() {
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

    if (pendingPlay && !proxyReady) {
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
    const zones = safeZoneRects(state.aspect);
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

  function drawSelection(width, height) {
    if (!state.selected || !state.edit) return;
    let rect = null;
    let label = "Selected";
    if (state.selected.kind === "text") {
      const layer = (state.edit.graphics || []).find((item) => item.id === state.selected.id);
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
    ctx.save();
    ctx.strokeStyle = "#e8a266";
    ctx.lineWidth = 6;
    ctx.strokeRect(x, y, w, h);
    const handle = 14;
    ctx.fillStyle = "#e8a266";
    for (const [hx, hy] of [[x, y], [x + w, y], [x, y + h], [x + w, y + h]]) {
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
        ctx.filter = colorFilter(state.edit?.color);
      }
      drawCover(source, width, height);
      ctx.restore();
    } else {
      drawPlaceholder(width, height);
    }

    drawSafeZones(width, height);
    drawSelection(width, height);
  }

  function applyAspect(aspect) {
    const next = aspect === "4:5" ? "4:5" : "9:16";
    if (state.aspect === next && dom.canvas.width === CANVAS[next].width) return;
    state.aspect = next;
    const size = CANVAS[next];
    dom.canvas.width = size.width;
    dom.canvas.height = size.height;
    dom.aspect.textContent = next;
    draw();
  }

  function updateTransport() {
    const duration = Math.max(0.1, numberOr(state.duration, 0.1));
    dom.scrub.max = String(duration);
    dom.scrub.value = String(clamp(state.time, 0, duration));
    dom.time.textContent = `${formatTime(state.time)} / ${formatTime(duration)}`;
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
          updateSource();
          draw();
        };
        image.onerror = () => {
          URL.revokeObjectURL(url);
          if (disposed || seq !== frameSeq) return;
          frameState = "error";
          updateSource();
        };
        image.src = url;
        return;
      }

      if (response.status === 409) {
        frameState = "stale";
        frameReady = false;
        updateSource();
        callbacks.onStale();
        return;
      }
      if (response.status === 404 || response.status === 405 || response.status === 501) {
        frameAvailable = false;
        frameReady = false;
        frameState = "unavailable";
        updateSource();
        ensureProxy();
        draw();
        return;
      }
      if (response.status === 422) {
        frameState = "bad-time";
        updateSource();
        return;
      }
      if (response.status === 401 || response.status === 403) {
        frameState = "locked";
        updateSource();
        return;
      }
      frameState = "error";
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

  function setEdit(edit, { keepTime = false } = {}) {
    const previousId = state.edit?.id || "";
    const nextId = edit?.id || "";
    state.edit = edit || null;
    state.duration = Math.max(0.1, numberOr(edit?.story_ref?.duration, state.duration));
    if (!keepTime) setTime(state.time);
    if (previousId !== nextId) {
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

  function setData({ aspect, edit, captions, duration, selected, jobId } = {}) {
    if (jobId && jobId !== state.jobId) {
      state.jobId = jobId;
      clearFrame();
      resetProxy();
    }
    if (aspect) applyAspect(aspect);
    if (typeof duration === "number" && Number.isFinite(duration)) {
      state.duration = Math.max(0.1, duration);
    }
    if (captions !== undefined) state.captions = captions;
    if (selected !== undefined) state.selected = selected;
    if (edit !== undefined) setEdit(edit);
    else draw();
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

  dom.safe.addEventListener("change", () => {
    state.showSafeZones = Boolean(dom.safe.checked);
    draw();
  });
  dom.play.addEventListener("click", play);
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
    if (event.code === "Space") {
      event.preventDefault();
      play();
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
      draw();
    },
    setTime,
    seek,
    step,
    play,
    pause,
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
