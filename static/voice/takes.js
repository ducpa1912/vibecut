/**
 * Voice Room — the Takes list beside the work.
 *
 * Every preview and voiceover is kept on this Mac by the server. This module
 * reads that list, lets a take be starred, replayed, loaded back into the
 * editor, saved as a new voice, or deleted, and shows the cleanup warning for
 * old unstarred takes. It never removes anything without a confirm.
 *
 * Routes:
 *   GET    /api/voices/takes
 *   GET    /api/voices/takes/cleanup
 *   POST   /api/voices/takes/cleanup      (confirm: true)
 *   PATCH  /api/voices/takes/{id}         (starred)
 *   DELETE /api/voices/takes/{id}
 *   GET    /api/voices/takes/{id}/audio
 *   POST   /api/voices/takes/{id}/save-voice
 */

import { request, syncTokenCookie } from "./api.js";
import { el } from "./ui.js";
import { relativeTime } from "./recent.js";

const DISMISS_KEY = "vibecut.voice.cleanup.dismissed.v1";
const FLAGS = [
  ["silent", "no speech"],
  ["too_quiet", "quiet"],
  ["too_loud", "loud"],
  ["clipping", "clipping"],
];

export function listTakes() {
  return request("/api/voices/takes");
}

export function starTake(takeId, starred = true) {
  return request(`/api/voices/takes/${encodeURIComponent(takeId)}`, {
    method: "PATCH", body: { starred: Boolean(starred) },
  });
}

export function deleteTake(takeId) {
  return request(`/api/voices/takes/${encodeURIComponent(takeId)}`, { method: "DELETE" });
}

export function saveTakeAsVoice(takeId, name) {
  return request(`/api/voices/takes/${encodeURIComponent(takeId)}/save-voice`, {
    method: "POST", body: { name },
  });
}

export function cleanupTakes(confirm = false, days = 30) {
  return request("/api/voices/takes/cleanup", {
    method: "POST", body: { confirm: Boolean(confirm), days },
  });
}

/** Play one kept take through the page's one player. */
export function playTakeAudio(take) {
  syncTokenCookie();
  if (!take?.audio_url) throw new Error("That take has no audio on this Mac. Delete it and make a new one.");
  const player = new Audio(take.audio_url);
  return player.play().then(() => player);
}

function dismissed() {
  try {
    return localStorage.getItem(DISMISS_KEY) === "1";
  } catch (_) {
    return false;
  }
}

function dismiss() {
  try {
    localStorage.setItem(DISMISS_KEY, "1");
  } catch (_) {
    /* storage disabled: the warning comes back next time */
  }
}

function seconds(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "";
  return `${number.toFixed(1)} s`;
}

export function takeMeta(take) {
  const parts = [relativeTime(take?.created)];
  if (take?.cached) parts.push("from cache");
  const rate = Number(take?.settings?.rate);
  if (Number.isFinite(rate) && Math.abs(rate - 1) > 0.001) parts.push(`${rate.toFixed(2)}×`);
  if (take?.seconds) parts.push(seconds(take.seconds));
  return parts.filter(Boolean).join(" · ");
}

/** Short, honest advice chips for one take. Advisory only. */
export function checkFlags(take) {
  const check = take?.check;
  if (!check || check.available === false) return [];
  const flags = [];
  for (const [key, label] of FLAGS) {
    if (check[key]) flags.push({ key, label, note: (check.notes || []).find((line) => line) || "" });
  }
  if (!flags.length && check.silent === false) return [];
  return flags;
}

export function driftLines(take) {
  const check = take?.selfcheck;
  if (!check || check.status !== "checked") return [];
  return (check.lines || []).filter((line) => line.drift);
}

/**
 * @param {{ onLoadSettings?: (take: any) => void, onPlayTake?: (take: any) => void,
 *           onSaved?: (record: any) => void, onNotice?: (message: string, tone?: string) => void,
 *           isActive?: (take: any) => boolean, showKeep?: boolean,
 *           onKeepTake?: (take: any) => Promise<any> }} options
 */
export function createTakesPanel({
  onLoadSettings = () => {},
  onPlayTake = () => {},
  onSaved = () => {},
  onNotice = () => {},
  isActive = () => false,
  onKeepTake = null,
  onLockVoice = null,
} = {}) {
  const node = el("aside", { class: "vg-takes", id: "vg-takes", "data-panel": "takes", "aria-label": "Takes" });
  let takes = [];
  let plan = null;
  let filter = "all";
  let error = "";
  let busy = "";
  let loaded = false;
  let showCleanup = false;
  let openDrift = "";

  async function refresh() {
    try {
      const result = await listTakes();
      takes = Array.isArray(result?.takes) ? result.takes : [];
      plan = result?.cleanup || null;
      error = "";
    } catch (cause) {
      error = cause?.message || "Could not read the takes on this Mac.";
    }
    loaded = true;
    render();
  }

  async function toggleStar(take) {
    if (busy) return;
    busy = `star:${take.id}`;
    render();
    try {
      await starTake(take.id, !take.starred);
      await refresh();
    } catch (cause) {
      onNotice(cause?.message || "Could not star that take.", "bad");
    } finally {
      busy = "";
      render();
    }
  }

  async function remove(take) {
    if (!window.confirm(`Delete the take “${take.label}”? Its audio is removed from this Mac.`)) return;
    busy = `delete:${take.id}`;
    render();
    try {
      await deleteTake(take.id);
      onNotice("Take deleted.", "ok");
      await refresh();
    } catch (cause) {
      onNotice(cause?.message || "Could not delete that take.", "bad");
    } finally {
      busy = "";
      render();
    }
  }

  async function saveAsVoice(take) {
    if (busy) return;
    const name = window.prompt("Name the new voice", `${take.label} take`);
    if (name === null) return;
    busy = `save:${take.id}`;
    render();
    try {
      const record = await saveTakeAsVoice(take.id, name.trim());
      onNotice(`Saved “${record?.name || name}” as a new voice.`, "ok");
      onSaved(record);
    } catch (cause) {
      onNotice(cause?.message || "Could not save that take as a voice.", "bad");
    } finally {
      busy = "";
      render();
    }
  }

  async function runCleanup() {
    const count = Number(plan?.count) || 0;
    if (!count) return;
    if (!window.confirm(`Remove ${count} unstarred take${count === 1 ? "" : "s"} older than ${plan.days} days? Starred takes are kept.`)) return;
    busy = "cleanup";
    render();
    try {
      const result = await cleanupTakes(true, plan.days);
      showCleanup = false;
      onNotice(`Cleaned up ${Number(result?.deleted) || 0} old take${Number(result?.deleted) === 1 ? "" : "s"}.`, "ok");
      await refresh();
    } catch (cause) {
      onNotice(cause?.message || "Could not clean up the old takes.", "bad");
    } finally {
      busy = "";
      render();
    }
  }

  async function keep(take) {
    if (!onKeepTake || busy) return;
    busy = `keep:${take.id}`;
    render();
    try {
      await onKeepTake(take);
      onNotice("Kept that take's settings for this voice.", "ok");
      await refresh();
    } catch (cause) {
      onNotice(cause?.message || "Could not keep that take.", "bad");
    } finally {
      busy = "";
      render();
    }
  }

  function flagsFor(take) {
    const flags = checkFlags(take);
    const advice = Array.isArray(take?.check?.advice) ? take.check.advice : [];
    if (!flags.length && !advice.length) return null;
    const box = el("div", { class: "vg-take-check" }, [
      flags.length ? el("div", { class: "vg-take-flags" }, flags.map((flag) => el("span", {
        class: `vg-take-flag is-${flag.key}`,
        text: flag.label,
        title: flag.note || "Advisory only; the audio was not changed.",
      }))) : null,
      advice.length ? el("span", { class: "vg-take-checknote", text: `${advice[0]} Advice only; the audio was not changed.` }) : null,
    ]);
    return box;
  }

  function driftFor(take) {
    const lines = driftLines(take);
    if (!lines.length) {
      const check = take?.selfcheck;
      if (check?.status === "checked") {
        return el("span", { class: "vg-take-ok", text: "Lines match the script" });
      }
      return null;
    }
    const open = openDrift === take.id;
    const button = el("button", {
      class: "vg-take-drift-open", type: "button",
      text: `${lines.length} line${lines.length === 1 ? "" : "s"} may differ`,
      "aria-expanded": open ? "true" : "false",
      on: {
        click: () => {
          openDrift = open ? "" : take.id;
          render();
        },
      },
    });
    const box = el("div", { class: "vg-take-drift" }, [button]);
    if (open) {
      box.append(el("ul", {}, lines.map((line) => el("li", {}, [
        el("span", { class: "vg-take-drift-line", text: `${line.index}. ${line.script}` }),
        el("span", { class: "vg-take-drift-heard", text: line.heard ? `heard: ${line.heard}` : "heard: nothing" }),
      ]))));
    }
    return box;
  }

  function row(take) {
    const active = Boolean(isActive(take));
    const star = el("button", {
      class: `vg-take-star${take.starred ? " is-on" : ""}`,
      type: "button",
      text: take.starred ? "★" : "☆",
      title: take.starred ? "Starred — kept by cleanup" : "Star this take to keep it",
      "aria-label": `${take.starred ? "Unstar" : "Star"} ${take.label}`,
      "aria-pressed": take.starred ? "true" : "false",
    });
    star.addEventListener("click", () => { void toggleStar(take); });

    const play = el("button", {
      class: "vg-take-action", type: "button",
      text: active ? "Stop" : "Play",
      "aria-label": `${active ? "Stop" : "Play"} ${take.label}`,
      on: { click: () => onPlayTake(take) },
    });
    const load = el("button", {
      class: "vg-take-action", type: "button", text: "Load settings",
      title: "Restore the script, voice, rate and language of this take",
      on: { click: () => onLoadSettings(take) },
    });
    const save = el("button", {
      class: "vg-take-action", type: "button", text: "Save as voice",
      disabled: !take.clone_voice,
      title: take.clone_voice
        ? "Make a new cloned voice from this take's reference"
        : "Only a take made in one of your cloned voices can become a voice",
      on: { click: () => { void saveAsVoice(take); } },
    });
    const del = el("button", {
      class: "vg-take-action is-danger", type: "button", text: "Delete",
      on: { click: () => { void remove(take); } },
    });
    const actions = [play, load, save];
    if (onKeepTake && take.clone_voice) {
      actions.push(el("button", {
        class: "vg-take-action", type: "button", text: "Keep take",
        title: "Pin this take's settings on its voice",
        on: { click: () => { void keep(take); } },
      }));
    }
    if (onLockVoice && take.clone_voice) {
      actions.push(el("button", {
        class: "vg-take-action", type: "button", text: "Open voice",
        title: "Open the voice page for this clone",
        on: { click: () => onLockVoice(take.clone_voice) },
      }));
    }
    actions.push(del);

    return el("article", { class: `vg-take${active ? " is-active" : ""}`, "data-take": take.id }, [
      el("div", { class: "vg-take-head" }, [
        star,
        el("div", { class: "vg-take-copy" }, [
          el("strong", { text: take.label || "Take" }),
          el("span", { class: "vg-take-meta", text: takeMeta(take) }),
        ]),
        el("span", { class: "vg-take-kind", text: take.kind === "voiceover" ? "Voiceover" : "Preview" }),
      ]),
      flagsFor(take),
      driftFor(take),
      el("div", { class: "vg-take-actions" }, actions),
    ]);
  }

  function cleanupCard() {
    if (!plan || !plan.count || dismissed()) return null;
    if (showCleanup) {
      return el("div", { class: "vg-cleanup" }, [
        el("strong", { text: `${plan.count} old take${plan.count === 1 ? "" : "s"} can be cleaned up` }),
        el("p", { text: `Unstarred takes older than ${plan.days} days may be removed. Star the ones you want to keep.` }),
        el("div", { class: "vg-take-actions" }, [
          el("button", { class: "vg-take-action", type: "button", text: "Clean up", on: { click: () => { void runCleanup(); } } }),
          el("button", {
            class: "vg-take-action", type: "button", text: "Keep for now",
            on: { click: () => { showCleanup = false; dismiss(); render(); } },
          }),
        ]),
      ]);
    }
    return el("div", { class: "vg-cleanup" }, [
      el("p", { text: `${plan.count} unstarred take${plan.count === 1 ? " is" : "s are"} older than ${plan.days} days.` }),
      el("button", {
        class: "vg-take-action", type: "button", text: "Review cleanup",
        on: { click: () => { showCleanup = true; render(); } },
      }),
    ]);
  }

  function render() {
    const head = el("div", { class: "vg-takes-head" }, [
      el("div", {}, [
        el("h2", { text: "Takes" }),
        el("span", { class: "vg-takes-count", text: `${takes.length}` }),
      ]),
      el("div", { class: "vg-take-filter" }, [
        el("button", {
          type: "button", text: "All", class: filter === "all" ? "is-on" : "",
          "aria-pressed": filter === "all" ? "true" : "false",
          on: { click: () => { filter = "all"; render(); } },
        }),
        el("button", {
          type: "button", text: "Starred", class: filter === "starred" ? "is-on" : "",
          "aria-pressed": filter === "starred" ? "true" : "false",
          on: { click: () => { filter = "starred"; render(); } },
        }),
      ]),
    ]);
    const children = [head];
    if (error) children.push(el("p", { class: "vg-take-error", role: "alert", text: error }));
    const warning = cleanupCard();
    if (warning) children.push(warning);
    if (!loaded) {
      children.push(el("p", { class: "vg-takes-empty", text: "Reading takes…" }));
    } else {
      const shown = filter === "starred" ? takes.filter((take) => take.starred) : takes;
      if (!shown.length) {
        children.push(el("p", {
          class: "vg-takes-empty",
          text: filter === "starred"
            ? "No starred takes yet. Star one to keep it through cleanup."
            : "Nothing yet. Play a voice or make a voiceover and it lands here.",
        }));
      } else {
        const list = el("div", { class: "vg-take-list" });
        for (const take of shown) list.append(row(take));
        children.push(list);
      }
    }
    node.replaceChildren(...children);
  }

  render();
  return { node, refresh };
}
