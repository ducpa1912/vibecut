/**
 * One inline icon set for the editor.
 *
 * Paths are adapted from Lucide (ISC License). Icons inherit `currentColor`, so the
 * layer palette can colour them without a second stylesheet.
 */

const ICONS = {
  "arrow-left": [
    ["path", { d: "M19 12H5" }],
    ["path", { d: "m12 19-7-7 7-7" }],
  ],
  "arrow-right": [
    ["path", { d: "M5 12h14" }],
    ["path", { d: "m12 5 7 7-7 7" }],
  ],
  eraser: [
    ["path", { d: "m7 21-4.3-4.3a2.4 2.4 0 0 1 0-3.4l9.6-9.6a2.4 2.4 0 0 1 3.4 0l5.6 5.6a2.4 2.4 0 0 1 0 3.4L13 21" }],
    ["path", { d: "M22 21H7" }],
    ["path", { d: "m5 11 9 9" }],
  ],
  type: [
    ["path", { d: "M4 7V4h16v3" }],
    ["path", { d: "M9 20h6" }],
    ["path", { d: "M12 4v16" }],
  ],
  captions: [
    ["rect", { x: "3", y: "5", width: "18", height: "14", rx: "2" }],
    ["path", { d: "M7 15h4" }],
    ["path", { d: "M15 15h2" }],
    ["path", { d: "M7 11h2" }],
    ["path", { d: "M13 11h4" }],
  ],
  sparkles: [
    ["path", { d: "m12 3-1.9 5.1L5 10l5.1 1.9L12 17l1.9-5.1L19 10l-5.1-1.9L12 3Z" }],
    ["path", { d: "M5 3v4" }],
    ["path", { d: "M3 5h4" }],
    ["path", { d: "M19 17v4" }],
    ["path", { d: "M17 19h4" }],
  ],
  palette: [
    ["path", { d: "M12 3a9 9 0 0 0 0 18h1.5a1.5 1.5 0 0 0 0-3H12a2 2 0 0 1 0-4h1a5 5 0 0 0 0-10h-1Z" }],
    ["circle", { cx: "7.5", cy: "10.5", r: "1" }],
    ["circle", { cx: "9.5", cy: "7", r: "1" }],
    ["circle", { cx: "14", cy: "7", r: "1" }],
    ["circle", { cx: "16.5", cy: "10", r: "1" }],
  ],
  "audio-lines": [
    ["path", { d: "M2 10v3" }],
    ["path", { d: "M6 6v11" }],
    ["path", { d: "M10 3v18" }],
    ["path", { d: "M14 8v7" }],
    ["path", { d: "M18 5v13" }],
    ["path", { d: "M22 10v3" }],
  ],
  cursor: [
    ["path", { d: "m3 3 7.1 18 3.8-7.1 7.1-3.8Z" }],
  ],
  square: [
    ["rect", { x: "3", y: "3", width: "18", height: "18", rx: "2" }],
  ],
  undo: [
    ["path", { d: "M9 14 4 9l5-5" }],
    ["path", { d: "M4 9h10a6 6 0 0 1 0 12h-3" }],
  ],
  redo: [
    ["path", { d: "m15 14 5-5-5-5" }],
    ["path", { d: "M20 9H10a6 6 0 0 0 0 12h3" }],
  ],
  keyboard: [
    ["rect", { x: "2", y: "6", width: "20", height: "12", rx: "2" }],
    ["path", { d: "M6 10h.01M10 10h.01M14 10h.01M18 10h.01M6 14h.01M18 14h.01M9 14h6" }],
  ],
  plus: [
    ["path", { d: "M12 5v14" }],
    ["path", { d: "M5 12h14" }],
  ],
  x: [
    ["path", { d: "M18 6 6 18" }],
    ["path", { d: "m6 6 12 12" }],
  ],
  lock: [
    ["rect", { x: "4", y: "10", width: "16", height: "11", rx: "2" }],
    ["path", { d: "M8 10V7a4 4 0 0 1 8 0v3" }],
  ],
  eye: [
    ["path", { d: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" }],
    ["circle", { cx: "12", cy: "12", r: "3" }],
  ],
  "eye-off": [
    ["path", { d: "M3 3l18 18" }],
    ["path", { d: "M10.6 10.7a2 2 0 0 0 2.7 2.7" }],
    ["path", { d: "M9.9 5.2A10.5 10.5 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3 4.2" }],
    ["path", { d: "M6.3 6.4A17 17 0 0 0 2 12s3.5 7 10 7a10.7 10.7 0 0 0 4.2-.9" }],
  ],
  minus: [["path", { d: "M5 12h14" }]],
  mic: [
    ["rect", { x: "9", y: "2", width: "6", height: "12", rx: "3" }],
    ["path", { d: "M5 10v2a7 7 0 0 0 14 0v-2" }],
    ["path", { d: "M12 19v3" }],
  ],
  scissors: [
    ["circle", { cx: "6", cy: "6", r: "3" }],
    ["circle", { cx: "6", cy: "18", r: "3" }],
    ["path", { d: "M20 4 8.12 15.88" }],
    ["path", { d: "m14.47 14.48 5.53 5.52" }],
    ["path", { d: "M8.12 8.12 12 12" }],
  ],
  trash: [
    ["path", { d: "M3 6h18" }],
    ["path", { d: "M8 6V4h8v2" }],
    ["path", { d: "M19 6l-1 14H6L5 6" }],
    ["path", { d: "M10 11v5M14 11v5" }],
  ],
  split: [
    ["path", { d: "M12 3v18" }],
    ["path", { d: "m8 7-4 4 4 4" }],
    ["path", { d: "m16 7 4 4-4 4" }],
  ],
  "rotate-cw": [
    ["path", { d: "M21 12a9 9 0 1 1-3-6.7" }],
    ["path", { d: "M21 3v6h-6" }],
  ],
  mirror: [
    ["path", { d: "M12 3v18" }],
    ["path", { d: "m8 7-4 5 4 5V7Z" }],
    ["path", { d: "m16 7 4 5-4 5V7Z" }],
  ],
  flip: [
    ["path", { d: "M12 3v18" }],
    ["path", { d: "M4 7h6v10H4z" }],
    ["path", { d: "M14 7h6v10h-6z" }],
  ],
  freeze: [
    ["path", { d: "M12 2v20" }],
    ["path", { d: "m4 6 4 4-4 4" }],
    ["path", { d: "m20 6-4 4 4 4" }],
    ["path", { d: "M4 12h16" }],
  ],
  reverse: [
    ["path", { d: "M3 12a9 9 0 1 0 3-6.7" }],
    ["path", { d: "M3 3v6h6" }],
    ["path", { d: "m10 8 5 4-5 4V8Z" }],
  ],
  copy: [
    ["rect", { x: "8", y: "8", width: "13", height: "13", rx: "2" }],
    ["path", { d: "M5 16H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1" }],
  ],
  brush: [
    ["path", { d: "m9.06 11.9 8.07-8.06a2.85 2.85 0 1 1 4.03 4.03l-8.06 8.08" }],
    ["path", { d: "M7.07 14.94c-1.66 0-3 1.35-3 3.02 0 1.33-2.5 1.52-2 2.02 1.08 1.1 2.49 2.02 4 2.02 2.2 0 4-1.8 4-4.04a3.01 3.01 0 0 0-3-3.02z" }],
  ],
  mosaic: [
    ["rect", { x: "3", y: "3", width: "7", height: "7", rx: "1" }],
    ["rect", { x: "14", y: "3", width: "7", height: "7", rx: "1" }],
    ["rect", { x: "3", y: "14", width: "7", height: "7", rx: "1" }],
    ["rect", { x: "14", y: "14", width: "7", height: "7", rx: "1" }],
  ],
  loop: [
    ["path", { d: "m17 2 4 4-4 4" }],
    ["path", { d: "M3 11V9a4 4 0 0 1 4-4h14" }],
    ["path", { d: "m7 22-4-4 4-4" }],
    ["path", { d: "M21 13v2a4 4 0 0 1-4 4H3" }],
  ],
  expand: [
    ["path", { d: "M8 3H5a2 2 0 0 0-2 2v3" }],
    ["path", { d: "M16 3h3a2 2 0 0 1 2 2v3" }],
    ["path", { d: "M8 21H5a2 2 0 0 1-2-2v-3" }],
    ["path", { d: "M16 21h3a2 2 0 0 0 2-2v-3" }],
  ],
  settings: [
    ["path", { d: "M4 6h10M18 6h2" }],
    ["path", { d: "M4 12h2M10 12h10" }],
    ["path", { d: "M4 18h10M18 18h2" }],
    ["circle", { cx: "16", cy: "6", r: "2" }],
    ["circle", { cx: "8", cy: "12", r: "2" }],
    ["circle", { cx: "16", cy: "18", r: "2" }],
  ],
  history: [
    ["path", { d: "M3 12a9 9 0 1 0 3-6.7" }],
    ["path", { d: "M3 3v6h6" }],
    ["path", { d: "M12 7v5l3 2" }],
  ],
  trim: [
    ["path", { d: "M4 4h4v4H4z" }],
    ["path", { d: "M16 16h4v4h-4z" }],
    ["path", { d: "M8 8l8 8" }],
  ],
  crop: [
    ["path", { d: "M6 2v14a2 2 0 0 0 2 2h14" }],
    ["path", { d: "M2 6h14a2 2 0 0 1 2 2v14" }],
  ],
  "chevron-up": [["path", { d: "m18 15-6-6-6 6" }]],
  library: [
    ["rect", { x: "3", y: "4", width: "18", height: "16", rx: "2" }],
    ["path", { d: "M7 4v16" }],
    ["path", { d: "M11 8h5" }],
    ["path", { d: "M11 12h5" }],
    ["path", { d: "M11 16h3" }],
  ],
  layers: [
    ["path", { d: "m12 2 9 5-9 5-9-5 9-5Z" }],
    ["path", { d: "m3 12 9 5 9-5" }],
    ["path", { d: "m3 17 9 5 9-5" }],
  ],
};

let uid = 0;

export function icon(name, { size = 14, className = "" } = {}) {
  const paths = ICONS[name] || ICONS.square;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("class", `st-icon${className ? ` ${className}` : ""}`);
  if (!svg.id) svg.id = `st-icon-${++uid}`;
  for (const [tag, attrs] of paths) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    svg.append(node);
  }
  return svg;
}
