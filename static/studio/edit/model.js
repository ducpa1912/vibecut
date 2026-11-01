/**
 * Pure helpers for the Studio editor: presets, time mapping, safe zones and
 * the small amount of geometry needed to draw the preview.
 *
 * Nothing here calls the server or touches the DOM. Keeping it pure makes the
 * editor deterministic: the same Edit always draws the same boxes and labels.
 */

export const ASPECTS = ["9:16", "4:5", "1:1", "16:9", "16:10"];

export const CANVAS = {
  "9:16": { width: 1080, height: 1920, label: "9:16 vertical" },
  "4:5": { width: 1080, height: 1350, label: "4:5 feed" },
  "1:1": { width: 1080, height: 1080, label: "1:1 square" },
  "16:9": { width: 1920, height: 1080, label: "16:9 wide" },
  "16:10": { width: 1920, height: 1200, label: "16:10 wide" },
};

/** Platform safe zones. Values are fractions of the output frame. */
export const SAFE_ZONE_PRESETS = {
  auto: { label: "This shape", safe_zone: { top: 0.08, right: 0.08, bottom: 0.16, left: 0.08 } },
  instagram: { label: "Instagram Reels", safe_zone: { top: 0.12, right: 0.06, bottom: 0.20, left: 0.06 } },
  tiktok: { label: "TikTok", safe_zone: { top: 0.10, right: 0.14, bottom: 0.22, left: 0.06 } },
  youtube: { label: "YouTube Shorts", safe_zone: { top: 0.08, right: 0.12, bottom: 0.18, left: 0.05 } },
  facebook: { label: "Facebook Reels", safe_zone: { top: 0.12, right: 0.06, bottom: 0.20, left: 0.06 } },
};

/** Mirrors the colour presets in `edits.COLOR_PRESETS`. */
export const COLOR_PRESETS = {
  none: {
    label: "Original",
    swatch: "linear-gradient(135deg, #3b3b40, #1b1b1e)",
    values: {
      exposure: 0, contrast: 0, saturation: 0, temperature: 0,
      vignette: 0, grain: 0, sharpen: 0,
    },
  },
  warm_film: {
    label: "Warm film",
    swatch: "linear-gradient(135deg, #d99a62, #6f4d36)",
    values: {
      exposure: 0.02, contrast: 0.08, saturation: -0.05, temperature: 0.25,
      vignette: 0.18, grain: 0.12, sharpen: 0.05,
    },
  },
  cool_fade: {
    label: "Cool fade",
    swatch: "linear-gradient(135deg, #7b9bb8, #3b4a5c)",
    values: {
      exposure: 0.01, contrast: -0.08, saturation: -0.12, temperature: -0.30,
      vignette: 0.10, grain: 0.05, sharpen: 0,
    },
  },
  vivid_pop: {
    label: "Vivid pop",
    swatch: "linear-gradient(135deg, #ff7a59, #b62a68)",
    values: {
      exposure: 0.04, contrast: 0.18, saturation: 0.28, temperature: 0.04,
      vignette: 0, grain: 0, sharpen: 0.20,
    },
  },
  soft_matte: {
    label: "Soft matte",
    swatch: "linear-gradient(135deg, #b9b2a8, #6e6a64)",
    values: {
      exposure: 0.06, contrast: -0.20, saturation: -0.08, temperature: 0.08,
      vignette: 0, grain: 0.04, sharpen: 0,
    },
  },
  golden_hour: {
    label: "Golden hour",
    swatch: "linear-gradient(135deg, #f4c169, #93531f)",
    values: {
      exposure: 0.03, contrast: 0.06, saturation: 0.10, temperature: 0.45,
      vignette: 0.12, grain: 0.06, sharpen: 0.04,
    },
  },
  teal_orange: {
    label: "Teal and orange",
    swatch: "linear-gradient(135deg, #e88a51, #1e5963)",
    values: {
      exposure: 0, contrast: 0.14, saturation: 0.12, temperature: -0.10,
      vignette: 0.08, grain: 0.03, sharpen: 0.10,
    },
  },
  mono_contrast: {
    label: "Mono contrast",
    swatch: "linear-gradient(135deg, #e4e4e4, #3a3a3a)",
    values: {
      exposure: 0.02, contrast: 0.24, saturation: -1.0, temperature: 0,
      vignette: 0.14, grain: 0.10, sharpen: 0.12,
    },
  },
  clean_bright: {
    label: "Clean bright",
    swatch: "linear-gradient(135deg, #f7f2e7, #b6ad9b)",
    values: {
      exposure: 0.10, contrast: 0.04, saturation: 0.05, temperature: 0,
      vignette: 0, grain: 0, sharpen: 0.12,
    },
  },
};

export const COLOR_RANGES = {
  exposure: [-1, 1],
  contrast: [-1, 1],
  saturation: [-1, 1],
  temperature: [-1, 1],
  vignette: [0, 1],
  grain: [0, 1],
  sharpen: [0, 1],
};

export const COLOR_CONTROLS = [
  ["exposure", "Brightness"],
  ["contrast", "Contrast"],
  ["saturation", "Colour"],
  ["temperature", "Warmth"],
  ["vignette", "Vignette"],
  ["grain", "Grain"],
  ["sharpen", "Sharpness"],
];

export const TEXT_KINDS = {
  hook: {
    label: "Hook card",
    anchor: "top-center",
    box: { w: 0.76, h: 0.16 },
    sample: "Your hook",
  },
  title: {
    label: "Title",
    anchor: "center",
    box: { w: 0.76, h: 0.14 },
    sample: "Title",
  },
  lower_third: {
    label: "Lower third",
    anchor: "bottom-left",
    box: { w: 0.64, h: 0.14 },
    sample: "Name or detail",
  },
  cta: {
    label: "End card",
    anchor: "center",
    box: { w: 0.64, h: 0.10 },
    sample: "Follow for more",
  },
  emphasis: {
    label: "Key word",
    anchor: "center",
    box: { w: 0.60, h: 0.12 },
    sample: "Key word",
  },
};

export const TEXT_ANCHORS = [
  ["top-left", "Top left"],
  ["top-center", "Top centre"],
  ["top-right", "Top right"],
  ["center-left", "Middle left"],
  ["center", "Middle"],
  ["center-right", "Middle right"],
  ["bottom-left", "Bottom left"],
  ["bottom-center", "Bottom centre"],
  ["bottom-right", "Bottom right"],
];

export const TEXT_STYLE_DEFAULTS = {
  font: "sans",
  size: 44,
  weight: 800,
  color: "#ffffff",
  background: "none",
  stroke: "#000000",
  align: "center",
  uppercase: false,
  shadow: true,
};

export const CAPTION_STYLE_DEFAULTS = {
  font: "Arial Unicode",
  font_size: 56,
  color: "#FFFFFF",
  stroke_color: "#000000",
  stroke_width: 3,
  background: "#000000",
  background_opacity: 0,
  position: "bottom",
  safe_zone: { top: 0.08, right: 0.08, bottom: 0.16, left: 0.08 },
  max_chars: 28,
  max_lines: 2,
  uppercase: false,
};

export const CAPTION_PRESETS = {
  clean: { label: "Clean", values: {} },
  bold: {
    label: "Bold",
    values: {
      font_size: 62,
      stroke_width: 6,
      max_chars: 22,
      max_lines: 2,
      uppercase: true,
    },
  },
  boxed: {
    label: "Boxed",
    values: {
      font_size: 52,
      stroke_width: 2,
      background: "#000000",
      background_opacity: 0.66,
      max_chars: 26,
      max_lines: 2,
    },
  },
  minimal: {
    label: "Minimal",
    values: {
      font_size: 46,
      stroke_width: 1,
      max_chars: 32,
      max_lines: 2,
      safe_zone: { top: 0.07, right: 0.07, bottom: 0.12, left: 0.07 },
    },
  },
};

export const CLEAN_LABELS = {
  crop_guard: "Keep out of crop",
  blur: "Blur",
  plate: "Cover plate",
  mask: "Mask",
  delogo: "Remove (interpolate)",
  fill: "AI fill",
};

export const MOTION_LABELS = {
  punch_in: "Punch in",
  snap_zoom: "Snap zoom",
  push: "Slow push",
  shake: "Shake",
};

export const FX_LABELS = {
  arrow: "Arrow",
  circle: "Circle",
  underline: "Underline",
  progress_bar: "Progress bar",
  sticker: "Sticker",
};

export const AUDIO_LABELS = {
  original: "Original sound",
  original_bed: "Original with music",
  voice_over: "Voice-over",
  dub: "Dub",
  music_only: "Music only",
};

export function clamp(value, low, high) {
  return Math.min(high, Math.max(low, Number.isFinite(value) ? value : low));
}

export function numberOr(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function round(value, digits = 3) {
  const factor = 10 ** digits;
  return Math.round(numberOr(value) * factor) / factor;
}

export function clone(value) {
  return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

export function uid(prefix) {
  const stamp = Date.now().toString(36);
  const noise = Math.random().toString(36).slice(2, 6);
  return `${prefix}_${stamp}${noise}`;
}

export function formatTime(seconds) {
  const value = Math.max(0, numberOr(seconds));
  const minutes = Math.floor(value / 60);
  const rest = value - minutes * 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}

export function formatSpan(start, end) {
  return `${formatTime(start)} – ${formatTime(end)}`;
}

export function aspectLabel(aspect) {
  return CANVAS[aspect]?.label || CANVAS["9:16"].label;
}

export function safeZoneRects(aspect, platform = "auto") {
  const canvas = CANVAS[aspect] || CANVAS["9:16"];
  const preset = SAFE_ZONE_PRESETS[platform] || SAFE_ZONE_PRESETS.auto;
  const zone = preset.safe_zone;
  const portrait = canvas.height > canvas.width;
  return {
    canvas,
    safe: {
      x: zone.left,
      y: zone.top,
      w: 1 - zone.left - zone.right,
      h: 1 - zone.top - zone.bottom,
    },
    reserved: portrait
      ? [
        { name: "Top bar", x: 0, y: 0, w: 1, h: zone.top },
        { name: "Bottom bar", x: 0, y: 1 - zone.bottom, w: 1, h: zone.bottom },
        { name: "Buttons", x: 1 - zone.right, y: 0.30, w: zone.right, h: 0.63 },
      ]
      : [
        { name: "Top bar", x: 0, y: 0, w: 1, h: zone.top },
        { name: "Bottom bar", x: 0, y: 1 - zone.bottom, w: 1, h: zone.bottom },
      ],
  };
}

/** Anchor and box to a top-left rectangle in output coordinates. */
export function graphicRect(layer) {
  const box = layer?.box || { w: 0.76, h: 0.16 };
  const width = clamp(numberOr(box.w, 0.76), 0.02, 1);
  const height = clamp(numberOr(box.h, 0.16), 0.02, 1);
  const anchor = String(layer?.anchor || "center").toLowerCase();
  const margins = { left: 0.05, right: 0.12, top: 0.05, bottom: 0.08 };
  let vertical = "center";
  let horizontal = "center";
  if (anchor === "center") {
    vertical = "center";
    horizontal = "center";
  } else if (anchor.includes("-")) {
    const parts = anchor.split("-");
    if (["top", "center", "bottom"].includes(parts[0])) {
      vertical = parts[0];
      horizontal = parts[1] || "center";
    } else {
      horizontal = parts[0] || "center";
      vertical = parts[1] || "center";
    }
  }
  let x = (1 - width) / 2;
  let y = (1 - height) / 2;
  if (horizontal === "left") x = margins.left;
  else if (horizontal === "right") x = 1 - margins.right - width;
  if (vertical === "top") y = margins.top;
  else if (vertical === "bottom") y = 1 - margins.bottom - height;
  return {
    x: clamp(x, 0, Math.max(0, 1 - width)),
    y: clamp(y, 0, Math.max(0, 1 - height)),
    w: width,
    h: height,
  };
}

/**
 * Map a story to output-time sentence segments.
 *
 * Story clips are already in output order and carry the source sentence id in
 * their `why` label. Using the clip list keeps the sentence track correct even
 * when the story was reordered.
 */
export function sentenceSegments(story) {
  const sentences = Array.isArray(story?.sentences) ? story.sentences : [];
  const byId = new Map(sentences.map((sentence) => [String(sentence.id), sentence]));
  const clips = Array.isArray(story?.clips) ? story.clips : [];
  const rows = [];
  let offset = 0;
  if (clips.length) {
    clips.forEach((clip, index) => {
      const duration = Math.max(
        0.05,
        numberOr(clip.dur, numberOr(clip.end) - numberOr(clip.start)),
      );
      const match = /Sentence\s+([A-Za-z0-9_-]+)/.exec(String(clip.why || ""));
      const sentence = match ? byId.get(match[1]) : null;
      const text = String(
        sentence?.text || clip.why || `Beat ${index + 1}`,
      ).trim();
      rows.push({
        id: `sentence-${index}`,
        sentenceId: sentence?.id ?? null,
        text,
        start: round(offset),
        end: round(offset + duration),
        role: clip.role || "beat",
      });
      offset += duration;
    });
    return rows;
  }
  if (!sentences.length) return rows;
  sentences.forEach((sentence, index) => {
    const duration = Math.max(0.1, numberOr(sentence.end) - numberOr(sentence.start));
    rows.push({
      id: `sentence-${index}`,
      sentenceId: sentence.id ?? null,
      text: String(sentence.text || `Sentence ${index + 1}`),
      start: round(offset),
      end: round(offset + duration),
      role: index === 0 ? "hook" : index === sentences.length - 1 ? "payoff" : "beat",
    });
    offset += duration;
  });
  return rows;
}

export function storyDuration(story, edit) {
  const fromEdit = numberOr(edit?.story_ref?.duration);
  if (fromEdit > 0) return fromEdit;
  const fromStory = numberOr(story?.dur);
  if (fromStory > 0) return fromStory;
  return Math.max(
    0.1,
    (story?.clips || []).reduce(
      (total, clip) => total + Math.max(0, numberOr(clip.dur, numberOr(clip.end) - numberOr(clip.start))),
      0,
    ),
  );
}

/**
 * One entry per timeline lane. Every item is in story/output seconds, so the
 * timeline can place it with a percentage and stay responsive.
 */
export function layerSpans(edit, captions, duration) {
  const span = { start: 0, end: Math.max(0.1, duration) };
  const rows = [];

  const cleanItems = (edit?.clean || []).map((layer, index) => {
    const ranges = Array.isArray(layer.ranges) && layer.ranges.length
      ? layer.ranges
      : [span];
    const label = layer.label || CLEAN_LABELS[layer.kind] || `Clean ${index + 1}`;
    return ranges.map((range, rangeIndex) => ({
      id: `${layer.id}-${rangeIndex}`,
      layerId: layer.id,
      label,
      start: numberOr(range.start),
      end: Math.max(numberOr(range.start) + 0.1, numberOr(range.end)),
    }));
  }).flat();
  rows.push({ id: "clean", label: "Clean", kind: "clean", items: cleanItems });

  const textItems = (edit?.graphics || [])
    .filter((layer) => layer.type === "text")
    .map((layer) => ({
      id: layer.id,
      layerId: layer.id,
      label: layer.text || TEXT_KINDS[layer.kind]?.label || "Text",
      start: numberOr(layer.start),
      end: numberOr(layer.end),
    }));
  rows.push({ id: "text", label: "Text", kind: "text", items: textItems });

  const cueItems = (captions?.cues || []).map((cue) => ({
    id: cue.id,
    layerId: cue.id,
    label: String(cue.text || "").replace(/\s+/g, " "),
    start: numberOr(cue.start),
    end: numberOr(cue.end),
  }));
  rows.push({ id: "captions", label: "Captions", kind: "captions", items: cueItems });

  const effectItems = [
    ...(edit?.motion || []).map((layer) => ({
      id: layer.id,
      layerId: layer.id,
      label: MOTION_LABELS[layer.kind] || "Motion",
      start: numberOr(layer.start),
      end: numberOr(layer.end),
      subgroup: "motion",
    })),
    ...(edit?.graphics || [])
      .filter((layer) => layer.type === "fx")
      .map((layer) => ({
        id: layer.id,
        layerId: layer.id,
        label: FX_LABELS[layer.kind] || "Effect",
        start: numberOr(layer.start),
        end: numberOr(layer.end),
        subgroup: "fx",
      })),
  ];
  rows.push({ id: "effects", label: "Effects", kind: "effects", items: effectItems });

  const preset = edit?.color?.preset || "none";
  rows.push({
    id: "color",
    label: "Color",
    kind: "color",
    items: [{
      id: "color",
      label: COLOR_PRESETS[preset]?.label || "Original",
      start: 0,
      end: Math.max(0.1, duration),
      muted: preset === "none",
    }],
  });

  const mode = edit?.audio?.mode || "original";
  rows.push({
    id: "audio",
    label: "Audio",
    kind: "audio",
    items: [{
      id: "audio",
      label: AUDIO_LABELS[mode] || "Original sound",
      start: 0,
      end: Math.max(0.1, duration),
      muted: mode === "original",
      dashed: true,
    }],
  });

  return rows;
}

export function colorFilter(color) {
  const exposure = numberOr(color?.exposure);
  const contrast = numberOr(color?.contrast);
  const saturation = numberOr(color?.saturation);
  const temperature = numberOr(color?.temperature);
  const parts = [
    `brightness(${clamp(1 + exposure * 0.55, 0.2, 2.2).toFixed(3)})`,
    `contrast(${clamp(1 + contrast * 0.65, 0.2, 2.2).toFixed(3)})`,
    `saturate(${clamp(1 + saturation * 0.9, 0, 2.4).toFixed(3)})`,
  ];
  if (temperature > 0) parts.push(`sepia(${(temperature * 0.32).toFixed(3)})`);
  if (temperature < 0) parts.push(`hue-rotate(${Math.round(temperature * -18)}deg)`);
  return parts.join(" ");
}

/** A hook sentence trimmed to a card: whole words, at most `limit` characters. */
export function hookCardText(sentence, limit = 60) {
  const value = String(sentence || "").replace(/\s+/g, " ").trim();
  if (!value) return "";
  if (value.length <= limit) return value;
  const cut = value.slice(0, limit + 1);
  const space = cut.lastIndexOf(" ");
  return `${(space > limit * 0.5 ? cut.slice(0, space) : value.slice(0, limit)).replace(/[,;:\-–—]+$/, "")}…`;
}

/** A bold plate that reads over any footage; the default for hook cards. */
export const HOOK_STYLE = { size: 64, weight: 900, background: "#000000b3", stroke: "none", shadow: false };

export function newTextLayer(kind, { duration = 5, playhead = 0, index = 0, hookText = "" } = {}) {
  const chosen = TEXT_KINDS[kind] ? kind : "hook";
  const preset = TEXT_KINDS[chosen];
  // A hook opens the story; titles and lower thirds go where the playhead is.
  const start = chosen === "hook" ? 0 : clamp(playhead, 0, Math.max(0, duration - 0.5));
  const end = clamp(start + 3, start + 0.4, Math.max(start + 0.5, duration));
  const text = chosen === "hook" ? (hookCardText(hookText) || preset.sample) : preset.sample;
  return {
    id: uid("tx"),
    type: "text",
    kind: chosen,
    text,
    start: round(start),
    end: round(end),
    anchor: preset.anchor,
    box: { ...preset.box },
    z: 10 + index,
    style: { ...TEXT_STYLE_DEFAULTS, ...(chosen === "hook" ? HOOK_STYLE : {}) },
    safe_zone: true,
    opacity: 1,
  };
}

export function captionPreset(styleId) {
  const preset = CAPTION_PRESETS[styleId] || CAPTION_PRESETS.clean;
  return {
    ...clone(CAPTION_STYLE_DEFAULTS),
    ...clone(preset.values),
    id: CAPTION_PRESETS[styleId] ? styleId : "clean",
  };
}
