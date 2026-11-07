const status = document.querySelector("#core-status");
const statusText = document.querySelector("#core-status-text");
const projectsHost = document.querySelector("#projects");
const importButton = document.querySelector("#import-button");
const engineGrid = document.querySelector("#engine-grid");
const engineNote = document.querySelector("#engine-note");
const editor = document.querySelector("#editor");
const editorTitle = document.querySelector("#editor-title");
const editorMeta = document.querySelector("#editor-meta");
const editorClose = document.querySelector("#editor-close");
const editorStories = document.querySelector("#editor-stories");
const editorEdits = document.querySelector("#editor-edits");
const editorEmpty = document.querySelector("#editor-empty");
const editPanel = document.querySelector("#edit-panel");
const editFull = document.querySelector("#edit-full");
const buildStory = document.querySelector("#build-story");
const storyStart = document.querySelector("#story-start");
const storyEnd = document.querySelector("#story-end");
const storyTitle = document.querySelector("#story-title");
const editKind = document.querySelector("#edit-kind");
const editTitle = document.querySelector("#edit-title");
const editMeta = document.querySelector("#edit-meta");
const cleanFromCheck = document.querySelector("#clean-from-check");
const cleanCount = document.querySelector("#clean-count");
const cleanLayers = document.querySelector("#clean-layers");

let activeProject = null;
let activeCheck = null;
let activeEdit = null;

let launchToken = "";
let baseURL = "";

function setStatus(text, kind = "") {
  if (!status || !statusText) return;
  statusText.textContent = text;
  status.classList.toggle("is-ok", kind === "ok");
  status.classList.toggle("is-bad", kind === "bad");
}

function readToken() {
  const hash = window.location.hash || "";
  const match = hash.match(/(?:^#|&)t=([^&]+)/);
  if (!match) return "";
  const token = decodeURIComponent(match[1]);
  history.replaceState(null, "", window.location.pathname + window.location.search);
  return token;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${launchToken}`);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatTime(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(value / 60);
  const rest = Math.floor(value % 60);
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function storyLine(story) {
  const row = document.createElement("div");
  row.className = "story-line";
  const title = document.createElement("span");
  title.className = "story-title";
  const hook = (story.sentences || []).find((item) => item.text)?.text || story.title || "Story";
  title.textContent = String(hook).slice(0, 110);
  const time = document.createElement("span");
  time.className = "story-time";
  time.textContent = `${formatTime(story.start)}–${formatTime(story.end)}`;
  row.append(title, time);
  return row;
}

function renderCheck(project, card, check) {
  const status = card.querySelector(".project-check-status");
  const button = card.querySelector(".project-check");
  const stories = card.querySelector(".project-stories");
  if (!status || !button || !stories) return;

  const state = check.state || "idle";
  const percent = Math.round((Number(check.progress) || 0) * 100);
  if (state === "queued" || state === "running") {
    status.textContent = `${check.stage || "Checking"} · ${percent}%`;
    button.textContent = "Checking…";
    button.disabled = true;
    return;
  }
  if (state === "done") {
    const rows = check.result?.stories?.stories || [];
    status.textContent = `Check complete · ${rows.length} ${rows.length === 1 ? "story" : "stories"}`;
    button.textContent = "Re-check";
    button.disabled = false;
    stories.replaceChildren(...rows.slice(0, 3).map(storyLine));
    return;
  }
  if (state === "failed" || state === "cancelled") {
    status.textContent = check.message || "Check failed";
    button.textContent = "Retry";
    button.disabled = false;
    stories.replaceChildren();
    return;
  }
  status.textContent = "Not checked";
  button.textContent = "Check";
  button.disabled = false;
  stories.replaceChildren();
}

async function pollCheck(project, card) {
  try {
    const data = await api(`/api/projects/${encodeURIComponent(project.id)}/check`);
    renderCheck(project, card, data.check);
    if (data.check.state === "queued" || data.check.state === "running") {
      setTimeout(() => pollCheck(project, card), 1500);
    }
  } catch (error) {
    setStatus(`Check status failed: ${error.message}`, "bad");
  }
}

async function startCheck(project, card) {
  const button = card.querySelector(".project-check");
  if (button) {
    button.disabled = true;
    button.textContent = "Starting…";
  }
  try {
    const data = await api(`/api/projects/${encodeURIComponent(project.id)}/check`, {
      method: "POST",
    });
    renderCheck(project, card, data.check);
    if (data.check.state === "queued" || data.check.state === "running") {
      setTimeout(() => pollCheck(project, card), 1000);
    }
  } catch (error) {
    setStatus(`Check failed: ${error.message}`, "bad");
    if (button) button.disabled = false;
  }
}

function closeEditor() {
  editor.hidden = true;
  activeProject = null;
  activeCheck = null;
  activeEdit = null;
}

function storyQuote(story) {
  const sentence = (story.sentences || []).find((item) => item.text);
  return String(sentence?.text || story.title || "Story").slice(0, 140);
}

function editorStoryRow(story) {
  const row = document.createElement("div");
  row.className = "editor-story";
  const copy = document.createElement("div");
  const title = document.createElement("p");
  title.className = "editor-story-title";
  title.textContent = storyQuote(story);
  const meta = document.createElement("p");
  meta.className = "editor-story-meta";
  meta.textContent = `${formatTime(story.start)}–${formatTime(story.end)} · ${Math.round(story.dur || 0)}s`;
  copy.append(title, meta);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "project-check";
  button.textContent = "Smart cut";
  button.addEventListener("click", () => smartCut(story.id));
  row.append(copy, button);
  return row;
}

function renderEditorStories() {
  if (!editorStories) return;
  editorStories.replaceChildren();
  if (!activeCheck || activeCheck.state !== "done" || !activeCheck.result) {
    const note = document.createElement("p");
    note.className = "editor-note";
    note.textContent = activeCheck?.state === "running"
      ? "Check is still running. Stories appear when it finishes."
      : "Run Check to find smart stories.";
    editorStories.append(note);
    return;
  }
  const rows = activeCheck.result.stories?.stories || [];
  if (!rows.length) {
    const note = document.createElement("p");
    note.className = "editor-note";
    note.textContent = "No story candidate yet. Build one manually below.";
    editorStories.append(note);
    return;
  }
  for (const story of rows) editorStories.append(editorStoryRow(story));
}

function renderEdits(rows) {
  if (!editorEdits) return;
  editorEdits.replaceChildren();
  if (!rows.length) {
    const note = document.createElement("p");
    note.className = "editor-note";
    note.textContent = "No edits yet.";
    editorEdits.append(note);
    return;
  }
  for (const row of rows) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "editor-edit-row";
    const label = document.createElement("span");
    label.textContent = row.title || (row.kind === "full" ? "Full video" : "Story");
    const meta = document.createElement("span");
    meta.textContent = `${formatTime(row.start)}–${formatTime(row.end)} · ${row.clean || 0} clean`;
    button.append(label, meta);
    button.addEventListener("click", () => selectEdit(row.id));
    if (activeEdit?.id === row.id) button.classList.add("is-active");
    editorEdits.append(button);
  }
}

async function loadEdits() {
  if (!activeProject) return;
  const data = await api(`/api/projects/${encodeURIComponent(activeProject.id)}/edits`);
  renderEdits(data.edits || []);
}

async function selectEdit(editId) {
  if (!activeProject) return;
  const data = await api(`/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(editId)}`);
  activeEdit = data.edit;
  editorEmpty.hidden = true;
  editPanel.hidden = false;
  editKind.textContent = activeEdit.kind === "full" ? "Full video" : "Story";
  editTitle.textContent = activeEdit.title || "Edit";
  editMeta.textContent = `${formatTime(activeEdit.start)}–${formatTime(activeEdit.end)} · ${activeEdit.clips?.length || 0} clips`;
  renderCleanLayers();
  await loadEdits();
}

function renderCleanLayers() {
  cleanLayers.replaceChildren();
  const layers = activeEdit?.clean || [];
  cleanCount.textContent = layers.length ? `${layers.length} layers` : "No clean layers yet";
  if (!layers.length) {
    const note = document.createElement("p");
    note.className = "editor-note";
    note.textContent = "Create layers from Check, or add a manual box later.";
    cleanLayers.append(note);
    return;
  }
  for (const layer of layers) {
    const row = document.createElement("div");
    row.className = "clean-row";
    const info = document.createElement("div");
    info.className = "clean-info";
    const title = document.createElement("p");
    title.className = "clean-title";
    title.textContent = layer.text_sample || layer.label || "Found text";
    const meta = document.createElement("p");
    meta.className = "clean-meta";
    const start = layer.ranges?.[0]?.start;
    const end = layer.ranges?.[layer.ranges.length - 1]?.end;
    meta.textContent = `${layer.tracklet_kind || "text"} · ${formatTime(start)}–${formatTime(end)}`;
    info.append(title, meta);
    const actions = document.createElement("div");
    actions.className = "clean-actions";
    for (const [action, label] of [["fill", "Fill"], ["blur", "Blur"], ["exclude", "Off"]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "clean-action";
      button.textContent = label;
      const current = layer.enabled === false ? "exclude" : (layer.kind === "blur" ? "blur" : "fill");
      if (current === action) button.classList.add("is-active");
      button.addEventListener("click", () => setLayerAction(layer.id, action));
      actions.append(button);
    }
    row.append(info, actions);
    cleanLayers.append(row);
  }
}

async function setLayerAction(layerId, action) {
  if (!activeProject || !activeEdit) return;
  const data = await api(
    `/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(activeEdit.id)}/clean/${encodeURIComponent(layerId)}`,
    { method: "PATCH", body: JSON.stringify({ action }) },
  );
  activeEdit = data.edit;
  renderCleanLayers();
  await loadEdits();
}

async function createFullEdit() {
  if (!activeProject) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(activeProject.id)}/edits/full`, { method: "POST" });
    await loadEdits();
    await selectEdit(data.edit.id);
  } catch (error) {
    setStatus(`Full edit failed: ${error.message}`, "bad");
  }
}

async function smartCut(storyId) {
  if (!activeProject) return;
  try {
    const data = await api(
      `/api/projects/${encodeURIComponent(activeProject.id)}/stories/${encodeURIComponent(storyId)}/smart-cut`,
      { method: "POST" },
    );
    await loadEdits();
    await selectEdit(data.edit.id);
  } catch (error) {
    setStatus(`Smart cut failed: ${error.message}`, "bad");
  }
}

async function buildManualStory() {
  if (!activeProject) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(activeProject.id)}/edits/story`, {
      method: "POST",
      body: JSON.stringify({
        start: Number(storyStart.value) || 0,
        end: Number(storyEnd.value) || 0,
        title: storyTitle.value || "",
      }),
    });
    storyTitle.value = "";
    await loadEdits();
    await selectEdit(data.edit.id);
  } catch (error) {
    setStatus(`Story build failed: ${error.message}`, "bad");
  }
}

async function cleanFromCheckLayers() {
  if (!activeProject || !activeEdit) return;
  try {
    const data = await api(
      `/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(activeEdit.id)}/clean/from-check`,
      { method: "POST" },
    );
    activeEdit = data.edit;
    renderCleanLayers();
    await loadEdits();
  } catch (error) {
    setStatus(`Clean layers failed: ${error.message}`, "bad");
  }
}

async function openProject(project) {
  activeProject = project;
  activeCheck = null;
  activeEdit = null;
  editor.hidden = false;
  editorTitle.textContent = project.name;
  editorMeta.textContent = `${formatBytes(project.source_bytes)} · local`;
  editorEmpty.hidden = false;
  editPanel.hidden = true;
  storyStart.value = "0";
  storyEnd.value = "";
  storyTitle.value = "";
  renderEditorStories();
  await loadEdits();
  try {
    const data = await api(`/api/projects/${encodeURIComponent(project.id)}/check`);
    activeCheck = data.check;
    renderEditorStories();
    const duration = Number(activeCheck.result?.meta?.duration) || 0;
    storyEnd.value = duration ? String(Math.round(duration * 10) / 10) : "";
  } catch (error) {
    setStatus(`Project check failed: ${error.message}`, "bad");
  }
}

editorClose?.addEventListener("click", closeEditor);
editFull?.addEventListener("click", createFullEdit);
buildStory?.addEventListener("click", buildManualStory);
cleanFromCheck?.addEventListener("click", cleanFromCheckLayers);
editor?.addEventListener("click", (event) => {
  if (event.target === editor) closeEditor();
});

function projectCard(project) {
  const card = document.createElement("article");
  card.className = "project-card";

  const name = document.createElement("h3");
  name.textContent = project.name;
  card.append(name);

  const meta = document.createElement("p");
  meta.className = "project-meta";
  meta.textContent = `${formatBytes(project.source_bytes)} · local`;
  card.append(meta);

  const actions = document.createElement("div");
  actions.className = "project-actions";
  const check = document.createElement("button");
  check.type = "button";
  check.className = "project-check";
  check.textContent = "Check";
  check.addEventListener("click", () => startCheck(project, card));
  const open = document.createElement("button");
  open.type = "button";
  open.className = "project-check";
  open.textContent = "Open";
  open.addEventListener("click", () => openProject(project));
  actions.append(check, open);
  card.append(actions);

  const status = document.createElement("p");
  status.className = "project-check-status";
  status.textContent = "Not checked";
  card.append(status);

  const stories = document.createElement("div");
  stories.className = "project-stories";
  card.append(stories);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "project-delete";
  remove.textContent = "Delete";
  remove.addEventListener("click", async () => {
    if (!confirm(`Delete “${project.name}” and its copied source?`)) return;
    try {
      await api(`/api/projects/${encodeURIComponent(project.id)}`, { method: "DELETE" });
      await loadProjects();
    } catch (error) {
      setStatus(`Delete failed: ${error.message}`, "bad");
    }
  });
  card.append(remove);

  void pollCheck(project, card);
  return card;
}

async function loadProjects() {
  if (!projectsHost || !launchToken) return;
  try {
    const data = await api("/api/projects");
    projectsHost.replaceChildren();
    if (!data.projects.length) {
      const empty = document.createElement("div");
      empty.className = "projects-empty";
      empty.textContent = "No projects yet. Import one video to begin.";
      projectsHost.append(empty);
      return;
    }
    for (const project of data.projects) {
      projectsHost.append(projectCard(project));
    }
  } catch (error) {
    setStatus(`Projects unavailable: ${error.message}`, "bad");
  }
}

async function importVideo() {
  if (window.webkit?.messageHandlers?.duck) {
    window.webkit.messageHandlers.duck.postMessage({ type: "import" });
    return;
  }

  // Browser development fallback. The sandboxed Mac app uses NSOpenPanel.
  const path = window.prompt("Development only: absolute path to a video");
  if (!path) return;
  try {
    await api("/api/projects/dev-import", {
      method: "POST",
      body: JSON.stringify({ source_path: path }),
    });
    await loadProjects();
  } catch (error) {
    setStatus(`Import failed: ${error.message}`, "bad");
  }
}

function engineCard(title, detail, ready) {
  const card = document.createElement("article");
  card.className = "engine-card";
  const head = document.createElement("div");
  head.className = "engine-head";
  const name = document.createElement("h3");
  name.textContent = title;
  const state = document.createElement("span");
  state.className = ready ? "engine-state is-ready" : "engine-state";
  state.textContent = ready ? "Ready" : "Unavailable";
  head.append(name, state);
  const copy = document.createElement("p");
  copy.textContent = detail;
  card.append(head, copy);
  return card;
}

async function loadEngine() {
  if (!engineGrid) return;
  try {
    const data = await api("/api/engine");
    engineGrid.replaceChildren(
      engineCard("Apple Vision", "OCR, faces, saliency and smart crop", data.vision.available),
      engineCard("Apple Speech", "On-device transcription" + (data.speech.whisper ? " · Whisper fallback" : ""), data.speech.apple),
      engineCard("LaMa", "Local text fill model", data.fill.ready),
      engineCard("Smart stories", "Local scene, speech and text evidence", data.stories.ready),
    );
    const ready = [data.vision.available, data.speech.apple, data.fill.ready, data.stories.ready].filter(Boolean).length;
    if (engineNote) engineNote.textContent = `${ready} of 4 ready`;
  } catch (error) {
    if (engineNote) engineNote.textContent = "Engine check failed";
    setStatus(`Engine check failed: ${error.message}`, "bad");
  }
}

async function health() {
  if (!launchToken) {
    setStatus("No launch token", "bad");
    return;
  }
  try {
    const data = await api("/api/health");
    setStatus(`Local core ${data.version}`, "ok");
    await Promise.all([loadProjects(), loadEngine()]);
  } catch (error) {
    setStatus("Local core unavailable", "bad");
    console.error(error);
  }
}

launchToken = readToken();
baseURL = window.location.origin;
importButton?.addEventListener("click", importVideo);
health();
