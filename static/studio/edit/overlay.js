/**
 * Live overlay for proxy playback.
 *
 * The 540p proxy is the raw story range, so while it plays the canvas draws
 * the Edit's text, graphics and the active caption cue on top. It mirrors the
 * server's layer compile (`compose_render._graphic_layers`,
 * `_caption_overlay_style`) and raster (`render._render_text_layer`,
 * `_render_fx_layer`) closely enough to judge timing and placement. It is an
 * approximation: the exact frame stays the source of truth.
 */

import { clamp, graphicRect, numberOr } from "./model.js";

/** Mirrors `overlays.DEFAULT_BOX["caption"]` and `ANCHOR_MARGIN`. */
const CAPTION_BOX = { w: 0.76, h: 0.12 };
const TEXT_DEFAULTS = {
  size: 44, weight: 800, color: "#ffffff", background: "none",
  stroke: "#000000", align: "center", uppercase: false, shadow: false,
};

function active(start, end, t) {
  const from = numberOr(start, 0);
  const to = numberOr(end, from);
  return t >= from && t < to;
}

function hexAlpha(color, alpha) {
  const value = Math.round(clamp(numberOr(alpha, 0), 0, 1) * 255);
  return `${color}${value.toString(16).padStart(2, "0")}`;
}

/** The caption track style as an overlay text style plus its anchor. */
export function captionOverlayStyle(trackStyle = {}) {
  const style = { ...TEXT_DEFAULTS };
  style.size = clamp(Math.round(numberOr(trackStyle.font_size, style.size)), 12, 160);
  style.color = String(trackStyle.color || "#ffffff");
  style.stroke = numberOr(trackStyle.stroke_width, 0) > 0
    ? String(trackStyle.stroke_color || "#000000")
    : "none";
  style.stroke_width = clamp(numberOr(trackStyle.stroke_width, 0), 0, 20);
  style.weight = 700;
  const opacity = numberOr(trackStyle.background_opacity, 0);
  style.background = opacity > 0 ? hexAlpha(String(trackStyle.background || "#000000"), opacity) : "none";
  style.uppercase = Boolean(trackStyle.uppercase);
  const position = String(trackStyle.position || "bottom").toLowerCase();
  const anchor = { top: "top-center", center: "center", bottom: "bottom-center" }[position] || "bottom-center";
  return { style, anchor };
}

/**
 * Everything to draw at story time `t`, lowest z first. Pure data, so it is
 * testable without a canvas.
 */
export function overlayLayers(edit, captions, t) {
  const time = numberOr(t, 0);
  const rows = [];
  for (const item of edit?.graphics || []) {
    if (!item || !active(item.start, item.end, time)) continue;
    const rect = graphicRect(item);
    const opacity = clamp(numberOr(item.opacity, 1), 0, 1);
    const z = numberOr(item.z, 10);
    if (item.type === "text") {
      const text = String(item.text || "");
      if (!text.trim()) continue;
      rows.push({
        type: "text", kind: item.kind, text, rect, opacity, z,
        style: { ...TEXT_DEFAULTS, ...(item.style || {}) },
      });
    } else if (["progress_bar", "underline", "arrow", "circle"].includes(item.kind)) {
      const span = Math.max(1e-6, numberOr(item.end, 0) - numberOr(item.start, 0));
      rows.push({
        type: "fx", kind: item.kind, rect, opacity, z,
        color: String(item.color || "#ffffff"),
        thickness: Math.max(1, numberOr(item.thickness, 6)),
        fraction: clamp((time - numberOr(item.start, 0)) / span, 0, 1),
      });
    }
  }
  const settings = edit?.captions || {};
  if (settings.enabled !== false && captions && settings.track_id && captions.id === settings.track_id) {
    const cue = (captions.cues || []).find((row) => active(row.start, row.end, time));
    if (cue && String(cue.text || "").trim()) {
      const { style, anchor } = captionOverlayStyle(captions.style || {});
      rows.push({
        type: "text", kind: "caption", text: String(cue.text), opacity: 1, z: 50, style,
        rect: graphicRect({ anchor, box: CAPTION_BOX }),
      });
    }
  }
  return rows.sort((left, right) => left.z - right.z);
}

/** Greedy word wrap that keeps stored line breaks, like `render._wrap_caption`. */
export function wrapText(measure, text, maxWidth) {
  const lines = [];
  for (const raw of String(text || "").split(/\r\n|\r|\n/)) {
    const paragraph = raw.trim();
    if (!paragraph) continue;
    let current = "";
    for (const word of paragraph.split(/\s+/)) {
      const candidate = current ? `${current} ${word}` : word;
      if (measure(candidate) <= maxWidth) {
        current = candidate;
        continue;
      }
      if (current) lines.push(current);
      if (measure(word) <= maxWidth) {
        current = word;
        continue;
      }
      current = "";
      for (const char of Array.from(word)) {
        if (current && measure(current + char) > maxWidth) {
          lines.push(current);
          current = char;
        } else {
          current += char;
        }
      }
    }
    if (current) lines.push(current);
  }
  return lines;
}

function fontFor(style, size) {
  const weight = clamp(Math.round(numberOr(style.weight, 800) / 100) * 100, 100, 900);
  const family = String(style.font || "sans") === "serif"
    ? "ui-serif, Georgia, serif"
    : String(style.font || "sans") === "mono"
      ? "ui-monospace, Menlo, monospace"
      : "-apple-system, 'SF Pro Display', 'Helvetica Neue', Helvetica, Arial, sans-serif";
  return `${weight} ${size}px ${family}, 'Apple Color Emoji'`;
}

function drawText(ctx, layer, width, height) {
  const x = layer.rect.x * width;
  const y = layer.rect.y * height;
  const w = Math.max(1, layer.rect.w * width);
  const h = Math.max(1, layer.rect.h * height);
  const style = layer.style;
  const text = style.uppercase ? layer.text.toUpperCase() : layer.text;
  let size = Math.max(10, Math.round(numberOr(style.size, 44) * height / 1920));
  let lines = [];
  // Shrink until the block fits the box, as the renderer does.
  while (size >= 10) {
    ctx.font = fontFor(style, size);
    lines = wrapText((value) => ctx.measureText(value).width, text, Math.max(8, w - 8));
    const widest = Math.max(0, ...lines.map((line) => ctx.measureText(line).width));
    if (!lines.length || (widest <= Math.max(8, w - 8) && Math.round(size * 1.18) * lines.length <= h)) break;
    size -= 2;
  }
  if (!lines.length) return;
  ctx.save();
  ctx.globalAlpha = layer.opacity;
  const background = String(style.background || "none");
  if (background && background !== "none") {
    ctx.fillStyle = background;
    const radius = Math.max(2, size * 0.18);
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, w, h, radius);
    else ctx.rect(x, y, w, h);
    ctx.fill();
  }
  const lineHeight = Math.max(1, Math.round(size * 1.18));
  const top = y + Math.max(0, (h - lineHeight * lines.length) / 2);
  const align = String(style.align || "center");
  ctx.textAlign = align === "left" ? "left" : align === "right" ? "right" : "center";
  ctx.textBaseline = "top";
  const px = align === "left" ? x + 4 : align === "right" ? x + w - 4 : x + w / 2;
  const stroke = String(style.stroke || "none");
  lines.forEach((line, index) => {
    const ly = top + index * lineHeight;
    if (style.shadow) {
      const offset = Math.max(1, Math.round(size * 0.06));
      ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
      ctx.fillText(line, px + offset, ly + offset);
    }
    if (stroke && stroke !== "none") {
      ctx.lineJoin = "round";
      // Same width as render._stroke_px; canvas strokes are centred, so double it.
      const width = Number.isFinite(Number(style.stroke_width))
        ? Math.round(Number(style.stroke_width) * height / 1920)
        : Math.max(1, Math.round(size * 0.08));
      ctx.lineWidth = width * 2;
      ctx.strokeStyle = stroke;
      ctx.strokeText(line, px, ly);
    }
    ctx.fillStyle = String(style.color || "#ffffff");
    ctx.fillText(line, px, ly);
  });
  ctx.restore();
}

function drawFx(ctx, layer, width, height) {
  const x = layer.rect.x * width;
  const y = layer.rect.y * height;
  const w = Math.max(1, layer.rect.w * width);
  const h = Math.max(1, layer.rect.h * height);
  const thickness = layer.thickness;
  ctx.save();
  ctx.globalAlpha = layer.opacity;
  ctx.fillStyle = layer.color;
  ctx.strokeStyle = layer.color;
  if (layer.kind === "progress_bar") {
    ctx.fillStyle = "rgba(255, 255, 255, 0.24)";
    ctx.fillRect(x, y, w, h);
    ctx.fillStyle = layer.color;
    ctx.fillRect(x, y, Math.max(1, w * layer.fraction), h);
  } else if (layer.kind === "underline") {
    ctx.fillRect(x, y + h - thickness - thickness / 2, w, thickness);
  } else if (layer.kind === "arrow") {
    const head = Math.max(4, w * 0.16);
    const mid = y + h / 2;
    ctx.lineWidth = Math.max(2, thickness);
    ctx.beginPath();
    ctx.moveTo(x, mid);
    ctx.lineTo(x + w - head, mid);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x + w, mid);
    ctx.lineTo(x + w - head, mid - head / 2);
    ctx.lineTo(x + w - head, mid + head / 2);
    ctx.closePath();
    ctx.fill();
  } else if (layer.kind === "circle") {
    ctx.lineWidth = thickness;
    ctx.beginPath();
    ctx.ellipse(x + w / 2, y + h / 2, Math.max(1, w / 2 - thickness / 2), Math.max(1, h / 2 - thickness / 2), 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

/** Draw the overlay for story time `t` onto a canvas of `width`×`height`. */
export function drawOverlay(ctx, edit, captions, t, width, height) {
  for (const layer of overlayLayers(edit, captions, t)) {
    if (layer.type === "text") drawText(ctx, layer, width, height);
    else drawFx(ctx, layer, width, height);
  }
}
