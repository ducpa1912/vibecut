/**
 * One inline icon set for the editor.
 *
 * Paths are adapted from Lucide (MIT). Icons inherit `currentColor`, so the
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
