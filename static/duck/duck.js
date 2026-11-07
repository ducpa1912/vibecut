const status = document.querySelector("#core-status");
const statusText = document.querySelector("#core-status-text");
const projectsHost = document.querySelector("#projects");
const importButton = document.querySelector("#import-button");
const engineGrid = document.querySelector("#engine-grid");
const engineNote = document.querySelector("#engine-note");
const queueList = document.querySelector("#queue-list");
const queueStatus = document.querySelector("#queue-status");
const queuePause = document.querySelector("#queue-pause");
const queueResume = document.querySelector("#queue-resume");
const settingsButton = document.querySelector("#settings");
const settingsPanel = document.querySelector("#settings-panel");
const settingsClose = document.querySelector("#settings-close");
const settingsEngine = document.querySelector("#settings-engine");
const settingsModels = document.querySelector("#settings-models");
const settingsStorage = document.querySelector("#settings-storage");
const settingsVersion = document.querySelector("#settings-version");
const onlineEnabled = document.querySelector("#online-enabled");
const onlineEndpoint = document.querySelector("#online-endpoint");
const onlineStatus = document.querySelector("#online-status");
const saveOnline = document.querySelector("#save-online");
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
const cleanPreview = document.querySelector("#clean-preview");
const cleanPreviewFigure = document.querySelector("#clean-preview-figure");
const cleanPreviewImage = document.querySelector("#clean-preview-image");
const cleanPreviewCaption = document.querySelector("#clean-preview-caption");
const cleanCount = document.querySelector("#clean-count");
const cleanLayers = document.querySelector("#clean-layers");
const renderEdit = document.querySelector("#render-edit");
const renderStatus = document.querySelector("#render-status");
const downloadRender = document.querySelector("#download-render");
const generateCaptions = document.querySelector("#generate-captions");
const downloadCaptions = document.querySelector("#download-captions");
const burnCaptions = document.querySelector("#burn-captions");
const captionStyle = document.querySelector("#caption-style");
const captionPosition = document.querySelector("#caption-position");
const captionsStatus = document.querySelector("#captions-status");
const captionCues = document.querySelector("#caption-cues");

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
  resetRenderUi();
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
  renderCaptions();
  resetRenderUi();
  void pollRender();
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

async function previewClean() {
  if (!activeProject || !activeEdit) return;
  const first = (activeEdit.clean || []).find((layer) => layer.enabled !== false && layer.ranges?.length);
  const when = first
    ? Number(first.ranges[0].start || 0) + 0.5
    : Number(activeEdit.start || 0) + 0.5;
  try {
    const response = await fetch(
      `/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(activeEdit.id)}/clean/preview?time=${encodeURIComponent(when)}`,
      { headers: { Authorization: `Bearer ${launchToken}` }, cache: "no-store" },
    );
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    if (cleanPreviewImage.dataset.url) URL.revokeObjectURL(cleanPreviewImage.dataset.url);
    const url = URL.createObjectURL(blob);
    cleanPreviewImage.dataset.url = url;
    cleanPreviewImage.src = url;
    cleanPreviewFigure.hidden = false;
    cleanPreviewCaption.textContent = `Frame at ${formatTime(when)} · ${activeEdit.clean?.length || 0} layers`;
  } catch (error) {
    setStatus(`Preview failed: ${error.message}`, "bad");
  }
}

let renderTimer = null;
let renderedBlobUrl = "";

function resetRenderUi() {
  if (renderTimer) clearTimeout(renderTimer);
  renderTimer = null;
  if (renderedBlobUrl) URL.revokeObjectURL(renderedBlobUrl);
  renderedBlobUrl = "";
  if (downloadRender) downloadRender.hidden = true;
  if (renderStatus) renderStatus.textContent = "";
}

function renderUrl(suffix = "") {
  return `/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(activeEdit.id)}/render${suffix}`;
}

function paintRender(state) {
  if (!renderStatus) return;
  const percent = Math.round((Number(state.progress) || 0) * 100);
  if (state.state === "queued" || state.state === "running") {
    renderStatus.textContent = `${state.stage || "Rendering"} · ${percent}%`;
    if (renderEdit) {
      renderEdit.disabled = true;
      renderEdit.textContent = "Rendering…";
    }
    return;
  }
  if (renderEdit) {
    renderEdit.disabled = false;
    renderEdit.textContent = state.state === "done" ? "Render again" : "Render 1080p";
  }
  if (state.state === "done") {
    renderStatus.textContent = "Render complete";
    if (downloadRender) downloadRender.hidden = false;
    return;
  }
  if (state.state === "failed") {
    renderStatus.textContent = state.message || "Render failed";
    return;
  }
  renderStatus.textContent = "";
}

async function pollRender() {
  if (!activeProject || !activeEdit) return;
  try {
    const data = await api(renderUrl());
    paintRender(data.render);
    if (data.render.state === "queued" || data.render.state === "running") {
      renderTimer = setTimeout(pollRender, 2000);
    }
  } catch (error) {
    if (renderStatus) renderStatus.textContent = `Render status failed: ${error.message}`;
  }
}

function renderCaptions() {
  if (!captionCues) return;
  const track = activeEdit?.captions;
  captionCues.replaceChildren();
  if (!track || !track.cues?.length) {
    const note = document.createElement("p");
    note.className = "editor-note";
    note.textContent = "No captions yet. Generate them from the transcript.";
    captionCues.append(note);
    if (captionsStatus) captionsStatus.textContent = "";
    if (downloadCaptions) downloadCaptions.hidden = true;
    if (burnCaptions) {
      burnCaptions.checked = false;
      burnCaptions.disabled = true;
    }
    if (captionStyle) captionStyle.disabled = true;
    if (captionPosition) captionPosition.disabled = true;
    return;
  }
  if (captionsStatus) captionsStatus.textContent = `${track.cues.length} cues · SRT`;
  if (downloadCaptions) downloadCaptions.hidden = false;
  if (burnCaptions) {
    burnCaptions.disabled = false;
    burnCaptions.checked = Boolean(track.burn);
  }
  const style = typeof track.style === "string" ? { id: track.style } : (track.style || {});
  if (captionStyle) {
    captionStyle.disabled = false;
    captionStyle.value = style.id || "clean";
  }
  if (captionPosition) {
    captionPosition.disabled = false;
    captionPosition.value = style.position || "bottom";
  }
  for (const cue of track.cues) {
    const row = document.createElement("div");
    row.className = "caption-row";
    const time = document.createElement("span");
    time.className = "caption-time";
    time.textContent = `${formatTime(cue.start)}–${formatTime(cue.end)}`;
    const input = document.createElement("input");
    input.type = "text";
    input.value = cue.text || "";
    input.maxLength = 240;
    input.addEventListener("change", () => saveCue(cue.id, input.value));
    row.append(time, input);
    captionCues.append(row);
  }
}

async function saveCue(cueId, text) {
  if (!activeProject || !activeEdit) return;
  try {
    const data = await api(
      `/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(activeEdit.id)}/captions/cues/${encodeURIComponent(cueId)}`,
      { method: "PATCH", body: JSON.stringify({ text }) },
    );
    activeEdit.captions = data.captions;
    if (captionsStatus) captionsStatus.textContent = "Saved";
  } catch (error) {
    if (captionsStatus) captionsStatus.textContent = `Save failed: ${error.message}`;
  }
}

async function generateCaptionTrack() {
  if (!activeProject || !activeEdit) return;
  if (captionsStatus) captionsStatus.textContent = "Generating…";
  try {
    const data = await api(
      `/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(activeEdit.id)}/captions/generate`,
      { method: "POST" },
    );
    activeEdit.captions = data.captions;
    renderCaptions();
  } catch (error) {
    if (captionsStatus) captionsStatus.textContent = `Captions failed: ${error.message}`;
  }
}

async function setCaptionStyle() {
  if (!activeProject || !activeEdit) return;
  try {
    const data = await api(
      `/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(activeEdit.id)}/captions`,
      {
        method: "PATCH",
        body: JSON.stringify({
          style: captionStyle?.value || "clean",
          position: captionPosition?.value || "bottom",
        }),
      },
    );
    activeEdit.captions = data.captions;
    if (captionsStatus) captionsStatus.textContent = "Caption style saved";
  } catch (error) {
    if (captionsStatus) captionsStatus.textContent = `Style failed: ${error.message}`;
  }
}

async function setCaptionBurn(burn) {
  if (!activeProject || !activeEdit) return;
  try {
    const data = await api(
      `/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(activeEdit.id)}/captions`,
      { method: "PATCH", body: JSON.stringify({ burn: Boolean(burn) }) },
    );
    activeEdit.captions = data.captions;
    if (captionsStatus) captionsStatus.textContent = burn ? "Captions will burn into render" : "SRT sidecar only";
  } catch (error) {
    if (captionsStatus) captionsStatus.textContent = `Burn setting failed: ${error.message}`;
  }
}

async function downloadCaptionTrack() {
  if (!activeProject || !activeEdit) return;
  try {
    const response = await fetch(
      `/api/projects/${encodeURIComponent(activeProject.id)}/edits/${encodeURIComponent(activeEdit.id)}/captions.srt`,
      { headers: { Authorization: `Bearer ${launchToken}` }, cache: "no-store" },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${activeProject.name.replace(/[^\w.-]+/g, "-")}-${activeEdit.id}.srt`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    if (captionsStatus) captionsStatus.textContent = `Download failed: ${error.message}`;
  }
}

async function startRenderEdit() {
  if (!activeProject || !activeEdit) return;
  renderTimer = null;
  try {
    const data = await api(renderUrl(), { method: "POST" });
    paintRender(data.render);
    await loadQueue();
    if (data.render.state === "queued" || data.render.state === "running") {
      renderTimer = setTimeout(pollRender, 1000);
    }
  } catch (error) {
    if (renderStatus) renderStatus.textContent = `Render failed: ${error.message}`;
  }
}

async function downloadRendered() {
  if (!activeProject || !activeEdit) return;
  try {
    const response = await fetch(renderUrl("/file"), {
      headers: { Authorization: `Bearer ${launchToken}` },
      cache: "no-store",
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    if (renderedBlobUrl) URL.revokeObjectURL(renderedBlobUrl);
    renderedBlobUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = renderedBlobUrl;
    anchor.download = `${activeProject.name.replace(/[^\w.-]+/g, "-")}-${activeEdit.id}.mp4`;
    anchor.click();
  } catch (error) {
    if (renderStatus) renderStatus.textContent = `Download failed: ${error.message}`;
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
cleanPreview?.addEventListener("click", previewClean);
renderEdit?.addEventListener("click", startRenderEdit);
downloadRender?.addEventListener("click", downloadRendered);
generateCaptions?.addEventListener("click", generateCaptionTrack);
downloadCaptions?.addEventListener("click", downloadCaptionTrack);
burnCaptions?.addEventListener("change", () => setCaptionBurn(burnCaptions.checked));
captionStyle?.addEventListener("change", setCaptionStyle);
captionPosition?.addEventListener("change", setCaptionStyle);
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

function queueRow(item) {
  const row = document.createElement("div");
  row.className = "queue-row";
  const info = document.createElement("div");
  info.className = "queue-info";
  const title = document.createElement("p");
  title.className = "queue-title";
  title.textContent = item.title || item.edit_id || "Render";
  const meta = document.createElement("p");
  meta.className = "queue-meta";
  const percent = Math.round((Number(item.progress) || 0) * 100);
  meta.textContent = `${item.project_name || item.project_id} · ${item.stage || item.state} · ${percent}%`;
  info.append(title, meta);
  row.append(info);
  if (["queued", "running", "cancelling"].includes(item.state)) {
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "clean-action";
    cancel.textContent = item.state === "cancelling" ? "Stopping…" : "Cancel";
    cancel.disabled = item.state === "cancelling";
    cancel.addEventListener("click", () => cancelQueueItem(item));
    row.append(cancel);
  }
  return row;
}

async function loadQueue() {
  if (!queueList) return;
  try {
    const data = await api("/api/queue");
    const items = data.items || [];
    queueList.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "projects-empty";
      empty.textContent = "No renders queued. Open an edit and choose Render 1080p.";
      queueList.append(empty);
    } else {
      for (const item of items) queueList.append(queueRow(item));
    }
    const active = items.filter((item) => ["queued", "running", "cancelling"].includes(item.state)).length;
    if (queueStatus) queueStatus.textContent = data.paused ? "Paused" : (active ? `${active} active` : "Idle");
    if (queuePause) queuePause.hidden = Boolean(data.paused);
    if (queueResume) queueResume.hidden = !data.paused;
  } catch (error) {
    if (queueStatus) queueStatus.textContent = "Queue unavailable";
  }
}

async function cancelQueueItem(item) {
  try {
    await api(
      `/api/projects/${encodeURIComponent(item.project_id)}/edits/${encodeURIComponent(item.edit_id)}/render/cancel`,
      { method: "POST" },
    );
    await loadQueue();
    await pollRender();
  } catch (error) {
    setStatus(`Cancel failed: ${error.message}`, "bad");
  }
}

async function setQueuePaused(paused) {
  try {
    await api(paused ? "/api/queue/pause" : "/api/queue/resume", { method: "POST" });
    await loadQueue();
  } catch (error) {
    setStatus(`Queue failed: ${error.message}`, "bad");
  }
}

queuePause?.addEventListener("click", () => setQueuePaused(true));
queueResume?.addEventListener("click", () => setQueuePaused(false));

function settingsRow(label, value) {
  const row = document.createElement("div");
  row.className = "settings-row";
  const key = document.createElement("span");
  key.textContent = label;
  const val = document.createElement("span");
  val.textContent = value;
  row.append(key, val);
  return row;
}

async function verifyModel(id, status) {
  status.textContent = "Verifying…";
  try {
    const data = await api(`/api/models/${encodeURIComponent(id)}/verify`, { method: "POST" });
    status.textContent = data.ok ? "Verified" : "Checksum mismatch";
    status.classList.toggle("is-bad", !data.ok);
  } catch (error) {
    status.textContent = error.message;
    status.classList.add("is-bad");
  }
}

async function loadSettingsPanel() {
  if (!settingsPanel) return;
  try {
    const [settings, engine, models] = await Promise.all([
      api("/api/settings"),
      api("/api/engine"),
      api("/api/models"),
    ]);
    settingsEngine.replaceChildren(
      settingsRow("Apple Vision", engine.vision.available ? "Ready" : "Unavailable"),
      settingsRow("Apple Speech", engine.speech.apple ? "Ready" : "Unavailable"),
      settingsRow("LaMa", engine.fill.ready ? "Ready" : (engine.fill.problem || "Unavailable")),
      settingsRow("Smart stories", engine.stories.ready ? "Ready" : "Unavailable"),
    );
    settingsModels.replaceChildren();
    for (const model of models.models || []) {
      const row = document.createElement("div");
      row.className = "settings-row";
      const name = document.createElement("span");
      name.textContent = `${model.label} · ${formatBytes(model.bytes)}`;
      const action = document.createElement("span");
      action.className = "settings-model-action";
      const status = document.createElement("span");
      status.className = "section-note";
      status.textContent = model.installed ? "Installed" : "Missing";
      const verify = document.createElement("button");
      verify.type = "button";
      verify.className = "clean-action";
      verify.textContent = "Verify";
      verify.addEventListener("click", () => verifyModel(model.id, status));
      action.append(status, verify);
      row.append(name, action);
      settingsModels.append(row);
    }
    settingsStorage.replaceChildren(
      settingsRow("Data folder", settings.storage.data_root),
      settingsRow("Projects", formatBytes(settings.storage.projects_bytes)),
      settingsRow("Models", formatBytes(settings.storage.models_bytes)),
      settingsRow("Free disk", formatBytes(settings.storage.free_bytes)),
    );
    onlineEnabled.checked = Boolean(settings.online.enabled);
    onlineEndpoint.value = settings.online.endpoint || "";
    settingsVersion.textContent = `DuckSuite ${settings.version} · local-first · no account`;
  } catch (error) {
    settingsEngine.replaceChildren(settingsRow("Settings", error.message));
  }
}

async function openSettings() {
  settingsPanel.hidden = false;
  await loadSettingsPanel();
}

function closeSettings() {
  settingsPanel.hidden = true;
}

async function saveOnlineSettings() {
  if (onlineStatus) onlineStatus.textContent = "Saving…";
  try {
    await api("/api/settings", {
      method: "PATCH",
      body: JSON.stringify({
        online_enabled: onlineEnabled.checked,
        online_endpoint: onlineEndpoint.value.trim(),
      }),
    });
    if (onlineStatus) onlineStatus.textContent = "Saved";
  } catch (error) {
    if (onlineStatus) onlineStatus.textContent = error.message;
  }
}

settingsButton?.addEventListener("click", openSettings);
settingsClose?.addEventListener("click", closeSettings);
saveOnline?.addEventListener("click", saveOnlineSettings);
settingsPanel?.addEventListener("click", (event) => {
  if (event.target === settingsPanel) closeSettings();
});

async function health() {
  if (!launchToken) {
    setStatus("No launch token", "bad");
    return;
  }
  try {
    const data = await api("/api/health");
    setStatus(`Local core ${data.version}`, "ok");
    await Promise.all([loadProjects(), loadEngine(), loadQueue()]);
    setInterval(loadQueue, 4000);
  } catch (error) {
    setStatus("Local core unavailable", "bad");
    console.error(error);
  }
}

launchToken = readToken();
baseURL = window.location.origin;
importButton?.addEventListener("click", importVideo);
health();
