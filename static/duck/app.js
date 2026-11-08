/* DuckSuite — Daylight Story Desk.
   One shell, six screens, no marketing page. */

const app = document.querySelector('#app');
const modalRoot = document.querySelector('#modal-root');
const toastEl = document.querySelector('#toast');
const NO_AUTO = new URLSearchParams(window.location.search).has('noauto');

const state = {
  token: '',
  screen: 'welcome',
  projects: [],
  queue: [],
  engine: null,
  settings: null,
  models: [],
  voices: [],
  project: null,
  check: null,
  sourceMeta: null,
  edits: [],
  edit: null,
  transcript: {},
  selectedScene: 0,
  selectedLayerId: '',
  proofTab: 'scenes',
  inspectorTab: 'clean',
  previewTime: 0,
  previewCache: new Map(),
  previewStatus: new Map(),
  previewRunning: false,
  previewRun: 0,
  cleanVersion: 0,
  voiceName: 'Samantha',
  voiceMode: 'voice_over',
  welcomeQuery: '',
  queuePaused: false,
  previewView: 'after',
  inlinePlaying: false,
  importing: false,
  lastCheckKey: '',
  lastQueueKey: '',
  autoOpened: false,
  editorReady: false,
  showAllLayers: false,
  showAllCues: false,
};

/* ------------------------------------------------------------------ utils */

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function pad(value, size = 2) {
  return String(value).padStart(size, '0');
}

function fmtTime(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(value / 60);
  const rest = Math.floor(value % 60);
  return `${minutes}:${pad(rest)}`;
}

function fmtTC(seconds, fps = 0) {
  const value = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = Math.floor(value % 60);
  const frames = fps > 0 ? Math.floor((value % 1) * fps) : 0;
  return `${pad(hours)}:${pad(minutes)}:${pad(secs)}${fps > 0 ? `:${pad(frames)}` : ''}`;
}

function fmtDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 60) return `${Math.round(value)}s`;
  const minutes = Math.floor(value / 60);
  const rest = Math.round(value % 60);
  if (minutes < 60) return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins ? `${hours}h ${mins}m` : `${hours}h`;
}

function fmtBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function relDate(seconds) {
  if (!seconds) return '';
  const date = new Date(Number(seconds) * 1000);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return 'Today';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function readToken() {
  const queryToken = new URLSearchParams(window.location.search).get('t') || '';
  if (queryToken) {
    sessionStorage.setItem('duckLaunchToken', queryToken);
    return queryToken;
  }
  const hash = window.location.hash || '';
  const match = hash.match(/(?:^#|&)t=([^&]+)/);
  if (match) {
    const token = decodeURIComponent(match[1]);
    sessionStorage.setItem('duckLaunchToken', token);
    history.replaceState(null, '', window.location.pathname + window.location.search);
    return token;
  }
  return sessionStorage.getItem('duckLaunchToken') || '';
}

function mediaUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value);
  }
  url.searchParams.set('t', state.token);
  return `${url.pathname}${url.search}`;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('Authorization', `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof File) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(path, { ...options, headers, cache: 'no-store' });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) { /* ignore */ }
    throw new Error(detail);
  }
  const type = response.headers.get('content-type') || '';
  if (type.includes('application/json')) return response.json();
  return response;
}

function toast(message, kind = '') {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.className = `toast${kind === 'bad' ? ' is-bad' : ''}`;
  toastEl.hidden = false;
  window.clearTimeout(toastEl._timer);
  toastEl._timer = window.setTimeout(() => { toastEl.hidden = true; }, 4200);
}

function icon(name, size = 18) {
  const paths = {
    folder: '<path d="M3.5 6.5h6l1.6 2H20a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 20 19.5H4A1.5 1.5 0 0 1 2.5 18V8A1.5 1.5 0 0 1 4 6.5Z"/>',
    upload: '<path d="M12 16V4m0 0 4 4m-4-4L8 8"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    film: '<rect x="3" y="4.5" width="18" height="15" rx="2"/><path d="M7.5 4.5v15M16.5 4.5v15M3 9h4.5M3 15h4.5M16.5 9H21M16.5 15H21"/>',
    play: '<path d="m8.5 5 10.5 7-10.5 7V5Z"/>',
    pause: '<path d="M8 5v14M16 5v14"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="1"/>',
    settings: '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06-1.7 1.7-.06-.06A1.7 1.7 0 0 0 16.17 18a1.7 1.7 0 0 0-1 .23 1.7 1.7 0 0 0-.86 1.49V20h-2.4v-.28a1.7 1.7 0 0 0-1.13-1.58 1.7 1.7 0 0 0-1.87.34l-.06.06-1.7-1.7.06-.06A1.7 1.7 0 0 0 6 16.17a1.7 1.7 0 0 0-.23-1 1.7 1.7 0 0 0-1.49-.86H4v-2.4h.28A1.7 1.7 0 0 0 5.86 9.8a1.7 1.7 0 0 0-.34-1.87l-.06-.06 1.7-1.7.06.06A1.7 1.7 0 0 0 9.1 6.6a1.7 1.7 0 0 0 1-.23 1.7 1.7 0 0 0 .86-1.49V4h2.4v.28A1.7 1.7 0 0 0 14.5 5.86a1.7 1.7 0 0 0 1.87-.34l.06-.06 1.7 1.7-.06.06A1.7 1.7 0 0 0 17.73 9.1c.13.36.21.74.23 1.13h.28v2.4h-.28A1.7 1.7 0 0 0 16.4 14.5c-.22.16-.43.35-.62.56Z"/>',
    check: '<path d="m5 12.5 4.2 4.2L19 7"/>',
    checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12.2 2.6 2.6L16.2 9"/>',
    circle: '<circle cx="12" cy="12" r="8.5"/>',
    loader: '<path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    chevronLeft: '<path d="m14.5 6-6 6 6 6"/>',
    chevronRight: '<path d="m9.5 6 6 6-6 6"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    arrowLeft: '<path d="M19 12H5m6-6-6 6 6 6"/>',
    arrowRight: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5"/>',
    download: '<path d="M12 4v11m0 0 4-4m-4 4-4-4"/><path d="M5 19h14"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    warning: '<path d="M12 4 3.5 19h17L12 4Z"/><path d="M12 9v4.5M12 16.5v.2"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    captions: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 10.2a2.4 2.4 0 1 0 0 3.6M17 10.2a2.4 2.4 0 1 0 0 3.6"/>',
    voice: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M6 11.5a6 6 0 0 0 12 0M12 17.5V21M9 21h6"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
    sparkle: '<path d="M12 3.5 13.6 9l5.4 1.6-5.4 1.6L12 17.7l-1.6-5.5L5 10.6 10.4 9 12 3.5Z"/><path d="M18.5 15.5 19.2 18l2.3.7-2.3.7-.7 2.4-.7-2.4-2.3-.7 2.3-.7.7-2.5Z"/>',
    grid: '<rect x="4" y="4" width="6.5" height="6.5" rx="1"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1"/>',
    list: '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    monitor: '<rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M8.5 20h7M12 16.5V20"/>',
    volume: '<path d="M11 5 6.5 9H3v6h3.5L11 19V5Z"/><path d="M15 9a4.2 4.2 0 0 1 0 6M17.5 6.5a8 8 0 0 1 0 11"/>',
    expand: '<path d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5"/>',
    more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
    eye: '<path d="M2.5 12S6 6.5 12 6.5 21.5 12 21.5 12 18 17.5 12 17.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="2.6"/>',
    eyeOff: '<path d="m4 4 16 16M10.6 6.7A9.8 9.8 0 0 1 12 6.5c6 0 9.5 5.5 9.5 5.5a17 17 0 0 1-3.3 3.7M6.2 8.3A17 17 0 0 0 2.5 12S6 17.5 12 17.5c1.2 0 2.3-.2 3.3-.6"/>',
    scissors: '<circle cx="6" cy="7" r="2.2"/><circle cx="6" cy="17" r="2.2"/><path d="m8 8.2 11 8M8 15.8l11-8"/>',
    trash: '<path d="M4 7h16M9 7V4.5h6V7M7 7l1 13h8l1-13M10 11v5M14 11v5"/>',
    folderOpen: '<path d="M3 7.5h6l1.6 2H21l-2 9.5H4L2.5 9.5H3Z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.6v.2"/>',
    sun: '<circle cx="12" cy="12" r="3.5"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4"/>',
  };
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.circle}</svg>`;
}

function duckMark(size = 34) {
  return `<svg class="brand-mark" width="${size}" height="${Math.round(size * 0.88)}" viewBox="0 0 40 35" aria-hidden="true">
    <path fill="currentColor" d="M7.2 22.1c0-5.5 4.7-9.7 10.7-9.7 4.2 0 8.1 2.1 10.4 5.4l3.2-1.2c.7-.3 1.4.5 1 1.2l-1.7 3.1c-1.9 3.4-5.6 5.6-9.7 5.6H8.3l-1.1-4.4Z"/>
    <path fill="currentColor" d="M28.4 9.3a5.6 5.6 0 1 1 0 11.2 5.6 5.6 0 0 1 0-11.2Z"/>
    <path fill="currentColor" d="M34.4 12.4 40 14.3l-5.6 2.1v-4Z"/>
    <circle cx="31.2" cy="12.6" r="1" fill="#fff"/>
    <path fill="currentColor" d="M7.3 20.8 2 16.9l1.2 7.2 4.1-3.3Z"/>
  </svg>`;
}

/* ------------------------------------------------------------------ data */

async function loadProjects() {
  const data = await api('/api/projects');
  state.projects = data.projects || [];
}

async function loadQueue() {
  const data = await api('/api/queue');
  state.queuePaused = Boolean(data.paused);
  state.queue = data.items || [];
}

async function loadEngine() {
  try { state.engine = await api('/api/engine'); } catch (_) { state.engine = null; }
}

async function loadSettings() {
  try { state.settings = await api('/api/settings'); } catch (_) { state.settings = null; }
}

async function loadVoices() {
  if (state.voices.length) return;
  try {
    const data = await api('/api/voices');
    state.voices = data.voices || [];
    const preferred = state.voices.find((voice) => voice.name === 'Samantha')
      || state.voices.find((voice) => voice.locale === 'en_US')
      || state.voices[0];
    if (preferred) state.voiceName = preferred.name;
  } catch (_) { /* voices stay empty */ }
}

async function openProject(id, { startCheck = false } = {}) {
  const data = await api(`/api/projects/${encodeURIComponent(id)}`);
  state.project = data.project;
  state.check = data.check;
  state.sourceMeta = data.check?.result?.meta || data.check?.source || null;
  state.lastCheckKey = checkKey();
  state.selectedScene = 0;
  state.selectedLayerId = '';
  state.proofTab = 'scenes';
  state.inspectorTab = 'clean';
  state.previewCache.clear();
  state.previewStatus.clear();
  state.previewRunning = false;
  state.previewRun += 1;
  state.previewTime = 0;
  state.autoOpened = false;
  state.editorReady = false;

  const [editsData, transcriptData] = await Promise.all([
    api(`/api/projects/${encodeURIComponent(id)}/edits`).catch(() => ({ edits: [] })),
    api(`/api/projects/${encodeURIComponent(id)}/transcript`).catch(() => ({ transcript: {} })),
  ]);
  state.edits = editsData.edits || [];
  state.transcript = transcriptData.transcript || {};
  await ensureEdit();
  const scenes = getScenes();
  if (scenes[0]) state.previewTime = Number(scenes[0].start || 0) + 0.1;

  if (startCheck && state.check?.state === 'idle') await startCheck();
}

async function ensureEdit() {
  if (!state.project) return null;
  if (state.edit && state.edit.project_id === state.project.id) return state.edit;
  const full = state.edits.find((edit) => edit.kind === 'full');
  const candidate = full || state.edits[0];
  if (candidate) {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(candidate.id)}`);
    state.edit = data.edit;
    await ensureCleanLayers();
    return state.edit;
  }
  if (!state.check?.result?.scenes?.length) return null;
  const created = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/full`, { method: 'POST' });
  state.edit = created.edit;
  state.edits = [{ ...created.edit, kind: 'full' }, ...state.edits];
  await ensureCleanLayers();
  return state.edit;
}

async function ensureCleanLayers() {
  if (!state.project || !state.edit) return;
  if (state.edit.clean?.length) return;
  if (!state.check?.result?.report?.tracklets?.length) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/from-check`, { method: 'POST' });
    state.edit = data.edit;
    state.cleanVersion += 1;
  } catch (_) { /* Editor still opens; Clean reports the failure */ }
}

async function refreshTranscript() {
  if (!state.project) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/transcript`);
    state.transcript = data.transcript || {};
  } catch (_) { /* keep the last transcript */ }
}

async function startCheck() {
  if (!state.project) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/check`, { method: 'POST' });
    state.check = data.check;
    state.edit = null;
    state.edits = [];
    state.transcript = {};
    state.previewCache.clear();
    state.previewStatus.clear();
    state.previewRun += 1;
    state.selectedScene = 0;
    state.selectedLayerId = '';
    state.showAllLayers = false;
    state.showAllCues = false;
    state.autoOpened = false;
    state.editorReady = false;
    state.lastCheckKey = checkKey();
    render();
  } catch (error) {
    toast(`Check could not start: ${error.message}`, 'bad');
  }
}

async function refreshCheck() {
  if (!state.project) return;
  const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/check`);
  const previous = state.lastCheckKey;
  const hadScenes = getScenes().length;
  state.check = data.check;
  const next = checkKey();
  const hasScenes = getScenes().length;
  if (state.screen === 'check' && !NO_AUTO && !state.autoOpened && hadScenes === 0 && hasScenes > 0 && ['queued', 'running'].includes(data.check?.state)) {
    state.autoOpened = true;
    toast('Scenes ready. Opening Editor while the rest finishes.');
    window.setTimeout(() => navigate(projectPath('edit')), 900);
  }
  if (data.check?.editor_ready && !state.editorReady) {
    state.editorReady = true;
    state.sourceMeta = data.check?.result?.meta || state.sourceMeta;
    if (!state.edit) await ensureEdit();
    await refreshTranscript();
  }
  if (data.check?.state === 'done') {
    state.sourceMeta = data.check?.result?.meta || state.sourceMeta;
    if (!state.edit) await ensureEdit();
    if (!state.editorReady) {
      state.editorReady = true;
      await refreshTranscript();
    }
  }
  if (next !== previous) {
    state.lastCheckKey = next;
    if (['check', 'edit', 'clean', 'preview'].includes(state.screen)) render();
  }
}

async function refreshQueue() {
  try {
    const data = await api('/api/queue');
    const next = JSON.stringify((data.items || []).map((item) => [item.id, item.state, item.progress, item.updated]));
    state.queuePaused = Boolean(data.paused);
    state.queue = data.items || [];
    if (next !== state.lastQueueKey) {
      state.lastQueueKey = next;
      if (['welcome', 'render'].includes(state.screen)) render();
    }
  } catch (_) { /* keep last queue */ }
}

function checkKey() {
  const check = state.check || {};
  const scenes = getScenes().length;
  return `${check.state || ''}|${check.stage || ''}|${Math.round((check.progress || 0) * 1000)}|${scenes}`;
}

/* ------------------------------------------------------------------ model */

function checkScenes() {
  return state.check?.result?.scenes || state.check?.scenes || [];
}

function getScenes() {
  const all = checkScenes();
  if (!state.edit || state.edit.kind !== 'story') return all;
  const ids = new Set(
    (state.edit.clips || [])
      .map((clip) => clip.scene)
      .filter((id) => id !== null && id !== undefined),
  );
  if (!ids.size) return all;
  return all.filter((scene) => ids.has(scene.id));
}

function getStories() {
  return state.check?.result?.stories?.stories || [];
}

function getSegments() {
  return state.transcript?.segments || [];
}

function currentScene() {
  const scenes = getScenes();
  return scenes[state.selectedScene] || scenes[0] || null;
}

function sceneMid(scene) {
  if (!scene) return 0;
  return Number(scene.start || 0) + Math.max(0.05, (Number(scene.end || 0) - Number(scene.start || 0)) * 0.5);
}

function sceneTitle(scene, index) {
  if (!scene) return 'Scene';
  const segment = getSegments().find((item) => Number(item.start || 0) < Number(scene.end || 0) && Number(item.end || 0) > Number(scene.start || 0));
  if (segment?.text) return truncate(segment.text, 46);
  const ocr = String(scene.ocr || '').replace(/\s+/g, ' ').trim();
  if (ocr) return truncate(ocr, 38);
  return `Scene ${pad(index + 1)}`;
}

function truncate(value, size) {
  const text = String(value || '').trim();
  return text.length > size ? `${text.slice(0, size - 1)}…` : text;
}

function sceneLayers(scene) {
  if (!scene || !state.edit?.clean) return [];
  const start = Number(scene.start || 0);
  const end = Number(scene.end || 0);
  return state.edit.clean.filter((layer) => (layer.ranges || []).some((range) => Number(range.end || 0) > start && Number(range.start || 0) < end));
}

function clipIndexForScene(scene, index = state.selectedScene) {
  const clips = state.edit?.clips || [];
  if (!clips.length) return -1;
  const byScene = clips.findIndex((clip) => clip.scene === scene?.id);
  if (byScene >= 0) return byScene;
  return Math.max(0, Math.min(index, clips.length - 1));
}

function clipForScene(scene, index = state.selectedScene) {
  const clips = state.edit?.clips || [];
  const at = clipIndexForScene(scene, index);
  return at >= 0 ? clips[at] : null;
}

function layerState(layer) {
  if (!layer || layer.enabled === false) return 'Off';
  return layer.kind === 'blur' ? 'Blur' : 'Fill';
}

const LAYER_KIND = {
  screen_text: 'Screen text',
  subtitle: 'Subtitle',
  lower_third: 'Lower third',
  title: 'Title',
  credit: 'Credit',
  watermark: 'Logo / watermark',
  handle_or_logo: 'Logo / watermark',
};

function layerLabel(layer, index) {
  const kind = LAYER_KIND[layer?.tracklet_kind] || 'Text block';
  return `${kind} ${pad(index + 1)}`;
}


function cleanState(scene) {
  if (!state.edit) return 'Waiting';
  if (!sceneLayers(scene).length) return 'Needs clean';
  return 'Layered';
}

function sceneCleanCount(scenes = getScenes()) {
  return scenes.filter((scene) => sceneLayers(scene).length > 0).length;
}

function sceneRenderReady(scene) {
  const layers = sceneLayers(scene);
  if (!layers.length) return true;
  if (layers.every((layer) => layer.enabled === false)) return true;
  return state.previewStatus.get(scene.id) === 'ready';
}

function sceneReadyCount(scenes = getScenes()) {
  return scenes.filter(sceneRenderReady).length;
}

function sceneStripControls(target) {
  return `<span class="strip-arrows"><button class="strip-arrow" type="button" data-action="strip-scroll" data-target="${target}" data-dir="-1" aria-label="Scroll scenes left">‹</button><button class="strip-arrow" type="button" data-action="strip-scroll" data-target="${target}" data-dir="1" aria-label="Scroll scenes right">›</button></span>`;
}

function frameUrl(time, projectId = state.project?.id) {
  if (!projectId) return '';
  return mediaUrl(`/api/projects/${encodeURIComponent(projectId)}/frame`, { time: Math.max(0, Number(time) || 0).toFixed(3) });
}

function cleanPreviewUrl(time) {
  if (!state.project || !state.edit) return '';
  return mediaUrl(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/preview`, {
    time: Math.max(0, Number(time) || 0).toFixed(3),
    v: state.cleanVersion,
  });
}

function cleanImg(url, alt, placeholder) {
  return `<img src="${esc(placeholder)}" data-clean-src="${esc(url)}" alt="${esc(alt)}">`;
}

const cleanFetchQueue = [];
let cleanFetchRunning = false;

function enqueueCleanFetch(url, priority = false) {
  return new Promise((resolve, reject) => {
    const item = { url, resolve, reject };
    if (priority) cleanFetchQueue.unshift(item);
    else cleanFetchQueue.push(item);
    pumpCleanFetch();
  });
}

async function pumpCleanFetch() {
  if (cleanFetchRunning) return;
  const item = cleanFetchQueue.shift();
  if (!item) return;
  cleanFetchRunning = true;
  try {
    let blob = null;
    for (let attempt = 0; attempt < 14; attempt += 1) {
      const response = await fetch(`${item.url}${attempt ? `&retry=${attempt}` : ''}`, { cache: 'no-store' });
      if (response.ok) { blob = await response.blob(); break; }
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    if (!blob) throw new Error('Clean preview is still busy.');
    item.resolve(blob);
  } catch (error) {
    item.reject(error);
  } finally {
    cleanFetchRunning = false;
    pumpCleanFetch();
  }
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Could not read the clean preview.'));
    reader.readAsDataURL(blob);
  });
}

function afterFrameUrl(scene) {
  if (!scene) return '';
  return state.previewCache.get(scene.id) || frameUrl(sceneMid(scene));
}

function sourceUrl(projectId = state.project?.id) {
  if (!projectId) return '';
  return mediaUrl(`/api/projects/${encodeURIComponent(projectId)}/source`);
}

function projectFacts() {
  const meta = state.check?.result?.meta || state.edit?.source || state.sourceMeta || {};
  const duration = Number(meta.duration || state.edit?.end || 0);
  const width = Number(meta.width || 0);
  const height = Number(meta.height || 0);
  const fps = Number(meta.fps || 0);
  return [
    duration ? fmtDuration(duration) : '',
    width && height ? `${width}×${height}` : '',
    fps ? `${Math.round(fps)}fps` : '',
  ].filter(Boolean).join(' · ');
}

function engineLabel() {
  if (!state.engine) return 'Starting local core…';
  return state.engine.fill?.ready && state.engine.vision?.available ? 'Local · ready' : 'Local · check';
}

function queueActiveCount() {
  return state.queue.filter((item) => ['queued', 'running', 'rendering', 'paused'].includes(item.state)).length;
}

function latestRender() {
  return state.queue.find((item) => item.state === 'done' && item.output) || null;
}

/* ------------------------------------------------------------------ router */

function parseRoute() {
  const raw = (window.location.hash || '').replace(/^#\/?/, '');
  if (!raw || raw === 'welcome') return { screen: 'welcome' };
  const parts = raw.split('/').filter(Boolean);
  if (parts[0] === 'project' && parts[1]) return { screen: parts[2] || 'check', projectId: parts[1] };
  return { screen: 'welcome' };
}

function navigate(path) {
  const target = `#/${path}`;
  if (window.location.hash === target) route();
  else window.location.hash = target;
}

function projectPath(screen) {
  if (!state.project) return 'welcome';
  return `project/${state.project.id}/${screen}`;
}

async function route() {
  const routeInfo = parseRoute();
  if (routeInfo.screen === 'welcome') {
    state.screen = 'welcome';
    state.project = null;
    state.check = null;
    state.edit = null;
    state.transcript = {};
    render();
    return;
  }
  try {
    if (!state.project || state.project.id !== routeInfo.projectId) {
      await openProject(routeInfo.projectId);
    }
    state.screen = routeInfo.screen;
    if (['edit', 'clean', 'preview', 'render'].includes(routeInfo.screen)) await ensureEdit();
    if (routeInfo.screen === 'check' && state.check?.state === 'idle') await startCheck();
    if (routeInfo.screen === 'preview') startPreviewClean();
    if (routeInfo.screen === 'clean' && state.edit) {
      const scene = currentScene();
      if (scene && !state.previewCache.has(scene.id)) startPreviewClean(scene.id);
    }
    render();
  } catch (error) {
    toast(`Project could not open: ${error.message}`, 'bad');
    navigate('welcome');
  }
}

/* ------------------------------------------------------------------ topbar */

function topbar() {
  const project = state.project;
  const screen = state.screen;
  const active = screen === 'clean' ? 'edit' : screen;
  const order = ['check', 'edit', 'preview', 'render'];
  const activeIndex = order.indexOf(active);
  const checkRunning = ['queued', 'running', 'cancelling'].includes(state.check?.state);
  const step = (name, label, index, busy = false) => {
    const isActive = active === name;
    const isDone = !busy && activeIndex > index;
    return `<button class="step${isActive ? ' is-active' : ''}${isDone ? ' is-done' : ''}" data-action="nav" data-screen="${name}" type="button">
      <span class="step-check">${busy ? icon('loader', 11) : isDone || isActive ? icon('check', 11) : icon('circle', 11)}</span>
      ${label}
    </button>`;
  };
  return `<header class="topbar">
    <div class="topbar-main">
      <a class="brand" href="#/welcome" data-action="welcome">${duckMark(34)}<span class="brand-name">DuckSuite</span></a>
      ${project ? `<button class="project-pill" type="button" data-action="welcome" title="All projects"><span>${esc(project.name)}</span>${icon('chevronDown', 14)}</button>
      <div class="project-facts">${esc(projectFacts())}</div>` : ''}
      <div class="top-actions">
        <span class="engine-pill"><span class="dot" id="engine-dot"></span>${esc(engineLabel())}</span>
        <span class="queue-pill">${icon('layers', 15)} Queue: ${state.queue.length}</span>
        <button class="icon-btn" type="button" data-action="settings" title="Settings" aria-label="Settings">${icon('settings', 18)}</button>
        ${project ? `<button class="back-welcome" type="button" data-action="welcome">${icon('arrowLeft', 15)} Back to Welcome</button>` : ''}
      </div>
    </div>
    ${project ? `<div class="stepper-row"><div class="stepper">
      ${step('check', checkRunning ? 'Checking' : 'Check', 0, checkRunning)}
      <span class="step-line"></span>
      ${step('edit', 'Edit', 1)}
      <span class="step-line"></span>
      ${step('preview', 'Preview', 2)}
      <span class="step-line"></span>
      ${step('render', 'Render', 3)}
    </div></div>` : ''}
  </header>`;
}

/* ------------------------------------------------------------------ welcome */

function screenWelcome() {
  const filtered = state.projects.filter((project) => project.name.toLowerCase().includes(state.welcomeQuery.toLowerCase()));
  const latest = latestRender();
  const activeQueue = state.queue.filter((item) => ['queued', 'running', 'rendering', 'paused'].includes(item.state));
  const recentQueue = state.queue
    .filter((item) => item.state === 'done' && item.id !== latest?.id)
    .slice(0, 2);
  const engine = state.engine || {};
  const free = state.settings?.storage?.free_bytes || 0;
  const retention = state.settings?.storage?.projects_bytes || 0;
  return `<main class="screen">
    <div class="workspace welcome">
      <aside class="panel welcome-left">
        <div class="search">${icon('search', 15)}<input id="project-search" type="search" placeholder="Search projects" value="${esc(state.welcomeQuery)}" aria-label="Search projects"></div>
        <p class="section-label">Projects</p>
        <div class="project-list">
          ${filtered.length ? filtered.map((project) => `
            <button class="project-row${state.project?.id === project.id ? ' is-active' : ''}" type="button" data-action="open-project" data-project="${esc(project.id)}">
              <span class="project-icon">${icon('folder', 19)}</span>
              <span style="min-width:0"><span class="project-name">${esc(project.name)}</span><span class="project-sub">${relDate(project.updated)} · ${fmtBytes(project.source_bytes)}</span></span>
              ${state.project?.id === project.id ? '<span class="chip amber">Editing</span>' : ''}
            </button>`).join('') : '<p class="muted small" style="padding:8px 9px">No projects yet.</p>'}
        </div>
        <button class="btn wide" type="button" data-action="import" style="margin-top:12px">${icon('plus', 15)} Import video</button>
      </aside>

      <section class="welcome-center">
        <div class="dropzone" data-dropzone>
          <span class="drop-icon">${icon('upload', 42)}</span>
          <h1>One long video in.</h1>
          <p>We find the scenes, clean the old text, and cut the clips.</p>
          <button class="btn primary" type="button" data-action="import">Choose Video</button>
          <p class="fine">or drag and drop a file here · MP4, MOV, M4V</p>
          <input id="file-input" type="file" accept="video/mp4,video/quicktime,video/x-m4v,.mp4,.mov,.m4v" hidden>
        </div>

        <section class="panel latest-render">
          <div class="panel-head"><h2>Latest render</h2><span class="meta">${latest ? esc(latest.project_name || '') : 'Nothing rendered yet'}</span></div>
          ${latest ? `<div class="latest-card">
            <div class="latest-thumb">
              <img src="${frameUrl(0.5, latest.project_id)}" alt="">
              <button class="play" type="button" data-action="play-render" data-project="${esc(latest.project_id)}" data-edit="${esc(latest.edit_id)}" aria-label="Play latest render">${icon('play', 14)}</button>
              <span class="duration">1080p</span>
            </div>
            <div class="latest-copy">
              <h3>${esc(latest.project_name || 'Project')} · ${esc(latest.title || 'Render')}</h3>
              <p>${esc(latest.stage || 'Render complete')} · H.264 · 1080p</p>
              <p>${esc(latest.message || '')}</p>
              <div class="actions">
                <button class="btn small" type="button" data-action="play-render" data-project="${esc(latest.project_id)}" data-edit="${esc(latest.edit_id)}">${icon('play', 13)} Play</button>
                <button class="btn small" type="button" data-action="reveal" data-path="${esc(latest.output || '')}">${icon('folderOpen', 13)} Show in Finder</button>
              </div>
            </div>
          </div>` : `<div class="queue-empty">Render a story and it lands here.</div>`}
        </section>
      </section>

      <aside class="panel welcome-right">
        <div class="panel-head"><h2>Render queue</h2><span class="meta">${queueActiveCount() ? `${queueActiveCount()} active` : 'Idle'}</span></div>
        <div class="queue-list">
          ${activeQueue.length ? activeQueue.map((item) => queueCard(item)).join('') : '<div class="queue-empty">No active renders.</div>'}
        </div>
        ${recentQueue.length ? `<div class="panel-head" style="padding:6px 14px 0"><h3 style="font-size:11px">Recent</h3><span class="meta">Finished</span></div>
        <div class="queue-list">${recentQueue.map((item) => queueCard(item)).join('')}</div>` : ''}
        <div class="engine-card">
          <p class="section-label">Engine</p>
          <div class="engine-row"><span class="dot"></span><strong>${esc(engineLabel())}</strong></div>
          <div class="engine-row">${icon('monitor', 14)} ${free ? `Disk space: ${fmtBytes(free)} free` : 'Disk space: —'}</div>
          <div class="engine-row">${icon('layers', 14)} ${retention ? `${fmtBytes(retention)} in projects` : 'Local project storage'}</div>
        </div>
      </aside>
    </div>
  </main>`;
}

function queueCard(item) {
  const active = ['queued', 'running', 'rendering', 'paused'].includes(item.state);
  const pct = Math.round((Number(item.progress) || 0) * 100);
  return `<div class="queue-card${active ? ' is-active' : ''}">
    <div class="queue-top">
      <span class="queue-icon">${icon('film', 17)}</span>
      <div style="min-width:0;flex:1"><div class="queue-title">${esc(item.title || 'Render')}</div><div class="queue-sub">${esc(item.project_name || '')}</div></div>
      <span class="chip ${item.state === 'done' ? 'green' : item.state === 'failed' ? 'red' : active ? 'amber' : ''}">${esc(queueLabel(item.state))}</span>
    </div>
    ${active ? `<div class="queue-row"><div class="progress"><span style="width:${pct}%"></span></div><span class="mono small">${pct}%</span></div>` : ''}
    <div class="queue-foot">
      <span class="small muted">${item.state === 'done' ? '1080p · MP4' : esc(item.message || '')}</span>
      ${item.state === 'done' ? `<button class="btn small" type="button" data-action="play-render" data-project="${esc(item.project_id)}" data-edit="${esc(item.edit_id)}">${icon('play', 12)} Play</button>` : ''}
    </div>
  </div>`;
}

function queueLabel(value) {
  return ({ queued: 'Queued', running: 'Rendering', rendering: 'Rendering', paused: 'Paused', done: 'Done', failed: 'Failed', cancelled: 'Cancelled' }[value] || value || 'Idle');
}

/* ------------------------------------------------------------------ check */

function screenCheck() {
  const check = state.check || {};
  const scenes = checkScenes();
  const running = ['queued', 'running', 'cancelling'].includes(check.state);
  const done = check.state === 'done';
  const scenesPct = stagePct('scenes');
  const transcriptPct = stagePct('transcript');
  const textPct = stagePct('text');
  const storiesPct = stagePct('stories');
  return `<main class="screen">
    <div class="workspace check">
      <aside style="display:grid;gap:14px">
        <section class="panel source-card">
          <div class="source-thumb">
            <img src="${frameUrl(0.5)}" alt="">
            <span class="media-badge">${esc(projectFacts())}</span>
          </div>
          <div class="source-name">${esc(state.project?.name || 'Source')}</div>
          <div class="source-meta">${esc(projectFacts() || 'Local video')}</div>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Stages</h2><span class="meta">${done ? 'Complete' : running ? `${Math.round((check.progress || 0) * 100)}%` : 'Not started'}</span></div>
          <div class="stage-list">
            ${stageRow('scenes', 'Stage 1 · Scenes', scenes.length ? `${scenes.length} scenes` : 'Detect and split scenes', scenesPct, done || scenesPct >= 1)}
            ${stageRow('transcript', 'Stage 2 · Transcript', 'Speech to text · auto language', transcriptPct, done || transcriptPct >= 0.999)}
            ${stageRow('text', 'Text detect', 'Find burned-in text', textPct, done || textPct >= 0.999)}
            ${stageRow('stories', 'Stories', 'Find story segments', storiesPct, done || storiesPct >= 0.999)}
          </div>
        </section>
      </aside>

      <section style="display:grid;gap:14px;min-width:0">
        <section class="panel" style="overflow:hidden">
          <div class="media-card" style="height:min(56vh, 540px)">
            <video data-preview controls preload="metadata" poster="${frameUrl(state.previewTime || 0.5)}" src="${sourceUrl()}"></video><span class="media-badge right">${mediaResolution()}</span>
            <div class="media-overlay"><span class="tc">${fmtTC(state.previewTime || 0.5)} / ${fmtTC(state.check?.result?.meta?.duration || state.edit?.source?.duration || 0)}</span><span class="spacer"></span></div>
          </div>
        </section>
        <section class="panel">
          <div class="scene-strip-wrap">
            <div class="scene-strip-head"><h3>Scenes · ${scenes.length || '—'} total</h3><span class="small muted">${running ? 'Scenes ready' : done ? 'All scenes ready' : 'Waiting for scene cuts'}</span>${sceneStripControls('check-scenes')}</div>
            ${scenes.length ? `<div class="scene-strip" id="check-scenes">${scenes.map((scene, index) => sceneTile(scene, index)).join('')}</div>` : `<div class="queue-empty">Scene cuts appear here first. The Editor opens as soon as they are ready.</div>`}
          </div>
        </section>
      </section>

      <aside class="panel check-panel">
        <div class="panel-head"><h2>Check</h2><span class="meta">${done ? 'Done' : running ? 'Running' : 'Idle'}</span></div>
        <div class="check-cta" style="padding-top:14px">
          <div class="check-summary">
            <strong>${scenes.length ? `${scenes.length} scenes ready` : running ? 'Finding scene cuts' : 'Not checked yet'}</strong>
            <span>${done ? 'Check complete. Transcript, text detection, and stories are ready.' : state.check?.editor_ready ? 'Editor ready. Stories finish in the background.' : `Transcript ${Math.round(transcriptPct * 100)}% · Text detect ${Math.round(textPct * 100)}% · Stories ${done ? 'ready' : 'pending'}`}</span>
          </div>
          ${done || scenes.length
            ? `<button class="btn primary wide" type="button" data-action="open-editor">${icon('arrowRight', 15)} Open Editor</button><p class="note">${running ? 'Scenes are ready. The Editor opens while the rest continues.' : 'Transcript and text detection continue in the background.'}</p>`
            : `<button class="btn primary wide" type="button" data-action="start-check" ${running ? 'disabled' : ''}>${running ? `${icon('loader', 15)} Checking…` : 'Start Check'}</button><p class="note">${running ? 'Scenes first. The Editor opens while the rest continues.' : 'Local only. Nothing leaves this Mac.'}</p>`}
          ${done ? `<button class="btn wide" type="button" data-action="start-check">${icon('loader', 14)} Re-check</button>` : ''}
        </div>
      </aside>
    </div>
  </main>`;
}

function stagePct(name) {
  const check = state.check || {};
  if (check.state === 'done') return 1;
  const p = Math.max(0, Math.min(1, Number(check.progress) || 0));
  const stage = String(check.stage || '').toLowerCase();
  if (name === 'scenes') return Math.min(1, p / 0.18);
  if (name === 'transcript') {
    if (['speech', 'scoring', 'stories', 'check', 'done'].some((item) => stage.includes(item))) return Math.min(1, Math.max(0.12, (p - 0.30) / 0.48));
    return 0;
  }
  if (name === 'text') {
    if (['vision', 'crop', 'scoring', 'stories', 'check', 'done'].some((item) => stage.includes(item))) return Math.min(1, Math.max(0.12, (p - 0.24) / 0.48));
    return 0;
  }
  if (name === 'stories') return p >= 0.74 ? Math.min(1, (p - 0.74) / 0.24) : 0;
  return 0;
}

function stageRow(key, title, sub, pct, done) {
  const p = Math.round(Math.max(0, Math.min(1, pct)) * 100);
  return `<div class="stage-row" data-stage="${key}">
    <span class="stage-icon ${done ? 'done' : p > 0 ? 'doing' : ''}">${done ? icon('check', 12) : p > 0 ? icon('loader', 12) : icon('circle', 12)}</span>
    <div><div class="stage-title">${esc(title)}</div><div class="stage-sub">${esc(sub)}</div><div class="progress"><span style="width:${p}%"></span></div></div>
    <span class="stage-pct">${p}%</span>
  </div>`;
}

function checkStage(key, title, sub, pct, done) {
  const p = Math.round(Math.max(0, Math.min(1, pct)) * 100);
  return `<div class="check-stage" data-stage="${key}">
    <span class="stage-icon ${done ? 'done' : p > 0 ? 'doing' : ''}">${done ? icon('check', 13) : p > 0 ? icon('loader', 13) : icon('circle', 13)}</span>
    <div><div class="stage-title">${esc(title)}</div><div class="stage-sub">${esc(sub)}</div><div class="progress"><span style="width:${p}%"></span></div></div>
    <span class="stage-pct">${done ? 'Done' : p > 0 ? `${p}%` : 'Pending'}</span>
  </div>`;
}

function sceneTile(scene, index) {
  const active = index === state.selectedScene;
  return `<button class="scene-tile${active ? ' is-active' : ''}" type="button" data-action="select-scene" data-index="${index}">
    <span class="thumb"><img src="${frameUrl(sceneMid(scene))}" alt=""><span class="tc">${fmtTC(scene.start, state.check?.result?.meta?.fps || 24)}</span></span>
    <span class="scene-label">${pad(index + 1)} · ${fmtDuration((scene.end || 0) - (scene.start || 0))}</span>
  </button>`;
}

/* ------------------------------------------------------------------ editor */

function screenEditor() {
  const scenes = getScenes();
  const stories = getStories();
  const scene = currentScene();
  if (!scene) return emptyEditor();
  const layers = sceneLayers(scene);
  const layer = layers.find((item) => item.id === state.selectedLayerId) || layers[0] || null;
  const segments = segmentsForScene(scene);
  const cleanCount = sceneCleanCount(scenes);
  const checking = ['queued', 'running', 'cancelling'].includes(state.check?.state);
  const clip = clipForScene(scene, state.selectedScene);
  const clipIndex = clipIndexForScene(scene, state.selectedScene);
  const clipStart = Number(clip?.start ?? scene.start ?? 0);
  const clipEnd = Number(clip?.end ?? scene.end ?? 0);
  const strip = Array.from({ length: 6 }, (_unused, at) => clipStart + (at + 0.5) * (clipEnd - clipStart) / 6);
  const playhead = clipEnd > clipStart ? Math.max(0, Math.min(1, (state.previewTime - clipStart) / (clipEnd - clipStart))) : 0;
  return `<main class="screen">
    <div class="workspace edit">
      <aside class="panel proof-panel">
        <div class="panel-head"><h2>Scenes</h2><span class="meta">${scenes.length} scenes</span></div>
        <div class="proof-tabs">
          <button class="proof-tab${state.proofTab === 'scenes' ? ' is-active' : ''}" type="button" data-action="proof-tab" data-tab="scenes">Scenes ${scenes.length}</button>
          <button class="proof-tab${state.proofTab === 'stories' ? ' is-active' : ''}" type="button" data-action="proof-tab" data-tab="stories">Stories ${stories.length}</button>
        </div>
        <div class="proof-list">
          ${state.proofTab === 'stories' ? storyProofRows(stories) : sceneProofRows(scenes)}
        </div>
      </aside>

      <section class="editor-center">
        ${checking ? `<div class="check-banner">${icon('loader', 14)} Check is still running. Transcript and clean layers appear as they finish. Scenes are safe to review now.</div>` : ''}
        <section class="panel preview-block">
          <div class="media-card" style="height:min(48vh, 460px)">
            <video data-preview controls preload="metadata" poster="${frameUrl(state.previewTime || scene.start)}" src="${sourceUrl()}"></video><span class="media-badge right">${mediaResolution()}</span>
            <div class="media-overlay"><span class="tc">${fmtTC(state.previewTime || scene.start)} / ${fmtTC(state.edit?.end || state.check?.result?.meta?.duration || 0)}</span><span class="spacer"></span></div>
          </div>
        </section>

        <section class="panel transcript-panel">
          <div class="transcript-head"><h3>Transcript</h3><span class="small muted">${segments.length} lines in this scene</span></div>
          <div class="transcript-list">
            ${segments.length ? segments.map((segment, index) => transcriptRow(segment, index)).join('') : '<div class="transcript-empty">Transcript is still running. Keep cutting; lines appear here when ready.</div>'}
          </div>
        </section>

        <section class="panel fine-trim">
          <div class="fine-head"><strong>Fine trim</strong><span class="mono">${fmtTC(clipStart, state.check?.result?.meta?.fps || 24)} – ${fmtTC(clipEnd, state.check?.result?.meta?.fps || 24)}</span><span class="muted">· ${fmtDuration(clipEnd - clipStart)}</span><button class="btn small" type="button" data-action="trim-apply" data-clip="${clipIndex}" ${clipIndex >= 0 ? '' : 'disabled'}>Apply</button></div>
          <div class="fine-controls">
            <label class="field"><span>In</span><input id="trim-in" type="number" step="0.05" min="0" value="${clipStart.toFixed(2)}" aria-label="Scene in point"></label>
            <label class="field"><span>Out</span><input id="trim-out" type="number" step="0.05" min="0" value="${clipEnd.toFixed(2)}" aria-label="Scene out point"></label>
          </div>
          <div class="fine-strip">
            ${strip.map((when) => `<button type="button" class="fine-frame" data-action="seek" data-time="${when.toFixed(3)}"><img src="${frameUrl(when)}" alt=""></button>`).join('')}
            <span class="fine-playhead" style="left:${(playhead * 100).toFixed(2)}%"></span>
          </div>
          <p class="fine-note">Trim this scene's clip. Proofs use the new range; regenerate captions after a trim.</p>
        </section>
      </section>

      <aside class="panel inspector">
        <div class="inspector-head">
          <h2 class="inspector-title">Scene ${pad(state.selectedScene + 1)} · ${esc(truncate(sceneTitle(scene, state.selectedScene), 32))}</h2>
          <p class="inspector-sub">${fmtTC(scene.start, state.check?.result?.meta?.fps || 24)} – ${fmtTC(scene.end, state.check?.result?.meta?.fps || 24)} · ${fmtDuration((scene.end || 0) - (scene.start || 0))}</p>
        </div>
        <div class="tabs">
          ${['clean', 'captions', 'voice'].map((tab) => `<button class="tab${state.inspectorTab === tab ? ' is-active' : ''}" type="button" data-action="inspector-tab" data-tab="${tab}">${tab[0].toUpperCase() + tab.slice(1)}</button>`).join('')}
        </div>
        <div class="inspector-body">
          ${state.inspectorTab === 'clean' ? inspectorClean(scene, layer, layers) : state.inspectorTab === 'captions' ? inspectorCaptions(scene) : inspectorVoice()}
          <div class="render-strip">
            <div class="panel-head" style="padding:0 0 4px"><h3 style="font-size:11px">Render queue</h3><span class="meta">${queueActiveCount()} active</span></div>
            ${state.queue.slice(0, 3).map((item) => `<div class="render-row"><span class="state-dot ${item.state === 'done' ? 'green' : ['running', 'rendering', 'queued', 'paused'].includes(item.state) ? 'amber' : ''}"></span><span>${esc(item.title || 'Render')}</span><span class="render-time">${item.state === 'done' ? 'Done' : queueLabel(item.state)}</span></div>`).join('') || '<p class="small muted">No renders yet.</p>'}
          </div>
        </div>
      </aside>
    </div>
  </main>`;
}

function emptyEditor() {
  return `<main class="screen"><div class="workspace edit"><section class="panel" style="grid-column:1/-1;padding:42px;text-align:center">
    <h1 style="margin:0 0 6px;font-size:24px;letter-spacing:-.03em">Scenes are not ready yet.</h1>
    <p class="muted">Check cuts the video into scenes first. The Editor opens as soon as they exist.</p>
    <button class="btn primary" type="button" data-action="nav" data-screen="check">${icon('arrowLeft', 15)} Back to Check</button>
  </section></div></main>`;
}

function sceneProofRows(scenes) {
  if (!scenes.length) return '<div class="proof-empty">No scenes yet.</div>';
  return scenes.map((scene, index) => {
    const layers = sceneLayers(scene);
    const status = cleanState(scene);
    return `<button class="proof-row${index === state.selectedScene ? ' is-active' : ''}" type="button" data-action="select-scene" data-index="${index}">
      <span class="proof-index">${pad(index + 1)}</span>
      <span class="proof-main">
        <span class="proof-title">${esc(truncate(sceneTitle(scene, index), 42))}</span>
        <span class="proof-sub">${fmtTC(scene.start)} – ${fmtTC(scene.end)}</span>
        <span class="proof-meta"><span class="${status === 'Layered' ? 'chip green' : 'chip'}">${esc(status)}</span>${layers.length ? `· ${layers.length} layer${layers.length === 1 ? '' : 's'}` : ''}</span>
      </span>
      <span class="proof-thumbs"><img src="${frameUrl(scene.start + 0.1)}" alt=""><span class="arrow">›</span><img src="${frameUrl(Math.max(scene.start + 0.1, scene.end - 0.1))}" alt=""></span>
    </button>`;
  }).join('');
}

function storyProofRows(stories) {
  if (!stories.length) return '<div class="proof-empty">No smart stories yet. Check is still finding them.</div>';
  return stories.map((story, index) => {
    const start = Number(story.start || 0);
    const end = Number(story.end || 0);
    const sceneIndex = Math.max(0, getScenes().findIndex((scene) => Number(scene.end || 0) > start));
    return `<button class="proof-row${sceneIndex === state.selectedScene ? ' is-active' : ''}" type="button" data-action="select-story" data-index="${index}" data-scene="${sceneIndex}">
      <span class="proof-index">${pad(index + 1)}</span>
      <span class="proof-main">
        <span class="proof-title">${esc(story.title || truncate(story.hook?.text || 'Story', 42))}</span>
        <span class="proof-sub">${fmtTC(start)} – ${fmtTC(end)}</span>
        <span class="proof-meta">${fmtDuration(end - start)} · <span class="chip">Story</span></span>
      </span>
      <span class="proof-thumbs"><img src="${frameUrl(start + 0.1)}" alt=""><span class="arrow">›</span><img src="${frameUrl(Math.max(start + 0.1, end - 0.2))}" alt=""></span>
    </button>`;
  }).join('');
}

function segmentsForScene(scene) {
  if (!scene) return [];
  const start = Number(scene.start || 0);
  const end = Number(scene.end || 0);
  return getSegments().filter((segment) => Number(segment.start || 0) < end && Number(segment.end || 0) > start);
}

function transcriptRow(segment, index) {
  const active = Number(segment.start || 0) <= state.previewTime && Number(segment.end || 0) > state.previewTime;
  return `<button class="transcript-row${active ? ' is-active' : ''}" type="button" data-action="seek" data-time="${Number(segment.start || 0).toFixed(3)}">
    <span class="tc">${fmtTC(segment.start, state.check?.result?.meta?.fps || 24)}</span>
    <span class="transcript-speaker">Speaker</span>
    <span class="transcript-text">${esc(segment.text || '')}</span>
    <span class="row-more">${icon('more', 14)}</span>
  </button>`;
}

function layerListMarkup(active, layers, emptyText = 'No text detected in this scene.') {
  const visible = state.showAllLayers ? layers : layers.slice(0, 6);
  return `<div class="layer-list${state.showAllLayers ? ' is-expanded' : ''}">
    ${layers.length ? visible.map((item, index) => `<button class="layer-row${item.id === active?.id ? ' is-active' : ''}" type="button" data-action="select-layer" data-layer="${esc(item.id)}">
      <span class="eye">${item.enabled === false ? icon('eyeOff', 14) : icon('eye', 14)}</span>
      <span class="layer-name" title="${esc(item.text_sample || '')}">${esc(layerLabel(item, index))}</span>
      <span class="layer-kind">${esc(layerState(item))}</span>
    </button>`).join('') : `<p class="small muted">${esc(emptyText)}</p>`}
  </div>
  ${layers.length > 6 ? `<button class="btn small wide" type="button" data-action="toggle-layers">${state.showAllLayers ? 'Show fewer layers' : `Show all ${layers.length} layers`}</button>` : ''}`;
}

function inspectorClean(scene, layer, layers) {
  if (!state.edit) return `<p class="small muted">Editor data is still loading. Clean controls appear when Check finishes.</p>`;
  return `<div class="proof-pair">
    <figure><div class="frame"><img src="${frameUrl(sceneMid(scene))}" alt=""></div><figcaption>Before</figcaption></figure>
    <span class="arrow">${icon('chevronRight', 14)}</span>
    <figure><div class="frame">${sceneLayers(scene).length ? cleanImg(cleanPreviewUrl(sceneMid(scene)), 'After', frameUrl(sceneMid(scene))) : `<img src="${frameUrl(sceneMid(scene))}" alt="">`}</div><figcaption>After</figcaption></figure>
  </div>
  <div class="segmented">
    ${['fill', 'blur', 'exclude'].map((action) => {
      const label = action === 'exclude' ? 'Off' : action[0].toUpperCase() + action.slice(1);
      const active = layer && ((action === 'fill' && layer.enabled !== false && layer.kind === 'fill') || (action === 'blur' && layer.enabled !== false && layer.kind === 'blur') || (action === 'exclude' && layer.enabled === false));
      return `<button class="${active ? 'is-active' : ''}" type="button" data-action="clean-action" data-layer="${esc(layer?.id || '')}" data-kind="${action}" ${layer ? '' : 'disabled'}>${label}</button>`;
    }).join('')}
  </div>
  ${layerListMarkup(layer, layers)}
  <div class="model-line"><span class="dot"></span><strong>AI fill · ready</strong><span>Local fill</span></div>
  <button class="btn primary wide" type="button" data-action="nav" data-screen="preview">${icon('play', 14)} Preview before / after</button>
  <button class="btn wide" type="button" data-action="nav" data-screen="clean">${icon('sparkle', 14)} Clean focus</button>`;
}

function inspectorCaptions(scene) {
  const track = state.edit?.captions;
  const cues = (track?.cues || []).filter((cue) => Number(cue.end || 0) > Number(scene.start || 0) && Number(cue.start || 0) < Number(scene.end || 0));
  return `<div class="toggle-row"><span>Burn into render</span><label class="switch"><input type="checkbox" data-action="caption-burn" ${track?.burn ? 'checked' : ''}><i></i></label></div>
  <div class="field"><label>Style</label><select data-action="caption-style">
    ${['clean', 'bold', 'minimal'].map((value) => `<option value="${value}" ${track?.style === value ? 'selected' : ''}>${value[0].toUpperCase() + value.slice(1)}</option>`).join('')}
  </select></div>
  <div class="field"><label>Position</label><select data-action="caption-position">
    ${['bottom', 'middle', 'top'].map((value) => `<option value="${value}" ${track?.position === value ? 'selected' : ''}>${value[0].toUpperCase() + value.slice(1)}</option>`).join('')}
  </select></div>
  ${track ? `<div class="layer-list${state.showAllCues ? ' is-expanded' : ''}">${(state.showAllCues ? cues : cues.slice(0, 6)).map((cue) => `<label class="field"><span class="small muted mono">${fmtTC(cue.start, 24)}</span><input type="text" value="${esc(cue.text || '')}" data-action="cue-save" data-cue="${esc(cue.id)}"></label>`).join('')}</div>` : `<p class="small muted">No captions yet. Generate from the transcript.</p>`}
  ${cues.length > 6 ? `<button class="btn small wide" type="button" data-action="toggle-cues">${state.showAllCues ? 'Show fewer cues' : `Show all ${cues.length} cues`}</button>` : ''}
  <button class="btn primary wide" type="button" data-action="caption-generate">${icon('captions', 14)} ${track ? 'Regenerate captions' : 'Generate captions'}</button>
  ${track ? `<button class="btn wide" type="button" data-action="download-captions">${icon('download', 14)} Download SRT</button>` : ''}`;
}

function inspectorVoice() {
  const voice = state.edit?.voice;
  return `<div class="field"><label>Local voice</label><select data-action="voice-select">
    ${state.voices.length ? state.voices.slice(0, 120).map((item) => `<option value="${esc(item.name)}" ${item.name === state.voiceName ? 'selected' : ''}>${esc(item.name)} · ${esc(item.locale)}</option>`).join('') : `<option>${esc(state.voiceName)}</option>`}
  </select></div>
  <div class="field"><label>Mode</label><select data-action="voice-mode">
    <option value="voice_over" ${state.voiceMode === 'voice_over' ? 'selected' : ''}>Voice over original</option>
    <option value="voice_only" ${state.voiceMode === 'voice_only' ? 'selected' : ''}>Voice only</option>
  </select></div>
  ${voice ? `<div class="ready-row"><span class="ready-icon">${icon('check', 12)}</span><span class="ready-main"><strong>${esc(voice.voice)}</strong><span>${voice.mode === 'voice_only' ? 'Voice only' : 'Voice over original'}</span></span></div>` : '<p class="small muted">No voice-over yet. Captions are the script.</p>'}
  <button class="btn primary wide" type="button" data-action="voice-generate">${icon('voice', 14)} ${voice ? 'Regenerate voice-over' : 'Generate voice-over'}</button>
  ${voice ? `<button class="btn wide" type="button" data-action="voice-preview">${icon('play', 14)} Preview voice</button>` : ''}`;
}

/* ------------------------------------------------------------------ clean */

function screenClean() {
  const scenes = getScenes();
  const scene = currentScene();
  if (!scene) return emptyEditor();
  const layers = sceneLayers(scene);
  const layer = layers.find((item) => item.id === state.selectedLayerId) || layers[0] || null;
  const checked = sceneCleanCount(scenes);
  const detectPct = Math.round(stagePct('text') * 100);
  return `<main class="screen">
    <div class="workspace clean">
      <aside class="panel">
        <div class="panel-head"><h2>Scenes</h2><span class="meta">${scenes.length} shown / ${scenes.length} total</span></div>
        <div class="clean-scene-list">
          ${scenes.map((item, index) => {
            const status = cleanState(item);
            const hasProof = state.previewCache.has(item.id);
            const cleaning = state.previewStatus.get(item.id) === 'cleaning';
            const failed = state.previewStatus.get(item.id) === 'failed';
            return `<button class="clean-scene${index === state.selectedScene ? ' is-active' : ''}" type="button" data-action="select-scene" data-index="${index}">
              <img src="${state.previewCache.get(item.id) || frameUrl(sceneMid(item))}" alt="">
              <span><span class="clean-scene-title">${esc(truncate(sceneTitle(item, index), 30))}</span><span class="clean-scene-sub">${fmtTime(item.start)} – ${fmtTime(item.end)}</span></span>
              <span class="chip ${failed ? 'red' : cleaning ? 'amber' : status === 'Layered' ? 'green' : ''}">${failed ? 'Failed' : cleaning ? 'Cleaning' : hasProof ? 'Proof' : status === 'Layered' ? 'Layered' : status}</span>
            </button>`;
          }).join('')}
        </div>
      </aside>

      <section style="display:grid;gap:14px;min-width:0">
        <section class="panel" style="overflow:hidden">
          ${splitStage(scene, { showCleaning: true, useCleanUrl: false })}
        </section>
        <section class="panel clean-scene-strip">
          <div class="scene-strip-head"><h3>Scene strip · clean status</h3><span class="small muted">${checked}/${scenes.length} layered</span>${sceneStripControls('clean-scenes')}</div>
          <div class="scene-strip" id="clean-scenes">
            ${scenes.map((item, index) => {
              const status = cleanState(item);
              return `<button class="scene-tile${index === state.selectedScene ? ' is-active' : ''}" type="button" data-action="select-scene" data-index="${index}">
                <span class="thumb"><img src="${state.previewCache.get(item.id) || frameUrl(sceneMid(item))}" alt=""><span class="tc">${pad(index + 1)}</span></span>
                <span class="scene-label">${state.previewCache.has(item.id) ? 'Proof' : status === 'Layered' ? 'Layered' : status}</span>
              </button>`;
            }).join('')}
          </div>
        </section>
      </section>

      <aside class="panel inspector">
        <div class="panel-head"><h2>Clean</h2><span class="meta">${checked}/${scenes.length} layered</span></div>
        <div class="inspector-body">
          <div class="field"><div class="toggle-row"><span class="small muted">Text detect</span><strong class="mono small">${detectPct}%</strong></div><div class="progress"><span style="width:${detectPct}%"></span></div></div>
          <div class="proof-pair">
            <figure><div class="frame"><img src="${frameUrl(sceneMid(scene))}" alt=""></div><figcaption>Before</figcaption></figure>
            <span class="arrow">${icon('chevronRight', 14)}</span>
            <figure><div class="frame"><img src="${afterFrameUrl(scene)}" alt=""></div><figcaption>${state.previewCache.has(scene.id) ? 'After' : 'After · cleaning…'}</figcaption></figure>
          </div>
          <div class="segmented">
            ${['fill', 'blur', 'exclude'].map((action) => {
              const label = action === 'exclude' ? 'Off' : action[0].toUpperCase() + action.slice(1);
              const active = layer && ((action === 'fill' && layer.enabled !== false && layer.kind === 'fill') || (action === 'blur' && layer.enabled !== false && layer.kind === 'blur') || (action === 'exclude' && layer.enabled === false));
              return `<button class="${active ? 'is-active' : ''}" type="button" data-action="clean-action" data-layer="${esc(layer?.id || '')}" data-kind="${action}" ${layer ? '' : 'disabled'}>${label}</button>`;
            }).join('')}
          </div>
          ${layerListMarkup(layer, layers, 'No text detected in this scene yet.')}
          <div class="model-line"><span class="dot"></span><strong>AI fill · ready</strong><span>Local fill</span></div>
          ${checked === scenes.length
            ? `<button class="btn primary wide" type="button" data-action="nav" data-screen="preview">${icon('play', 15)} Preview clean</button><button class="btn wide" type="button" data-action="clean-all">${icon('sparkle', 14)} Clean all scenes</button>`
            : `<button class="btn primary wide" type="button" data-action="clean-all">${icon('sparkle', 15)} Clean all scenes</button><button class="btn wide" type="button" data-action="nav" data-screen="preview">${icon('play', 14)} Preview</button>`}
          <button class="btn wide" type="button" data-action="nav" data-screen="edit">${icon('arrowLeft', 14)} Back to Edit</button>
        </div>
      </aside>
    </div>
  </main>`;
}

function splitStage(scene, { showCleaning = false, useCleanUrl = false } = {}) {
  const view = state.previewView || 'compare';
  if (!scene) return '';
  if (state.inlinePlaying) {
    return `<div class="split-stage inline-player" style="aspect-ratio:${mediaAspect()};min-height:380px">
      <video data-inline-player data-start="${Number(scene.start || 0).toFixed(3)}" controls autoplay playsinline poster="${frameUrl(sceneMid(scene))}" src="${sourceUrl()}"></video>
      <button class="btn small inline-close" type="button" data-action="close-inline-player">${icon('arrowLeft', 12)} Back to proof</button>
    </div>`;
  }
  const status = state.previewStatus.get(scene.id) || 'pending';
  const cached = state.previewCache.get(scene.id);
  const after = cached || (useCleanUrl && sceneLayers(scene).length ? cleanPreviewUrl(sceneMid(scene)) : frameUrl(sceneMid(scene)));
  const blurred = showCleaning && status !== 'ready' && status !== 'failed';
  const ready = state.previewStatus.get(scene.id) === 'ready';
  const scenes = getScenes();
  const readyCount = scenes.filter((item) => state.previewStatus.get(item.id) === 'ready').length;
  const afterMarkup = useCleanUrl && !cached && sceneLayers(scene).length
    ? cleanImg(cleanPreviewUrl(sceneMid(scene)), 'After', frameUrl(sceneMid(scene)))
    : `<img src="${after}" alt="After">`;
  const beforeMarkup = `<img src="${frameUrl(sceneMid(scene))}" alt="Before">`;
  const cleaningMarkup = showCleaning && blurred ? `<span class="cleaning-pill"><span class="dot"></span>Cleaning ${readyCount}/${scenes.length}</span>` : '';
  const overlay = `<div class="media-overlay"><button type="button" data-action="play-source" aria-label="Play source">${icon('play', 14)}</button><span class="tc">${fmtTC(scene.start, 24)} – ${fmtTC(scene.end, 24)}</span><span class="spacer"></span><span class="small" style="opacity:.82">${esc(cleanState(scene))}</span></div>`;
  if (view === 'before') {
    return `<div class="split-stage" data-split="0" style="aspect-ratio:${mediaAspect()};min-height:380px">${beforeMarkup}<span class="split-tag before">Before</span>${overlay}</div>`;
  }
  if (view === 'after') {
    return `<div class="split-stage" data-split="0" style="aspect-ratio:${mediaAspect()};min-height:380px"><div class="after-layer${blurred ? ' is-cleaning' : ''}">${afterMarkup}</div><span class="split-tag after">After</span>${cleaningMarkup}${overlay}</div>`;
  }
  return `<div class="split-stage" data-split="50" style="aspect-ratio:${mediaAspect()};min-height:380px">
    ${beforeMarkup}
    <div class="after-layer${blurred ? ' is-cleaning' : ''}">${afterMarkup}</div>
    <span class="split-tag before">Before</span>
    <span class="split-tag after">After</span>
    <span class="split-handle" aria-hidden="true"></span>
    ${cleaningMarkup}
    ${overlay}
  </div>`;
}

function mediaResolution() {
  const meta = state.check?.result?.meta || state.edit?.source || state.sourceMeta || {};
  const width = Number(meta.width || 0);
  const height = Number(meta.height || 0);
  return width && height ? `${width}×${height}` : '';
}

function mediaAspect() {
  const meta = state.check?.result?.meta || state.edit?.source || state.sourceMeta || {};
  const width = Number(meta.width || 0);
  const height = Number(meta.height || 0);
  return width && height ? `${width} / ${height}` : '16 / 9';
}

/* ------------------------------------------------------------------ preview */

function screenPreview() {
  const scenes = getScenes();
  const scene = currentScene();
  if (!scene) return emptyEditor();
  const ready = scenes.filter((item) => state.previewStatus.get(item.id) === 'ready').length;
  const status = state.previewStatus.get(scene.id) || 'pending';
  return `<main class="screen">
    <div class="workspace preview">
      <section class="preview-main">
        <section class="panel preview-stage" style="overflow:hidden">
          ${splitStage(scene, { showCleaning: true, useCleanUrl: false })}
        </section>
        <section class="panel preview-scenes">
          <div class="scene-strip-head"><h3>Scenes · ${scenes.length} total</h3><span class="small muted">${ready}/${scenes.length} proofs</span>${sceneStripControls('preview-scenes')}</div>
          <div class="scene-strip" id="preview-scenes">
            ${scenes.map((item, index) => {
              const itemStatus = state.previewStatus.get(item.id) || 'pending';
              return `<button class="scene-tile${index === state.selectedScene ? ' is-active' : ''}" type="button" data-action="select-scene" data-index="${index}">
                <span class="thumb"><img src="${state.previewCache.get(item.id) || frameUrl(sceneMid(item))}" alt=""><span class="tc">${pad(index + 1)}</span></span>
                <span class="scene-label">${previewStatusLabel(itemStatus)}</span>
              </button>`;
            }).join('')}
          </div>
        </section>
      </section>

      <aside class="preview-side">
        <section class="panel preview-status-card">
          <div class="preview-thumb"><img src="${frameUrl(sceneMid(scene))}" alt=""><div><h3>Scene ${pad(state.selectedScene + 1)}</h3><p>${fmtTC(scene.start)} – ${fmtTC(scene.end)} · ${fmtDuration((scene.end || 0) - (scene.start || 0))}</p></div></div>
          <div class="panel-rule" style="margin:12px 0"></div>
          <div class="ready-row"><span class="ready-icon" style="${status === 'ready' ? '' : 'background:var(--amber-soft);color:var(--amber-ink)'}">${status === 'ready' ? icon('check', 12) : icon('loader', 12)}</span><span class="ready-main"><strong>${status === 'ready' ? 'Proof generated' : status === 'failed' ? 'Clean failed' : 'Cleaning…'}</strong><span>${status === 'ready' ? 'Review the before / after' : 'Building a proof frame from this scene.'}</span></span></div>
        </section>

        <section class="panel preview-actions">
          <div class="panel-head" style="padding-bottom:8px"><h2>Preview</h2><span class="meta">${ready}/${scenes.length}</span></div>
          <div class="panel-pad" style="padding-top:0;display:grid;gap:9px">
            <div class="segmented">
              ${['before', 'compare', 'after'].map((view) => `<button class="${state.previewView === view ? 'is-active' : ''}" type="button" data-action="preview-view" data-view="${view}">${view[0].toUpperCase() + view.slice(1)}</button>`).join('')}
            </div>
            <div class="toggle-row"><span>Current scene first</span><span class="small muted">Always</span></div>
            <button class="btn wide" type="button" data-action="preview-reclean">${icon('loader', 14)} Re-clean this scene</button>
            <button class="btn wide" type="button" data-action="clean-all">${icon('sparkle', 14)} Clean all</button>
            ${status === 'failed' ? `<p class="small" style="color:var(--red)">This scene failed. Retry before render.</p>` : ''}
          </div>
        </section>

        <section class="panel readiness">
          <div class="readiness-head"><strong>Readiness</strong><span>${ready} / ${scenes.length} proofs</span></div>
          <div class="progress"><span style="width:${scenes.length ? (ready / scenes.length) * 100 : 0}%"></span></div>
          <p class="readiness-note">${ready === scenes.length ? 'All scenes have a proof. Review before render.' : 'Rendering stays blocked until each scene is ready or explicitly set to Off.'}</p>
        </section>

        <button class="btn primary wide" type="button" data-action="nav" data-screen="render" style="height:46px;font-size:15px" ${sceneReadyCount(scenes) === scenes.length ? '' : 'disabled'}>${icon('play', 15)} Render</button>
      </aside>
    </div>
  </main>`;
}

function previewStatusLabel(value) {
  return ({ ready: 'Proof', cleaning: 'Cleaning…', failed: 'Failed', pending: 'Queued', queued: 'Queued' }[value] || 'Queued');
}

/* ------------------------------------------------------------------ render */

function screenRender() {
  const scenes = getScenes();
  const checked = sceneReadyCount(scenes);
  const captions = state.edit?.captions?.cues?.length ? 1 : 0;
  const voice = state.edit?.voice ? 1 : 0;
  const outputPath = state.settings?.storage?.data_root
    ? `${state.settings.storage.data_root}/exports`
    : '';
  const outputDir = 'DuckSuite Exports';
  const fps = Math.round(Number(state.edit?.source?.fps || 24));
  const sourceMeta = state.edit?.source || state.sourceMeta || {};
  const sourceW = Number(sourceMeta.width || 0);
  const sourceH = Number(sourceMeta.height || 0);
  const resolutionLabel = sourceW && sourceH ? `${sourceW} × ${sourceH}` : '1080p';
  const activeJobs = state.queue.filter((item) => ['queued', 'running', 'rendering', 'paused'].includes(item.state)).length;
  const queue = state.queue;
  return `<main class="screen">
    <div class="workspace render">
      <aside class="panel">
        <div class="panel-head"><h2>Render settings</h2></div>
        <div class="render-settings">
          <div class="render-setting"><div class="setting-head">${icon('monitor', 14)} Resolution</div><div class="readonly">1080p (${resolutionLabel})</div></div>
          <div class="render-setting"><div class="setting-head">${icon('film', 14)} Frame rate</div><select data-action="render-fps"><option>${fps || 24} fps</option><option>30 fps</option></select></div>
          <div class="render-setting"><div class="setting-head">${icon('volume', 14)} Audio mix</div><div class="readonly">${esc(state.edit?.voice ? 'Voice over + original' : 'Original audio')}</div></div>
          <div class="render-setting"><div class="setting-head">${icon('captions', 14)} Captions</div><div class="toggle-row"><span>${state.edit?.captions?.burn ? 'Burn into render' : 'Sidecar SRT'}</span><label class="switch"><input type="checkbox" data-action="caption-burn" ${state.edit?.captions?.burn ? 'checked' : ''}><i></i></label></div></div>
          <div class="render-setting"><div class="setting-head">${icon('voice', 14)} Voice-over</div><div class="toggle-row"><span>${state.edit?.voice ? 'Included' : 'None'}</span><label class="switch"><input type="checkbox" ${state.edit?.voice ? 'checked' : ''} disabled><i></i></label></div></div>
          <div class="media-rule"></div>
          <div class="render-setting"><div class="setting-head">${icon('folder', 14)} Output folder</div><div class="path-row"><span class="path" title="${esc(outputPath)}">${esc(outputDir)}</span>${outputPath ? `<button class="btn small" type="button" data-action="reveal" data-path="${esc(outputPath)}">${icon('folderOpen', 11)} Show</button>` : ''}</div></div>
          <div class="render-setting"><div class="setting-head">${icon('monitor', 14)} Disk space</div><div class="small muted">${state.settings?.storage?.free_bytes ? `${fmtBytes(state.settings.storage.free_bytes)} free` : 'Local storage'}</div></div>
        </div>
      </aside>

      <section class="panel render-queue">
        <div class="render-queue-head"><h2>Render queue · ${queue.length} ${queue.length === 1 ? 'job' : 'jobs'}</h2><div style="display:flex;gap:6px">${queue.some((item) => ['done', 'failed', 'cancelled'].includes(item.state)) ? `<button class="btn small" type="button" data-action="clear-queue">Clear finished</button>` : ''}${state.queuePaused ? `<button class="btn small" type="button" data-action="resume-queue">${icon('play', 12)} Resume</button>` : activeJobs ? `<button class="btn small" type="button" data-action="pause-queue">${icon('pause', 12)} Pause</button>` : `<button class="btn small" type="button" disabled>Queue idle</button>`}</div></div>
        <div class="queue-head-row"><span>Project / Story</span><span>Edit</span><span>Duration</span><span>Resolution</span><span>State</span><span>Progress</span><span>Output</span></div>
        ${queue.length ? queue.map((item) => renderQueueRow(item)).join('') : '<div class="queue-empty">No jobs yet. Start a render from Preview.</div>'}
      </section>

      <aside class="render-ready">
        <section class="panel render-ready" style="border:0;box-shadow:none;padding:0;background:transparent">
          <div class="panel-head" style="padding:0 0 2px"><h2>Ready</h2><span class="meta">${checked}/${scenes.length}</span></div>
          <div class="ready-card">
            <div class="ready-row"><span class="ready-icon">${icon('check', 12)}</span><span class="ready-main"><strong>${checked} / ${scenes.length} scenes ready</strong><span>${checked === scenes.length ? 'Review proofs before render' : 'Some scenes still need a decision'}</span></span></div>
            <div class="ready-row"><span class="ready-icon">${icon('check', 12)}</span><span class="ready-main"><strong>Captions</strong><span>${captions ? '1 track' : 'None'}</span></span></div>
            <div class="ready-row"><span class="ready-icon">${icon('check', 12)}</span><span class="ready-main"><strong>Voice</strong><span>${voice ? '1 track' : 'None'}</span></span></div>
            <div class="ready-row"><span class="ready-icon" style="background:var(--paper-2);color:var(--muted)">${icon('clock', 12)}</span><span class="ready-main"><strong>Render</strong><span>Local · 1080p · H.264</span></span></div>
          </div>
          <button class="btn primary wide start" type="button" data-action="start-render" ${checked === scenes.length ? '' : 'disabled'}>${icon('play', 16)} Start render</button>
          <div class="ready-card"><div class="ready-row"><span class="ready-icon" style="background:var(--paper-2);color:var(--muted)">${icon('folder', 12)}</span><span class="ready-main"><strong>Output</strong><span class="output-path" title="${esc(outputPath)}">${esc(outputDir)}</span></span></div></div>
        </section>
      </aside>
    </div>
  </main>`;
}

function renderQueueRow(item) {
  const pct = Math.round((Number(item.progress) || 0) * 100);
  const active = item.state === 'running' || item.state === 'rendering' || item.state === 'queued' || item.state === 'paused';
  const duration = item.duration ? fmtDuration(item.duration) : (item.edit_id === state.edit?.id ? fmtDuration(state.edit?.end || 0) : '—');
  return `<div class="queue-item${active ? ' is-active' : ''}">
    <div class="queue-story"><img src="${frameUrl(0.5, item.project_id)}" alt=""><div><strong title="${esc(item.project_name || 'Project')} · ${esc(item.title || 'Render')}">${esc(item.title || 'Render')}</strong><span>${esc(item.project_name || 'Project')} · ${duration} · ${item.width && item.height ? `${item.width}×${item.height}` : '1080p'} · v1</span></div></div>
    <span class="queue-cell">v1</span>
    <span class="queue-cell">${duration}</span>
    <span class="queue-cell">${item.width && item.height ? `${item.width}×${item.height}` : '1080p'}</span>
    <span class="chip ${item.state === 'done' ? 'green' : item.state === 'failed' || item.state === 'cancelled' ? 'red' : active ? 'amber' : ''}">${esc(queueLabel(item.state))}</span>
    ${item.state === 'cancelled' ? '<div class="queue-cell">—</div>' : `<div class="queue-progress"><div class="progress"><span style="width:${pct}%"></span></div><span>${active ? `${pct}%` : item.state === 'done' ? '100%' : '—'}</span></div>`}
    <div class="queue-actions">
      ${item.state === 'done' ? `<button class="btn small" type="button" data-action="play-render" data-project="${esc(item.project_id)}" data-edit="${esc(item.edit_id)}">${icon('play', 11)} Play</button><button class="btn small" type="button" data-action="reveal" data-path="${esc(item.output || '')}">${icon('folderOpen', 11)}</button>` : ''}
      ${active ? `<button class="btn small" type="button" data-action="cancel-render" data-project="${esc(item.project_id)}" data-edit="${esc(item.edit_id)}">${icon('close', 11)} Cancel</button>` : ''}
      ${item.state === 'failed' || item.state === 'cancelled' ? `<button class="btn small" type="button" data-action="start-render" data-project="${esc(item.project_id)}" data-edit="${esc(item.edit_id)}">${icon('loader', 11)} Retry</button>` : ''}
    </div>
  </div>`;
}

/* ------------------------------------------------------------------ modal */

function openModal(html) {
  modalRoot.innerHTML = html;
  const dialog = modalRoot.querySelector('dialog');
  if (!dialog) return;
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) closeModal();
  });
  dialog.showModal();
}

function closeModal() {
  modalRoot.innerHTML = '';
}

function openVideoModal(url, title = 'Preview') {
  openModal(`<dialog class="modal" aria-label="${esc(title)}">
    <div class="modal-head"><h2>${esc(title)}</h2><button class="icon-btn" type="button" data-action="close-modal" aria-label="Close">${icon('close', 16)}</button></div>
    <div class="modal-body"><video controls autoplay src="${url}"></video></div>
  </dialog>`);
}

function openAudioModal(url, title = 'Voice-over') {
  openModal(`<dialog class="modal" aria-label="${esc(title)}">
    <div class="modal-head"><h2>${esc(title)}</h2><button class="icon-btn" type="button" data-action="close-modal" aria-label="Close">${icon('close', 16)}</button></div>
    <div class="modal-body"><audio controls autoplay style="width:100%" src="${url}"></audio></div>
  </dialog>`);
}

async function openSettings() {
  try {
    const [models, settings] = await Promise.all([
      api('/api/models').catch(() => ({ models: [] })),
      api('/api/settings').catch(() => state.settings),
    ]);
    state.models = models.models || [];
    state.settings = settings || state.settings;
  } catch (_) { /* keep current */ }
  const storage = state.settings?.storage || {};
  openModal(`<dialog class="modal" aria-label="Settings">
    <div class="modal-head"><h2>Settings</h2><button class="icon-btn" type="button" data-action="close-modal" aria-label="Close">${icon('close', 16)}</button></div>
    <div class="modal-body">
      <div class="settings-grid">
        <section>
          <h3>Local engine</h3>
          <div class="kv"><span>Engine</span><strong>${esc(engineLabel())}</strong></div>
          <div class="kv"><span>Vision</span><strong>${state.engine?.vision?.available ? 'Ready' : 'Unavailable'}</strong></div>
          <div class="kv"><span>Speech</span><strong>${state.engine?.speech?.default || 'Auto'}</strong></div>
          <div class="kv"><span>AI fill</span><strong>${state.engine?.fill?.ready ? 'Ready' : 'Missing'}</strong></div>
          <h3 style="margin-top:10px">Models</h3>
          ${state.models.map((model) => `<div class="kv"><span>${esc(model.label || model.id)}</span><strong>${model.ready ? 'Ready' : 'Missing'} <button class="btn small" type="button" data-action="verify-model" data-model="${esc(model.id)}">Verify</button></strong></div>`).join('') || '<p class="small muted">No models reported.</p>'}
        </section>
        <section>
          <h3>Storage</h3>
          <div class="kv"><span>Data root</span><strong class="small">${esc(storage.data_root || '—')}</strong></div>
          <div class="kv"><span>Projects</span><strong>${fmtBytes(storage.projects_bytes)}</strong></div>
          <div class="kv"><span>Models</span><strong>${fmtBytes(storage.models_bytes)}</strong></div>
          <div class="kv"><span>Free</span><strong>${fmtBytes(storage.free_bytes)}</strong></div>
          <h3 style="margin-top:10px">Footage rights</h3>
          <div class="toggle-row"><span>I own this footage or have permission to edit it</span><label class="switch"><input type="checkbox" checked disabled><i></i></label></div>
          <p class="small muted">Always on. Clean is for your own footage or footage you are authorized to edit. Do not use DuckSuite to remove another creator’s watermark or logo. See Terms &amp; Conditions.</p>
          <div class="kv"><span>Language</span><strong>Auto-detect only</strong></div>
          <div class="kv"><span>Version</span><strong>${esc(state.settings?.version || '1.0.0')}</strong></div>
        </section>
      </div>
    </div>
  </dialog>`);
}

/* ------------------------------------------------------------------ import */

async function triggerImport() {
  if (state.importing) return;
  if (window.webkit?.messageHandlers?.duck) {
    window.webkit.messageHandlers.duck.postMessage({ type: 'import' });
    toast('Choose a video in the Mac file panel.');
    return;
  }
  document.querySelector('#file-input')?.click();
}

async function handleFile(file) {
  if (!file || state.importing) return;
  state.importing = true;
  toast(`Importing ${file.name}…`);
  try {
    const response = await fetch('/api/projects/upload', {
      method: 'POST',
      headers: { Authorization: `Bearer ${state.token}`, 'X-Filename': file.name },
      body: file,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
    const data = await response.json();
    await loadProjects();
    navigate(`project/${data.project.id}/check`);
    toast('Imported. Check starts with scenes first.');
  } catch (error) {
    toast(`Import failed: ${error.message}`, 'bad');
  } finally {
    state.importing = false;
  }
}

/* ------------------------------------------------------------------ preview cleaning */

function prioritizeScenes(scenes) {
  if (!scenes.length) return [];
  const index = Math.min(state.selectedScene, scenes.length - 1);
  return [...scenes.slice(index), ...scenes.slice(0, index)];
}

async function startPreviewClean(forceSceneId = '') {
  if (state.previewRunning || !state.edit) return;
  const scenes = getScenes();
  if (!scenes.length) return;
  if (!state.edit.clean?.length) {
    try {
      const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/from-check`, { method: 'POST' });
      state.edit = data.edit;
      state.cleanVersion += 1;
    } catch (error) {
      toast(`Clean could not start: ${error.message}`, 'bad');
      return;
    }
  }
  state.previewRunning = true;
  state.previewRun += 1;
  const run = state.previewRun;
  const order = forceSceneId ? scenes.filter((scene) => scene.id === forceSceneId) : prioritizeScenes(scenes);
  for (const scene of order) {
    if (run !== state.previewRun) break;
    if (!forceSceneId && state.previewCache.has(scene.id)) {
      state.previewStatus.set(scene.id, 'ready');
      continue;
    }
    state.previewStatus.set(scene.id, 'cleaning');
    updatePreviewUI();
    try {
      const url = cleanPreviewUrl(sceneMid(scene));
      const blob = await enqueueCleanFetch(url);
      if (run !== state.previewRun) break;
      const dataUrl = await blobToDataUrl(blob);
      state.previewCache.set(scene.id, dataUrl);
      state.previewStatus.set(scene.id, 'ready');
    } catch (error) {
      state.previewStatus.set(scene.id, 'failed');
    }
    updatePreviewUI();
  }
  if (run === state.previewRun) state.previewRunning = false;
  updatePreviewUI();
}

function updatePreviewUI() {
  if (state.screen === 'preview' || state.screen === 'clean') render();
}

/* ------------------------------------------------------------------ actions */

async function cleanAction(layerId, action) {
  if (!state.project || !state.edit || !layerId) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/${encodeURIComponent(layerId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ action }),
    });
    state.edit = data.edit;
    state.cleanVersion += 1;
    const scene = currentScene();
    if (scene) {
      state.previewCache.delete(scene.id);
      state.previewStatus.set(scene.id, 'queued');
    }
    if (state.previewRunning) {
      state.previewRun += 1;
      state.previewRunning = false;
    }
    render();
    toast(`Clean set to ${action === 'exclude' ? 'Off' : action}.`);
    if (scene && ['clean', 'preview'].includes(state.screen)) startPreviewClean(scene.id);
  } catch (error) {
    toast(`Clean change failed: ${error.message}`, 'bad');
  }
}

async function clearQueue() {
  try {
    const data = await api('/api/queue/clear', { method: 'POST' });
    state.queue = data.items || [];
    state.lastQueueKey = JSON.stringify(state.queue.map((item) => [item.id, item.state]));
    render();
    toast('Finished renders cleared.');
  } catch (error) {
    toast(`Queue clear failed: ${error.message}`, 'bad');
  }
}

async function applyTrim() {
  if (!state.project || !state.edit) return;
  const index = Number(document.querySelector('[data-action="trim-apply"]')?.dataset.clip ?? -1);
  const start = Number(document.querySelector('#trim-in')?.value);
  const end = Number(document.querySelector('#trim-out')?.value);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start + 0.1) {
    toast('Out point must be at least 0.1 s after In.', 'bad');
    return;
  }
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clips/${index}`, {
      method: 'PATCH',
      body: JSON.stringify({ start, end }),
    });
    state.edit = data.edit;
    state.cleanVersion += 1;
    state.previewCache.clear();
    state.previewStatus.clear();
    render();
    toast('Scene trimmed.');
  } catch (error) {
    toast(`Trim failed: ${error.message}`, 'bad');
  }
}

async function cleanAll() {
  if (!state.project || !state.edit) {
    toast('Finish Check first.', 'bad');
    return;
  }
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/from-check`, { method: 'POST' });
    state.edit = data.edit;
    state.cleanVersion += 1;
    state.previewCache.clear();
    state.previewStatus.clear();
    render();
    toast(`${data.layers || state.edit.clean.length} clean layers ready.`);
    if (state.screen === 'preview') startPreviewClean();
  } catch (error) {
    toast(`Clean failed: ${error.message}`, 'bad');
  }
}

async function generateCaptions() {
  if (!state.project || !state.edit) {
    toast('Finish Check first.', 'bad');
    return;
  }
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/captions/generate`, { method: 'POST' });
    state.edit.captions = data.captions;
    render();
    toast('Captions generated.');
  } catch (error) {
    toast(`Captions failed: ${error.message}`, 'bad');
  }
}

async function patchCaptions(payload) {
  if (!state.project || !state.edit) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/captions`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    state.edit.captions = data.captions;
    render();
  } catch (error) {
    toast(`Caption change failed: ${error.message}`, 'bad');
  }
}

async function saveCue(cueId, text) {
  if (!state.project || !state.edit || !cueId) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/captions/cues/${encodeURIComponent(cueId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ text }),
    });
    state.edit.captions = data.captions;
    toast('Cue saved.');
  } catch (error) {
    toast(`Cue save failed: ${error.message}`, 'bad');
  }
}

async function generateVoice() {
  if (!state.project || !state.edit) {
    toast('Finish Check first.', 'bad');
    return;
  }
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/voice`, {
      method: 'POST',
      body: JSON.stringify({ voice: state.voiceName, mode: state.voiceMode }),
    });
    state.edit.voice = data.voice;
    render();
    toast(`Voice-over ready: ${data.voice.voice}.`);
  } catch (error) {
    toast(`Voice failed: ${error.message}`, 'bad');
  }
}

function previewVoice() {
  if (!state.project || !state.edit?.voice) return;
  const url = mediaUrl(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/voice/audio`);
  openAudioModal(url, 'Voice-over preview');
}

async function startRender(projectId = '', editId = '') {
  const pid = projectId || state.project?.id;
  const eid = editId || state.edit?.id;
  if (!pid || !eid) {
    toast('Nothing to render yet.', 'bad');
    return;
  }
  try {
    await api(`/api/projects/${encodeURIComponent(pid)}/edits/${encodeURIComponent(eid)}/render`, { method: 'POST' });
    await refreshQueue();
    toast('Render queued.');
    if (state.project?.id !== pid) navigate(`project/${pid}/render`);
    else render();
  } catch (error) {
    toast(`Render could not start: ${error.message}`, 'bad');
  }
}

async function cancelRender(projectId, editId) {
  try {
    await api(`/api/projects/${encodeURIComponent(projectId)}/edits/${encodeURIComponent(editId)}/render/cancel`, { method: 'POST' });
    await refreshQueue();
    toast('Render cancelled.');
  } catch (error) {
    toast(`Cancel failed: ${error.message}`, 'bad');
  }
}

async function queueAction(action) {
  try {
    await api(`/api/queue/${action}`, { method: 'POST' });
    await refreshQueue();
    toast(action === 'pause' ? 'Queue paused.' : 'Queue resumed.');
  } catch (error) {
    toast(`Queue action failed: ${error.message}`, 'bad');
  }
}

async function revealPath(path) {
  if (!path) return;
  try {
    await api('/api/reveal', { method: 'POST', body: JSON.stringify({ path }) });
  } catch (error) {
    toast(`Could not reveal: ${error.message}`, 'bad');
  }
}

function playRender(projectId, editId) {
  const url = mediaUrl(`/api/projects/${encodeURIComponent(projectId)}/edits/${encodeURIComponent(editId)}/render/file`);
  openVideoModal(url, 'Rendered story');
}

function playSource() {
  if (!state.project) return;
  state.inlinePlaying = true;
  render();
}

async function downloadCaptions() {
  if (!state.project || !state.edit) return;
  const response = await fetch(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/captions.srt`, {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (!response.ok) {
    toast('No captions to download.', 'bad');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${state.project.name || 'duck'}.srt`;
  link.click();
  URL.revokeObjectURL(url);
}


async function verifyModel(modelId) {
  try {
    const result = await api(`/api/models/${encodeURIComponent(modelId)}/verify`, { method: 'POST' });
    toast(result.ok ? 'Model verified.' : `Model check failed: ${result.error || result.expected || ''}`, result.ok ? '' : 'bad');
  } catch (error) {
    toast(`Verify failed: ${error.message}`, 'bad');
  }
}

/* ------------------------------------------------------------------ events */

app.addEventListener('click', async (event) => {
  const target = event.target.closest('[data-action]');
  if (!target) return;
  const action = target.dataset.action;
  try {
    if (action === 'welcome') navigate('welcome');
    else if (action === 'open-project') {
      const id = target.dataset.project;
      await openProject(id);
      const screen = state.check?.state === 'done' ? 'edit' : 'check';
      navigate(`project/${id}/${screen}`);
      if (state.check?.state === 'idle') await startCheck();
    } else if (action === 'import') await triggerImport();
    else if (action === 'settings') await openSettings();
    else if (action === 'close-modal') closeModal();
    else if (action === 'start-check') await startCheck();
    else if (action === 'open-editor') navigate(projectPath('edit'));
    else if (action === 'nav') navigate(projectPath(target.dataset.screen || 'edit'));
    else if (action === 'proof-tab') { state.proofTab = target.dataset.tab || 'scenes'; render(); }
    else if (action === 'inspector-tab') { state.inspectorTab = target.dataset.tab || 'clean'; render(); }
    else if (action === 'select-scene') {
      const index = Number(target.dataset.index || 0);
      const scenes = getScenes();
      state.selectedScene = Math.max(0, Math.min(index, scenes.length - 1));
      state.previewTime = Number(scenes[state.selectedScene]?.start || 0) + 0.1;
      state.selectedLayerId = '';
      state.inlinePlaying = false;
      state.showAllLayers = false;
      state.showAllCues = false;
      state.previewStatus.set(scenes[state.selectedScene]?.id, state.previewCache.has(scenes[state.selectedScene]?.id) ? 'ready' : (state.previewStatus.get(scenes[state.selectedScene]?.id) || 'pending'));
      render();
    } else if (action === 'select-story') {
      const index = Number(target.dataset.scene || 0);
      state.proofTab = 'stories';
      state.selectedScene = Math.max(0, Math.min(index, getScenes().length - 1));
      state.previewTime = Number(getStories()[Number(target.dataset.index || 0)]?.start || 0) + 0.1;
      render();
    } else if (action === 'select-layer') { state.selectedLayerId = target.dataset.layer || ''; render(); }
    else if (action === 'toggle-layers') { state.showAllLayers = !state.showAllLayers; render(); }
    else if (action === 'toggle-cues') { state.showAllCues = !state.showAllCues; render(); }
    else if (action === 'strip-scroll') {
      const strip = document.getElementById(target.dataset.target || '');
      if (strip) strip.scrollBy({ left: Number(target.dataset.dir || 1) * Math.max(180, strip.clientWidth * 0.75), behavior: 'smooth' });
    }
    else if (action === 'trim-apply') await applyTrim();
    else if (action === 'clear-queue') await clearQueue();
    else if (action === 'clean-action') await cleanAction(target.dataset.layer || '', target.dataset.kind || 'fill');
    else if (action === 'clean-all') await cleanAll();
    else if (action === 'caption-generate') await generateCaptions();
    else if (action === 'download-captions') await downloadCaptions();
    else if (action === 'voice-generate') await generateVoice();
    else if (action === 'voice-preview') previewVoice();
    else if (action === 'start-render') await startRender(target.dataset.project || '', target.dataset.edit || '');
    else if (action === 'cancel-render') await cancelRender(target.dataset.project || '', target.dataset.edit || '');
    else if (action === 'pause-queue') await queueAction('pause');
    else if (action === 'resume-queue') await queueAction('resume');
    else if (action === 'play-render') playRender(target.dataset.project || '', target.dataset.edit || '');
    else if (action === 'play-source') playSource();
    else if (action === 'close-inline-player') { state.inlinePlaying = false; render(); }
    else if (action === 'reveal') await revealPath(target.dataset.path || '');
    else if (action === 'preview-view') { state.previewView = target.dataset.view || 'compare'; render(); }
    else if (action === 'preview-reclean') {
      const scene = currentScene();
      if (scene) {
        state.previewCache.delete(scene.id);
        state.previewStatus.set(scene.id, 'queued');
        if (state.previewRunning) {
          state.previewRun += 1;
          state.previewRunning = false;
        }
        startPreviewClean(scene.id);
      }
    }
    else if (action === 'verify-model') await verifyModel(target.dataset.model || '');
    else if (action === 'seek') {
      state.previewTime = Number(target.dataset.time || 0) + 0.01;
      const video = document.querySelector('video[data-preview]');
      if (video) video.currentTime = state.previewTime;
      render();
    }
  } catch (error) {
    toast(error.message || 'Action failed.', 'bad');
  }
});

app.addEventListener('change', async (event) => {
  const target = event.target;
  if (target.id === 'file-input') {
    const file = target.files?.[0];
    target.value = '';
    await handleFile(file);
    return;
  }
  const action = target.dataset?.action;
  if (action === 'caption-burn') await patchCaptions({ burn: target.checked });
  else if (action === 'caption-style') await patchCaptions({ style: target.value });
  else if (action === 'caption-position') await patchCaptions({ position: target.value });
  else if (action === 'cue-save') await saveCue(target.dataset.cue || '', target.value);
  else if (action === 'voice-select') { state.voiceName = target.value; render(); }
  else if (action === 'voice-mode') { state.voiceMode = target.value; render(); }
});

app.addEventListener('input', (event) => {
  if (event.target.id === 'project-search') {
    state.welcomeQuery = event.target.value;
    render();
    const input = document.querySelector('#project-search');
    if (input) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
  }
});

/* ------------------------------------------------------------------ after render */

function afterRender() {
  const inline = document.querySelector('video[data-inline-player]');
  if (inline) {
    const start = Number(inline.dataset.start || 0);
    if (start > 0 && Math.abs(inline.currentTime - start) > 0.5) {
      try { inline.currentTime = start; } catch (_) { /* metadata not ready */ }
    }
    inline.play().catch(() => {});
    inline.addEventListener('timeupdate', () => { state.previewTime = inline.currentTime; }, { passive: true });
  }
  const video = document.querySelector('video[data-preview]');
  if (video) {
    if (state.previewTime > 0 && Math.abs(video.currentTime - state.previewTime) > 0.35) {
      try { video.currentTime = state.previewTime; } catch (_) { /* metadata not ready */ }
    }
    video.addEventListener('timeupdate', () => { state.previewTime = video.currentTime; }, { passive: true });
  }

  document.querySelectorAll('.split-stage').forEach((stage) => {
    const after = stage.querySelector('.after-layer');
    const handle = stage.querySelector('.split-handle');
    if (!after || !handle) return;
    let value = Number(stage.dataset.split || 50);
    const apply = (pct) => {
      value = Math.max(8, Math.min(92, pct));
      after.style.clipPath = `inset(0 0 0 ${value}%)`;
      handle.style.left = `${value}%`;
    };
    apply(value);
    const move = (event) => {
      const rect = stage.getBoundingClientRect();
      apply(((event.clientX - rect.left) / Math.max(1, rect.width)) * 100);
    };
    stage.addEventListener('pointerdown', (event) => {
      if (event.target.closest('button')) return;
      stage.setPointerCapture(event.pointerId);
      move(event);
      const up = () => {
        stage.removeEventListener('pointermove', move);
        stage.removeEventListener('pointerup', up);
      };
      stage.addEventListener('pointermove', move);
      stage.addEventListener('pointerup', up);
    });
  });

  document.querySelectorAll('img[data-clean-src]').forEach((img) => {
    if (img.dataset.loadingClean === '1' || img.dataset.loadedClean === '1') return;
    const src = img.dataset.cleanSrc;
    if (!src) return;
    img.dataset.loadingClean = '1';
    (async () => {
      try {
        const blob = await enqueueCleanFetch(src, true);
        img.src = await blobToDataUrl(blob);
        img.dataset.loadedClean = '1';
      } catch (_) {
        img.dataset.failedClean = '1';
      }
    })();
  });

  const dropzone = document.querySelector('[data-dropzone]');
  if (dropzone) {
    dropzone.addEventListener('dragover', (event) => { event.preventDefault(); dropzone.classList.add('is-over'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('is-over'));
    dropzone.addEventListener('drop', async (event) => {
      event.preventDefault();
      dropzone.classList.remove('is-over');
      const file = event.dataTransfer?.files?.[0];
      await handleFile(file);
    });
  }

  const activeTile = document.querySelector('.scene-tile.is-active');
  if (activeTile) {
    const strip = activeTile.parentElement;
    if (strip) {
      const target = activeTile.offsetLeft - strip.clientWidth / 2 + activeTile.clientWidth / 2;
      strip.scrollTo({ left: Math.max(0, target), behavior: 'smooth' });
    }
  }
}

/* ------------------------------------------------------------------ render */

function render() {
  if (!state.project && state.screen !== 'welcome') state.screen = 'welcome';
  const screen = state.screen === 'welcome'
    ? screenWelcome()
    : state.screen === 'check'
      ? screenCheck()
      : state.screen === 'edit'
        ? screenEditor()
        : state.screen === 'clean'
          ? screenClean()
          : state.screen === 'preview'
            ? screenPreview()
            : screenRender();
  app.innerHTML = `${topbar()}${screen}`;
  afterRender();
}

/* ------------------------------------------------------------------ boot */

function startPolls() {
  window.setInterval(async () => {
    if (!state.project) return;
    if (['queued', 'running', 'cancelling'].includes(state.check?.state)) {
      try { await refreshCheck(); } catch (_) { /* keep last */ }
    }
  }, 1500);
  window.setInterval(async () => {
    if (['welcome', 'render'].includes(state.screen)) await refreshQueue();
  }, 2500);
}

async function boot() {
  state.token = readToken();
  if (!state.token) {
    app.innerHTML = `<div class="boot"><div class="boot-mark"></div><p>DuckSuite needs the local launch token.</p><p class="small" style="max-width:380px;text-align:center">Open DuckSuite from the Mac app. The web preview alone cannot reach the local core.</p></div>`;
    return;
  }
  try {
    await Promise.all([loadProjects(), loadQueue(), loadEngine(), loadSettings()]);
    loadVoices();
    const routeParam = new URLSearchParams(window.location.search).get('route');
    if (routeParam) window.location.hash = `#/${routeParam.replace(/^\/+/, '')}`;
    if (!window.location.hash || window.location.hash === '#') window.location.hash = '#/welcome';
    await route();
    startPolls();
  } catch (error) {
    app.innerHTML = `<div class="boot"><div class="boot-mark"></div><p>DuckSuite could not start.</p><p class="small" style="max-width:420px;text-align:center">${esc(error.message)}</p></div>`;
  }
}

window.addEventListener('hashchange', () => { route(); });
boot();
