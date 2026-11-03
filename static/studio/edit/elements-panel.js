/**
 * Elements — the left panel.
 *
 * Four tabs own creation: Moments, Elements (FX), Text and Audio. The panel
 * never owns an Edit; every change goes back through the parent's callbacks,
 * exactly like the old moment board and inspector.
 */

import { el, formatCount } from "../ui.js";
import { icon } from "./icons.js";
import { formatTime } from "./model.js";
import { mountEffectsPanel } from "./layers/effects.js";
import { mountTextPanel } from "./layers/text.js";
import { mountAudioPanel } from "./layers/audio.js";

const TABS = [
  ["moments", "Moments", "layers"],
  ["elements", "Elements", "sparkles"],
  ["text", "Text", "type"],
  ["audio", "Audio", "audio-lines"],
];

function roleLabel(clip) {
  if (clip?.kind === "blank") return "Blank";
  if (clip?.kind === "file") return clip?.asset_kind === "photo" ? "Photo" : "Clip";
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

function clipDuration(clip) {
  return Math.max(0, Number(clip?.end) - Number(clip?.start));
}

function sceneFor(job, id) {
  return (job?.analysis?.scenes || []).find((scene) => Number(scene.id) === Number(id)) || null;
}

function thumbFor(job, scene) {
  return scene?.thumb_url || `/api/jobs/${encodeURIComponent(job?.id || "")}/thumb/${Number(scene?.id ?? 0)}`;
}

function clipThumb(job, edit, clip) {
  if (clip?.kind === "file") {
    return `/api/jobs/${encodeURIComponent(job?.id || "")}/assets/${encodeURIComponent(clip.asset_id)}/thumb`;
  }
  return thumbFor(job, sceneFor(job, clip?.scene));
}

export function mountElementsPanel(host, ctx) {
  if (!host) return null;
  let active = String(ctx.getTab?.() || "moments");
  let search = "";
  let filter = "all";
  let sort = "source";
  let selectedClip = -1;
  let dragged = -1;

  const nav = el("nav", { class: "st-el-tabs", role: "tablist", "aria-label": "Elements" });
  const body = el("div", { class: "st-el-body" });
  host.replaceChildren(nav, body);

  function renderNav() {
    nav.replaceChildren();
    for (const [id, label, iconName] of TABS) {
      const selected = id === active;
      const button = el("button", {
        class: `st-el-tab${selected ? " is-active" : ""}`,
        type: "button",
        role: "tab",
        "aria-selected": selected ? "true" : "false",
        "aria-controls": "st-el-body",
        tabindex: selected ? "0" : "-1",
        title: label,
        dataset: { tab: id },
      }, [icon(iconName, { size: 14 }), el("span", { text: label })]);
      button.addEventListener("click", () => {
        active = id;
        ctx.setTab?.(id);
        renderNav();
        renderBody();
      });
      nav.append(button);
    }
  }

  function renderBody() {
    if (!host.isConnected) return;
    body.replaceChildren();
    if (active === "moments") renderMoments();
    else if (active === "elements") {
      mountEffectsPanel(body, ctx);
    } else if (active === "text") {
      mountTextPanel(body, ctx);
    } else {
      mountAudioPanel(body, { ...ctx, libraryOnly: true });
    }
  }

  function renderMoments() {
    const job = ctx.getJob();
    const story = ctx.getStory();
    const edit = ctx.getEdit();
    const custom = Array.isArray(edit?.sequence) ? edit.sequence : [];
    const clips = custom.length ? custom : (story?.clips || []);
    const expanded = Boolean(ctx.getExpanded?.());
    const total = clips.reduce((sum, clip) => sum + clipDuration(clip), 0);

    const actions = el("div", { class: "st-el-actions" }, [
      el("button", {
        class: "st-icon-btn st-el-action",
        type: "button",
        title: "Import another video",
        "aria-label": "Import another video",
      }, [icon("plus", { size: 15 })]),
      el("button", {
        class: "st-icon-btn st-el-action",
        type: "button",
        title: "Dissect another video into scenes",
        "aria-label": "Dissect another video into scenes",
      }, [icon("scissors", { size: 15 })]),
      el("span", { class: "st-el-count", text: `${formatTime(total)} · ${formatCount(clips.length, "scene", "scenes")}` }),
    ]);
    const [importButton, dissectButton] = actions.querySelectorAll("button");
    importButton.addEventListener("click", () => ctx.openImport?.());
    dissectButton.addEventListener("click", () => ctx.openDissect?.());

    const cutHead = el("div", { class: "st-el-group-head" }, [
      el("strong", { text: "This cut" }),
      el("span", { text: String(clips.length).padStart(2, "0") }),
    ]);
    const strip = el("div", { class: "st-el-cut" });
    let offset = 0;
    clips.forEach((clip, index) => {
      const asset = (edit?.assets || []).find((item) => item.id === clip.asset_id);
      const file = clip?.kind === "file";
      const blank = clip?.kind === "blank";
      const tile = el("button", {
        class: `st-el-clip${blank ? " is-blank" : ""}${selectedClip === index ? " is-selected" : ""}`,
        type: "button",
        draggable: "true",
        "aria-pressed": selectedClip === index ? "true" : "false",
        title: `${roleLabel(clip)} · ${blank ? "blank" : `scene ${Number(clip.scene) + 1}`} · ${formatTime(offset)}`,
        dataset: { index: String(index) },
      }, [
        blank ? null : el("img", { src: clipThumb(job, edit, clip), alt: "", loading: "lazy" }),
        el("span", { class: "st-el-num", text: String(index + 1) }),
        el("span", { class: `st-el-role is-${String(clip.role || "beat")}`, text: roleLabel({ ...clip, asset_kind: asset?.kind }) }),
        el("span", { class: "st-el-dur", text: formatTime(clipDuration(clip)) }),
      ]);
      tile.addEventListener("click", () => {
        selectedClip = index;
        renderBody();
        ctx.seek?.(offset);
      });
      tile.addEventListener("dragstart", (event) => {
        dragged = index;
        event.dataTransfer?.setData("text/plain", String(index));
      });
      tile.addEventListener("dragover", (event) => {
        event.preventDefault();
      });
      tile.addEventListener("drop", (event) => {
        event.preventDefault();
        if (dragged < 0 || dragged === index) return;
        ctx.reorder?.(dragged, index);
        dragged = -1;
        selectedClip = index;
        renderBody();
      });
      strip.append(tile);
      offset += clipDuration(clip);
    });
    if (!clips.length) {
      strip.append(el("p", { class: "st-el-empty", text: "No scenes in this cut yet." }));
    }

    const addRow = el("div", { class: "st-el-add-row" }, [
      el("button", { class: "st-btn st-btn-ghost st-btn-small", type: "button", text: "Blank" }),
      el("button", {
        class: `st-btn st-btn-ghost st-btn-small${expanded ? " is-active" : ""}`,
        type: "button",
        text: expanded ? "Hide source" : "Add scene",
        "aria-expanded": expanded ? "true" : "false",
      }),
    ]);
    const [blank, addScene] = addRow.querySelectorAll("button");
    blank.addEventListener("click", () => ctx.appendBlank?.());
    addScene.addEventListener("click", () => ctx.toggleExpanded?.());

    body.append(actions, cutHead, strip, addRow);

    if (expanded) {
      const used = new Set(clips.map((clip) => Number(clip.scene)));
      const unused = (job?.analysis?.scenes || []).filter((scene) => !used.has(Number(scene.id)));
      const sources = el("div", { class: "st-el-source" });
      for (const scene of unused) {
        const tile = el("button", {
          class: "st-el-source-tile",
          type: "button",
          title: `Add scene ${Number(scene.id) + 1}`,
        }, [
          el("img", { src: thumbFor(job, scene), alt: "", loading: "lazy" }),
          el("span", { text: `+ ${Number(scene.id) + 1}` }),
        ]);
        tile.addEventListener("click", () => ctx.appendScene?.(scene));
        sources.append(tile);
      }
      if (!unused.length) sources.append(el("p", { class: "st-el-empty", text: "Every source scene is in this cut." }));
      body.append(el("div", { class: "st-el-group-head" }, [
        el("strong", { text: "Source scenes" }),
        el("span", { text: String(unused.length) }),
      ]), sources);
    }

    const scenes = job?.analysis?.scenes || [];
    const query = search.trim().toLowerCase();
    const filtered = scenes
      .filter((scene) => {
        if (filter === "used" && !clips.some((clip) => Number(clip.scene) === Number(scene.id))) return false;
        if (filter === "unused" && clips.some((clip) => Number(clip.scene) === Number(scene.id))) return false;
        if (!query) return true;
        return `${scene.id} ${scene.label || ""} ${scene.text || ""}`.toLowerCase().includes(query);
      })
      .sort((a, b) => {
        if (sort === "duration") return Number(b.end) - Number(b.start) - (Number(a.end) - Number(a.start));
        if (sort === "score") return Number(b.score || 0) - Number(a.score || 0);
        return Number(a.id) - Number(b.id);
      });

    const searchInput = el("input", {
      type: "search",
      class: "st-el-search",
      placeholder: "Search scenes",
      "aria-label": "Search scenes",
      value: search,
    });
    searchInput.addEventListener("input", () => { search = searchInput.value; renderBody(); });
    const filterSelect = el("select", { class: "st-el-filter", "aria-label": "Filter scenes" });
    for (const [value, label] of [["all", "All"], ["used", "Used"], ["unused", "Unused"]]) {
      filterSelect.append(el("option", { value, text: label, selected: filter === value }));
    }
    filterSelect.addEventListener("change", () => { filter = filterSelect.value; renderBody(); });
    const sortSelect = el("select", { class: "st-el-filter", "aria-label": "Sort scenes" });
    for (const [value, label] of [["source", "Source"], ["duration", "Longest"], ["score", "Score"]]) {
      sortSelect.append(el("option", { value, text: label, selected: sort === value }));
    }
    sortSelect.addEventListener("change", () => { sort = sortSelect.value; renderBody(); });

    const galleryHead = el("div", { class: "st-el-group-head" }, [
      el("strong", { text: "Gallery" }),
      el("span", { text: String(filtered.length) }),
    ]);
    const gallery = el("div", { class: "st-el-gallery" });
    for (const scene of filtered.slice(0, 80)) {
      const used = clips.some((clip) => Number(clip.scene) === Number(scene.id));
      const tile = el("button", {
        class: `st-el-gallery-tile${used ? " is-used" : ""}`,
        type: "button",
        title: `${scene.label || `Scene ${Number(scene.id) + 1}`} · ${formatTime(Number(scene.end) - Number(scene.start))}`,
      }, [
        el("img", { src: thumbFor(job, scene), alt: "", loading: "lazy" }),
        used ? el("span", { class: "st-el-used", text: "In cut" }) : el("span", { class: "st-el-plus", text: "+" }),
      ]);
      tile.addEventListener("click", () => {
        if (used) {
          const index = clips.findIndex((clip) => Number(clip.scene) === Number(scene.id));
          selectedClip = index;
          renderBody();
          return;
        }
        ctx.appendScene?.(scene);
      });
      gallery.append(tile);
    }
    if (!filtered.length) gallery.append(el("p", { class: "st-el-empty", text: "No scenes match." }));

    body.append(galleryHead, el("div", { class: "st-el-tools" }, [searchInput, filterSelect, sortSelect]), gallery);
  }

  renderNav();
  renderBody();

  return {
    setActive(tab) {
      if (!TABS.some(([id]) => id === tab)) return;
      active = tab;
      renderNav();
      renderBody();
    },
    refresh() {
      renderNav();
      renderBody();
    },
    getActive() {
      return active;
    },
  };
}
