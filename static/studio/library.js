/**
 * Finished-video library for Studio.
 *
 * "Your videos" has two tabs:
 *   Finished — every render artifact across jobs, read from GET /api/artifacts
 *   Sources  — the existing job picker, titled by story/job/date, not source.mp4
 *
 * Read-only: Play uses the artifact media URL, Download is a link to the same
 * file, and Open in Finish opens the job and switches to the Finish step.
 * Nothing is deleted, renamed or uploaded.
 */

import { deleteCheck, deleteJob, listJobs, request } from "./api.js";
import { deleteVideoButton, el, formatBytes, formatDuration, shortDate, statusText, statusTone } from "./ui.js";

export const FINISHED_TAB = "finished";
export const SOURCES_TAB = "sources";
export const ARTIFACTS_PATH = "/api/artifacts";
/** Rows per page: finished cuts (the server allows up to 200), then sources. */
export const PAGE_SIZE = 60;
export const SOURCES_PAGE_SIZE = 30;

const GENERIC_SOURCE_NAMES = new Set([
  "source.mp4", "source.mov", "source.mkv", "source.webm",
  "video.mp4", "video.mov", "clip.mp4", "clip.mov", "untitled",
]);

/** The server path behind the Finished tab. Exported for the static tests. */
export function artifactsPath({ query = "", limit = 60, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return `${ARTIFACTS_PATH}?${params.toString()}`;
}

/**
 * The offset of the next page, or null when every row is shown. Works for
 * `GET /api/artifacts` and `GET /api/jobs`, which both answer
 * `{total, offset}`; `shown` is how many rows the list holds now.
 */
export function nextOffset(data, shown) {
  const total = Number(data?.total);
  const count = Number(shown) || 0;
  if (data?.has_more === false) return null;
  if (!Number.isFinite(total)) return data?.has_more ? count : null;
  return count < total ? count : null;
}

/** "Load more" label: how many are left. */
export function moreLabel(total, shown) {
  const left = Math.max(0, (Number(total) || 0) - (Number(shown) || 0));
  return left ? `Load more (${left} more)` : "Load more";
}

function clean(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function idTail(value) {
  return clean(value).slice(-6);
}

/**
 * A source row's title. A job title wins, then the first story title, then a
 * readable date/id fallback. A generic source.mp4 name is never the title.
 */
export function sourceTitle(job = {}) {
  const direct = clean(job.title);
  if (direct) return direct;
  const stories = Array.isArray(job.story_titles) ? job.story_titles : [];
  const story = stories.map(clean).find(Boolean);
  if (story) return story;
  const name = clean(job.name);
  if (name && !GENERIC_SOURCE_NAMES.has(name.toLowerCase())) {
    return name.replace(/\.[a-z0-9]{2,5}$/i, "");
  }
  const when = shortDate(job.created);
  const tail = idTail(job.id);
  return ["Source", when, tail ? `#${tail}` : ""].filter(Boolean).join(" · ");
}

/** Story title, job label, then an artifact-id fallback — never a blank row. */
export function artifactTitle(artifact = {}) {
  return clean(artifact.story_title)
    || clean(artifact.job_title)
    || clean(artifact.source_label)
    || `Cut ${idTail(artifact.artifact_id) || "without a name"}`;
}

function qualityLabel(quality) {
  const value = clean(quality).toLowerCase();
  if (value === "draft") return "Draft";
  if (value === "final") return "Final";
  return clean(quality);
}

/**
 * The small metadata cells under a finished cut. Missing fields are omitted,
 * so an old manifest never renders "undefined ·  · v?" or crashes the list.
 */
export function artifactMeta(artifact = {}) {
  return [
    clean(artifact.aspect),
    qualityLabel(artifact.quality),
    clean(artifact.version_label) || (artifact.version ? `v${artifact.version}` : ""),
    shortDate(artifact.created) || clean(artifact.date),
    formatBytes(artifact.size),
  ].filter(Boolean);
}

/** A safe download name that does not reuse an untrusted story title. */
export function downloadFileName(artifact = {}, index = 0) {
  const shape = clean(artifact.aspect).replace(":", "x") || "cut";
  const version = artifact.version ? `-v${artifact.version}` : "";
  return `story-${String(Math.max(0, Number(index) || 0) + 1).padStart(2, "0")}-${shape}${version}.mp4`;
}

function isReady(artifact) {
  return clean(artifact.status).toLowerCase() === "ready";
}

/**
 * Mount the library into the "Your videos" dialog body.
 * Returns {refresh, setTab, getTab, destroy}; the shell calls refresh on open.
 */
export function mount(root, ctx = {}) {
  let tab = FINISHED_TAB;
  let query = "";
  let ticket = 0;
  let searchTimer = 0;
  let disposed = false;

  root.innerHTML = `
    <div class="st-library-tabs" role="tablist" aria-label="Your videos" style="display:flex;gap:6px;align-items:center">
      <button id="st-library-tab-finished" class="st-btn st-btn-small st-btn-primary" type="button" role="tab" aria-selected="true" aria-controls="st-library-list" tabindex="0" data-library-tab="finished">Finished</button>
      <button id="st-library-tab-sources" class="st-btn st-btn-small st-btn-ghost" type="button" role="tab" aria-selected="false" aria-controls="st-library-list" tabindex="-1" data-library-tab="sources">Sources</button>
    </div>
    <input id="st-library-search" class="st-input" type="search" placeholder="Search finished videos" aria-label="Search finished videos">
    <div id="st-library-list" class="st-library-list" role="tabpanel" aria-labelledby="st-library-tab-finished"></div>
  `;

  const dom = {
    tabs: Array.from(root.querySelectorAll("[role=tab]")),
    search: root.querySelector("#st-library-search"),
    list: root.querySelector("#st-library-list"),
  };

  function dialog() {
    return root.closest("dialog");
  }

  function closeDialog() {
    const box = dialog();
    if (box && typeof box.close === "function") box.close();
  }

  function loading(message) {
    dom.list.replaceChildren(el("p", { class: "st-hint", text: message }));
  }

  function empty(message) {
    dom.list.replaceChildren(el("p", { class: "st-hint", text: message }));
  }

  function fail(error) {
    dom.list.replaceChildren(el("p", {
      class: "st-error",
      text: error?.message || "Could not load the library.",
    }));
  }

  function renderTabs() {
    for (const button of dom.tabs) {
      const active = button.dataset.libraryTab === tab;
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
      button.className = `st-btn st-btn-small ${active ? "st-btn-primary" : "st-btn-ghost"}`;
    }
    dom.list.setAttribute(
      "aria-labelledby",
      tab === FINISHED_TAB ? "st-library-tab-finished" : "st-library-tab-sources",
    );
    dom.search.placeholder = tab === FINISHED_TAB
      ? "Search finished videos"
      : "Search sources";
    dom.search.setAttribute(
      "aria-label",
      tab === FINISHED_TAB ? "Search finished videos" : "Search sources",
    );
  }

  function selectTab(next, { focus = false } = {}) {
    if (next !== FINISHED_TAB && next !== SOURCES_TAB) return;
    tab = next;
    renderTabs();
    if (focus) dom.search.focus();
    void load();
  }

  function sourceRow(job) {
    const current = ctx.getJobId?.() === job.id;
    const stories = Array.isArray(job.story_titles) ? job.story_titles.length : 0;
    const meta = [
      formatDuration(job.duration),
      shortDate(job.created),
      stories ? `${stories} ${stories === 1 ? "moment" : "moments"}` : "",
    ].filter(Boolean).join(" · ");
    const thumb = job.hook_thumb && !job.source_deleted
      ? el("img", { class: "st-library-thumb", src: job.hook_thumb, alt: "", loading: "lazy" })
      : el("span", { class: "st-library-thumb st-library-thumb-empty", "aria-hidden": "true" });
    const row = el("button", {
      class: `st-library-item${current ? " is-current" : ""}`,
      type: "button",
      "aria-current": current ? "true" : null,
    }, [
      thumb,
      el("span", { class: "st-library-copy" }, [
        el("strong", { text: sourceTitle(job), title: job.name || "" }),
        el("span", { text: meta }),
      ]),
      el("span", {
        class: `st-chip st-chip-${statusTone(job.status)}`,
        text: current ? "Open now" : statusText(job.status),
      }),
    ]);
    row.addEventListener("click", () => {
      closeDialog();
      void ctx.openJobAndContinue?.(job.id, { name: job.name || "", status: job.status || "" });
    });
    return el("div", { class: "st-library-row" }, [
      row,
      deleteVideoButton({
        name: sourceTitle(job),
        check: () => deleteCheck(job.id),
        onDelete: async () => {
          await deleteJob(job.id);
          ctx.jobDeleted?.(job.id);
          await refresh();
        },
        onError: (error) => window.alert(error.message || "Could not delete that video."),
      }),
    ]);
  }

  function playRow(row, artifact, button) {
    const existing = row.querySelector("video.st-library-player");
    if (existing) {
      existing.remove();
      button.textContent = "Play";
      return;
    }
    if (!artifact.url) return;
    const video = el("video", {
      class: "st-library-player",
      src: artifact.url,
      controls: true,
      autoplay: true,
      playsInline: true,
      style: "grid-column:1/-1;width:100%;border-radius:9px;margin-top:6px;background:#000",
    });
    row.append(video);
    button.textContent = "Hide";
  }

  function openInFinish(artifact) {
    const jobId = clean(artifact.job_id);
    if (!jobId) return;
    closeDialog();
    if (typeof ctx.openFinished === "function") {
      ctx.openFinished(artifact);
      return;
    }
    ctx.openJob?.(jobId, { name: clean(artifact.job_title) || clean(artifact.source_label) });
    ctx.go?.("finish", { force: true });
  }

  function finishedRow(artifact, index) {
    const status = clean(artifact.status);
    const thumb = artifact.poster_url
      ? el("img", { class: "st-library-thumb", src: artifact.poster_url, alt: "", loading: "lazy" })
      : el("span", { class: "st-library-thumb st-library-thumb-empty", "aria-hidden": "true" });
    const meta = artifactMeta(artifact).join(" · ");
    const title = artifactTitle(artifact);
    const jobLine = [clean(artifact.job_title), clean(artifact.source_label)]
      .filter((value, position, values) => (
        value && value !== title && values.indexOf(value) === position
      ))
      .join(" · ");
    const actions = el("span", { class: "st-story-actions", style: "flex-wrap:wrap" }, [
      el("span", {
        class: `st-chip st-chip-${statusTone(status)}`,
        text: statusText(status),
      }),
    ]);
    if (isReady(artifact) && artifact.url) {
      const play = el("button", {
        class: "st-btn st-btn-small st-btn-ghost",
        type: "button",
        text: "Play",
      });
      const row = el("div", {
        class: "st-library-item",
        "data-artifact-id": artifact.artifact_id || "",
        style: "cursor:default",
      }, [
        thumb,
        el("span", { class: "st-library-copy" }, [
          el("strong", { text: artifactTitle(artifact) }),
          el("span", { text: meta }),
          jobLine ? el("span", { text: jobLine }) : null,
        ]),
        actions,
      ]);
      play.addEventListener("click", () => playRow(row, artifact, play));
      actions.append(play);
      actions.append(el("a", {
        class: "st-btn st-btn-small st-btn-ghost",
        href: artifact.download_url || artifact.url,
        download: downloadFileName(artifact, index),
        text: "Download",
      }));
      actions.append(el("button", {
        class: "st-btn st-btn-small st-btn-primary",
        type: "button",
        text: "Open in Finish",
        on: { click: () => openInFinish(artifact) },
      }));
      return row;
    }
    const row = el("div", {
      class: "st-library-item",
      "data-artifact-id": artifact.artifact_id || "",
      style: "cursor:default",
    }, [
      thumb,
      el("span", { class: "st-library-copy" }, [
        el("strong", { text: artifactTitle(artifact) }),
        el("span", { text: meta }),
        jobLine ? el("span", { text: jobLine }) : null,
      ]),
      actions,
    ]);
    actions.append(el("button", {
      class: "st-btn st-btn-small st-btn-quiet",
      type: "button",
      text: "Open in Finish",
      on: { click: () => openInFinish(artifact) },
    }));
    return row;
  }

  // "Load more" appends the next page under the rows already shown, so a
  // long library never needs a bigger first request.
  function moreButton(data, shown, loadPage) {
    const offset = nextOffset(data, shown);
    if (offset === null) return null;
    const button = el("button", {
      class: "st-btn st-btn-ghost st-btn-small st-library-more",
      type: "button",
      text: moreLabel(data?.total, shown),
      style: "justify-self:center;margin:8px auto 2px;display:block",
    });
    button.addEventListener("click", async () => {
      const current = ticket;
      button.disabled = true;
      button.textContent = "Loading…";
      try {
        await loadPage(current, offset);
      } catch (error) {
        if (current !== ticket || disposed) return;
        button.disabled = false;
        button.textContent = moreLabel(data?.total, shown);
        button.after(el("p", { class: "st-error", text: error?.message || "Could not load more." }));
      }
    });
    return button;
  }

  async function loadFinished(current, offset = 0) {
    if (!offset) loading("Loading finished videos…");
    const data = await request(artifactsPath({ query, limit: PAGE_SIZE, offset }));
    if (current !== ticket || disposed) return;
    const artifacts = Array.isArray(data?.artifacts) ? data.artifacts : [];
    if (!offset && !artifacts.length) {
      empty(query
        ? "No finished video matches that search."
        : "No finished videos yet. Render a story in Finish and it will appear here.");
      return;
    }
    dom.list.querySelector(".st-library-more")?.remove();
    const rows = artifacts.map((artifact, index) => finishedRow(artifact, offset + index));
    if (offset) dom.list.append(...rows);
    else dom.list.replaceChildren(...rows);
    const more = moreButton(data, offset + artifacts.length, loadFinished);
    if (more) dom.list.append(more);
  }

  async function loadSources(current, offset = 0) {
    if (!offset) loading("Loading your sources…");
    const data = await listJobs({ query, limit: SOURCES_PAGE_SIZE, offset });
    if (current !== ticket || disposed) return;
    const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
    if (!offset && !jobs.length) {
      empty(query ? "No source matches that search." : "No sources yet. Import one to begin.");
      return;
    }
    dom.list.querySelector(".st-library-more")?.remove();
    if (offset) dom.list.append(...jobs.map(sourceRow));
    else dom.list.replaceChildren(...jobs.map(sourceRow));
    const more = moreButton(data, offset + jobs.length, loadSources);
    if (more) dom.list.append(more);
  }

  async function load() {
    const current = ++ticket;
    renderTabs();
    try {
      if (tab === FINISHED_TAB) await loadFinished(current);
      else await loadSources(current);
    } catch (error) {
      if (current !== ticket || disposed) return;
      fail(error);
    }
  }

  function refresh() {
    if (disposed) return Promise.resolve();
    return load();
  }

  function destroy() {
    disposed = true;
    ticket += 1;
    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = 0;
  }

  for (const button of dom.tabs) {
    button.addEventListener("click", () => selectTab(button.dataset.libraryTab));
  }
  root.querySelector(".st-library-tabs")?.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const index = dom.tabs.indexOf(document.activeElement);
    if (index < 0) return;
    event.preventDefault();
    let next = index;
    if (event.key === "ArrowLeft") next = (index - 1 + dom.tabs.length) % dom.tabs.length;
    if (event.key === "ArrowRight") next = (index + 1) % dom.tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = dom.tabs.length - 1;
    selectTab(dom.tabs[next].dataset.libraryTab, { focus: true });
  });
  dom.search.addEventListener("input", () => {
    query = dom.search.value.trim();
    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => { void refresh(); }, 250);
  });

  renderTabs();
  return {
    refresh,
    setTab: (next) => selectTab(next),
    getTab: () => tab,
    destroy,
  };
}
