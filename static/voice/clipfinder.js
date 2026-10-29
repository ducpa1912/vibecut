/**
 * Voice Room — clean-clip finder for one video.
 *
 * Pick a video already in VibeCut, find its cleanest speech clips (music
 * removed, denoised, speech only), listen to each one, and clone the speaker
 * from the clip you pick. A time range is the fallback when no clip fits.
 * The same routes back Studio's Edit audio panel.
 *
 * Routes:
 *   POST   /api/jobs/{id}/voices/candidates          start (or rejoin) the search
 *   GET    /api/jobs/{id}/voices/candidates          state, stage and clips
 *   DELETE /api/jobs/{id}/voices/candidates          cancel the search
 *   GET    /api/jobs/{id}/voices/candidates/{n}/audio
 *   POST   /api/jobs/{id}/voices/clone               (candidate, or start/end)
 *   DELETE /api/voices/tasks/{task}                   cancel that clone
 */

import { syncTokenCookie } from "./api.js";
import { el, formatDuration } from "./ui.js";
import {
  CONSENT_COPY,
  cancelVoiceCandidates,
  cancelVoiceTask,
  cleaningNote,
  cloneFromVideo,
  findVoiceCandidates,
  newVoiceTask,
  voiceCandidateAudioUrl,
  voiceCandidateState,
  wasCancelled,
} from "./voiceclone.js";

const POLL_MS = 1500;

/** Plain words for the search state, or "" when there is nothing to say. */
export function stageCopy(task) {
  if (!task) return "";
  if (task.state === "failed") return task.error || "The clip search failed.";
  if (task.state === "cancelled") return "Search cancelled.";
  if (task.state === "done" || task.state === "idle") return "";
  const stage = String(task.stage || task.state || "");
  if (stage === "queued") return "Queued behind other voice work…";
  if (stage === "preparing" || stage === "starting") return "Finding the speech and removing music…";
  if (stage === "scoring") return "Scoring speech windows…";
  if (stage === "exporting") return "Cutting the best clips…";
  return "Working…";
}

export function isRunning(task) {
  return task?.state === "queued" || task?.state === "running";
}

/** A short quality line for one clip: score, signal to noise, music left. */
export function clipFacts(item) {
  const facts = [];
  const quality = item?.quality || {};
  if (Number.isFinite(Number(item?.duration)) && Number(item.duration) > 0) {
    facts.push(`${Math.round(Number(item.duration))} s`);
  }
  if (quality.snr_db !== null && quality.snr_db !== undefined && Number.isFinite(Number(quality.snr_db))) {
    facts.push(`clarity ${Math.round(Number(quality.snr_db))} dB`);
  }
  if (item?.speech_fraction !== null && item?.speech_fraction !== undefined && Number.isFinite(Number(item.speech_fraction))) {
    facts.push(`${Math.round(Number(item.speech_fraction) * 100)}% speech`);
  }
  return facts.join(" · ");
}

/**
 * The clip finder card. Owns its node and state so a running search and its
 * poll survive the page re-rendering around it.
 * @param {{ jobs: () => Array<any>, available: () => boolean, onCloned?: (record: any) => void,
 *           onNotice?: (message: string, tone?: string) => void }} options
 */
export function createClipFinder({ jobs, available, onCloned = () => {}, onNotice = () => {} }) {
  const node = el("section", { class: "vr-card vr-finder", "data-panel": "clip-finder" });
  let jobId = "";
  let task = null;
  let error = "";
  let busy = "";
  let pollTimer = 0;
  let picked = 0;
  let playing = 0;
  let player = null;
  let manual = false;
  let fullSearch = false;
  let start = "";
  let end = "";
  let name = "";
  let consent = false;
  let cloneTask = "";
  let disposed = false;

  function stopPoll() {
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = 0;
  }

  function stopPlayer() {
    if (player) player.pause();
    player = null;
    playing = 0;
  }

  function schedule(delay = POLL_MS) {
    stopPoll();
    const forJob = jobId;
    pollTimer = window.setTimeout(() => { void poll(forJob); }, delay);
  }

  async function poll(forJob) {
    if (disposed || forJob !== jobId) return;
    try {
      const state = await voiceCandidateState(forJob);
      if (disposed || forJob !== jobId) return;
      const same = task && task.state === state.state && task.stage === state.stage;
      task = state;
      error = state.state === "failed" ? (state.error || "The clip search failed.") : "";
      if (isRunning(state)) schedule();
      else pollTimer = 0;
      // Redraw only on a change, so a button under the pointer stays put.
      if (same && isRunning(state)) return;
    } catch (cause) {
      if (disposed || forJob !== jobId) return;
      pollTimer = 0;
      error = cause?.message || "Could not read the clip search.";
    }
    render();
  }

  function choose(id) {
    if (id === jobId) return;
    stopPoll();
    stopPlayer();
    jobId = id;
    task = null;
    error = "";
    picked = 0;
    consent = false;
    manual = false;
    const job = (jobs() || []).find((row) => row.id === id);
    name = job ? `${String(job.name || "Video").replace(/\.[^.]+$/, "")} voice`.slice(0, 64) : "";
    render();
    // A search that already ran (or is still running) for this video shows up.
    if (id) void poll(id);
  }

  async function find() {
    if (!jobId || busy || isRunning(task)) return;
    stopPlayer();
    picked = 0;
    consent = false;
    error = "";
    busy = "find";
    render();
    try {
      task = await findVoiceCandidates(jobId, { full: fullSearch });
      if (isRunning(task)) schedule(1200);
    } catch (cause) {
      error = cause?.message || "Could not start the clip search.";
    } finally {
      busy = "";
      render();
    }
  }

  async function cancelSearch() {
    if (!jobId || busy) return;
    const forJob = jobId;
    stopPoll();
    busy = "cancel-search";
    render();
    try {
      const state = await cancelVoiceCandidates(forJob);
      if (forJob === jobId) {
        task = state;
        error = "";
        // The worker stops at its next check; poll until it says so.
        if (isRunning(state)) schedule(800);
      }
    } catch (cause) {
      error = cause?.message || "Could not cancel the search.";
      if (isRunning(task)) schedule();
    } finally {
      busy = "";
      render();
    }
  }

  async function play(item) {
    if (!jobId || !item?.index) return;
    if (playing === item.index && player) {
      stopPlayer();
      render();
      return;
    }
    stopPlayer();
    syncTokenCookie();
    const audio = new Audio(voiceCandidateAudioUrl(jobId, item.index));
    player = audio;
    playing = item.index;
    const done = () => {
      if (player !== audio) return;
      player = null;
      playing = 0;
      render();
    };
    audio.addEventListener("ended", done, { once: true });
    audio.addEventListener("error", done, { once: true });
    render();
    try {
      await audio.play();
    } catch (cause) {
      done();
      onNotice(cause?.message || "Could not play that clip.", "bad");
    }
  }

  async function clone() {
    if (!jobId || busy || !consent) return;
    const body = { name: name.trim(), consent: true };
    let clip = null;
    if (manual) {
      const from = Number.parseFloat(start);
      const to = Number.parseFloat(end);
      if (Number.isFinite(from) && from >= 0) body.start = from;
      if (Number.isFinite(to) && to > 0) body.end = to;
    } else {
      clip = (task?.candidates || []).find((item) => item.index === picked);
      if (!clip) {
        error = "Pick one of the clips first.";
        render();
        return;
      }
      body.candidate = clip.index;
    }
    stopPlayer();
    busy = "clone";
    cloneTask = newVoiceTask();
    body.task = cloneTask;
    error = "";
    render();
    try {
      const record = await cloneFromVideo(jobId, body);
      consent = false;
      const which = clip
        ? `clip ${clip.index} (${formatDuration(clip.start)}–${formatDuration(clip.end)})`
        : "the time range you chose";
      const note = cleaningNote(record);
      onNotice(`Cloned “${record.name}” from ${which}.${note ? ` ${note}` : ""} It is in Your voices.`, note ? "" : "ok");
      onCloned(record);
    } catch (cause) {
      if (wasCancelled(cause)) onNotice("Cancelled. No voice was cloned.", "");
      else error = cause?.message || "Could not clone the video voice.";
    } finally {
      busy = "";
      cloneTask = "";
      render();
    }
  }

  async function cancelClone() {
    if (busy !== "clone" || !cloneTask) return;
    busy = "cancel-clone";
    render();
    try {
      await cancelVoiceTask(cloneTask);
    } catch (cause) {
      error = cause?.message || "Could not cancel the clone.";
      busy = "clone";
      render();
    }
  }

  function clipRow(item) {
    const selected = picked === item.index;
    const listen = el("button", {
      class: "ghost small", type: "button",
      text: playing === item.index ? "Stop" : "Play",
      "aria-label": `${playing === item.index ? "Stop" : "Play"} clip ${item.index}`,
    });
    listen.addEventListener("click", () => { void play(item); });
    const pick = el("button", {
      class: selected ? "primary small" : "ghost small", type: "button",
      text: selected ? "Picked" : "Use this clip",
      "aria-pressed": selected ? "true" : "false",
    });
    pick.addEventListener("click", () => {
      picked = item.index;
      manual = false;
      render();
    });
    return el("li", { class: `vr-clip${selected ? " is-picked" : ""}`, "data-clip": String(item.index) }, [
      el("div", { class: "vr-clip-copy" }, [
        el("strong", { text: `Clip ${item.index} · ${formatDuration(item.start)}–${formatDuration(item.end)}` }),
        el("span", { class: "hint mono", text: clipFacts(item) }),
        ...(item.warnings || []).slice(0, 2).map((line) => el("span", { class: "hint", text: line })),
      ]),
      el("div", { class: "vr-actions" }, [listen, pick]),
    ]);
  }

  function cloneForm() {
    const nameInput = el("input", { type: "text", maxLength: 64, value: name, placeholder: "Video voice", "aria-label": "Voice name" });
    nameInput.addEventListener("input", () => { name = nameInput.value; });
    const tick = el("input", { type: "checkbox", checked: consent, id: "vr-consent-video" });
    tick.addEventListener("change", () => { consent = Boolean(tick.checked); render(); });
    const ready = manual || Boolean(picked);
    const cloning = busy === "clone" || busy === "cancel-clone";
    const go = el("button", {
      class: "primary small", type: "button",
      text: cloning ? "Cloning…" : (manual ? "Clone this range" : "Clone this clip"),
      disabled: Boolean(busy) || !consent || !ready,
    });
    go.addEventListener("click", () => { void clone(); });
    const stop = cloning ? el("button", {
      class: "ghost small", type: "button",
      text: busy === "cancel-clone" ? "Cancelling…" : "Cancel",
      disabled: busy === "cancel-clone",
      "aria-label": "Cancel the clone",
    }) : null;
    stop?.addEventListener("click", () => { void cancelClone(); });
    const form = el("div", { class: "vr-clone-form" }, [
      el("label", { class: "vr-field" }, [el("span", { text: "Name" }), nameInput]),
    ]);
    if (manual) {
      const from = el("input", { type: "number", min: "0", step: "1", value: start, placeholder: "auto", "aria-label": "From (seconds)" });
      from.addEventListener("input", () => { start = from.value; });
      const to = el("input", { type: "number", min: "0", step: "1", value: end, placeholder: "auto", "aria-label": "To (seconds)" });
      to.addEventListener("input", () => { end = to.value; });
      form.append(el("div", { class: "vr-row" }, [
        el("label", { class: "vr-field" }, [el("span", { text: "From (s)" }), from]),
        el("label", { class: "vr-field" }, [el("span", { text: "To (s)" }), to]),
      ]));
    }
    form.append(
      el("label", { class: "vr-consent", for: "vr-consent-video" }, [tick, el("span", { text: CONSENT_COPY.video })]),
      el("div", { class: "vr-actions" }, [go, stop]),
    );
    return form;
  }

  function render() {
    if (disposed) return;
    node.replaceChildren(el("div", { class: "vr-card-head" }, [
      el("h3", { text: "From a video" }),
      el("p", { class: "hint", text: "Pick a video in VibeCut. VibeCut finds its cleanest speech clips with the music removed; listen, pick one, and clone the speaker." }),
    ]));
    if (!available()) {
      node.append(el("p", { class: "hint", text: "Add an OpenRouter key in Setup to clone a voice." }));
      return;
    }
    const list = jobs() || [];
    if (!list.length) {
      node.append(el("p", { class: "hint", text: "No finished videos yet. Import one in VibeCut first." }));
      return;
    }
    const select = el("select", { "aria-label": "Video" }, [
      el("option", { value: "", text: "Choose a video", selected: !jobId }),
      ...list.map((job) => el("option", {
        value: job.id,
        text: `${job.name || job.id}${job.duration ? ` · ${formatDuration(job.duration)}` : ""}`,
        selected: job.id === jobId,
      })),
    ]);
    select.addEventListener("change", () => choose(select.value));
    const running = isRunning(task);
    const search = el("button", {
      class: "ghost small", type: "button",
      text: running || busy === "find" ? "Searching…" : (task?.state === "done" ? "Search again" : "Find clean clips"),
      disabled: !jobId || Boolean(busy) || running,
    });
    search.addEventListener("click", () => { void find(); });
    const stop = running ? el("button", {
      class: "ghost small danger", type: "button",
      text: busy === "cancel-search" ? "Cancelling…" : "Cancel",
      disabled: busy === "cancel-search",
      "aria-label": "Cancel the clip search",
    }) : null;
    stop?.addEventListener("click", () => { void cancelSearch(); });
    node.append(el("div", { class: "vr-finder-pick" }, [
      el("label", { class: "vr-field" }, [el("span", { text: "Video" }), select]),
      el("div", { class: "vr-actions" }, [search, stop]),
    ]));
    if (!jobId) return;

    const whole = el("input", {
      type: "checkbox",
      checked: fullSearch,
      disabled: running || Boolean(busy),
    });
    whole.addEventListener("change", () => { fullSearch = whole.checked; });
    node.append(el("label", { class: "vr-consent" }, [
      whole,
      el("span", {
        text: "Search the whole video. Off: the first 2:00 only, which is much faster. For a quick clone, use a time range instead.",
      }),
    ]));

    const progress = stageCopy(task);
    if (running && progress) node.append(el("p", { class: "vr-status", role: "status", "data-stage": task.stage || "", text: progress }));
    else if (task?.state === "cancelled") node.append(el("p", { class: "vr-status", role: "status", text: progress }));
    if (error) node.append(el("p", { class: "error", role: "alert", text: error }));

    const clips = task?.state === "done" ? (task.candidates || []) : [];
    if (task?.state === "done") {
      if (clips.length) {
        node.append(el("ol", { class: "vr-clips" }, clips.map(clipRow)));
      } else {
        node.append(el("p", { class: "hint", text: "No clean speech clip was found. Use a time range instead." }));
      }
      for (const line of (task.warnings || []).slice(0, 2)) node.append(el("p", { class: "hint", text: line }));
    }
    const toggle = el("button", {
      class: "vr-link", type: "button",
      text: manual ? "Use a found clip instead" : "Use a time range instead",
    });
    toggle.addEventListener("click", () => {
      manual = !manual;
      if (manual) picked = 0;
      render();
    });
    if (!running) node.append(toggle);
    if (manual || picked) node.append(cloneForm());
  }

  render();

  return {
    node,
    render,
    choose,
    dispose() {
      disposed = true;
      stopPoll();
      stopPlayer();
    },
  };
}
