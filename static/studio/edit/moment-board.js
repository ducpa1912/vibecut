/**
 * Compact moment board at the top of Edit.
 *
 * Only the selected clips show by default. Numbers are cut order, not source
 * scene order. "Add scene" opens unused source scenes in the same 1:1 strip;
 * clicking one appends it to the Edit sequence.
 */

import { el, formatCount } from "../ui.js";
import { formatTime } from "./model.js";

function roleLabel(clip) {
  if (clip?.kind === "blank") return "Blank";
  const role = String(clip?.role || "beat");
  if (role === "hook") return "Hook";
  if (role === "payoff") return "Payoff";
  const kind = String(clip?.beat_kind || "");
  if (kind === "broll") return "B-roll";
  if (kind === "statement") return "Statement";
  if (kind === "proof") return "Proof";
  if (kind === "context") return "Context";
  if (kind === "transition") return "Transition";
  return "Scene";
}

function duration(clip) {
  return Math.max(0, Number(clip?.end) - Number(clip?.start));
}

function sceneFor(job, id) {
  return (job?.analysis?.scenes || []).find((scene) => Number(scene.id) === Number(id)) || null;
}

function thumbFor(job, scene) {
  return scene?.thumb_url || `/api/jobs/${encodeURIComponent(job?.id || "")}/thumb/${Number(scene?.id ?? 0)}`;
}

export function mountMomentBoard(host, ctx) {
  if (!host) return;
  const job = ctx.getJob();
  const story = ctx.getStory();
  const edit = ctx.getEdit();
  const custom = Array.isArray(edit?.sequence) ? edit.sequence : [];
  const clips = custom.length ? custom : (story?.clips || []);
  const used = new Set(clips.map((clip) => Number(clip.scene)));
  const expanded = Boolean(ctx.getExpanded?.());
  const total = clips.reduce((sum, clip) => sum + duration(clip), 0);

  const head = el("div", { class: "st-mb-head" }, [
    el("h2", { text: "Cut moments" }),
    el("p", { text: "Only selected scenes. Number is cut order." }),
    el("span", { class: "st-mb-total", text: `${formatTime(total)} · ${formatCount(clips.length, "scene")}` }),
  ]);
  const strip = el("div", { class: "st-mb-strip" });
  let offset = 0;
  clips.forEach((clip, index) => {
    const scene = sceneFor(job, clip.scene);
    const blank = clip?.kind === "blank";
    const tile = el("button", {
      class: `st-mb-tile${blank ? " is-blank" : ""}`,
      type: "button",
      title: `${roleLabel(clip)} · ${blank ? "blank" : `scene ${Number(clip.scene) + 1}`} · ${formatTime(offset)}`,
    }, [
      blank ? null : el("img", { src: thumbFor(job, scene), alt: "", loading: "lazy" }),
      el("span", { class: "st-mb-num", text: String(index + 1) }),
      el("span", { class: `st-mb-role is-${String(clip.role || "beat")} ${clip.beat_kind ? `is-${clip.beat_kind}` : ""}`, text: roleLabel(clip) }),
    ]);
    tile.addEventListener("click", () => ctx.seek(offset));
    strip.append(tile);
    offset += duration(clip);
  });

  if (expanded) {
    const unused = (job?.analysis?.scenes || []).filter((scene) => !used.has(Number(scene.id)));
    for (const scene of unused) {
      const tile = el("button", {
        class: "st-mb-tile is-source",
        type: "button",
        title: `Add scene ${Number(scene.id) + 1}`,
      }, [
        el("img", { src: thumbFor(job, scene), alt: "", loading: "lazy" }),
        el("span", { class: "st-mb-role", text: "Source scene" }),
      ]);
      tile.addEventListener("click", () => ctx.appendScene(scene));
      strip.append(tile);
    }
  }

  const blank = el("button", {
    class: "st-mb-add is-blank",
    type: "button",
    text: "Blank",
    title: "Add 0.8s dark filler",
  });
  blank.addEventListener("click", () => ctx.appendBlank());
  strip.append(blank);

  const add = el("button", {
    class: `st-mb-add${expanded ? " is-open" : ""}`,
    type: "button",
    "aria-expanded": expanded ? "true" : "false",
    text: expanded ? "Close scenes" : "Add scene",
  });
  add.addEventListener("click", () => ctx.toggleExpanded());
  strip.append(add);

  host.replaceChildren(head, strip);
}
