/* DuckSuite — Daylight Story Desk.
   One shell, six screens, no marketing page. */

import {
  storyClipAt as findStoryClip,
  storyDuration,
  timelineToSource as mapTimelineToSource,
  sourceToTimeline as mapSourceToTimeline,
  storyRanges,
} from './timeline-model.js';
import { waveformPeaks, audibleRows, mixEntry } from './audio-tools.js';
import { storyBannerMarkup, mediaInspectorMarkup, audioFocusMarkup } from './editor-markup.js';

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
  packs: [],
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
  cleanFilter: 'all',
  previewTime: 0,
  timelineTime: 0,
  previewCache: new Map(),
  previewStatus: new Map(),
  previewRunning: false,
  previewRun: 0,
  cleanVersion: 0,
  renderEstimate: null,
  renderEstimateKey: '',
  voiceName: 'Samantha',
  voiceMode: 'voice_over',
  welcomeQuery: '',
  queuePaused: false,
  queueScope: 'project',
  previewView: 'after',
  proofStep: 1,
  inlinePlaying: false,
  scriptOpen: false,
  scriptBusy: false,
  scriptStatus: 'Script ready',
  scriptStatusKind: 'ready',
  transcriptBusy: false,
  scriptTarget: 'vi',
  scriptMode: 'clean',
  editScope: 'scene',
  focusMode: '',
  transcriptOverlay: true,
  overlayTop: false,
  sfxKind: '',
  storySelect: false,
  storyScenes: [],
  openAudioRows: new Set(),
  waveformCache: new Map(),
  audioBuffers: new Map(),
  audioContext: null,
  audioSources: [],
  mixPlaying: false,
  mixVideo: false,
  mixTimer: null,
  auditionId: '',
  voicePreview: '',
  recording: false,
  brushMode: false,
  brushKind: 'fill',
  brushSize: 0.025,
  brushStrokes: [],
  importing: false,
  pendingImportMode: 'new',
  lastCheckKey: '',
  lastQueueKey: '',
  autoOpened: false,
  editorReady: false,
  showAllLayers: false,
  transcriptSideHidden: false,
  transcriptAlpha: 100,
  timelineZoom: 1,
  safeZone: 'off',
  safeZoneOpen: false,
  sequenceActive: false,
  sequenceSegments: [],
  sequenceIndex: 0,
  sequenceSkipped: 0,
  sequenceTotal: 0,
  sequencePlaying: false,
  storyWriting: false,
  cueMenu: '',
  showAllCues: false,
  sceneQuery: '',
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
    split: '<path d="M12 3v18M8 3h8M8 21h8"/>',
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
  state.timelineTime = 0;
  state.autoOpened = false;
  state.editorReady = false;
  state.brushMode = false;
  state.brushStrokes = [];
  try {
    const stored = Number(localStorage.getItem(`duck.transcriptAlpha.${encodeURIComponent(id)}`));
    state.transcriptAlpha = Number.isFinite(stored) && stored >= 30 && stored <= 100 ? stored : 100;
  } catch (_error) {
    state.transcriptAlpha = 100;
  }
  state.editScope = 'scene';
  state.focusMode = '';
  state.transcriptOverlay = true;
  state.sfxKind = '';
  state.storySelect = false;
  state.storyScenes = [];
  state.showAllLayers = false;
  state.showAllCues = false;
  state.sceneQuery = '';

  const [editsData, transcriptData] = await Promise.all([
    api(`/api/projects/${encodeURIComponent(id)}/edits`).catch(() => ({ edits: [] })),
    api(`/api/projects/${encodeURIComponent(id)}/transcript`).catch(() => ({ transcript: {} })),
  ]);
  state.edits = editsData.edits || [];
  state.transcript = transcriptData.transcript || {};
  state.edit = null;
  await ensureEdit();
  syncScriptStatus();
  await ensureCaptions();
  const scenes = getScenes();
  if (scenes[0]) {
    state.previewTime = Number(scenes[0].start || 0) + 0.1;
    state.timelineTime = sourceToTimeline(state.previewTime);
  }

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
  const previousAppend = state.check?.result?.append?.analysis || '';
  const previousEditorReady = state.editorReady;
  const hadEdit = Boolean(state.edit);
  const hadScenes = getScenes().length;
  state.check = data.check;
  let editorReloaded = false;
  if (previousAppend === 'pending' && state.check?.result?.append?.analysis !== 'pending') {
    await refreshTranscript();
    state.edit = null;
    await ensureEdit();
    await ensureCaptions();
    editorReloaded = true;
  }
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
    if (!state.edit) {
      await ensureEdit();
      editorReloaded = true;
    }
    await refreshTranscript();
    await ensureCaptions();
  }
  if (data.check?.state === 'done') {
    state.sourceMeta = data.check?.result?.meta || state.sourceMeta;
    if (!state.edit) {
      await ensureEdit();
      editorReloaded = true;
    }
    if (!state.editorReady) {
      state.editorReady = true;
      await refreshTranscript();
    }
  }
  if (next !== previous) {
    state.lastCheckKey = next;
    if (state.screen === 'check') {
      if (hadScenes !== hasScenes) render();
      else {
        patchCheckProgress();
        refreshToolbar();
      }
    } else if (['edit', 'clean', 'preview', 'render'].includes(state.screen)) {
      if (editorReloaded || (!hadEdit && state.edit)) render();
      else refreshToolbar();
    }
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
  return `${check.state || ''}|${check.stage || ''}|${Math.round((check.progress || 0) * 1000)}|${scenes}|${check.result?.append?.analysis || ''}`;
}

/* ------------------------------------------------------------------ model */

function checkScenes() {
  return state.check?.result?.scenes || state.check?.scenes || [];
}

function getScenes() {
  const all = checkScenes();
  if (!state.edit || state.edit.kind !== 'story') return all;
  const byId = new Map(all.map((scene) => [scene.id, scene]));
  const ordered = (state.edit.clips || [])
    .map((clip) => byId.get(clip.scene))
    .filter(Boolean);
  return ordered.length ? ordered : all;
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

// AI fill only looks clean while the picture under the line holds still. Check
// measures that per line, so a layer can say when Fill is a gamble.
function isMine(layer) {
  return Boolean(layer) && layer.auto === false;
}

function mineLayers(layers) {
  return (layers || []).filter(isMine);
}

function layerRisk(layer) {
  return Boolean(layer && layer.enabled !== false && layer.kind === 'fill' && layer.quality === 'moving');
}

const LAYER_KIND = {
  screen_text: 'Screen text',
  subtitle: 'Subtitle',
  lower_third: 'Lower third',
  title: 'Title',
  credit: 'Credit',
  watermark: 'Logo / watermark',
  handle_or_logo: 'Logo / watermark',
  manual: 'Manual brush',
};

function layerLabel(layer, index) {
  const kind = LAYER_KIND[layer?.tracklet_kind] || 'Text block';
  return `${kind} ${pad(index + 1)}`;
}


function cleanState(scene) {
  if (!state.edit) return 'Waiting';
  if (!sceneLayers(scene).length) return 'No text';
  return 'Layered';
}

function sceneCleanCount(scenes = getScenes()) {
  return scenes.filter((scene) => sceneLayers(scene).length > 0).length;
}

function sceneNeedsProof(scene) {
  return sceneLayers(scene).some((layer) => layer.enabled !== false);
}

function proofTargets(scenes = getScenes()) {
  return scenes.filter(sceneNeedsProof);
}

function sceneReadyCount(scenes = getScenes()) {
  return proofTargets(scenes).filter((scene) => state.previewStatus.get(scene.id) === 'ready').length;
}

function activeRenderJob() {
  return (state.queue || []).find((item) => ['queued', 'running', 'rendering', 'paused', 'pausing'].includes(item.state)) || null;
}

function renderPercent(job) {
  return job ? Math.max(0, Math.min(100, Math.round(Number(job.progress || 0) * 100))) : 0;
}

function sceneStripControls(target) {
  return `<span class="strip-arrows"><button class="strip-arrow" type="button" data-action="strip-scroll" data-target="${target}" data-dir="-1" aria-label="Scroll scenes left">‹</button><button class="strip-arrow" type="button" data-action="strip-scroll" data-target="${target}" data-dir="1" aria-label="Scroll scenes right">›</button></span>`;
}

function frameUrl(time, projectId = state.project?.id) {
  if (!projectId) return '';
  return mediaUrl(`/api/projects/${encodeURIComponent(projectId)}/frame`, { time: Math.max(0, Number(time) || 0).toFixed(3) });
}

function cleanPreviewUrl(time, mode = 'blur') {
  if (!state.project || !state.edit) return '';
  const params = {
    time: Math.max(0, Number(time) || 0).toFixed(3),
    v: state.cleanVersion,
  };
  if (mode === 'blur') params.mode = 'blur';
  return mediaUrl(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/preview`, params);
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
  const append = projectId === state.project?.id ? state.check?.result?.append : null;
  const version = append ? `${Math.round(Number(append.at || 0) * 1000)}-${append.analysis || ''}` : '';
  return mediaUrl(`/api/projects/${encodeURIComponent(projectId)}/source`, version ? { v: version } : {});
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
  return state.engine.fill?.ready && state.engine.vision?.available ? 'Local · ready' : 'Local · setup needed';
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
    if (routeInfo.screen !== 'preview') {
      state.sequenceActive = false;
      state.sequencePlaying = false;
    }
    if (['edit', 'clean', 'preview', 'render'].includes(routeInfo.screen)) await ensureEdit();
    if (routeInfo.screen === 'check' && state.check?.state === 'idle') await startCheck();
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
  const disabled = project ? '' : ' disabled';
  const tab = (name, label, index, busy = false) => {
    const isActive = active === name;
    const isDone = !busy && activeIndex > index;
    return `<button class="toolbar-tab${isActive ? ' is-active' : ''}${isDone ? ' is-done' : ''}" data-action="nav" data-screen="${name}" type="button"${disabled}>
      ${busy ? icon('loader', 12) : ''}<span>${label}</span>${isDone ? icon('check', 11) : ''}
    </button>`;
  };
  return `<header class="toolbar" data-toolbar>
    <div class="toolbar-left">
      <button class="duck-home" type="button" data-action="welcome" title="Home" aria-label="Home">${duckMark(28)}</button>
      ${screen === 'welcome' ? '' : `<button class="btn toolbar-import" type="button" data-action="import"${state.importing ? ' disabled' : ''}>${icon(state.importing ? 'loader' : 'plus', 14)} Import</button>`}
      <button class="icon-btn toolbar-search" type="button" data-action="search" title="Search" aria-label="Search">${icon('search', 16)}</button>
    </div>
    <nav class="toolbar-tabs" aria-label="Workflow">
      ${tab('check', checkRunning ? 'Checking' : 'Check', 0, checkRunning)}
      ${tab('edit', 'Edit', 1)}
      ${tab('preview', 'Preview', 2)}
      ${tab('render', 'Render', 3)}
    </nav>
    <div class="toolbar-right">
      <button class="toolbar-engine" type="button" data-action="settings" title="${esc(engineLabel())} · open engine settings"><span class="dot${state.engine?.fill?.ready && state.engine?.vision?.available ? '' : ' is-idle'}"></span><span class="engine-text">${state.engine?.fill?.ready && state.engine?.vision?.available ? 'Ready' : 'Setup needed'}</span></button>
      <button class="toolbar-queue${queueActiveCount() ? ' is-active' : ''}" type="button" data-action="nav" data-screen="render" title="Render queue"${disabled}>${icon('layers', 14)}<span>Queue</span><strong>${queueActiveCount()}</strong></button>
      <button class="icon-btn toolbar-settings" type="button" data-action="settings" title="Settings" aria-label="Settings">${icon('settings', 18)}</button>
    </div>
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
          <div class="engine-row"><span class="dot${state.engine?.fill?.ready && state.engine?.vision?.available ? '' : ' is-idle'}"></span><strong>${esc(engineLabel())}</strong></div>
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
          <div class="media-card hug" style="height:min(56vh, 540px);--media-ratio:${(Number(state.check?.result?.meta?.width) && Number(state.check?.result?.meta?.height)) ? (Number(state.check.result.meta.width) / Number(state.check.result.meta.height)).toFixed(4) : '1.7778'}">
            <video data-preview data-app-player preload="metadata" poster="${frameUrl(state.previewTime || 0.5)}" src="${sourceUrl()}"></video><span class="media-badge right">${mediaResolution()}</span>${playerBar()}
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
          ${checkCtaMarkup(scenes, running, done)}
        </div>
      </aside>
    </div>
  </main>`;
}

function checkCtaMarkup(scenes, running, done) {
  return `${done || scenes.length
    ? `<button class="btn primary wide" type="button" data-action="open-editor">${icon('arrowRight', 15)} Open Editor</button><p class="note">${running ? 'Scenes are ready. The Editor opens while the rest continues.' : 'Transcript and text detection continue in the background.'}</p>`
    : `<button class="btn primary wide" type="button" data-action="start-check" ${running ? 'disabled' : ''}>${running ? `${icon('loader', 15)} Checking…` : 'Start Check'}</button><p class="note">${running ? 'Scenes first. The Editor opens while the rest continues.' : 'Local only. Nothing leaves this Mac.'}</p>`}
  ${done ? `<button class="btn wide" type="button" data-action="start-check">${icon('loader', 14)} Re-check</button>` : ''}
  ${done && !(Number(state.check?.result?.transcript?.segments) || 0)
    ? `<button class="btn wide" type="button" data-action="retry-transcript" ${state.transcriptBusy ? 'disabled' : ''}>${icon('captions', 14)} ${state.transcriptBusy ? 'Reading speech…' : 'Re-read speech'}</button>`
    : ''}`;
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

function patchCheckProgress() {
  const check = state.check || {};
  const scenes = checkScenes();
  const running = ['queued', 'running', 'cancelling'].includes(check.state);
  const done = check.state === 'done';
  const values = {
    scenes: stagePct('scenes'),
    transcript: stagePct('transcript'),
    text: stagePct('text'),
    stories: stagePct('stories'),
  };
  const subs = {
    scenes: scenes.length ? `${scenes.length} scenes` : 'Detect and split scenes',
    transcript: 'Speech to text · auto language',
    text: 'Find burned-in text',
    stories: 'Find story segments',
  };
  document.querySelectorAll('.stage-row[data-stage]').forEach((row) => {
    const key = row.dataset.stage;
    const pct = values[key];
    if (pct === undefined) return;
    const p = Math.round(Math.max(0, Math.min(1, pct)) * 100);
    const finished = done || pct >= 0.999;
    const marker = row.querySelector('.stage-icon');
    if (marker) {
      marker.className = `stage-icon ${finished ? 'done' : p > 0 ? 'doing' : ''}`;
      marker.innerHTML = finished ? icon('check', 12) : p > 0 ? icon('loader', 12) : icon('circle', 12);
    }
    const sub = row.querySelector('.stage-sub');
    if (sub && subs[key]) sub.textContent = subs[key];
    const bar = row.querySelector('.progress span');
    if (bar) bar.style.width = `${p}%`;
    const label = row.querySelector('.stage-pct');
    if (label) label.textContent = `${p}%`;
  });
  const summary = document.querySelector('.check-summary');
  if (summary) {
    const text = done
      ? 'Check complete. Transcript, text detection, and stories are ready.'
      : state.check?.editor_ready
        ? 'Editor ready. Stories finish in the background.'
        : `Transcript ${Math.round(values.transcript * 100)}% · Text detect ${Math.round(values.text * 100)}% · Stories ${done ? 'ready' : 'pending'}`;
    summary.innerHTML = `<strong>${scenes.length ? `${scenes.length} scenes ready` : running ? 'Finding scene cuts' : 'Not checked yet'}</strong><span>${text}</span>`;
  }
  const checkPanel = document.querySelector('.check-panel .panel-head .meta');
  if (checkPanel) checkPanel.textContent = done ? 'Done' : running ? 'Running' : 'Idle';
  const stagePanel = document.querySelector('.stage-list')?.closest('.panel');
  const stageMeta = stagePanel?.querySelector('.panel-head .meta');
  if (stageMeta) stageMeta.textContent = done ? 'Complete' : running ? `${Math.round((check.progress || 0) * 100)}%` : 'Not started';
  const stripHead = document.querySelector('.scene-strip-head .small');
  if (stripHead) stripHead.textContent = running ? 'Scenes ready' : done ? 'All scenes ready' : 'Waiting for scene cuts';
  const cta = document.querySelector('.check-cta');
  if (cta) cta.innerHTML = checkCtaMarkup(scenes, running, done);
}

function refreshToolbar() {
  const header = document.querySelector('.toolbar');
  if (header) header.outerHTML = topbar();
}

function sceneTile(scene, index) {
  const active = index === state.selectedScene;
  return `<button class="scene-tile${active ? ' is-active' : ''}" type="button" data-action="select-scene" data-index="${index}">
    <span class="thumb"><img src="${frameUrl(sceneMid(scene))}" alt=""><span class="tc">${fmtTC(scene.start, state.check?.result?.meta?.fps || 24)}</span></span>
    <span class="scene-label">${pad(index + 1)} · ${fmtDuration((scene.end || 0) - (scene.start || 0))}</span>
  </button>`;
}

/* ------------------------------------------------------------------ editor */

function overlayCuesForTime() {
  const allCues = scriptCues();
  let cueIndex = allCues.findIndex((cue) => Number(cue.end || 0) > Number(state.timelineTime || 0) && Number(cue.start || 0) <= Number(state.timelineTime || 0));
  if (cueIndex < 0) cueIndex = Math.max(0, allCues.length - 1);
  if (allCues.length) return allCues.slice(cueIndex, cueIndex + 2);
  return getSegments().filter((segment) => Number(segment.end || 0) > Number(state.previewTime || 0)).slice(0, 2);
}

function transcriptGhostMarkup(cues) {
  return `<div class="ghost-head"><strong>Transcript</strong><span>${cues.length} line${cues.length === 1 ? '' : 's'} in this scene</span></div>
    ${cues.slice(0, 2).map((cue, index) => {
      const source = String(cue.source_text || cue.text || '').trim();
      const text = String(cue.text || '').trim();
      const same = source.toLocaleLowerCase() === text.toLocaleLowerCase();
      return `<button class="ghost-line${index === 0 ? ' is-current' : ''}" type="button" data-action="seek" data-time="${Number(cue.start || 0).toFixed(3)}" data-start="${Number(cue.start || 0).toFixed(3)}" data-end="${Number(cue.end || 0).toFixed(3)}">
        <span class="ghost-tc">${fmtTC(cue.start, state.check?.result?.meta?.fps || 24)}</span>
        <span class="ghost-speaker">Speaker</span>
        <span class="ghost-copy">${source && !same ? `<span class="ghost-source">${esc(source)}</span>` : ''}<span>${esc(text || source)}</span></span>
        <span class="ghost-more">${icon('more', 12)}</span>
      </button>`;
    }).join('') || '<span class="overlay-empty">Transcript appears here when speech is ready.</span>'}`;
}

function refreshTranscriptOverlay(force = false) {
  const ghost = document.querySelector('.transcript-ghost');
  if (!ghost) return;
  const cues = overlayCuesForTime();
  const key = `${state.timelineTime}|${state.edit?.script?.mode || ''}|${state.edit?.script?.target_language || ''}|${cues.map((cue) => cue.text).join('|')}`;
  if (!force && key === state.overlayKey) return;
  state.overlayKey = key;
  ghost.innerHTML = transcriptGhostMarkup(cues);
}

function syncSceneForTime() {
  const scenes = getScenes();
  const time = Number(state.previewTime || 0);
  const index = scenes.findIndex((scene) => time >= Number(scene.start || 0) && time < Number(scene.end || 0));
  if (index < 0 || index === state.selectedScene) return;
  state.selectedScene = index;
  state.selectedLayerId = '';
  document.querySelectorAll('.proof-row').forEach((row, rowIndex) => row.classList.toggle('is-active', rowIndex === index));
  const scene = scenes[index];
  const title = document.querySelector('.inspector-title');
  const sub = document.querySelector('.inspector-sub');
  if (title) title.textContent = `Scene ${pad(index + 1)} · ${truncate(sceneTitle(scene, index), 26)}`;
  if (sub) sub.textContent = `${fmtTC(scene.start, state.check?.result?.meta?.fps || 24)} – ${fmtTC(scene.end, state.check?.result?.meta?.fps || 24)} · ${fmtDuration((scene.end || 0) - (scene.start || 0))}`;
}

function fullVideoEdit() {
  return (state.edits || []).find((edit) => edit.kind === 'full') || null;
}

function storyClipAt(time) {
  return findStoryClip(state.edit?.clips || [], time);
}

function storyClipLabel(clip, index) {
  if (clip?.kind === 'media') return clip.media === 'image' ? 'IMG' : 'VID';
  const scene = getScenes().find((item) => item.id === clip?.scene);
  const at = scene ? getScenes().indexOf(scene) : index;
  return `S${pad(at + 1)}`;
}

function storyFileUrl(name) {
  return mediaUrl(`/api/projects/${encodeURIComponent(state.project?.id || '')}/edits/${encodeURIComponent(state.edit?.id || '')}/story/file`, { name });
}

function storyDisplayTitle() {
  const clips = state.edit?.clips || [];
  const stored = String(state.edit?.title || 'Story');
  if (!stored.startsWith('Story · ')) return stored;
  const scenes = clips.filter((clip) => clip.kind !== 'media').length;
  return `Story · ${scenes} scenes`;
}

function storyOptionLabel(edit) {
  const title = String(edit?.title || 'Story');
  const seconds = Math.max(0, Number(edit?.end || 0));
  const updated = Number(edit?.updated || 0);
  const when = updated
    ? new Date(updated * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : String(edit?.id || '').slice(-4);
  return `${title} · ${fmtDuration(seconds)} · ${when}`;
}

function storyBanner() {
  if (!isStoryEdit()) return '';
  const clips = state.edit?.clips || [];
  const full = fullVideoEdit();
  const stories = (state.edits || []).filter((edit) => edit.kind === 'story');
  if (!stories.some((edit) => edit.id === state.edit.id)) stories.unshift(state.edit);
  const used = new Set(clips.filter((clip) => clip.kind !== 'media').map((clip) => clip.scene));
  const available = checkScenes().filter((scene) => !used.has(scene.id));
  return storyBannerMarkup({
    esc,
    icon,
    title: storyDisplayTitle(),
    beatCount: clips.length,
    duration: fmtDuration(timelineDuration()),
    fullId: full?.id || '',
    editOptions: stories.map((edit) => ({
      id: edit.id,
      label: storyOptionLabel(edit),
      selected: edit.id === state.edit.id,
    })),
    sceneOptions: available.map((scene) => {
      const at = checkScenes().indexOf(scene);
      return { id: scene.id, label: `S${pad(at + 1)} · ${truncate(sceneTitle(scene, at), 20)}` };
    }),
    beats: clips.map((clip, index) => ({
      index,
      chip: storyClipLabel(clip, index),
      name: clip.label || (clip.kind === 'media' ? 'Inserted beat' : `Scene ${pad(index + 1)}`),
      duration: fmtDuration(Math.max(0, Number(clip.end || 0) - Number(clip.start || 0))),
      first: index === 0,
      last: index === clips.length - 1,
      single: clips.length <= 1,
    })),
  });
}

function storyThesisBar(story) {
  if (!story || !story.thesis) return '';
  return `<div class="story-thesis">
    <span class="chip ${story.model === 'apple' ? 'green' : 'amber'}">${story.model === 'apple' ? 'Apple Intelligence' : 'No model · basic story'}</span>
    <strong>${esc(story.thesis)}</strong>
    <span class="small muted">${(story.beats || []).length} beats · ${fmtDuration(Number(story.runtime || 0))}</span>
    <span class="spacer"></span>
    <button class="btn small" type="button" data-action="write-story" ${state.storyWriting ? 'disabled' : ''}>Write again</button>
    <div class="story-beats">
      ${(story.beats || []).map((beat, index) => `<span class="story-beat" title="${esc(beat.reason || '')}">${index + 1}. ${esc(String(beat.cue || '').slice(0, 72))}</span>`).join('')}
    </div>
  </div>`;
}

function storyContextBar() {
  if (!isStoryEdit()) return '';
  const clips = state.edit?.clips || [];
  return `<div class="story-context">
    <span class="chip green">Story edit</span>
    <strong>${esc(storyDisplayTitle())}</strong>
    <span class="small muted">${clips.length} beats · ${fmtDuration(timelineDuration())}</span>
    <span class="spacer"></span>
    ${editSwitch()}
    <button class="btn small" type="button" data-action="back-to-full">${icon('arrowLeft', 12)} Full video</button>
  </div>`;
}

function outputSizeLabel() {
  const meta = state.edit?.source || state.sourceMeta || {};
  const width = Number(meta.width || 0);
  const height = Number(meta.height || 0);
  if (!width || !height) return '1080 × 1920';
  const outW = width >= height ? Math.round((width * 1080) / height) : 1080;
  const outH = width >= height ? 1080 : Math.round((height * 1080) / width);
  const even = (value) => (value % 2 === 0 ? value : value + 1);
  return `${even(outW)} × ${even(outH)}`;
}

function editSwitch() {
  const full = fullVideoEdit();
  const stories = (state.edits || []).filter((edit) => edit.kind === 'story');
  if (!stories.length) return '';
  if (!stories.some((edit) => edit.id === state.edit?.id)) {
    if (state.edit?.kind === 'story') stories.unshift(state.edit);
  }
  return `<div class="edit-switch"><span class="small muted">Edit</span>
    <select id="edit-select" title="Switch edit">
      ${full ? `<option value="${esc(full.id)}" ${state.edit?.id === full.id ? 'selected' : ''}>Full video</option>` : ''}
      ${stories.map((edit) => `<option value="${esc(edit.id)}" ${state.edit?.id === edit.id ? 'selected' : ''}>${esc(storyOptionLabel(edit))}</option>`).join('')}
    </select>
  </div>`;
}

function mediaFileDuration(file) {
  return new Promise((resolve) => {
    const video = document.createElement('video');
    const url = URL.createObjectURL(file);
    const finish = (value) => { URL.revokeObjectURL(url); resolve(value); };
    video.preload = 'metadata';
    video.onloadedmetadata = () => finish(Math.max(0.2, Math.min(120, Number(video.duration || 5))));
    video.onerror = () => finish(5);
    video.src = url;
  });
}

function applyEdit(edit) {
  state.edit = edit;
  const row = (state.edits || []).find((item) => item.id === edit.id);
  if (row) {
    row.title = edit.title;
    row.kind = edit.kind;
    row.end = edit.end;
  }
}

async function openEditById(editId) {
  if (!state.project || !editId) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(editId)}`);
    if (data.edit.kind === 'story' && String(data.edit.title || '').startsWith('Story · ')) {
      const scenes = (data.edit.clips || []).filter((clip) => clip.kind !== 'media').length;
      data.edit.title = `Story · ${scenes} scenes`;
    }
    applyEdit(data.edit);
    state.focusMode = '';
    state.storySelect = false;
    state.storyScenes = [];
    state.timelineTime = 0;
    state.previewTime = Number(data.edit.clips?.[0]?.start || 0) + 0.1;
    state.selectedScene = 0;
    await ensureCleanLayers();
    await ensureCaptions();
    syncScriptStatus();
    render();
  } catch (error) {
    toast(`Edit: ${error.message}`, 'bad');
  }
}

async function backToFullVideo() {
  const full = fullVideoEdit();
  if (!full) {
    toast('Full video edit is missing.', 'bad');
    return;
  }
  await openEditById(full.id);
  toast('Back to full video.');
}

async function refreshStoryCaptions() {
  if (!state.edit?.captions?.cues?.length) {
    await ensureCaptions();
    return;
  }
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/captions/generate`, { method: 'POST' });
    state.edit.captions = data.captions;
  } catch (_) { /* keep the existing cues if regeneration fails */ }
}

async function addStoryScene() {
  const chosen = Number(document.querySelector('#story-scene-select')?.value || 0);
  const scene = checkScenes().find((item) => Number(item.id) === chosen) || currentScene();
  if (!state.project || !state.edit || !scene) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/story/scene`, {
      method: 'POST',
      body: JSON.stringify({ scene_id: scene.id }),
    });
    applyEdit(data.edit);
    await refreshStoryCaptions();
    render();
    toast(`Scene ${pad(checkScenes().indexOf(scene) + 1)} added to the story.`);
  } catch (error) {
    toast(`Story: ${error.message}`, 'bad');
  }
}

async function uploadStoryBeat(kind, file) {
  if (!state.project || !state.edit || !file) return;
  try {
    const duration = kind === 'video' ? await mediaFileDuration(file) : 3;
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/story/beat`, {
      method: 'POST',
      body: await file.arrayBuffer(),
      headers: {
        'Content-Type': 'application/octet-stream',
        'x-kind': kind,
        'x-filename': file.name,
        'x-duration': String(duration),
      },
    });
    applyEdit(data.edit);
    await refreshStoryCaptions();
    render();
    toast(`${kind === 'image' ? 'Image' : 'Video'} beat added.`);
  } catch (error) {
    toast(`Story beat: ${error.message}`, 'bad');
  }
}

async function removeStoryBeat(index) {
  if (!state.project || !state.edit) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/story/clip/${Number(index)}`, { method: 'DELETE' });
    applyEdit(data.edit);
    await refreshStoryCaptions();
    render();
    toast('Story beat removed.');
  } catch (error) {
    toast(`Story: ${error.message}`, 'bad');
  }
}

async function moveStoryBeat(index, delta) {
  if (!state.project || !state.edit) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/story/clip/move`, {
      method: 'POST',
      body: JSON.stringify({ index: Number(index), delta: Number(delta) }),
    });
    applyEdit(data.edit);
    await refreshStoryCaptions();
    render();
  } catch (error) {
    toast(`Story: ${error.message}`, 'bad');
  }
}

function mediaInspector(story) {
  const clip = story.clip;
  const fileName = String(clip.file || '').split('/').pop();
  return mediaInspectorMarkup({
    esc,
    kind: clip.media === 'image' ? 'Image' : 'Video',
    label: clip.label || 'Inserted',
    duration: fmtDuration(Math.max(0, Number(clip.end || 0) - Number(clip.start || 0))),
    start: fmtTC(story.start),
    end: fmtTC(story.start + Math.max(0, Number(clip.end || 0) - Number(clip.start || 0))),
    fileUrl: storyFileUrl(clip.file),
    fileName,
    isImage: clip.media === 'image',
    index: story.index,
    total: (state.edit?.clips || []).length,
  });
}

function screenEditor() {
  const scenes = getScenes();
  const scene = currentScene();
  if (!scene) return emptyEditor();
  const layers = sceneLayers(scene);
  const layer = layers.find((item) => item.id === state.selectedLayerId) || layers[0] || null;
  const checking = ['queued', 'running', 'cancelling'].includes(state.check?.state);
  const overlayCues = overlayCuesForTime();
  const tab = state.inspectorTab === 'cut' ? 'cut'
    : state.inspectorTab === 'audio' || state.inspectorTab === 'voice' ? 'audio'
      : state.inspectorTab === 'sfx' ? 'sfx'
        : state.inspectorTab === 'script' ? 'script' : 'clean';
  const tabBody = tab === 'cut' ? inspectorCut()
    : tab === 'clean' ? inspectorClean(scene, layer, layers)
      : tab === 'script' ? inspectorScript()
        : tab === 'audio' ? inspectorAudio()
          : inspectorSFX();
  const focusLabel = { cut: 'Cut', clean: 'Clean', script: 'Script', audio: 'Audio', sfx: 'SFX' }[tab];
  const story = isStoryEdit() ? storyClipAt(state.timelineTime || 0) : null;
  const mediaClip = story?.clip?.kind === 'media' ? story.clip : null;
  const sourceMeta = state.check?.result?.meta || state.edit?.source || state.sourceMeta || {};
  const cutView = cutPreview();
  return `<main class="screen">${storyBanner()}${storyThesisBar(state.edit?.story)}
    <div class="workspace edit edit-clean">
      <aside class="panel proof-panel">
        <div class="panel-head"><h2>Scenes</h2><span class="meta">${scenes.length} scenes</span><button class="btn small story-toggle" type="button" data-action="toggle-story-select">${state.storySelect ? 'Cancel' : 'Story'}</button></div>
        ${state.storySelect ? `<div class="story-select-banner"><span class="chip amber">Story selection</span><strong>${state.storyScenes.length} selected</strong><div class="story-select-actions"><button class="btn small" type="button" data-action="toggle-story-select">Cancel</button><button class="btn small primary" type="button" data-action="build-story" ${state.storyScenes.length ? '' : 'disabled'}>Build story</button></div></div>` : ''}
        <div class="proof-tabs">
          <button class="proof-tab${state.proofTab === 'scenes' ? ' is-active' : ''}" type="button" data-action="proof-tab" data-tab="scenes">Scenes ${scenes.length}</button>
          <button class="proof-tab${state.proofTab === 'stories' ? ' is-active' : ''}" type="button" data-action="proof-tab" data-tab="stories">Stories ${getStories().length}</button>
        </div>
        ${state.proofTab === 'stories' ? `<button class="btn wide story-write" type="button" data-action="write-story" ${state.storyWriting ? 'disabled' : ''}>${icon('sparkle', 13)} ${state.storyWriting ? 'Writing a story…' : 'Write a story'}</button>` : ''}
        ${editSwitch()}
        <label class="scene-filter"><span class="small muted">Filter</span><input id="scene-search" type="search" placeholder="Scene title or number" value="${esc(state.sceneQuery)}"></label>
        <div class="proof-list compact">
          ${state.proofTab === 'stories' ? storyProofRows(getStories()) : sceneProofRows(scenes)}
        </div>
      </aside>

      <section class="editor-center">
        ${checking ? `<div class="check-banner">${icon('loader', 14)} Check is still running. Scenes, transcript and layers appear as they finish.</div>` : ''}
        <section class="panel preview-block">
          <div class="preview-row${Number(sourceMeta.height || 0) > Number(sourceMeta.width || 0) ? ' portrait' : ' landscape'}">
            <div class="media-card preview-large${cutView.cls}" style="${cutView.style}">
              ${mediaClip
                ? mediaClip.media === 'image'
                  ? `<img class="story-media-preview" src="${storyFileUrl(mediaClip.file)}" alt="${esc(mediaClip.label || 'Story image')}">`
                  : `<video class="story-media-preview" data-story-media data-app-player preload="metadata" src="${storyFileUrl(mediaClip.file)}"></video>`
                : `<video class="cut-video" style="filter:${gradeFilter()}" data-preview data-app-player preload="metadata" poster="${frameUrl(state.previewTime || scene.start)}" src="${sourceUrl()}"></video>`}
              <span class="media-badge right">${mediaClip ? (mediaClip.media === 'image' ? 'IMAGE BEAT' : 'VIDEO BEAT') : mediaResolution()}</span>
              ${playerBar()}
            </div>
            ${overlayCues.length ? `<aside class="transcript-side${state.transcriptSideHidden ? ' is-hidden' : ''}" style="--ta:${(Number(state.transcriptAlpha || 100) / 100).toFixed(2)}" aria-label="Transcript">
              <div class="transcript-side-head"><strong>Transcript</strong><span>${overlayCues.length} line${overlayCues.length === 1 ? '' : 's'} in this scene</span><button class="transcript-hide" type="button" data-action="toggle-transcript-side" aria-pressed="${state.transcriptSideHidden ? 'true' : 'false'}">${state.transcriptSideHidden ? 'Show' : 'Hide'}</button></div>
              <div class="transcript-alpha-row"><label for="transcript-alpha">Opacity</label><input id="transcript-alpha" type="range" min="30" max="100" step="5" value="${Number(state.transcriptAlpha || 100)}" aria-label="Transcript opacity"><span data-alpha-value>${Number(state.transcriptAlpha || 100)}%</span></div>
              ${state.transcriptSideHidden ? '' : overlayCues.map((cue) => `<div class="transcript-side-row">
                <button class="transcript-row-main" type="button" data-action="seek" data-time="${Number(cue.start || 0).toFixed(3)}" data-start="${Number(cue.start || 0).toFixed(3)}" data-end="${Number(cue.end || 0).toFixed(3)}">
                  <span class="transcript-side-time">${fmtTC(cue.start, 24)}</span>
                  <span class="speaker-chip">Speaker</span>
                  <span class="transcript-side-copy">${esc(cue.source_text && cue.source_text !== cue.text ? `${cue.source_text} · ` : '')}${esc(cue.text || '')}</span>
                </button>
                <button class="transcript-menu" type="button" data-action="cue-menu" data-cue="${esc(cue.id || '')}" aria-label="Line actions">${icon('more', 12)}</button>
                ${state.cueMenu && state.cueMenu === cue.id ? `<div class="cue-menu">
                  <button type="button" data-action="cue-seek" data-time="${Number(cue.start || 0).toFixed(3)}">Seek to this line</button>
                  <button type="button" data-action="cue-copy" data-cue="${esc(cue.id || '')}">Copy text</button>
                </div>` : ''}
              </div>`).join('')}
            </aside>` : ''}
          </div>
        </section>
      </section>

      ${mediaClip ? mediaInspector(story) : `<aside class="panel inspector">
        <div class="inspector-head">
          <h2 class="inspector-title">Scene ${pad(state.selectedScene + 1)} · ${esc(truncate(sceneTitle(scene, state.selectedScene), 26))}</h2>
          <p class="inspector-sub">${fmtTC(scene.start, state.check?.result?.meta?.fps || 24)} – ${fmtTC(scene.end, state.check?.result?.meta?.fps || 24)} · ${fmtDuration((scene.end || 0) - (scene.start || 0))}</p>
        </div>
        ${tab === 'clean' ? `<div class="scope-line">
          <span class="small muted">Clean scope</span>
          <span class="chip">This scene’s text</span>
          <span class="scope-note">Use Clean all in Preview to clean every scene.</span>
        </div>` : ''}
        <div class="tabs">
          ${['cut', 'clean', 'script', 'audio', 'sfx'].map((item) => `<button class="tab${tab === item ? ' is-active' : ''}" type="button" data-action="inspector-tab" data-tab="${item}">${item === 'audio' ? 'Audio' : item === 'sfx' ? 'SFX' : item[0].toUpperCase() + item.slice(1)}</button>`).join('')}
        </div>
        <div class="inspector-body">
          ${tabBody}
          <button class="btn wide focus-open" type="button" data-action="open-focus" data-focus="${tab}">${icon('expand', 14)} Open ${focusLabel} Focus</button>
          <div class="render-strip">
            <div class="panel-head" style="padding:0 0 4px"><h3 style="font-size:11px">Render queue</h3><span class="meta">${queueActiveCount()} active</span></div>
            ${(state.project ? state.queue.filter((item) => !item.project_id || item.project_id === state.project.id) : state.queue).slice(0, 3).map((item) => `<div class="render-row"><span class="state-dot ${item.state === 'done' ? 'green' : ['running', 'rendering', 'queued', 'paused'].includes(item.state) ? 'amber' : ''}"></span><span>${esc(item.title || 'Render')}</span><span class="render-time">${item.state === 'done' ? 'Done' : queueLabel(item.state)}</span></div>`).join('') || '<p class="small muted">No renders yet.</p>'}
          </div>
        </div>
      </aside>`}
    </div>
    ${state.focusMode ? focusDock() : timelinePanel()}
    <input id="music-input" type="file" accept="audio/*,.m4a,.mp3,.wav,.aac" hidden>
    <input id="sfx-file-input" type="file" accept="audio/*,image/*,video/*,.gif,.webp" hidden>
    <input id="story-image-input" type="file" accept="image/*,.png,.jpg,.jpeg,.webp,.gif" hidden>
    <input id="story-video-input" type="file" accept="video/*,.mp4,.mov,.m4v,.webm" hidden>
  </main>`;
}

async function writeStory() {
  if (!state.project || state.storyWriting) return;
  state.storyWriting = true;
  render();
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/story/write`, {
      method: 'POST',
      body: JSON.stringify({ count: 4 }),
    });
    state.edit = data.edit;
    state.edits = [{ ...data.edit }, ...(state.edits || []).filter((item) => item.id !== data.edit.id)];
    state.selectedScene = 0;
    state.selectedLayerId = '';
    state.timelineTime = 0;
    state.previewTime = 0;
    state.focusMode = '';
    state.storySelect = false;
    state.storyScenes = [];
    state.proofTab = 'stories';
    await ensureCaptions();
    render();
    const model = data.story?.model === 'apple' ? 'Apple Intelligence' : 'no model, basic story';
    toast(`Story written · ${model} · ${(data.story?.beats || []).length} beats.`);
  } catch (error) {
    toast(`Story: ${error.message}`, 'bad');
  } finally {
    state.storyWriting = false;
    render();
  }
}

async function buildStory() {
  if (!state.project || !state.storyScenes.length) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/story/scenes`, {
      method: 'POST',
      body: JSON.stringify({
        scene_ids: state.storyScenes,
        title: `Story · ${state.storyScenes.length} scenes`,
      }),
    });
    state.edit = data.edit;
    state.edits = [{ ...data.edit }, ...(state.edits || []).filter((item) => item.id !== data.edit.id)];
    state.storySelect = false;
    state.storyScenes = [];
    state.selectedScene = 0;
    state.focusMode = '';
    state.timelineTime = 0;
    state.screen = 'edit';
    await ensureCaptions();
    render();
    toast(`Story built from ${data.edit.clips?.length || 0} scenes.`);
  } catch (error) {
    toast(`Story: ${error.message}`, 'bad');
  }
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
    const order = state.storyScenes.indexOf(scene.id);
    const search = `${sceneTitle(scene, index)} ${index + 1}`.toLowerCase();
    return `<button class="proof-row compact${index === state.selectedScene ? ' is-active' : ''}${order >= 0 ? ' is-story' : ''}" type="button" data-action="${state.storySelect ? 'story-toggle' : 'select-scene'}" data-index="${index}" data-search="${esc(search)}">
      <span class="proof-index">${state.storySelect && order >= 0 ? order + 1 : pad(index + 1)}</span>
      <span class="proof-thumb"><img src="${frameUrl(scene.start + 0.1)}" alt=""></span>
      <span class="proof-main">
        <span class="proof-title">${esc(truncate(sceneTitle(scene, index), 34))}</span>
        <span class="proof-sub">${fmtTC(scene.start)} · ${fmtDuration((scene.end || 0) - (scene.start || 0))}</span>
      </span>
      <span class="proof-state"><span class="${status === 'Layered' ? 'chip green' : 'chip'}">${esc(status)}</span></span>
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
  return `<div class="layer-head"><span>${visible.length} of ${layers.length} layer${layers.length === 1 ? '' : 's'}</span>${layers.length > 6 ? `<button class="layer-head-more" type="button" data-action="toggle-layers">${state.showAllLayers ? 'Show fewer' : 'Show all'}</button>` : ''}</div>
  <div class="layer-list${state.showAllLayers ? ' is-expanded' : ''}" data-layer-list>
    ${layers.length ? visible.map((item, index) => `<button class="layer-row${item.id === active?.id ? ' is-active' : ''}${item.enabled === false ? ' is-off' : ''}" type="button" data-action="select-layer" data-layer="${esc(item.id)}">
      <span class="eye">${item.enabled === false ? icon('eyeOff', 14) : icon('eye', 14)}</span>
      <span class="layer-name" title="${esc(item.text_sample || '')}">${esc(layerLabel(item, index))}</span>
      ${isMine(item) ? '<span class="layer-flag is-mine" title="You set this layer; Clean all keeps it">yours</span>' : ''}
      ${item.quality === 'moving' && item.enabled !== false ? `<span class="layer-flag" title="Background moves behind this line">moves</span>` : ''}
      <span class="layer-kind">${esc(layerState(item))}</span>
    </button>`).join('') : `<p class="small muted">${esc(emptyText)}</p>`}
  </div>`;
}

function gradeOf() {
  const grade = state.edit?.cut?.grade || {};
  return {
    exposure: Number(grade.exposure || 0),
    contrast: Number(grade.contrast || 0),
    saturation: Number(grade.saturation || 0),
    temperature: Number(grade.temperature || 0),
  };
}

function signedValue(value) {
  const number = Math.round(Number(value) || 0);
  return number > 0 ? `+${number}` : String(number);
}

function gradeFilter(grade = gradeOf()) {
  const parts = [
    `brightness(${(1 + Number(grade.exposure || 0) / 200).toFixed(3)})`,
    `contrast(${(1 + Number(grade.contrast || 0) / 100).toFixed(3)})`,
    `saturate(${(1 + Number(grade.saturation || 0) / 100).toFixed(3)})`,
  ];
  const temperature = Number(grade.temperature || 0);
  if (temperature > 0) parts.push(`sepia(${(temperature / 100 * 0.45).toFixed(3)})`);
  if (temperature < 0) parts.push(`hue-rotate(${(temperature / 100 * 18).toFixed(1)}deg)`);
  return parts.join(' ');
}

function cutPreview() {
  const meta = state.check?.result?.meta || state.edit?.source || state.sourceMeta || {};
  const sw = Number(meta.width || 0);
  const sh = Number(meta.height || 0);
  const cut = state.edit?.cut || {};
  const aspect = cut.aspect || 'source';
  const crop = cut.crop || null;
  const sizes = { '9:16': 9 / 16, '1:1': 1, '4:5': 4 / 5, '16:9': 16 / 9 };
  let ratio = sw && sh ? sw / sh : 16 / 9;
  let style = `--media-ratio:${ratio.toFixed(4)}`;
  let cls = cut.fit === 'fill' ? ' cut-fill' : ' cut-fit';
  if (aspect !== 'source' && sizes[aspect]) ratio = sizes[aspect];
  style = `--media-ratio:${ratio.toFixed(4)}`;
  if (crop) {
    const cw = Math.max(0.02, Number(crop.w) || 1);
    const ch = Math.max(0.02, Number(crop.h) || 1);
    const ratioCrop = ((sw || 16) * cw) / ((sh || 9) * ch);
    style = `--media-ratio:${ratioCrop.toFixed(4)};--vw:${(100 / cw).toFixed(2)}%;--vh:${(100 / ch).toFixed(2)}%;--vx:${(-(Number(crop.x) || 0) / cw * 100).toFixed(2)}%;--vy:${(-(Number(crop.y) || 0) / ch * 100).toFixed(2)}%`;
    cls += ' cut-cropped';
  }
  return { cls, style };
}

function cutOutputLabel() {
  const meta = state.check?.result?.meta || state.edit?.source || state.sourceMeta || {};
  const cut = state.edit?.cut || {};
  const sizes = { '9:16': '1080 × 1920', '1:1': '1080 × 1080', '4:5': '1080 × 1350', '16:9': '1920 × 1080' };
  return sizes[cut.aspect] || `${Number(meta.width || 1080)} × ${Number(meta.height || 1920)} (source)`;
}

async function saveCut(patch) {
  if (!state.project || !state.edit) return;
  const cut = { aspect: 'source', fit: 'fit', crop: null, ...(state.edit.cut || {}), ...patch };
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/cut`, { method: 'PATCH', body: JSON.stringify(cut) });
    state.edit = data.edit;
    state.cleanVersion += 1;
    render();
    toast(`Cut saved · ${cutOutputLabel()}.`);
  } catch (error) {
    toast(`Cut: ${error.message}`, 'bad');
  }
}

function cutFocus() {
  const cut = state.edit?.cut || {};
  const aspect = cut.aspect || 'source';
  const fit = cut.fit || 'fit';
  const crop = cut.crop || { x: 0, y: 0, w: 1, h: 1 };
  const presets = [['warm', 'Warm'], ['cool', 'Cool'], ['bw', 'B&W'], ['vivid', 'Vivid']];
  return `<div class="cut-focus">
    <div class="focus-card">
      <h3>Output</h3>
      <div class="cut-label">Aspect</div>
      <div class="segmented cut-aspect">
        ${['source', '9:16', '1:1', '4:5', '16:9'].map((value) => `<button class="${aspect === value ? 'is-active' : ''}" type="button" data-action="cut-aspect" data-aspect="${value}">${value === 'source' ? 'Source' : value}</button>`).join('')}
      </div>
      <p class="small muted">Output ${cutOutputLabel()}</p>
      <div class="cut-label">Framing</div>
      <div class="segmented">
        <button class="${fit === 'fit' ? 'is-active' : ''}" type="button" data-action="cut-fit" data-fit="fit">Fit</button>
        <button class="${fit === 'fill' ? 'is-active' : ''}" type="button" data-action="cut-fit" data-fit="fill">Fill</button>
      </div>
      <div class="cut-label">Crop · normalized</div>
      <div class="box-grid">
        <label>X <input id="cut-x" type="number" min="0" max="1" step="0.005" value="${Number(crop.x || 0).toFixed(3)}"></label>
        <label>Y <input id="cut-y" type="number" min="0" max="1" step="0.005" value="${Number(crop.y || 0).toFixed(3)}"></label>
        <label>W <input id="cut-w" type="number" min="0.02" max="1" step="0.005" value="${Number(crop.w || 1).toFixed(3)}"></label>
        <label>H <input id="cut-h" type="number" min="0.02" max="1" step="0.005" value="${Number(crop.h || 1).toFixed(3)}"></label>
      </div>
      <div class="box-actions"><button class="btn small" type="button" data-action="cut-crop">Apply crop</button><button class="btn small" type="button" data-action="cut-reset">Reset crop</button></div>
    </div>
    <div class="focus-card">
      <h3>Look</h3>
      <div class="cut-label">Grade</div>
      <div class="grade-grid">
        ${[['exposure', 'Exposure'], ['contrast', 'Contrast'], ['saturation', 'Saturation'], ['temperature', 'Temperature']].map(([key, label]) => `<label><span>${label}</span><input data-grade="${key}" type="range" min="-100" max="100" step="1" value="${gradeOf()[key]}"><span data-grade-value>${signedValue(gradeOf()[key])}</span></label>`).join('')}
      </div>
      <div class="box-actions"><button class="btn small" type="button" data-action="grade-reset">Reset grade</button></div>
      <p class="small muted">The player preview is approximate; the render applies these in ffmpeg.</p>
      <div class="cut-label">Presets</div>
      <div class="filter-presets">
        ${presets.map(([value, label]) => `<button class="filter-chip ${value}" type="button" data-action="sfx-filter-add" data-preset="${value}">${label}</button>`).join('')}
      </div>
    </div>
    <div class="focus-card">
      <h3>Enhance</h3>
      <p class="small muted">Upscaling is planned (loop 19). Today the output is 1080-class and keeps the source detail.</p>
    </div>
  </div>`;
}

function inspectorCut() {
  return cutFocus();
}

function inspectorClean(scene, layer, layers) {
  if (!state.edit) return `<p class="small muted">Editor data is still loading. Clean controls appear when Check finishes.</p>`;
  const proof = state.previewCache.get(scene.id) || '';
  const sceneIndex = getScenes().indexOf(scene);
  return `<div class="proof-pair">
    <figure><div class="frame"><img src="${frameUrl(sceneMid(scene))}" alt=""></div><figcaption>Before</figcaption></figure>
    <span class="arrow">${icon('chevronRight', 14)}</span>
    <figure><div class="frame"><img src="${proof || frameUrl(sceneMid(scene))}" alt="After"></div><figcaption>${proof ? 'After · blur proof' : 'After · no proof yet'}</figcaption></figure>
  </div>
  <button class="btn wide" type="button" data-action="prove-scene" data-index="${sceneIndex}" ${state.previewRunning ? 'disabled' : ''}>${icon('sparkle', 14)} ${proof ? 'Prove again' : 'Prove this scene'}</button>
  <div class="segmented">
    ${['fill', 'blur', 'exclude'].map((action) => {
      const label = action === 'exclude' ? 'Off' : action[0].toUpperCase() + action.slice(1);
      const active = layer && ((action === 'fill' && layer.enabled !== false && layer.kind === 'fill') || (action === 'blur' && layer.enabled !== false && layer.kind === 'blur') || (action === 'exclude' && layer.enabled === false));
      return `<button class="${active ? 'is-active' : ''}" type="button" data-action="clean-action" data-layer="${esc(layer?.id || '')}" data-kind="${action}" ${layer ? '' : 'disabled'}>${label}</button>`;
    }).join('')}
  </div>
  ${layer ? `<p class="layer-note${layerRisk(layer) ? ' is-warn' : ''}">${esc(layerNote(layer))}</p>` : ''}
  ${layer ? `<div class="box-editor">
    <span class="rail-head">Fill box · normalized</span>
    <div class="box-grid">
      <label>X <input id="box-x" type="number" min="0" max="1" step="0.005" value="${Number(layer.box?.x || 0).toFixed(3)}"></label>
      <label>Y <input id="box-y" type="number" min="0" max="1" step="0.005" value="${Number(layer.box?.y || 0).toFixed(3)}"></label>
      <label>W <input id="box-w" type="number" min="0.01" max="1" step="0.005" value="${Number(layer.box?.w || 0.1).toFixed(3)}"></label>
      <label>H <input id="box-h" type="number" min="0.01" max="1" step="0.005" value="${Number(layer.box?.h || 0.1).toFixed(3)}"></label>
    </div>
    <div class="box-actions"><button class="btn small" type="button" data-action="box-apply" data-layer="${esc(layer.id)}">Apply box</button><button class="btn small" type="button" data-action="recheck-scene">Re-check &amp; re-apply</button></div>
  </div>` : ''}
  <div class="fill-engine-line"><span class="rail-head">AI fill engine</span>${fillEngineControl()}</div>
  ${layerListMarkup(layer, layers)}
  <button class="btn wide" type="button" data-action="nav-clean-brush">${icon('sparkle', 14)} Paint a mask</button>
  <div class="model-line"><span class="dot${state.engine?.fill?.ready ? '' : ' is-idle'}"></span><strong>AI fill · ${state.engine?.fill?.ready ? 'ready' : 'missing'}</strong><span>${esc(fillStatusText())}</span>${state.engine?.fill?.ready ? '' : `<button class="btn small" type="button" data-action="settings">Set up</button>`}</div>
  <button class="btn primary wide" type="button" data-action="nav" data-screen="preview">${icon('play', 14)} Preview before / after</button>
  <button class="btn wide" type="button" data-action="nav" data-screen="clean">${icon('sparkle', 14)} Clean focus</button>`;
}

function layerNote(layer) {
  if (!layer) return '';
  if (layer.enabled === false) return 'Off. The words stay exactly as they are in the source.';
  if (layer.kind === 'fill') {
    if (layer.quality === 'moving') return 'Background moves here, so AI fill can smear. Switch to Blur if it shows.';
    if (layer.quality === 'steady') return 'Still background. AI fill rebuilds the plate behind the words.';
    return 'AI fill rebuilds the plate behind the words.';
  }
  return layer.quality === 'moving'
    ? 'Blur hides the words and keeps the motion.'
    : 'Blur hides the words without rebuilding the background.';
}

function fillStatusText() {
  if (state.engine?.fill?.ready) return 'Local fill';
  const problem = String(state.engine?.fill?.problem || '').trim();
  return problem ? problem.slice(0, 90) : 'Model not found. Reinstall DuckSuite to restore it.';
}


function focusDock() {
  const titles = { cut: 'Cut Focus', script: 'Script Focus', audio: 'Audio Focus', sfx: 'SFX Focus' };
  const mode = state.focusMode;
  return `<section class="panel focus-dock">
    <div class="focus-dock-head">
      <div><span class="focus-kicker">Edit Focus</span><h2>${titles[mode] || 'Focus'}</h2></div>
      <button class="btn small" type="button" data-action="close-focus">${icon('arrowLeft', 12)} Back to timeline</button>
    </div>
    <div class="focus-dock-body">${mode === 'cut' ? cutFocus() : mode === 'script' ? scriptFocus() : mode === 'audio' ? audioFocus() : sfxFocus()}</div>
  </section>`;
}

function focusShell() {
  const titles = { cut: 'Cut Focus', script: 'Script Focus', audio: 'Audio Focus', sfx: 'SFX Focus' };
  const mode = state.focusMode;
  return `<section class="focus-shell">
    <div class="focus-head">
      <div><span class="focus-kicker">Edit Focus</span><h1>${titles[mode] || 'Focus'}</h1></div>
      <button class="btn" type="button" data-action="close-focus">${icon('arrowLeft', 14)} Back to Edit</button>
    </div>
    <div class="focus-body">${mode === 'cut' ? cutFocus() : mode === 'script' ? scriptFocus() : mode === 'audio' ? audioFocus() : sfxFocus()}</div>
  </section>`;
}

function waveformBars(seed = 0) {
  return `<span class="waveform">${Array.from({ length: 44 }, (_unused, index) => {
    const height = 22 + Math.abs(Math.sin((index + seed) * 1.7)) * 70;
    return `<i style="height:${height.toFixed(0)}%"></i>`;
  }).join('')}</span>`;
}

function audioFocus() {
  const music = state.edit?.music;
  const voice = state.edit?.voice;
  const dub = state.edit?.dub;
  const rows = editAudioRows().map((row) => ({
    ...row,
    color: audioColor(row.kind),
    open: state.openAudioRows.has(String(row.id)),
  }));
  const sounds = (state.edit?.sfx || [])
    .filter((fx) => fx.kind === 'sound')
    .map((fx) => ({ id: fx.id, name: fx.name || 'Sound' }));
  return audioFocusMarkup({
    esc,
    icon,
    rows,
    music,
    voice,
    dub,
    mixing: state.mixPlaying,
    sounds,
    voicePanel: inspectorVoice(),
  });
}

function sfxFocus() {
  return `<div class="focus-grid sfx-focus">
    <div class="focus-card">
      <h3>Add special effect</h3>
      <p class="small muted">Text, stickers, GIFs, images, layers, colour filters and sounds share the same timeline.</p>
      <div class="sfx-add-grid">
        <button class="btn" data-action="sfx-text">${icon('captions', 14)} Text block</button>
        <button class="btn" data-action="sfx-add" data-kind="sticker">${icon('sparkle', 14)} Sticker</button>
        <button class="btn" data-action="sfx-add" data-kind="gif">${icon('film', 14)} GIF / animation</button>
        <button class="btn" data-action="sfx-add" data-kind="image">${icon('grid', 14)} Image</button>
        <button class="btn" data-action="sfx-add" data-kind="layer">${icon('layers', 14)} Layer</button>
        <button class="btn" data-action="sfx-add" data-kind="sound">${icon('volume', 14)} Sound</button>
      </div>
    </div>
    <div class="focus-card">
      <h3>Timeline effects</h3>
      ${inspectorSFX()}
    </div>
  </div>`;
}

function sfxRange() {
  const scene = currentScene();
  const start = Number(scene?.start || 0);
  const end = Number(scene?.end || 3);
  return { start: Math.max(0, start), end: Math.max(start + 0.2, end) };
}

function openSfxTextModal() {
  const range = sfxRange();
  openModal(`<dialog class="modal sfx-modal" aria-label="Add text effect">
    <div class="modal-head"><h2>Add text block</h2><button class="icon-btn" type="button" data-action="close-modal">${icon('close', 16)}</button></div>
    <div class="modal-body">
      <div class="field"><label>Text</label><input id="sfx-text-value" type="text" maxlength="240" placeholder="Text on screen"></div>
      <div class="grid g2">
        <div class="field"><label>Style</label><select id="sfx-text-style"><option value="headline">Headline</option><option value="caption">Caption</option><option value="badge">Badge</option></select></div>
        <div class="field"><label>Colour</label><input id="sfx-text-color" type="color" value="#ffffff"></div>
        <div class="field"><label>Start</label><input id="sfx-text-start" type="number" step="0.1" value="${range.start.toFixed(2)}"></div>
        <div class="field"><label>End</label><input id="sfx-text-end" type="number" step="0.1" value="${range.end.toFixed(2)}"></div>
      </div>
      <button class="btn primary wide" type="button" data-action="sfx-text-add">Add text block</button>
    </div>
  </dialog>`);
}

function openSfxFilterModal() {
  const range = sfxRange();
  openModal(`<dialog class="modal sfx-modal" aria-label="Add colour filter">
    <div class="modal-head"><h2>Add colour filter</h2><button class="icon-btn" type="button" data-action="close-modal">${icon('close', 16)}</button></div>
    <div class="modal-body">
      <div class="filter-presets">
        ${[['warm', 'Warm'], ['cool', 'Cool'], ['bw', 'Black & white'], ['vivid', 'Vivid']].map(([value, label]) => `<button class="filter-chip ${value}" type="button" data-action="sfx-filter-add" data-preset="${value}" data-start="${range.start.toFixed(2)}" data-end="${range.end.toFixed(2)}">${label}</button>`).join('')}
      </div>
    </div>
  </dialog>`);
}

async function addSfxText() {
  if (!state.project || !state.edit) return;
  const value = document.getElementById('sfx-text-value')?.value || '';
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/sfx/text`, {
      method: 'POST',
      body: JSON.stringify({
        text: value,
        start: Number(document.getElementById('sfx-text-start')?.value || 0),
        end: Number(document.getElementById('sfx-text-end')?.value || 3),
        style: document.getElementById('sfx-text-style')?.value || 'headline',
        color: document.getElementById('sfx-text-color')?.value || '#ffffff',
      }),
    });
    state.edit = data.edit;
    closeModal();
    render();
    toast('Text effect added.');
  } catch (error) {
    toast(`Text effect: ${error.message}`, 'bad');
  }
}

async function addSfxFilter(preset, start, end) {
  if (!state.project || !state.edit) return;
  const range = sfxRange();
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/sfx/filter`, {
      method: 'POST',
      body: JSON.stringify({ preset, start: start ?? range.start, end: end ?? range.end }),
    });
    state.edit = data.edit;
    closeModal();
    render();
    toast('Filter added.');
  } catch (error) {
    toast(`Filter: ${error.message}`, 'bad');
  }
}

async function handleSfxFile(file) {
  if (!file || !state.project || !state.edit || !state.sfxKind) return;
  const range = sfxRange();
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/sfx/upload`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${state.token}`,
        'X-Kind': state.sfxKind,
        'X-Filename': file.name,
        'X-Start': String(range.start),
        'X-End': String(range.end),
        'X-Volume': '0.9',
      },
      body: file,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    state.edit = data.edit;
    render();
    toast(`${state.sfxKind} effect added.`);
  } catch (error) {
    toast(`Effect: ${error.message}`, 'bad');
  } finally {
    state.sfxKind = '';
  }
}

async function patchAudioTrack(trackId, values) {
  if (!state.project || !state.edit || !trackId) return;
  const active = document.activeElement;
  const activeField = active?.dataset?.audioField || '';
  const activeTrack = active?.dataset?.track || '';
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/audio/${encodeURIComponent(trackId)}`, {
      method: 'PATCH',
      body: JSON.stringify(values),
    });
    state.edit = data.edit;
    render();
    if (activeField && activeTrack) {
      const next = [...document.querySelectorAll('[data-audio-field]')]
        .find((input) => input.dataset.audioField === activeField && input.dataset.track === activeTrack);
      next?.focus();
    }
  } catch (error) {
    toast(`Audio track: ${error.message}`, 'bad');
  }
}

function ensureAudioContext() {
  const AudioCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtor) return null;
  state.audioContext = state.audioContext || new AudioCtor();
  return state.audioContext;
}

function audioTrackUrl(trackId) {
  return mediaUrl(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/audio/${encodeURIComponent(trackId)}/file`);
}

async function audioBufferFor(row) {
  const key = String(row.id);
  if (state.audioBuffers.has(key)) return state.audioBuffers.get(key);
  const ctx = ensureAudioContext();
  if (!ctx) return null;
  try {
    const response = await fetch(audioTrackUrl(row.id));
    if (!response.ok) return null;
    const buffer = await ctx.decodeAudioData((await response.arrayBuffer()).slice(0));
    state.audioBuffers.set(key, buffer);
    return buffer;
  } catch (_) {
    return null;
  }
}

function stopAudioPlayback() {
  for (const source of state.audioSources) {
    try { source.stop(); } catch (_) { /* already stopped */ }
  }
  state.audioSources = [];
  if (state.mixTimer) {
    clearTimeout(state.mixTimer);
    state.mixTimer = null;
  }
  if (state.mixVideo) {
    const video = document.querySelector('[data-preview]');
    if (video) {
      video.pause();
      video.muted = false;
      video.volume = 1;
    }
    state.mixVideo = false;
  }
  state.mixPlaying = false;
  state.auditionId = '';
  syncAudioMixButton();
}

function syncAudioMixButton() {
  const button = document.querySelector('[data-action="audio-mix-preview"]');
  if (button) button.innerHTML = `${icon('play', 12)} ${state.mixPlaying ? 'Stop' : 'Preview mix'}`;
}

async function auditionAudioTrack(trackId) {
  const row = editAudioRows().find((item) => String(item.id) === String(trackId));
  if (!row) return;
  const wasPlaying = state.auditionId === String(trackId);
  stopAudioPlayback();
  if (wasPlaying) return;
  const ctx = ensureAudioContext();
  if (!ctx) return;
  await ctx.resume();
  const buffer = await audioBufferFor(row);
  if (!buffer) {
    toast('Audio row: file could not be read.', 'bad');
    return;
  }
  const offset = Math.max(0, Math.min(buffer.duration - 0.01, Number(row.offset || 0)));
  const wanted = Math.max(0.2, Number(row.duration || 0.2));
  const playable = Math.max(0.01, Math.min(wanted, buffer.duration - offset));
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  const gain = ctx.createGain();
  gain.gain.value = Math.max(0, Math.min(1.5, Number(row.volume ?? (row.kind === 'music' ? 0.25 : 1))));
  source.connect(gain).connect(ctx.destination);
  source.start(0, offset, playable);
  source.onended = () => {
    state.audioSources = state.audioSources.filter((item) => item !== source);
    if (!state.audioSources.length && !state.mixPlaying) {
      state.auditionId = '';
      syncAudioMixButton();
    }
  };
  state.audioSources.push(source);
  state.auditionId = String(trackId);
  toast(`Auditioning ${row.name || row.kind}`);
}

async function toggleAudioMixPreview() {
  if (state.mixPlaying) {
    stopAudioPlayback();
    return;
  }
  stopAudioPlayback();
  const ctx = ensureAudioContext();
  if (!ctx) {
    toast('Audio preview is not available in this browser.', 'bad');
    return;
  }
  await ctx.resume();
  const rows = editAudioRows().filter((row) => !row.muted);
  const audible = audibleRows(rows);
  const soloActive = rows.some((row) => row.solo);
  const dub = audible.some((row) => row.kind === 'dub');
  const voiceOnly = audible.some((row) => row.kind === 'voice' && row.mode === 'voice_only');
  const voices = audible.filter((row) => row.kind === 'voice' || row.kind === 'dub');
  const playhead = Math.max(0, Number(state.timelineTime || 0));
  const total = Math.max(0, Number(timelineDuration() || 0));
  const video = document.querySelector('[data-preview]');
  if (video) {
    try {
      video.currentTime = playhead;
      video.muted = soloActive || dub || voiceOnly;
      video.volume = voices.length ? 0.22 : 1;
      await video.play();
      state.mixVideo = true;
    } catch (_) { /* keep the mix without the source player */ }
  }
  const base = ctx.currentTime + 0.08;
  let last = playhead + 0.4;
  for (const row of audible) {
    const buffer = await audioBufferFor(row);
    if (!buffer) continue;
    const entry = mixEntry(row, playhead, buffer.duration);
    if (!entry) continue;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const gain = ctx.createGain();
    const startTime = base + entry.delay;
    const endTime = startTime + entry.duration;
    gain.gain.setValueAtTime(entry.fadeIn ? 0 : entry.level, startTime);
    if (entry.fadeIn) gain.gain.linearRampToValueAtTime(entry.level, startTime + entry.fadeIn);
    if (entry.fadeOut) {
      gain.gain.setValueAtTime(entry.level, Math.max(startTime, endTime - entry.fadeOut));
      gain.gain.linearRampToValueAtTime(0, endTime);
    }
    source.connect(gain).connect(ctx.destination);
    source.start(startTime, entry.offset, entry.duration);
    state.audioSources.push(source);
    last = Math.max(last, Number(row.start || 0) + Math.max(0.2, Number(row.duration || 0.2)));
  }
  state.mixPlaying = true;
  const stopAt = total > playhead ? total : last;
  state.mixTimer = setTimeout(() => stopAudioPlayback(), Math.max(400, (stopAt - playhead + 0.25) * 1000));
  syncAudioMixButton();
}

async function toggleAudioTrack(trackId, field) {
  const row = editAudioRows().find((item) => String(item.id) === String(trackId));
  if (!row) return;
  await patchAudioTrack(trackId, { [field]: !row[field] });
}

async function removeAudioTrack(trackId) {
  if (!state.project || !state.edit || !trackId) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/audio/${encodeURIComponent(trackId)}`, { method: 'DELETE' });
    state.edit = data.edit;
    render();
    toast('Audio track removed.');
  } catch (error) {
    toast(`Audio: ${error.message}`, 'bad');
  }
}

async function removeSfx(effectId) {
  if (!state.project || !state.edit || !effectId) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/sfx/${encodeURIComponent(effectId)}`, { method: 'DELETE' });
    state.edit = data.edit;
    render();
  } catch (error) {
    toast(`Effect: ${error.message}`, 'bad');
  }
}

function startSfxUpload(kind) {
  state.sfxKind = kind;
  const input = document.querySelector('#sfx-file-input');
  if (input) {
    input.value = '';
    input.click();
  }
}

function scriptCues() {
  return (state.edit?.captions?.cues || []).filter((cue) => String(cue.text || '').trim());
}

function syncScriptStatus() {
  const script = state.edit?.script || {};
  if (script.mode === 'translated') {
    state.scriptStatusKind = 'ready';
    state.scriptStatus = `Translated · ${({ en: 'English', vi: 'Vietnamese', zh: 'Chinese' })[script.target_language] || script.target_language || ''}`;
  } else if (script.mode === 'rewritten') {
    const engine = script.engine || (script.fallback ? 'basic-cleanup' : 'apple-intelligence');
    state.scriptStatusKind = engine === 'basic-cleanup' ? 'warn' : 'ready';
    state.scriptStatus = `Rewritten · ${script.rewrite || 'clean'} · ${engine === 'apple-intelligence' ? 'Apple Intelligence' : 'basic cleanup'}`;
  } else {
    state.scriptStatusKind = 'ready';
    state.scriptStatus = 'Script ready';
  }
}

function scriptLanguage() {
  return state.edit?.script?.source_language
    || state.check?.result?.transcript?.language
    || 'en';
}

function isStoryEdit() {
  return state.edit?.kind === 'story';
}

function editAudioRows() {
  const edit = state.edit || {};
  const rows = [];
  if (Array.isArray(edit.audio_tracks) && edit.audio_tracks.length) {
    rows.push(...edit.audio_tracks);
  } else {
    if (edit.dub) rows.push({ id: 'legacy-dub', kind: 'dub', name: edit.dub.voice || 'Dub', audio: edit.dub.audio, duration: edit.dub.duration || 0, start: 0, volume: 1, offset: 0 });
    if (edit.voice) rows.push({ id: 'legacy-voice', kind: 'voice', name: edit.voice.voice || 'Voice-over', audio: edit.voice.audio, duration: edit.voice.duration || 0, start: 0, volume: 1, offset: 0 });
    if (edit.music) rows.push({ id: 'legacy-music', kind: 'music', name: edit.music.name || 'Music', audio: edit.music.audio, duration: edit.music.duration || 0, start: 0, volume: edit.music.volume ?? 0.25, offset: 0 });
  }
  for (const effect of edit.sfx || []) {
    if (effect.kind === 'sound') {
      rows.push({ id: effect.id, kind: 'sound', name: effect.name || 'Sound effect', audio: effect.file, duration: Math.max(0.2, Number(effect.end || 0) - Number(effect.start || 0)), start: Number(effect.start || 0), volume: effect.volume ?? 0.9, muted: effect.muted, solo: effect.solo, fade_in: effect.fade_in, fade_out: effect.fade_out, offset: effect.offset || 0 });
    }
  }
  return rows;
}

function audioColor(kind) {
  return { voice: '#2d7b59', dub: '#c46812', music: '#6b5a9e', sound: '#b63a2c' }[kind] || '#6f7f86';
}

function centerTimelineOnPlayhead() {
  const scroller = document.querySelector('.timeline-scroll');
  if (!scroller) return;
  const total = Number(document.querySelector('.timeline')?.dataset.total || 0);
  const fraction = total ? Math.max(0, Math.min(1, Number(state.timelineTime || 0) / total)) : 0;
  scroller.scrollLeft = Math.max(0, fraction * scroller.scrollWidth - scroller.clientWidth / 2);
}

function timelineDuration() {
  const edit = state.edit;
  if (isStoryEdit()) {
    return storyDuration(edit?.clips || []);
  }
  const scenes = getScenes();
  return Math.max(
    Number(edit?.end || 0),
    Number(scenes[scenes.length - 1]?.end || 0),
    ...scriptCues().map((cue) => Number(cue.end || 0)),
    ...editAudioRows().map((row) => Number(row.start || 0) + Number(row.duration || 0)),
    ...(edit?.sfx || []).map((effect) => Number(effect.end || 0)),
  );
}

function timelineSceneRanges() {
  const scenes = getScenes();
  if (!isStoryEdit()) {
    return scenes.map((scene, index) => ({ scene, index, start: Number(scene.start || 0), end: Number(scene.end || 0) }));
  }
  const byId = new Map(scenes.map((scene) => [scene.id, scene]));
  return storyRanges(state.edit?.clips || [], byId);
}

function timelineToSource(time) {
  if (!isStoryEdit()) return Number(time) || 0;
  return mapTimelineToSource(state.edit?.clips || [], time);
}

function sourceToTimeline(time) {
  if (!isStoryEdit()) return Number(time) || 0;
  return mapSourceToTimeline(state.edit?.clips || [], time);
}

function timelineBlock(start, end, total, label, action = '', data = '', extraStyle = '', title = '') {
  const left = total > 0 ? Math.max(0, Math.min(100, (Number(start) / total) * 100)) : 0;
  const width = total > 0 ? Math.max(0.6, Math.min(100 - left, ((Number(end) - Number(start)) / total) * 100)) : 0;
  return `<button class="timeline-block" type="button" ${action ? `data-action="${action}" ${data}` : 'disabled'} ${title ? `title="${esc(title)}"` : ''} style="left:${left.toFixed(2)}%;width:${width.toFixed(2)}%;${extraStyle}">${esc(label)}</button>`;
}

function timelinePanel() {
  if (!state.edit) return '';
  const total = timelineDuration();
  const clips = state.edit.clips || [];
  const scenes = getScenes();
  const cues = scriptCues();
  const voice = state.edit.dub || state.edit.voice;
  const music = state.edit.music;
  const audioRows = editAudioRows();
  const audioHeight = Math.max(22, audioRows.length * 17 + 4);
  const visualFx = (state.edit.sfx || []).filter((effect) => effect.kind !== 'sound');
  const scriptHeight = cues.length ? 22 : 32;
  const audioHeightLane = audioRows.length ? audioHeight : 32;
  const sfxHeight = visualFx.length ? 22 : 32;
  const laneRows = `22px 22px ${scriptHeight}px ${audioHeightLane}px ${sfxHeight}px`;
  const playhead = total > 0 ? Math.max(0, Math.min(100, (Number(state.timelineTime || 0) / total) * 100)) : 0;
  const tickCount = Math.max(7, Math.round(7 * Number(state.timelineZoom || 1)));
  const ruler = Array.from({ length: tickCount }, (_unused, index) => {
    const at = index / (tickCount - 1);
    const time = total > 0 ? total * at : 0;
    return `<span class="ruler-tick${index === tickCount - 1 ? ' is-last' : ''}" style="left:${(at * 100).toFixed(2)}%">${fmtTC(time, 24)}</span>`;
  }).join('');
  return `<section class="panel timeline" data-total="${total}">
    <div class="timeline-head"><h2>Timeline</h2><span class="small muted">${fmtDuration(total)} · ${scenes.length} scenes · ${cues.length} cues · ${(state.edit.sfx || []).length} effects</span><span class="spacer"></span>
      <span class="timeline-trim"><label>In <input id="trim-in" type="number" step="0.05" min="0" value="${Number(clipForScene(currentScene(), state.selectedScene)?.start ?? currentScene()?.start ?? 0).toFixed(2)}"></label><label>Out <input id="trim-out" type="number" step="0.05" min="0" value="${Number(clipForScene(currentScene(), state.selectedScene)?.end ?? currentScene()?.end ?? 0).toFixed(2)}"></label><button class="icon-btn timeline-action" type="button" data-action="trim-apply" data-clip="${clipIndexForScene(currentScene(), state.selectedScene)}" title="Trim selected clip">${icon('scissors', 14)}</button><button class="icon-btn timeline-action" type="button" data-action="split-at-playhead" title="Split at playhead">${icon('split', 14)}</button><button class="icon-btn timeline-action" type="button" data-action="slip-clip" data-delta="-0.5" title="Slip earlier">${icon('chevronLeft', 14)}</button><button class="icon-btn timeline-action" type="button" data-action="slip-clip" data-delta="0.5" title="Slip later">${icon('chevronRight', 14)}</button></span>
      <span class="timeline-zoom" aria-label="Timeline zoom">
        <button type="button" data-action="timeline-zoom" data-dir="-1" aria-label="Zoom out">−</button>
        <span data-zoom-label>${Math.round(Number(state.timelineZoom || 1) * 10) / 10}×</span>
        <button type="button" data-action="timeline-zoom" data-dir="1" aria-label="Zoom in">+</button>
        <button type="button" data-action="timeline-zoom" data-dir="0">Fit</button>
      </span>
      <button class="icon-btn timeline-action" type="button" data-action="open-script" title="Open Script Focus">${icon('captions', 14)}</button></div>
    <div class="timeline-scroll">
    <div class="timeline-inner" style="--zoom:${Number(state.timelineZoom || 1)}">
    <div class="timeline-ruler" id="timeline-ruler" data-total="${total}">${ruler}<span class="ruler-playhead" style="left:${playhead.toFixed(2)}%"></span></div>
    <div class="timeline-body">
      <div class="timeline-labels" style="grid-template-rows:${laneRows}">
        <div class="timeline-label"><strong>Video</strong><button class="timeline-tool icon" type="button" data-action="trim-focus" title="Trim, cut or slip video">${icon('expand', 10)}</button></div>
        <div class="timeline-label"><strong>Scene</strong><span class="timeline-tool">All</span></div>
        <div class="timeline-label"><strong>Script</strong><button class="timeline-tool" type="button" data-action="open-script">Edit</button></div>
        <div class="timeline-label audio-labels"><strong>Voice & Music</strong><span><button class="timeline-tool icon" type="button" data-action="voice-tab" title="Add voice-over">${icon('plus', 10)}</button><button class="timeline-tool icon" type="button" data-action="add-music" title="Add music">${icon('volume', 10)}</button></span></div>
        <div class="timeline-label"><strong>SFX</strong><button class="timeline-tool icon" type="button" data-action="open-focus" data-focus="sfx" title="Add special effect">${icon('plus', 10)}</button></div>
      </div>
      <div class="timeline-tracks" style="grid-template-rows:${laneRows}">
        <div class="timeline-track video">${total > 0 ? timelineBlock(0, total, total, 'Full video · trim / cut / split', 'trim-focus', '') : ''}</div>
        <div class="timeline-track scene">${(() => {
          const rows = timelineSceneRanges();
          const dense = rows.length > 18;
          return rows.map((row) => {
            const story = isStoryEdit();
            const full = story ? storyClipLabel(row.clip, row.index) : `S${pad(row.index + 1)}`;
            const label = dense && row.index !== state.selectedScene ? '' : full;
            const action = story ? 'timeline-seek' : 'select-scene';
            const data = story ? `data-time="${row.start.toFixed(3)}"` : `data-index="${row.index}"`;
            const extra = !story && row.index === state.selectedScene ? 'outline:1px solid var(--amber);z-index:2' : '';
            const title = `${full} · ${fmtDuration((row.end || 0) - (row.start || 0))}`;
            return timelineBlock(row.start, row.end, total, label, action, data, extra, title);
          }).join('');
        })()}</div>
        <div class="timeline-track script${cues.length ? '' : ' is-empty'}">${cues.length ? cues.map((cue) => timelineBlock(cue.start, cue.end, total, '', 'timeline-seek', `data-time="${Number(cue.start || 0).toFixed(3)}"`)).join('') : `<button class="lane-add" type="button" data-action="open-script">${icon('plus', 10)} Add a caption</button>`}</div>
        <div class="timeline-track audio-stack${audioRows.length ? '' : ' is-empty'}">${audioRows.length ? audioRows.map((row) => {
          const start = Number(row.start || 0);
          const duration = Math.max(0.2, Number(row.duration || 0.2));
          const left = total > 0 ? Math.max(0, Math.min(100, (start / total) * 100)) : 0;
          const width = total > 0 ? Math.max(0.6, Math.min(100 - left, (duration / total) * 100)) : 0;
          const bars = Array.from({ length: 36 }, (_unused, index) => `<i style="height:${(25 + Math.abs(Math.sin((index + start) * 1.7)) * 70).toFixed(0)}%"></i>`).join('');
          return `<div class="audio-lane${row.muted ? ' is-muted' : ''}${row.solo ? ' is-solo' : ''}" style="--lane-color:${audioColor(row.kind)}">
            <span class="audio-lane-tools">
              <button class="lane-tool${row.muted ? ' is-on' : ''}" type="button" data-action="audio-mute" data-track="${esc(row.id)}" title="Mute ${esc(row.name || row.kind)}">M</button>
              <button class="lane-tool${row.solo ? ' is-on' : ''}" type="button" data-action="audio-solo" data-track="${esc(row.id)}" title="Solo ${esc(row.name || row.kind)}">S</button>
            </span>
            <button class="timeline-block audio-block" type="button" data-action="open-focus" data-focus="audio" data-track="${esc(row.id)}" data-start="${start.toFixed(3)}" data-duration="${duration.toFixed(3)}" data-offset="${Number(row.offset || 0).toFixed(3)}" style="left:${left.toFixed(2)}%;width:${width.toFixed(2)}%;background:${audioColor(row.kind)}b8;color:#fff;border-color:transparent">
              <span class="audio-wave" data-track="${esc(row.id)}" data-offset="${Number(row.offset || 0).toFixed(3)}" data-duration="${duration.toFixed(3)}" aria-hidden="true">${bars}</span>
              <span class="audio-handle left" data-edge="start"></span><span class="audio-block-label">${esc(row.name || row.kind)}</span><span class="audio-handle right" data-edge="end"></span>
            </button>
          </div>`;
        }).join('') : ''}</div>
        <div class="timeline-track sfx${visualFx.length ? '' : ' is-empty'}">${visualFx.length ? visualFx.map((effect, index) => timelineBlock(effect.start, effect.end, total, effect.name || effect.kind || 'FX', 'open-focus', 'data-focus="sfx"', `top:${2 + (index % 2) * 9}px;bottom:auto;height:9px`)).join('') : `<button class="lane-add" type="button" data-action="open-focus" data-focus="sfx">${icon('plus', 10)} Add an effect</button>`}</div>
        <span class="timeline-playhead" style="left:${playhead.toFixed(2)}%"></span>
      </div>
    </div>
    </div>
    </div>
  </section>`;
}

function scriptFocus() {
  const cues = scriptCues();
  const track = state.edit?.captions;
  const script = state.edit?.script || {};
  const modeLabel = script.mode === 'translated'
    ? `Translated · ${script.target_language || state.scriptTarget}`
    : script.mode === 'rewritten'
      ? `Rewrite · ${script.rewrite || state.scriptMode}`
      : 'Original';
  const statusKind = state.scriptStatusKind || 'ready';
  const needsTranslationLink = statusKind === 'error' && /translation|language/i.test(state.scriptStatus || '');
  return `<div class="script-focus">
    <div class="script-status ${statusKind}">
      <span class="status-light"></span>
      <strong>${esc(state.scriptStatus || 'Script ready')}</strong>
      ${state.scriptBusy ? `<span class="status-spinner">${icon('loader', 12)}</span>` : ''}
      ${needsTranslationLink ? `<a class="status-link" href="x-apple.systempreferences:com.apple.Localization-Settings.extension">Open Translation settings</a>` : ''}
    </div>
    ${cues.length ? `<div class="script-focus-grid">
      <div class="script-focus-pane">
        <div class="focus-col-head"><span>Cues</span><span>${cues.length}</span></div>
        <div class="focus-scroll">
          ${cues.map((cue, index) => `<button class="focus-cue${Number(cue.start || 0) <= state.timelineTime && Number(cue.end || 0) > state.timelineTime ? ' is-current' : ''}" type="button" data-action="script-seek" data-time="${Number(cue.start || 0).toFixed(3)}">
            <span class="focus-tc">${fmtTC(cue.start, 24)}</span><span>${esc(truncate(cue.text || '', 58))}</span>
          </button>`).join('')}
        </div>
      </div>
      <div class="script-focus-pane">
        <div class="focus-col-head"><span>Script</span><span class="focus-mode-tag">${esc(modeLabel)}</span></div>
        <div class="focus-scroll">
          ${cues.map((cue) => `<label class="focus-edit-row">
            <span class="focus-edit-meta"><span class="focus-tc">${fmtTC(cue.start, 24)}</span>${cue.source_text && cue.source_text !== cue.text ? `<span class="focus-source">${esc(truncate(cue.source_text, 64))}</span>` : ''}</span>
            <input type="text" value="${esc(cue.text || '')}" data-action="cue-save" data-cue="${esc(cue.id)}" aria-label="Script line ${fmtTC(cue.start, 24)}">
          </label>`).join('')}
        </div>
      </div>
      <aside class="script-focus-rules">
        <div class="rail-head">Script tools</div>
        <div class="rule-block"><label>Target language</label><select data-action="script-target">
          ${['en', 'vi', 'zh'].map((code) => `<option value="${code}" ${state.scriptTarget === code ? 'selected' : ''}>${({ en: 'English', vi: 'Vietnamese', zh: 'Chinese' })[code]}</option>`).join('')}
        </select></div>
        <button class="btn wide" type="button" data-action="script-translate" ${state.scriptBusy ? 'disabled' : ''}>${icon('captions', 13)} Translate</button>
        <p class="setup-note">First use may ask for a macOS language pack.</p>
        <div class="rule-block"><label>Rewrite style</label><select data-action="script-mode">
          ${[['clean', 'Clean up'], ['short', 'Shorten'], ['punchy', 'Punchier']].map(([value, label]) => `<option value="${value}" ${state.scriptMode === value ? 'selected' : ''}>${label}</option>`).join('')}
        </select></div>
        <button class="btn wide" type="button" data-action="script-rewrite" ${state.scriptBusy ? 'disabled' : ''}>${icon('sparkle', 13)} Rewrite</button>
        <p class="setup-note">${state.engine?.rewrite?.available === false ? 'Apple Intelligence is off. Rewrite uses a basic cleanup.' : 'Rewrite uses the best available local engine.'}</p>
        <button class="btn wide" type="button" data-action="script-reset">Reset to source</button>
        <div class="rule-sep"></div>
        <div class="rail-head">Caption tools</div>
        <div class="rule-block"><label>Caption style</label><select data-action="caption-style">
          ${['clean', 'bold', 'minimal'].map((value) => `<option value="${value}" ${track?.style === value ? 'selected' : ''}>${value[0].toUpperCase() + value.slice(1)}</option>`).join('')}
        </select></div>
        <div class="rule-block"><label>Position</label><select data-action="caption-position">
          ${['bottom', 'middle', 'top'].map((value) => `<option value="${value}" ${track?.position === value ? 'selected' : ''}>${value[0].toUpperCase() + value.slice(1)}</option>`).join('')}
        </select></div>
        <div class="toggle-row"><span>Burn captions</span><label class="switch"><input type="checkbox" data-action="caption-burn" ${track?.burn ? 'checked' : ''}><i></i></label></div>
        <button class="btn wide" type="button" data-action="download-captions">${icon('download', 13)} Download SRT</button>
      </aside>
    </div>` : '<div class="script-empty">No transcript yet. Re-read speech from the Check screen first.</div>'}
  </div>`;
}

function scriptDrawer(focus = false) {
  const cues = scriptCues();
  if (!cues.length) {
    return `<section class="script-drawer"><div class="script-head"><strong>Script</strong><span class="spacer"></span><button class="btn small" type="button" data-action="${focus ? 'close-focus' : 'close-script'}">Close</button></div><p class="small muted" style="padding:18px">Generate captions first. The script uses the caption track.</p></section>`;
  }
  return `<section class="script-drawer">
    <div class="script-head">
      <strong>Script</strong><span class="small muted">${cues.length} lines · ${esc(scriptLanguage())}</span>
      <span class="spacer"></span>
      <select data-action="script-target" aria-label="Target language">
        ${['en','vi','zh'].map((code) => `<option value="${code}" ${state.scriptTarget === code ? 'selected' : ''}>${({en:'English',vi:'Vietnamese',zh:'Chinese'})[code]}</option>`).join('')}
      </select>
      <button class="btn small" type="button" data-action="script-translate" ${state.scriptBusy ? 'disabled' : ''}>Translate</button>
      <select data-action="script-mode" aria-label="Rewrite style">
        ${[['clean','Clean up'],['short','Shorten'],['punchy','Punchier']].map(([value,label]) => `<option value="${value}" ${state.scriptMode === value ? 'selected' : ''}>${label}</option>`).join('')}
      </select>
      <button class="btn small" type="button" data-action="script-rewrite" ${state.scriptBusy ? 'disabled' : ''}>Rewrite</button>
      <button class="btn small" type="button" data-action="script-reset">Reset</button>
      <button class="btn small" type="button" data-action="${focus ? 'close-focus' : 'close-script'}">Close</button>
    </div>
    ${state.scriptBusy ? '<div class="script-progress">Working on the script…</div>' : ''}
    <div class="script-columns">
      <div class="script-column"><h3>Original</h3><div class="script-rows">${cues.map((cue) => `<div class="script-row"><span class="tc">${fmtTC(cue.start, 24)}</span><p>${esc(cue.source_text || cue.text || '')}</p></div>`).join('')}</div></div>
      <div class="script-column"><h3>Script</h3><div class="script-rows">${cues.map((cue) => `<label class="script-row editing"><span class="tc">${fmtTC(cue.start, 24)}</span><input type="text" value="${esc(cue.text || '')}" data-action="cue-save" data-cue="${esc(cue.id)}"></label>`).join('')}</div></div>
    </div>
  </section>`;
}

function inspectorScript() {
  const track = state.edit?.captions;
  return `<div class="field"><label>Target language</label><select data-action="script-target">
    ${['en', 'vi', 'zh'].map((code) => `<option value="${code}" ${state.scriptTarget === code ? 'selected' : ''}>${({ en: 'English', vi: 'Vietnamese', zh: 'Chinese' })[code]}</option>`).join('')}
  </select></div>
  <div class="field"><label>Rewrite style</label><div class="inline-control"><select data-action="script-mode">
    ${[['clean', 'Clean up'], ['short', 'Shorten'], ['punchy', 'Punchier']].map(([value, label]) => `<option value="${value}" ${state.scriptMode === value ? 'selected' : ''}>${label}</option>`).join('')}
  </select><button class="btn small" type="button" data-action="script-rewrite">Rewrite</button></div></div>
  <div class="inline-control"><button class="btn small" type="button" data-action="script-translate">Translate</button><button class="btn small" type="button" data-action="script-reset">Reset</button></div>
  <div class="toggle-row"><span>Burn captions</span><label class="switch"><input type="checkbox" data-action="caption-burn" ${track?.burn ? 'checked' : ''}><i></i></label></div>
  <div class="field"><label>Caption style</label><select data-action="caption-style">
    ${['clean', 'bold', 'minimal'].map((value) => `<option value="${value}" ${track?.style === value ? 'selected' : ''}>${value[0].toUpperCase() + value.slice(1)}</option>`).join('')}
  </select></div>
  <div class="field"><label>Caption position</label><select data-action="caption-position">
    ${['bottom', 'middle', 'top'].map((value) => `<option value="${value}" ${track?.position === value ? 'selected' : ''}>${value[0].toUpperCase() + value.slice(1)}</option>`).join('')}
  </select></div>
  <button class="btn wide" type="button" data-action="open-script">${icon('captions', 14)} Edit script lines</button>`;
}

function inspectorAudio() {
  return `<div class="audio-mini"><span class="audio-mini-icon">${icon('volume', 15)}</span><span><strong>Original audio</strong><small>${state.edit?.voice || state.edit?.dub ? 'Voice mix active' : 'Original only'}</small></span><span class="chip ${state.edit?.dub ? 'green' : ''}">${state.edit?.dub ? 'Dub' : state.edit?.voice ? 'Voice' : 'Audio'}</span></div>
  ${inspectorVoice()}`;
}

function inspectorSFX() {
  const rows = state.edit?.sfx || [];
  return `<div class="sfx-add-grid">
    <button class="btn small" type="button" data-action="sfx-add" data-kind="sound">${icon('volume', 13)} Sound</button>
    <button class="btn small" type="button" data-action="sfx-add" data-kind="image">${icon('grid', 13)} Image</button>
    <button class="btn small" type="button" data-action="sfx-add" data-kind="gif">${icon('film', 13)} GIF</button>
    <button class="btn small" type="button" data-action="sfx-add" data-kind="sticker">${icon('sparkle', 13)} Sticker</button>
    <button class="btn small" type="button" data-action="sfx-add" data-kind="layer">${icon('layers', 13)} Layer</button>
    <button class="btn small" type="button" data-action="sfx-text">${icon('captions', 13)} Text</button>
  </div>
  <div class="sfx-list">
    ${rows.length ? rows.map((effect) => `<div class="sfx-row"><span class="sfx-kind">${esc(effect.kind)}</span><span class="sfx-name">${esc(effect.name || effect.text || 'Effect')}</span><button class="icon-btn" type="button" data-action="sfx-remove" data-effect="${esc(effect.id)}" title="Remove">${icon('trash', 14)}</button></div>`).join('') : '<p class="small muted">No effects yet. Add text, a sticker, a filter or a sound.</p>'}
  </div>`;
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
  const dub = state.edit?.dub;
  const music = state.edit?.music;
  const cues = scriptCues();
  const active = dub || voice;
  return `<div class="field"><label>Local voice</label><select data-action="voice-select">
    ${state.voices.length ? state.voices.slice(0, 120).map((item) => `<option value="${esc(item.name)}" ${item.name === state.voiceName ? 'selected' : ''}>${esc(item.label || item.name)} · ${esc(item.locale)}</option>`).join('') : `<option>${esc(state.voiceName)}</option>`}
  </select></div>
  <div class="field"><label>Voice-over mode</label><select data-action="voice-mode">
    <option value="voice_over" ${state.voiceMode === 'voice_over' ? 'selected' : ''}>Over original sound</option>
    <option value="voice_only" ${state.voiceMode === 'voice_only' ? 'selected' : ''}>Voice only</option>
  </select></div>
  ${state.voicePreview ? `<audio class="inline-audio" controls autoplay src="${esc(state.voicePreview)}"></audio>` : ''}
  <div class="voice-actions">
    <button class="btn wide" type="button" data-action="voice-generate">${icon('voice', 14)} Add voice-over</button>
    ${active ? `<button class="btn wide" type="button" data-action="voice-preview">${icon('play', 14)} Preview ${dub ? 'dub' : 'voice'}</button>` : ''}
  </div>
  <div class="record-row">
    ${state.recording
      ? `<button class="btn wide record-live" type="button" data-action="record-stop">${icon('stop', 14)} Stop recording</button>`
      : `<button class="btn wide" type="button" data-action="record-start">${icon('voice', 14)} Record voice-over</button>`}
    <p class="small muted">${state.recording ? 'Recording from the microphone…' : 'Or record your own voice.'}</p>
  </div>
  <div class="media-rule"></div>
  <div class="voice-section">
    <strong>Dub</strong>
    <p class="small muted">Speaks the current script. Original audio is muted; add music if you want a bed.</p>
    <button class="btn wide" type="button" data-action="dub-build">${icon('captions', 14)} ${dub ? 'Rebuild dub' : 'Build dub'}</button>
    ${dub ? `<p class="small" style="color:var(--green-ink)">Dub · ${esc(dub.voice)} · ${esc(dub.language || '')}</p>` : ''}
  </div>
  <div class="voice-section">
    <strong>Background music</strong>
    ${music ? `<div class="kv"><span>${esc(music.name || 'Music')}</span><button class="btn small" type="button" data-action="remove-music">Remove</button></div>` : `<button class="btn wide" type="button" data-action="add-music">${icon('volume', 14)} Add music</button>`}
  </div>
  ${cues.length ? `<div class="voice-section"><div class="toggle-row"><strong>Preview a line</strong><span class="small muted">${cues.length} cues</span></div>
    <div class="line-preview-list">${(state.showAllCues ? cues : cues.slice(0, 4)).map((cue) => `<div class="line-preview"><span>${esc(truncate(cue.text || '', 54))}</span><button class="btn small" type="button" data-action="voice-line" data-cue="${esc(cue.id)}">${icon('play', 11)}</button></div>`).join('')}</div>
    ${cues.length > 4 ? `<button class="btn small wide" type="button" data-action="toggle-cues">${state.showAllCues ? 'Show fewer lines' : `Show all ${cues.length} lines`}</button>` : ''}
  </div>` : '<p class="small muted">Generate captions first; they are the voice script.</p>'}`;
}

/* ------------------------------------------------------------------ clean */

function screenClean() {
  const allScenes = getScenes();
  const mineTotal = mineLayers(state.edit?.clean || []).length;
  const scenes = state.cleanFilter === 'mine'
    ? allScenes.filter((item) => mineLayers(sceneLayers(item)).length)
    : allScenes;
  const scene = currentScene();
  if (!scene) return emptyEditor();
  const layers = sceneLayers(scene);
  const layer = layers.find((item) => item.id === state.selectedLayerId) || layers[0] || null;
  const checked = sceneCleanCount(allScenes);
  const hasProof = state.previewCache.has(scene.id);
  const detectPct = Math.round(stagePct('text') * 100);
  return `<main class="screen">
    <div class="workspace clean">
      <aside class="panel">
        <div class="panel-head"><h2>Scenes</h2><span class="meta">${scenes.length} shown / ${allScenes.length} total</span></div>
        <div class="clean-filter">
          <div class="segmented" style="grid-template-columns:1fr 1fr">
            <button class="${state.cleanFilter === 'all' ? 'is-active' : ''}" type="button" data-action="clean-filter" data-filter="all">All ${allScenes.length}</button>
            <button class="${state.cleanFilter === 'mine' ? 'is-active' : ''}" type="button" data-action="clean-filter" data-filter="mine" ${mineTotal ? '' : 'disabled'}>Yours ${mineTotal}</button>
          </div>
        </div>
        <div class="clean-scene-list">
          ${scenes.length ? '' : '<p class="small muted clean-empty">No layers you set. Clean all keeps your Fill, Blur or Off choices.</p>'}
          ${scenes.map((item) => {
            const at = allScenes.indexOf(item);
            const status = cleanState(item);
            const hasProof = state.previewCache.has(item.id);
            const cleaning = state.previewStatus.get(item.id) === 'cleaning';
            const failed = state.previewStatus.get(item.id) === 'failed';
            return `<button class="clean-scene${at === state.selectedScene ? ' is-active' : ''}" type="button" data-action="select-scene" data-index="${at}">
              <img src="${state.previewCache.get(item.id) || frameUrl(sceneMid(item))}" alt="">
              <span><span class="clean-scene-title">${esc(truncate(sceneTitle(item, at), 30))}${mineLayers(sceneLayers(item)).length ? ' <span class="chip amber yours-chip">Yours</span>' : ''}</span><span class="clean-scene-sub">${fmtTime(item.start)} – ${fmtTime(item.end)}</span></span>
              <span class="chip ${failed ? 'red' : cleaning ? 'amber' : status === 'Layered' ? 'green' : ''}">${failed ? 'Failed' : cleaning ? 'Cleaning' : hasProof ? 'Proof' : status === 'Layered' ? 'Layered' : status}</span>
            </button>`;
          }).join('')}
        </div>
      </aside>

      <section style="display:grid;gap:14px;min-width:0">
        <section class="panel" style="overflow:hidden">
          ${state.brushMode ? brushStage(scene) : splitStage(scene, { showCleaning: true, useCleanUrl: true })}
        </section>
        <section class="panel clean-scene-strip">
          <div class="scene-strip-head"><h3>Scene strip · clean status</h3><span class="small muted">${checked}/${allScenes.length} layered</span>${sceneStripControls('clean-scenes')}</div>
          <div class="scene-strip" id="clean-scenes">
            ${scenes.map((item) => {
              const at = allScenes.indexOf(item);
              const status = cleanState(item);
              return `<button class="scene-tile${at === state.selectedScene ? ' is-active' : ''}" type="button" data-action="select-scene" data-index="${at}">
                <span class="thumb"><img src="${state.previewCache.get(item.id) || frameUrl(sceneMid(item))}" alt=""><span class="tc">${pad(at + 1)}</span></span>
                <span class="scene-label">${mineLayers(sceneLayers(item)).length ? 'Yours' : state.previewCache.has(item.id) ? 'Proof' : status === 'Layered' ? 'Layered' : status}</span>
              </button>`;
            }).join('')}
          </div>
        </section>
      </section>

      <aside class="panel inspector">
        <div class="panel-head"><h2>Clean</h2><span class="meta">${checked}/${allScenes.length} layered</span></div>
        <div class="inspector-body">
          <div class="field"><div class="toggle-row"><span class="small muted">Text detect</span><strong class="mono small">${detectPct}%</strong></div><div class="progress"><span style="width:${detectPct}%"></span></div></div>
          <div class="proof-pair">
            <figure><div class="frame"><img src="${frameUrl(sceneMid(scene))}" alt=""></div><figcaption>Before</figcaption></figure>
            <span class="arrow">${icon('chevronRight', 14)}</span>
            <figure><div class="frame"><img src="${afterFrameUrl(scene)}" alt=""></div><figcaption>${state.previewCache.has(scene.id) ? 'After' : 'After · no proof yet'}</figcaption></figure>
          </div>
          <div class="segmented">
            ${['fill', 'blur', 'exclude'].map((action) => {
              const label = action === 'exclude' ? 'Off' : action[0].toUpperCase() + action.slice(1);
              const active = layer && ((action === 'fill' && layer.enabled !== false && layer.kind === 'fill') || (action === 'blur' && layer.enabled !== false && layer.kind === 'blur') || (action === 'exclude' && layer.enabled === false));
              return `<button class="${active ? 'is-active' : ''}" type="button" data-action="clean-action" data-layer="${esc(layer?.id || '')}" data-kind="${action}" ${layer ? '' : 'disabled'}>${label}</button>`;
            }).join('')}
          </div>
          ${layer ? `<p class="layer-note${layerRisk(layer) ? ' is-warn' : ''}">${esc(layerNote(layer))}</p>` : ''}
          ${layer ? `<div class="box-editor">
            <span class="rail-head">Fill box · normalized</span>
            <div class="box-grid">
              <label>X <input id="box-x" type="number" min="0" max="1" step="0.005" value="${Number(layer.box?.x || 0).toFixed(3)}"></label>
              <label>Y <input id="box-y" type="number" min="0" max="1" step="0.005" value="${Number(layer.box?.y || 0).toFixed(3)}"></label>
              <label>W <input id="box-w" type="number" min="0.01" max="1" step="0.005" value="${Number(layer.box?.w || 0.1).toFixed(3)}"></label>
              <label>H <input id="box-h" type="number" min="0.01" max="1" step="0.005" value="${Number(layer.box?.h || 0.1).toFixed(3)}"></label>
            </div>
            <div class="box-actions"><button class="btn small" type="button" data-action="box-apply" data-layer="${esc(layer.id)}">Apply box</button><button class="btn small" type="button" data-action="recheck-scene">Re-check &amp; re-apply</button></div>
          </div>` : ''}
          <div class="fill-engine-line"><span class="rail-head">AI fill engine</span>${fillEngineControl()}</div>
          ${layerListMarkup(layer, layers, 'No text detected in this scene yet.')}
          <button class="btn wide" type="button" data-action="prove-scene" data-index="${allScenes.indexOf(scene)}" ${state.previewRunning ? 'disabled' : ''}>${icon('sparkle', 14)} ${hasProof ? 'Prove again · blur' : 'Prove this scene · blur'}</button>
          <button class="btn wide" type="button" data-action="brush-toggle">${icon('sparkle', 14)} ${state.brushMode ? 'Close brush' : 'Paint a mask'}</button>
          <div class="model-line"><span class="dot${state.engine?.fill?.ready ? '' : ' is-idle'}"></span><strong>AI fill · ${state.engine?.fill?.ready ? 'ready' : 'missing'}</strong><span>${esc(fillStatusText())}</span>${state.engine?.fill?.ready ? '' : `<button class="btn small" type="button" data-action="settings">Set up</button>`}</div>
          ${checked === scenes.length
            ? `<button class="btn primary wide" type="button" data-action="nav" data-screen="preview">${icon('play', 15)} Preview clean</button><button class="btn wide" type="button" data-action="clean-all">${icon('sparkle', 14)} Clean all scenes</button>`
            : `<button class="btn primary wide" type="button" data-action="clean-all">${icon('sparkle', 15)} Clean all scenes</button><button class="btn wide" type="button" data-action="nav" data-screen="preview">${icon('play', 14)} Preview</button>`}
          <button class="btn wide" type="button" data-action="nav" data-screen="edit">${icon('arrowLeft', 14)} Back to Edit</button>
        </div>
      </aside>
    </div>
  </main>`;
}

function brushStage(scene) {
  return `<div class="brush-stage" style="aspect-ratio:${mediaAspect()};min-height:380px">
    <img src="${frameUrl(sceneMid(scene))}" alt="Frame to paint">
    <canvas id="brush-canvas" aria-label="Paint a clean mask"></canvas>
    <div class="brush-toolbar">
      <div class="segmented" style="width:170px">
        <button class="${state.brushKind === 'fill' ? 'is-active' : ''}" type="button" data-action="brush-kind" data-kind="fill">Fill</button>
        <button class="${state.brushKind === 'blur' ? 'is-active' : ''}" type="button" data-action="brush-kind" data-kind="blur">Blur</button>
      </div>
      <label class="brush-size">Size <input id="brush-size" type="range" min="0.008" max="0.08" step="0.004" value="${state.brushSize}"></label>
      <button class="btn small" type="button" data-action="brush-undo">Undo</button>
      <button class="btn small" type="button" data-action="brush-clear">Clear</button>
      <button class="btn small primary" type="button" data-action="brush-apply">Apply mask</button>
      <button class="btn small" type="button" data-action="brush-toggle">Cancel</button>
    </div>
  </div>`;
}

function seekToTime(time) {
  const total = Number(document.querySelector('.timeline')?.dataset.total || 0);
  const mediaBefore = !!document.querySelector('.story-media-preview');
  state.timelineTime = Math.max(0, Math.min(total || Number(time || 0), Number(time || 0)));
  state.previewTime = timelineToSource(state.timelineTime);
  const video = document.querySelector('video[data-preview]');
  if (video) {
    try { video.currentTime = state.previewTime; } catch (_) { /* metadata not ready */ }
  }
  updateTimelinePlayhead(state.timelineTime);
  updateGhostActive();
  refreshTranscriptOverlay();
  const mediaAfter = isStoryEdit() && storyClipAt(state.timelineTime)?.clip?.kind === 'media';
  if (mediaBefore || mediaAfter) {
    render();
    const player = document.querySelector('video[data-preview]');
    if (player) {
      try { player.currentTime = state.previewTime; } catch (_) { /* metadata not ready */ }
    }
  }
}

function updateGhostActive() {
  const time = Number(state.timelineTime || 0);
  document.querySelectorAll('.ghost-line').forEach((line) => {
    const start = Number(line.dataset.start || 0);
    const end = Number(line.dataset.end || 0);
    line.classList.toggle('is-current', time >= start && time < end);
  });
}

async function loadAudioWaveforms() {
  if (!state.project || !state.edit) return;
  const waves = [...document.querySelectorAll('.audio-wave[data-track]')];
  if (!waves.length) return;
  const rows = editAudioRows();
  for (const wave of waves) {
    const id = wave.dataset.track || '';
    const row = rows.find((item) => String(item.id) === id);
    if (!row) continue;
    const offset = Math.max(0, Number(wave.dataset.offset || 0));
    const duration = Math.max(0.05, Number(wave.dataset.duration || 0.05));
    const count = Math.max(6, Math.min(64, Math.round((wave.clientWidth || 48) / 2)));
    const key = `${id}:${offset.toFixed(2)}:${duration.toFixed(2)}:${count}`;
    if (state.waveformCache.has(key)) {
      const peaks = state.waveformCache.get(key);
      wave.innerHTML = peaks.map((peak) => `<i style="height:${Math.max(8, peak * 100).toFixed(0)}%"></i>`).join('');
      continue;
    }
    const buffer = await audioBufferFor(row);
    if (!buffer) continue;
    const peaks = waveformPeaks(buffer.getChannelData(0), buffer.duration, offset, duration, count);
    state.waveformCache.set(key, peaks);
    wave.innerHTML = peaks.map((peak) => `<i style="height:${Math.max(8, peak * 100).toFixed(0)}%"></i>`).join('');
  }
}

function setupAudioRows() {
  document.querySelectorAll('.audio-track-card').forEach((card) => {
    const id = String(card.dataset.audioRow || '');
    if (!id) return;
    card.addEventListener('toggle', () => {
      if (card.open) state.openAudioRows.add(id);
      else state.openAudioRows.delete(id);
    });
    card.querySelectorAll('summary button').forEach((button) => {
      button.addEventListener('click', (event) => event.preventDefault());
    });
    card.querySelectorAll('[data-audio-field="volume"]').forEach((input) => {
      const value = input.parentElement.querySelector('.audio-value');
      input.addEventListener('input', () => { if (value) value.textContent = Number(input.value).toFixed(2); });
    });
  });
}

function setupAudioDrag() {
  document.querySelectorAll('.audio-block').forEach((block) => {
    block.addEventListener('pointerdown', (event) => {
      if (!window.PointerEvent) return;
      const total = Number(document.querySelector('.timeline')?.dataset.total || 0);
      const lane = block.parentElement;
      if (total <= 0 || !lane) return;
      const rect = lane.getBoundingClientRect();
      const startValue = Number(block.dataset.start || 0);
      const durationValue = Number(block.dataset.duration || 0.2);
      const offsetValue = Number(block.dataset.offset || 0);
      const edge = event.target.closest('.audio-handle')?.dataset.edge || 'move';
      const originX = event.clientX;
      const pointerId = event.pointerId;
      let nextStart = startValue;
      let nextDuration = durationValue;
      let nextOffset = offsetValue;
      let moved = false;
      block.setPointerCapture?.(pointerId);
      event.preventDefault();
      const move = (moveEvent) => {
        const delta = ((moveEvent.clientX - originX) / Math.max(1, rect.width)) * total;
        if (Math.abs(moveEvent.clientX - originX) > 2) moved = true;
        if (edge === 'start') {
          const end = startValue + durationValue;
          nextStart = Math.max(0, Math.min(end - 0.2, startValue + delta));
          nextDuration = end - nextStart;
          nextOffset = Math.max(0, offsetValue + (nextStart - startValue));
        } else if (edge === 'end') {
          nextStart = startValue;
          nextDuration = Math.max(0.2, Math.min(total - startValue, durationValue + delta));
        } else {
          nextStart = Math.max(0, Math.min(total - durationValue, startValue + delta));
          nextDuration = durationValue;
        }
        block.style.left = `${(nextStart / total * 100).toFixed(2)}%`;
        block.style.width = `${(nextDuration / total * 100).toFixed(2)}%`;
        let tip = document.querySelector('.audio-drag-tip');
        if (!tip) {
          tip = document.createElement('span');
          tip.className = 'audio-drag-tip';
          document.body.appendChild(tip);
        }
        tip.textContent = `${nextStart.toFixed(2)}s – ${(nextStart + nextDuration).toFixed(2)}s`;
        tip.style.left = `${moveEvent.clientX + 10}px`;
        tip.style.top = `${moveEvent.clientY - 26}px`;
      };
      const up = async () => {
        block.removeEventListener('pointermove', move);
        block.removeEventListener('pointerup', up);
        block.removeEventListener('pointercancel', up);
        document.querySelector('.audio-drag-tip')?.remove();
        if (!moved) return;
        block.dataset.dragged = '1';
        await patchAudioTrack(block.dataset.track || '', {
          start: Number(nextStart.toFixed(3)),
          duration: Number(nextDuration.toFixed(3)),
          offset: Number(nextOffset.toFixed(3)),
        });
      };
      block.addEventListener('pointermove', move);
      block.addEventListener('pointerup', up);
      block.addEventListener('pointercancel', up);
    }, { capture: true });
    block.addEventListener('click', (event) => {
      if (block.dataset.dragged === '1') {
        block.dataset.dragged = '0';
        event.preventDefault();
        event.stopPropagation();
      }
    }, { capture: true });
  });
}

function setupTimelineRuler() {
  const ruler = document.getElementById('timeline-ruler');
  if (!ruler) return;
  const total = Number(ruler.dataset.total || 0);
  if (total <= 0) return;
  const apply = (event) => {
    const rect = ruler.getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width)));
    seekToTime(fraction * total);
  };
  ruler.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    ruler.setPointerCapture(event.pointerId);
    apply(event);
    const move = (moveEvent) => apply(moveEvent);
    const up = () => {
      ruler.removeEventListener('pointermove', move);
      ruler.removeEventListener('pointerup', up);
      ruler.removeEventListener('pointercancel', up);
    };
    ruler.addEventListener('pointermove', move);
    ruler.addEventListener('pointerup', up);
    ruler.addEventListener('pointercancel', up);
  });
}

function updateTimelinePlayhead(time) {
  const timeline = document.querySelector('.timeline');
  const head = timeline?.querySelector('.timeline-playhead');
  const total = Number(timeline?.dataset.total || 0);
  if (!head || total <= 0) return;
  head.style.left = `${Math.max(0, Math.min(100, (Number(time) / total) * 100)).toFixed(2)}%`;
  const rulerHead = timeline?.querySelector('.ruler-playhead');
  if (rulerHead) rulerHead.style.left = head.style.left;
}

function setupBrushCanvas() {
  const canvas = document.getElementById('brush-canvas');
  if (!canvas) return;
  const stage = canvas.parentElement;
  const context = canvas.getContext('2d');
  const resize = () => {
    const rect = stage.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width));
    canvas.height = Math.max(1, Math.round(rect.height));
    draw();
  };
  const draw = () => {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = 'rgba(217,119,22,.45)';
    for (const stroke of state.brushStrokes) {
      const radius = Math.max(2, stroke.r * canvas.width);
      for (const point of stroke.points) {
        context.beginPath();
        context.arc(point.x * canvas.width, point.y * canvas.height, radius, 0, Math.PI * 2);
        context.fill();
      }
    }
  };
  let drawing = false;
  let stroke = null;
  const point = (event) => {
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
    };
  };
  canvas.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    drawing = true;
    stroke = { r: state.brushSize, points: [point(event)] };
    state.brushStrokes.push(stroke);
    draw();
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!drawing || !stroke) return;
    stroke.points.push(point(event));
    draw();
  });
  const end = () => { drawing = false; stroke = null; };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  resize();
}

async function applyBrush() {
  if (!state.project || !state.edit || !state.brushStrokes.length) {
    toast('Paint at least one stroke.', 'bad');
    return;
  }
  const scene = currentScene();
  if (!scene) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/manual`, {
      method: 'POST',
      body: JSON.stringify({
        kind: state.brushKind,
        start: scene.start,
        end: scene.end,
        strokes: state.brushStrokes,
      }),
    });
    state.edit = data.edit;
    state.brushMode = false;
    state.brushStrokes = [];
    state.selectedLayerId = data.layer?.id || '';
    state.previewCache.delete(scene.id);
    state.previewStatus.set(scene.id, 'pending');
    render();
    toast('Brush mask added.');
  } catch (error) {
    toast(`Brush: ${error.message}`, 'bad');
  }
}

function layerBoxAt(layer, time) {
  const track = Array.isArray(layer?.track) ? layer.track : [];
  const fallback = layer?.box || { x: 0, y: 0, w: 0, h: 0 };
  if (!track.length) return fallback;
  const points = track.filter((item) => item?.box);
  if (!points.length) return fallback;
  let before = points[0];
  let after = points[points.length - 1];
  for (const point of points) {
    if (Number(point.t || 0) <= time) before = point;
    if (Number(point.t || 0) >= time) { after = point; break; }
  }
  if (before === after) return before.box;
  const span = Math.max(0.001, Number(after.t || 0) - Number(before.t || 0));
  const mix = Math.max(0, Math.min(1, (time - Number(before.t || 0)) / span));
  const box = (key) => Number(before.box[key] || 0) + (Number(after.box[key] || 0) - Number(before.box[key] || 0)) * mix;
  return { x: box('x'), y: box('y'), w: box('w'), h: box('h') };
}

function detectionLayers(scene, time) {
  return sceneLayers(scene)
    .filter((layer) => layer.enabled !== false)
    .filter((layer) => !(layer.ranges || []).length || (layer.ranges || []).some((range) => (
      Number(range.start || 0) <= time && Number(range.end || 0) > time
    )))
    .map((layer) => ({ layer, box: layerBoxAt(layer, time) }));
}

function updateDetectionOverlay(player, scene) {
  const overlay = document.querySelector('[data-detect-overlay]');
  if (!overlay || !scene) return;
  const stage = player.parentElement;
  const vw = Number(player.videoWidth || 0);
  const vh = Number(player.videoHeight || 0);
  if (stage && vw && vh) {
    const scale = Math.min(stage.clientWidth / vw, stage.clientHeight / vh);
    const width = vw * scale;
    const height = vh * scale;
    Object.assign(overlay.style, {
      left: `${(stage.clientWidth - width) / 2}px`,
      top: `${(stage.clientHeight - height) / 2}px`,
      width: `${width}px`,
      height: `${height}px`,
      right: 'auto',
      bottom: 'auto',
    });
  }
  const boxes = detectionLayers(scene, Number(player.currentTime || 0));
  overlay.innerHTML = boxes.map(({ layer, box }) => {
    const label = layer.label || LAYER_KIND[layer.tracklet_kind] || 'Text';
    return `<span class="detect-box ${layer.kind === 'blur' ? 'is-blur' : 'is-fill'}" style="left:${(box.x * 100).toFixed(2)}%;top:${(box.y * 100).toFixed(2)}%;width:${(box.w * 100).toFixed(2)}%;height:${(box.h * 100).toFixed(2)}%"><span class="detect-tag">${esc(layer.kind === 'blur' ? 'Blur' : label).slice(0, 22)}</span></span>`;
  }).join('');
}

function setupInlineDetectionReview() {
  const player = document.querySelector('[data-inline-player]');
  if (!player) return;
  const scene = currentScene();
  if (!scene) return;
  const start = Number(player.dataset.start || scene.start || 0);
  const end = Number(player.dataset.end || scene.end || 0);
  const seek = () => {
    try { player.currentTime = start; } catch (_) { /* metadata not ready */ }
    updateDetectionOverlay(player, scene);
  };
  if (player.readyState >= 1) seek();
  else player.addEventListener('loadedmetadata', seek, { once: true });
  const update = () => {
    if (end > start && player.currentTime >= end - 0.04) {
      player.pause();
      player.currentTime = end - 0.04;
    }
    updateDetectionOverlay(player, scene);
  };
  player.addEventListener('timeupdate', update);
  player.addEventListener('seeked', update);
  player.addEventListener('play', update);
  update();
}

function proofTime(scene) {
  const layers = sceneLayers(scene).filter((layer) => layer.enabled !== false && (layer.ranges || []).length);
  if (!layers.length) return Number(sceneMid(scene));
  const first = layers[0].ranges[0] || {};
  return Number(first.start ?? scene.start ?? 0) + 0.05;
}

function proofBoxes(scene) {
  const at = Number(proofTime(scene));
  const live = (layer) => {
    const ranges = layer.ranges || [];
    if (!ranges.length) return true;
    return ranges.some((range) => Number(range.start || 0) <= at && at <= Number(range.end || 0));
  };
  const boxAt = (layer) => {
    const track = layer.track || [];
    if (!track.length) return layer.box;
    return track.reduce((best, item) => (
      Math.abs(Number(item.t || 0) - at) < Math.abs(Number(best.t || 0) - at) ? item : best
    ), track[0]).box || layer.box;
  };
  return sceneLayers(scene)
    .filter((layer) => layer.enabled !== false && live(layer))
    .map((layer) => {
      const box = boxAt(layer);
      if (!box) return '';
      return `<span class="proof-box" style="left:${(Number(box.x || 0) * 100).toFixed(2)}%;top:${(Number(box.y || 0) * 100).toFixed(2)}%;width:${(Number(box.w || 0) * 100).toFixed(2)}%;height:${(Number(box.h || 0) * 100).toFixed(2)}%"></span>`;
    }).join('');
}

function proofStepBar(hasProof) {
  const step = hasProof ? (state.proofStep || 1) : 1;
  return `<div class="proof-steps" aria-label="Proof steps">
    ${[[1, 'Detect'], [2, 'Compare'], [3, 'Review']].map(([number, label]) => `<button class="proof-step${step === number ? ' is-active' : ''}" type="button" data-action="proof-step" data-step="${number}" ${number > 1 && !hasProof ? 'disabled' : ''} aria-pressed="${step === number}">${number} · ${label}</button>`).join('')}
  </div>`;
}

function sequenceSegments() {
  if (isStoryEdit()) {
    const out = [];
    let skipped = 0;
    (state.edit?.clips || []).forEach((clip) => {
      if (clip.kind === 'media') { skipped += 1; return; }
      const start = Number(clip.start || 0);
      const end = Number(clip.end || 0);
      if (end > start + 0.02) out.push({ start, end, label: storyClipLabel(clip, out.length) });
    });
    return { segments: out, skipped };
  }
  const segments = getScenes()
    .map((scene, index) => ({ start: Number(scene.start || 0), end: Number(scene.end || 0), label: `Scene ${pad(index + 1)}` }))
    .filter((segment) => segment.end > segment.start + 0.02);
  return { segments, skipped: 0 };
}

function sequenceBar() {
  return `<div class="sequence-bar" data-sequence-bar>
    <button class="player-play" type="button" data-action="sequence-play" aria-label="Play or pause the sequence">${icon('play', 13)}</button>
    <span class="sequence-time" data-sequence-time>00:00 / 00:00</span>
    <input id="sequence-scrub" class="sequence-scrub" type="range" min="0" max="1000" value="0" step="1" aria-label="Seek in the sequence">
    <span class="sequence-label" data-sequence-label></span>
    <button class="sequence-close" type="button" data-action="sequence-close" aria-label="Close the sequence">${icon('close', 12)}</button>
  </div>`;
}

function sequenceElapsed(video) {
  const before = state.sequenceSegments.slice(0, state.sequenceIndex).reduce((sum, item) => sum + Math.max(0, item.end - item.start), 0);
  const seg = state.sequenceSegments[state.sequenceIndex] || { start: 0 };
  return before + Math.max(0, Math.min(Number(video.currentTime || 0) - seg.start, (state.sequenceSegments[state.sequenceIndex]?.end || 0) - seg.start));
}

function paintSequence(video) {
  const bar = document.querySelector('[data-sequence-bar]');
  if (!bar || !video) return;
  const total = state.sequenceTotal || 0;
  const elapsed = sequenceElapsed(video);
  const time = bar.querySelector('[data-sequence-time]');
  if (time) time.textContent = `${clockText(elapsed)} / ${clockText(total)}`;
  const scrub = bar.querySelector('#sequence-scrub');
  if (scrub && total > 0) scrub.value = String(Math.round((elapsed / total) * 1000));
  const label = bar.querySelector('[data-sequence-label]');
  if (label) {
    const seg = state.sequenceSegments[state.sequenceIndex] || { label: '' };
    label.textContent = `${isStoryEdit() ? 'Story' : 'All scenes'} · ${state.sequenceIndex + 1} of ${state.sequenceSegments.length} · ${seg.label}${state.sequenceSkipped ? ` · ${state.sequenceSkipped} image beat${state.sequenceSkipped === 1 ? '' : 's'} skipped` : ''}`;
  }
  const play = bar.querySelector('.player-play');
  if (play) play.innerHTML = video.paused ? icon('play', 13) : icon('pause', 13);
}

function advanceSequence(video) {
  if (state.sequenceIndex + 1 < state.sequenceSegments.length) {
    state.sequenceIndex += 1;
    const next = state.sequenceSegments[state.sequenceIndex];
    try { video.currentTime = next.start; } catch (_error) { /* metadata not ready */ }
    video.play().catch(() => {});
  } else {
    video.pause();
    state.sequencePlaying = false;
  }
  paintSequence(video);
}

function setupSequencePlayer() {
  const video = document.querySelector('[data-sequence-player]');
  if (!video) return;
  const first = state.sequenceSegments[state.sequenceIndex];
  const start = () => {
    try { video.currentTime = first.start; } catch (_error) { /* metadata not ready */ }
    video.play().then(() => { state.sequencePlaying = true; paintSequence(video); }).catch(() => {});
  };
  video.addEventListener('timeupdate', () => {
    if (!state.sequenceActive) return;
    const seg = state.sequenceSegments[state.sequenceIndex];
    if (seg && video.currentTime >= seg.end - 0.03) advanceSequence(video);
    paintSequence(video);
  });
  video.addEventListener('loadedmetadata', start, { once: true });
  video.addEventListener('play', () => { state.sequencePlaying = true; paintSequence(video); });
  video.addEventListener('pause', () => { state.sequencePlaying = false; paintSequence(video); });
  if (video.readyState >= 1) start();
  paintSequence(video);
}

function startSequence() {
  const { segments, skipped } = sequenceSegments();
  if (!segments.length) {
    toast('Nothing to play in this edit.', 'bad');
    return;
  }
  state.sequenceActive = true;
  state.sequenceSegments = segments;
  state.sequenceIndex = 0;
  state.sequenceSkipped = skipped;
  state.sequenceTotal = segments.reduce((sum, item) => sum + Math.max(0, item.end - item.start), 0);
  state.sequencePlaying = false;
  state.inlinePlaying = false;
  render();
  setupSequencePlayer();
}

function sequenceSeek(fraction) {
  const video = document.querySelector('[data-sequence-player]');
  if (!video || !state.sequenceSegments.length) return;
  const target = Math.max(0, Math.min(1, Number(fraction) || 0)) * (state.sequenceTotal || 0);
  let before = 0;
  let index = 0;
  for (let i = 0; i < state.sequenceSegments.length; i += 1) {
    const length = Math.max(0, state.sequenceSegments[i].end - state.sequenceSegments[i].start);
    if (target <= before + length || i === state.sequenceSegments.length - 1) {
      index = i;
      break;
    }
    before += length;
  }
  state.sequenceIndex = index;
  const seg = state.sequenceSegments[index];
  try { video.currentTime = seg.start + Math.max(0, target - before); } catch (_error) { /* metadata not ready */ }
  paintSequence(video);
}

function splitStage(scene, { showCleaning = false, useCleanUrl = false, steps = false, inlineCta = true, overlay = '' } = {}) {
  const view = state.previewView || 'compare';
  if (!scene) return '';
  if (state.sequenceActive) {
    const first = state.sequenceSegments[state.sequenceIndex] || { start: scene.start || 0 };
    return `<div class="split-stage inline-player sequence-player" style="aspect-ratio:${mediaAspect()};min-height:380px">
      <video data-sequence-player playsinline poster="${frameUrl(first.start || 0)}" src="${sourceUrl()}"></video>
      ${sequenceBar()}
    </div>`;
  }
  if (state.inlinePlaying) {
    return `<div class="split-stage inline-player" style="aspect-ratio:${mediaAspect()};min-height:380px">
      <video data-inline-player data-app-player data-start="${Number(scene.start || 0).toFixed(3)}" data-end="${Number(scene.end || 0).toFixed(3)}" autoplay playsinline poster="${frameUrl(sceneMid(scene))}" src="${sourceUrl()}"></video>${playerBar()}
      <div class="detect-overlay" data-detect-overlay></div>
      <span class="detect-legend">Detection review · blur preview</span>
      <button class="btn small inline-close" type="button" data-action="close-inline-player">${icon('arrowLeft', 12)} Back to proof</button>
    </div>`;
  }
  const at = getScenes().indexOf(scene);
  const shot = steps ? proofTime(scene) : Number(sceneMid(scene));
  const status = state.previewStatus.get(scene.id) || 'pending';
  const cached = state.previewCache.get(scene.id) || '';
  const after = cached || frameUrl(shot);
  const blurred = showCleaning && status === 'cleaning';
  const scenes = getScenes();
  const readyCount = scenes.filter((item) => state.previewCache.has(item.id)).length;
  const beforeMarkup = `<img src="${frameUrl(shot)}" alt="Before">`;
  const afterMarkup = `<img src="${after}" alt="After">`;
  const cleaningMarkup = showCleaning && blurred ? `<span class="cleaning-pill"><span class="dot"></span>Cleaning ${readyCount}/${scenes.length}</span>` : '';
  const mediaOverlay = `<div class="media-overlay"><button type="button" data-action="play-source" aria-label="Play source">${icon('play', 14)}</button><span class="tc">${fmtTC(scene.start, 24)} – ${fmtTC(scene.end, 24)}</span><span class="spacer"></span><span class="small" style="opacity:.82">${esc(cleanState(scene))}</span></div>`;
  const safeOverlay = overlay;
  const cta = `<div class="proof-cta"><span>${cached ? 'Blur proof ready.' : 'No proof yet. A proof is a fast blur, not the AI fill.'}</span><button class="btn small${cached ? '' : ' primary'}" type="button" data-action="prove-scene" data-index="${at}" ${state.previewRunning ? 'disabled' : ''}>${icon('sparkle', 12)} ${cached ? 'Prove again' : 'Prove this scene'}</button></div>`;

  if (steps) {
    const step = cached ? (state.proofStep || 1) : 1;
    const detect = `<div class="split-stage" data-split="0" style="aspect-ratio:${mediaAspect()};min-height:380px">${beforeMarkup}${proofBoxes(scene)}<span class="split-tag before">Detect · blur area</span>${mediaOverlay}${overlay}</div>`;
    const compare = `<div class="split-stage" data-split="50" style="aspect-ratio:${mediaAspect()};min-height:380px">
      ${beforeMarkup}
      <div class="after-layer">${afterMarkup}</div>
      <span class="split-tag before">Before</span>
      <span class="split-tag after">After · blur</span>
      <span class="split-handle" aria-hidden="true"></span>
      ${mediaOverlay}${overlay}
    </div>`;
    const review = `<div class="split-stage" data-split="0" style="aspect-ratio:${mediaAspect()};min-height:380px"><div class="after-layer">${afterMarkup}</div><span class="split-tag after">After · blur</span>${mediaOverlay}${overlay}</div>`;
    return `<div class="proof-frame">${proofStepBar(Boolean(cached))}${step === 1 ? detect : step === 2 ? compare : review}${inlineCta ? cta : ''}</div>`;
  }

  if (view === 'before') {
    return `<div class="split-stage" data-split="0" style="aspect-ratio:${mediaAspect()};min-height:380px">${beforeMarkup}<span class="split-tag before">Before</span>${mediaOverlay}${overlay}</div>`;
  }
  if (view === 'after') {
    return `<div class="proof-frame"><div class="split-stage" data-split="0" style="aspect-ratio:${mediaAspect()};min-height:380px"><div class="after-layer${blurred ? ' is-cleaning' : ''}">${afterMarkup}</div><span class="split-tag after">After</span>${cleaningMarkup}${mediaOverlay}${safeOverlay}</div>${cta}</div>`;
  }
  return `<div class="proof-frame"><div class="split-stage" data-split="50" style="aspect-ratio:${mediaAspect()};min-height:380px">
    ${beforeMarkup}
    <div class="after-layer${blurred ? ' is-cleaning' : ''}">${afterMarkup}</div>
    <span class="split-tag before">Before</span>
    <span class="split-tag after">After</span>
    <span class="split-handle" aria-hidden="true"></span>
    ${cleaningMarkup}
    ${mediaOverlay}${safeOverlay}
  </div>${cta}</div>`;
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

const SAFE_ZONES = {
  tiktok: {
    label: 'TikTok', ratio: 9 / 16,
    top: 240 / 1920, bottom: 660 / 1920, left: 120 / 1080, right: 120 / 1080,
    block: { x: 780 / 1080, y: 840 / 1920, w: 180 / 1080, h: 1080 / 1920 },
    source: 'TikTok In-Feed safe-zone template, 720×1280 scaled ×1.5',
  },
  reels: {
    label: 'Reels', ratio: 9 / 16,
    top: 0.14, bottom: 0.35, left: 0.06, right: 0.06,
    block: { x: 1 - 0.06 - 0.16, y: 0.60, w: 0.16, h: 0.40 },
    source: 'Meta Ads Guide: 14 % top, 35 % bottom, 6 % sides',
  },
  shorts: {
    label: 'Shorts', ratio: 9 / 16,
    top: 288 / 1920, bottom: 672 / 1920, left: 48 / 1080, right: 192 / 1080,
    source: 'Google universal vertical ad template: 288 / 672 / 48 / 192 px',
  },
  ig45: {
    label: 'IG 4:5', ratio: 4 / 5, titleSafe: 0.10,
    source: 'No player chrome in Feed; 10 % title-safe; the 3:4 profile grid trims about 34 px a side',
  },
  ig11: {
    label: 'IG 1:1', ratio: 1, titleSafe: 0.10,
    source: 'No player chrome in Feed; 10 % title-safe; the 3:4 profile grid trims about 135 px a side',
  },
  youtube: {
    label: 'YouTube 16:9', ratio: 16 / 9, titleSafe: 0.10,
    source: 'No chrome over a 16:9 frame; 10 % title-safe is a convention, Google publishes its 16:9 template as an image',
  },
};

function cutOutputRatio() {
  const meta = state.check?.result?.meta || state.edit?.source || state.sourceMeta || {};
  const sw = Number(meta.width || 0);
  const sh = Number(meta.height || 0);
  const cut = state.edit?.cut || {};
  const crop = cut.crop;
  if (crop) {
    const cw = Math.max(0.02, Number(crop.w) || 1);
    const ch = Math.max(0.02, Number(crop.h) || 1);
    return ((sw || 16) * cw) / ((sh || 9) * ch);
  }
  const sizes = { '9:16': 9 / 16, '1:1': 1, '4:5': 4 / 5, '16:9': 16 / 9 };
  if (cut.aspect && sizes[cut.aspect]) return sizes[cut.aspect];
  return sw && sh ? sw / sh : 16 / 9;
}

function safeZoneFrame() {
  const meta = state.check?.result?.meta || state.edit?.source || state.sourceMeta || {};
  const sw = Number(meta.width || 0);
  const sh = Number(meta.height || 0);
  const stageRatio = sw && sh ? sw / sh : 16 / 9;
  const outRatio = cutOutputRatio();
  return outRatio >= stageRatio
    ? { width: 100, height: (stageRatio / outRatio) * 100 }
    : { width: (outRatio / stageRatio) * 100, height: 100 };
}

function safeZoneOverlay() {
  const zone = SAFE_ZONES[state.safeZone];
  if (!zone) return '';
  const frame = safeZoneFrame();
  const bands = [];
  const safe = {};
  if (zone.titleSafe) {
    const inset = zone.titleSafe;
    ['top', 'bottom', 'left', 'right'].forEach((edge) => {
      const style = {
        top: `top:0;left:0;right:0;height:${inset * 100}%`,
        bottom: `bottom:0;left:0;right:0;height:${inset * 100}%`,
        left: `left:0;top:0;bottom:0;width:${inset * 100}%`,
        right: `right:0;top:0;bottom:0;width:${inset * 100}%`,
      }[edge];
      bands.push(`<span class="sz-band" style="${style}"></span>`);
    });
    Object.assign(safe, { left: inset, right: inset, top: inset, bottom: inset });
  } else {
    bands.push(`<span class="sz-band" style="top:0;left:0;right:0;height:${zone.top * 100}%"></span>`);
    bands.push(`<span class="sz-band" style="bottom:0;left:0;right:0;height:${zone.bottom * 100}%"></span>`);
    bands.push(`<span class="sz-band" style="left:0;top:${zone.top * 100}%;height:${(1 - zone.top - zone.bottom) * 100}%;width:${zone.left * 100}%"></span>`);
    bands.push(`<span class="sz-band" style="right:0;top:${zone.top * 100}%;height:${(1 - zone.top - zone.bottom) * 100}%;width:${zone.right * 100}%"></span>`);
    if (zone.block) {
      bands.push(`<span class="sz-band sz-block" style="left:${zone.block.x * 100}%;top:${zone.block.y * 100}%;width:${zone.block.w * 100}%;height:${zone.block.h * 100}%"></span>`);
    }
    safe.left = zone.left;
    safe.right = zone.right;
    safe.top = zone.top;
    safe.bottom = zone.bottom;
  }
  const outline = `<span class="sz-safe" style="left:${safe.left * 100}%;right:${safe.right * 100}%;top:${safe.top * 100}%;bottom:${safe.bottom * 100}%"></span>`;
  return `<div class="safe-zone" aria-label="${esc(zone.label)} safe zone">
    <div class="safe-frame" style="width:${frame.width.toFixed(2)}%;height:${frame.height.toFixed(2)}%">
      ${bands.join('')}${outline}
      <span class="sz-label">${esc(zone.label)} · safe area</span>
    </div>
  </div>`;
}

function safeZoneMatches(zone) {
  if (!zone) return false;
  return Math.abs(cutOutputRatio() - zone.ratio) <= 0.01;
}

function safeZonePanel() {
  const zone = SAFE_ZONES[state.safeZone];
  const mismatch = zone && !safeZoneMatches(zone);
  return `<div class="safe-zone-panel">
    <button class="btn wide${state.safeZoneOpen ? ' primary' : ''}" type="button" data-action="safe-zone-toggle" aria-pressed="${state.safeZoneOpen}">${icon('grid', 13)} Safe zones${zone ? ` · ${esc(zone.label)}` : ''}</button>
    ${state.safeZoneOpen ? `<div class="segmented safe-zone-list">
      <button class="${state.safeZone === 'off' ? 'is-active' : ''}" type="button" data-action="safe-zone" data-zone="off">Off</button>
      ${Object.entries(SAFE_ZONES).map(([id, item]) => `<button class="${state.safeZone === id ? 'is-active' : ''}" type="button" data-action="safe-zone" data-zone="${id}">${esc(item.label)}</button>`).join('')}
    </div>
    <p class="small muted sz-source">${esc(zone ? zone.source : 'Pick a platform. Guides are drawn on the Cut output frame.')}</p>
    ${mismatch ? `<p class="small sz-warn">This guide is ${zone.ratio > 1 ? '16:9' : zone.ratio === 1 ? '1:1' : zone.ratio === 0.8 ? '4:5' : '9:16'}; the Cut is another shape. Set the Cut aspect first, or the guide is not true.</p>` : ''}` : ''}
  </div>`;
}



function screenPreview() {
  const scenes = getScenes();
  const scene = currentScene();
  if (!scene) return emptyEditor();
  const proofScenes = proofTargets(scenes);
  const ready = sceneReadyCount(scenes);
  const needsProof = sceneNeedsProof(scene);
  const status = needsProof ? (state.previewStatus.get(scene.id) || 'pending') : 'no-text';
  const activeJob = activeRenderJob();
  const meta = state.check?.result?.meta || state.edit?.source || state.sourceMeta || {};
  const portrait = Number(meta.height || 0) > Number(meta.width || 0);
  const ratio = Number(meta.width || 0) && Number(meta.height || 0) ? (Number(meta.width) / Number(meta.height)).toFixed(4) : '1.7778';
  return `<main class="screen">${storyContextBar()}${storyThesisBar(state.edit?.story)}
    <div class="workspace preview${portrait ? ' portrait' : ''}">
      <section class="preview-main">
        <section class="panel preview-stage${portrait ? ' portrait-stage' : ''}" style="overflow:hidden;--stage-ratio:${ratio}">
          ${state.brushMode ? brushStage(scene) : splitStage(scene, { showCleaning: true, useCleanUrl: true, steps: true, inlineCta: false, overlay: state.safeZone !== 'off' && safeZoneMatches(SAFE_ZONES[state.safeZone]) ? safeZoneOverlay() : '' })}
        </section>
        <section class="panel preview-scenes">
          <div class="scene-strip-head"><h3>Scenes · ${scenes.length} total</h3><span class="small muted">${ready}/${proofScenes.length} proofs</span>${sceneStripControls('preview-scenes')}</div>
          <div class="scene-strip" id="preview-scenes">
            ${scenes.map((item, index) => {
              const itemStatus = sceneNeedsProof(item) ? (state.previewStatus.get(item.id) || 'pending') : 'no-text';
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
          <div class="ready-row"><span class="ready-icon" style="${status === 'ready' ? '' : 'background:var(--amber-soft);color:var(--amber-ink)'}">${status === 'ready' ? icon('check', 12) : icon('loader', 12)}</span><span class="ready-main"><strong>${status === 'no-text' ? 'No text' : status === 'ready' ? 'Proof generated' : status === 'failed' ? 'Clean failed' : status === 'cleaning' ? 'Cleaning…' : 'No proof yet'}</strong><span>${status === 'no-text' ? 'Nothing to clean in this scene.' : status === 'ready' ? 'Review it in the steps below' : status === 'cleaning' ? 'Building a blur proof from this scene.' : 'A proof is a fast blur; press Prove this scene.'}</span></span></div>
        </section>

        <section class="panel preview-actions">
          <div class="panel-head" style="padding-bottom:8px"><h2>Preview</h2><span class="meta">${ready}/${proofScenes.length}</span></div>
          <div class="panel-pad" style="padding-top:0;display:grid;gap:9px">
            <button class="btn wide" type="button" data-action="play-sequence">${icon('play', 14)} ${isStoryEdit() ? 'Play story order' : 'Play all scenes'}</button>
            <button class="btn wide" type="button" data-action="prove-scene" data-index="${state.selectedScene}" ${state.previewRunning ? 'disabled' : ''}>${icon('sparkle', 14)} ${state.previewCache.has(scene.id) ? 'Prove this scene again · blur' : 'Prove this scene · blur'}</button>
            ${safeZonePanel()}
            <button class="btn wide" type="button" data-action="preview-reclean">${icon('loader', 14)} Re-clean this scene</button>
            <button class="btn wide" type="button" data-action="clean-all">${icon('sparkle', 14)} Clean all</button>
            ${status === 'failed' ? `<p class="small" style="color:var(--red)">This scene failed. Retry before render.</p>` : ''}
          </div>
        </section>

        <section class="panel readiness">
          <div class="readiness-head"><strong>Proofs</strong><span>${ready} / ${proofScenes.length} text scenes</span></div>
          <div class="progress"><span style="width:${proofScenes.length ? (ready / proofScenes.length) * 100 : 0}%"></span></div>
          <p class="readiness-note">Proofs are optional review frames. You can render any time. ${ready}/${proofScenes.length} text scenes have a proof.</p>
          <button class="btn wide" type="button" data-action="proof-all" ${state.previewRunning ? 'disabled' : ''}>${icon('sparkle', 13)} Prove remaining scenes · blur</button>
        </section>

        <button class="btn ${activeJob ? '' : 'primary'} wide" type="button" data-action="nav" data-screen="render" style="height:46px;font-size:15px">${icon(activeJob ? 'loader' : 'arrowRight', 15)} ${activeJob ? `View active render · ${renderPercent(activeJob)}%` : 'Continue to Render'}</button>
      </aside>
    </div>
  </main>`;
}

function previewStatusLabel(value) {
  return ({ ready: 'Proof', cleaning: 'Cleaning…', failed: 'Failed', pending: 'Needs proof', queued: 'Queued', 'no-text': 'No text' }[value] || 'Needs proof');
}

/* ------------------------------------------------------------------ render */

// ---- render cost: the AI fill estimate, shown before a render starts ----

function renderEstimateKey() {
  if (!state.project || !state.edit) return '';
  const finished = state.queue.filter((item) => item.state === 'done').length;
  const device = state.settings?.fill?.device || 'cpu';
  return `${state.project.id}|${state.edit.id}|${state.edit.updated || 0}|${state.cleanVersion}|${finished}|${device}`;
}

async function fetchRenderEstimate() {
  const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/render/estimate`);
  return data;
}

function renderEstimateHtml() {
  const payload = state.renderEstimate;
  if (!payload) return `<p class="render-cost-line muted">Working out the AI fill time…</p>`;
  if (payload.failed) return `<p class="render-cost-line muted">AI fill time could not be worked out.</p>`;
  const working = payload.state === 'working';
  const measuring = working
    ? `<p class="render-cost-line muted">Measuring the fill… ${Math.round(Math.max(0, Math.min(1, payload.progress || 0)) * 100)}%</p>`
    : '';
  const estimate = payload.estimate || null;
  if (!estimate) {
    return measuring || `<p class="render-cost-line muted">Working out the AI fill time…</p>`;
  }
  const oldNote = working ? ' Old figure: the edit changed since it was measured.' : '';
  const layers = estimate.layers || {};
  const disk = estimate.disk?.low ? `<p class="render-cost-warn">${esc(estimate.disk.text)}</p>` : '';
  if (!estimate.beats) return `<p class="render-cost-line muted">No AI fill in this render.</p>${disk}`;
  const left = estimate.beats - estimate.beats_cached;
  const head = left
    ? `AI fill · up to ${esc(fmtDuration(estimate.seconds))}`
    : 'AI fill · already done';
  const basis = !left ? 'adds no time' : estimate.measured ? 'measured on this Mac' : 'first guess, no render measured here yet';
  const detail = [
    `${fmtDuration(estimate.fill_seconds)} of video in ${layers.fill} fill layer${layers.fill === 1 ? '' : 's'}`,
    estimate.beats_cached && left ? `${estimate.beats_cached} of ${estimate.beats} clips already filled` : '',
    basis,
  ].filter(Boolean).join(' · ');
  const span = estimate.total_range && estimate.total_range.length === 2
    ? `${esc(fmtDuration(estimate.total_range[0]))}–${esc(fmtDuration(estimate.total_range[1]))}`
    : estimate.total_seconds ? esc(fmtDuration(estimate.total_seconds)) : '';
  const whole = span
    ? `<p class="render-cost-note">Whole render ≈ ${span} on this Mac, fill and check included. The range is this Mac's own spread.${esc(oldNote)}</p>`
    : `<p class="render-cost-note">Whole render time is not measured on this Mac yet.${esc(oldNote)}</p>`;
  const checkNote = estimate.check_seconds
    ? `<p class="render-cost-note">Check reads ${estimate.check_layers} layers, ≈ ${esc(fmtDuration(estimate.check_seconds))}. Lines under 5 frames are not judged; they are counted as not checked.</p>`
    : '';
  return `${measuring}<p class="render-cost-line${left && estimate.seconds >= 600 ? ' is-long' : ''}"><strong>${head}</strong><span>${esc(detail)}</span></p>${whole}${checkNote}${disk}`;
}

function paintRenderEstimate() {
  document.querySelectorAll('[data-render-estimate]').forEach((node) => { node.innerHTML = renderEstimateHtml(); });
}

// Asks once per edit state. The screen is patched in place, never re-rendered.
function ensureRenderEstimate() {
  const key = renderEstimateKey();
  if (!key || state.renderEstimateKey === key) return;
  state.renderEstimateKey = key;
  state.renderEstimate = null;
  fetchRenderEstimate()
    .then((payload) => {
      if (state.renderEstimateKey !== key) return;
      state.renderEstimate = payload;
      paintRenderEstimate();
      if (payload.state === 'working') {
        window.setTimeout(() => {
          if (state.renderEstimateKey === key) {
            state.renderEstimateKey = '';
            ensureRenderEstimate();
          }
        }, 700);
      }
    })
    .catch(() => {
      if (state.renderEstimateKey === key) {
        state.renderEstimate = { failed: true };
        paintRenderEstimate();
      }
    });
}

function fillEngineControl() {
  const device = state.settings?.fill?.device === 'cpu' ? 'cpu' : 'gpu';
  const gpuReady = Boolean(state.engine?.fill?.gpu_ready);
  const cpuReady = Boolean(state.engine?.fill?.cpu_ready);
  const gpuNote = String(state.engine?.fill?.gpu_problem || '');
  let note = '';
  if (device === 'gpu') {
    note = gpuReady
      ? 'Apple GPU. Measured 4.6× faster on this Mac; same output.'
      : esc(gpuNote || 'GPU is unavailable.');
  } else if (cpuReady) {
    note = 'CPU engine. Slower, but it runs when the GPU is busy.';
  } else {
    note = `CPU engine is optional. <button class="btn small" type="button" data-action="settings">Download in Settings</button>`;
  }
  if (device === 'gpu' && !cpuReady) {
    note += `<br>CPU engine is optional. <button class="btn small" type="button" data-action="settings">Download in Settings</button>`;
  }
  return `<div class="segmented" style="grid-template-columns:repeat(2,minmax(0,1fr))">
    <button class="${device === 'cpu' ? 'is-active' : ''}" type="button" data-action="fill-device" data-device="cpu" ${cpuReady ? '' : 'disabled'} title="${esc(state.engine?.fill?.cpu_problem || 'CPU engine is not installed')}">CPU</button>
    <button class="${device === 'gpu' ? 'is-active' : ''}" type="button" data-action="fill-device" data-device="gpu" ${gpuReady ? '' : 'disabled'} title="${esc(gpuNote || 'Apple GPU')}">GPU</button>
  </div>
  <p class="small muted">${note}</p>`;
}

function screenRender() {
  const scenes = getScenes();
  const checked = sceneReadyCount(scenes);
  const captions = state.edit?.captions?.cues?.length ? 1 : 0;
  const voice = state.edit?.voice ? 1 : 0;
  const dub = state.edit?.dub ? 1 : 0;
  const music = state.edit?.music ? 1 : 0;
  const outputPath = state.settings?.storage?.data_root && state.project
    ? `${state.settings.storage.data_root}/projects/${state.project.id}/renders`
    : '';
  const outputLabel = outputPath
    ? outputPath.replace(state.settings?.storage?.data_root || '', '').replace(/^\//, '')
    : 'Project render folder';
  const fps = Math.round(Number(state.edit?.source?.fps || 24));
  const sourceMeta = state.edit?.source || state.sourceMeta || {};
  const sourceW = Number(sourceMeta.width || 0);
  const sourceH = Number(sourceMeta.height || 0);
  const resolutionLabel = outputSizeLabel();
  const activeJobs = state.queue.filter((item) => ['queued', 'running', 'rendering', 'paused'].includes(item.state)).length;
  const activeJob = activeRenderJob();
  const proofTotal = proofTargets(scenes).length;
  const mine = state.project
    ? state.queue.filter((item) => !item.project_id || item.project_id === state.project.id)
    : state.queue;
  const queue = state.queueScope === 'all' ? state.queue : mine;
  const elsewhere = state.queue.length - mine.length;
  const cleanOn = (state.edit?.clean || []).filter((layer) => layer.enabled !== false);
  const lastCheck = state.queue.find(
    (item) => item.state === 'done' && item.edit_id === state.edit?.id && item.checked_frames,
  ) || null;
  let checkTimes = [];
  try { checkTimes = lastCheck ? JSON.parse(lastCheck.check_times || '[]') : []; } catch (_) { checkTimes = []; }
  let checkFlicker = {};
  try { checkFlicker = lastCheck ? JSON.parse(lastCheck.check_flicker || '{}') : {}; } catch (_) { checkFlicker = {}; }
  const roughLines = Object.values(checkFlicker).filter((value) => Number(value) > 2.2).length;
  const cleanFill = cleanOn.filter((layer) => layer.kind !== 'blur').length;
  const cleanBlur = cleanOn.length - cleanFill;
  const movingBlur = cleanOn.filter((layer) => layer.kind === 'blur' && layer.quality === 'moving').length;
  const movingFill = cleanOn.filter((layer) => layer.kind !== 'blur' && layer.quality === 'moving').length;
  ensureRenderEstimate();
  const done = queue.filter((item) => item.state === 'done');
  const leftover = lastCheck
    ? `Checked ${lastCheck.checked_frames} frames · ${lastCheck.check_hits} found${Number(lastCheck.check_unchecked) ? ` · ${lastCheck.check_unchecked} line${Number(lastCheck.check_unchecked) === 1 ? '' : 's'} not checked` : ''}`
    : 'No check yet';
  return `<main class="screen">${storyContextBar()}
    <div class="workspace render">
      <aside class="render-left">
        <section class="panel render-left-panel">
          <div class="panel-head"><h2>Render settings</h2><span class="meta">${resolutionLabel}</span></div>
          <div class="render-settings">
            <div class="render-setting"><div class="setting-head">${icon('sparkle', 14)} AI fill engine</div>${fillEngineControl()}</div>
            <div class="render-setting"><div class="setting-head">${icon('film', 14)} Frame rate</div><select data-action="render-fps"><option>${fps || 24} fps</option><option>30 fps</option></select></div>
            <div class="render-setting"><div class="setting-head">${icon('volume', 14)} Audio mix</div><div class="readonly">${dub ? `Dub${music ? ' + music' : ''}` : state.edit?.voice ? `Voice over + original${music ? ' + music' : ''}` : music ? 'Original + music' : 'Original audio'}</div></div>
            <div class="render-setting"><div class="setting-head">${icon('captions', 14)} Captions</div>
                <div class="toggle-row"><span>Burn into video</span><label class="switch"><input type="checkbox" data-action="caption-burn" ${state.edit?.captions?.burn ? 'checked' : ''}><i></i></label></div>
                <div class="toggle-row"><span>Write .srt file</span><label class="switch"><input type="checkbox" data-action="caption-srt" ${state.edit?.captions?.srt ? 'checked' : ''}><i></i></label></div>
              </div>
            <div class="render-setting"><div class="setting-head">${icon('folder', 14)} Output</div><div class="path-row"><span class="path" title="${esc(outputPath)}">${esc(outputLabel)}</span>${outputPath ? `<button class="btn small" type="button" data-action="reveal" data-path="${esc(outputPath)}">${icon('folderOpen', 11)} Show</button>` : ''}</div><div class="small muted">${state.settings?.storage?.free_bytes ? `${fmtBytes(state.settings.storage.free_bytes)} free` : 'Local storage'}</div></div>
          </div>
          <div class="render-start">
            ${activeJob ? `<div class="render-live"><div><strong>${state.queuePaused ? 'Render paused' : activeJob.state === 'queued' ? 'Render queued' : 'Rendering'} · ${renderPercent(activeJob)}%</strong><span>${esc(activeJob.title || 'Current render')}</span></div><div class="render-live-actions">${state.queuePaused ? `<button class="btn small" type="button" data-action="resume-queue">Resume</button>` : `<button class="btn small" type="button" data-action="pause-queue">Pause</button>`}<button class="btn small" type="button" data-action="cancel-render" data-project="${esc(activeJob.project_id || state.project?.id || '')}" data-edit="${esc(activeJob.edit_id || '')}">Cancel</button></div></div>` : `<button class="btn primary wide start" type="button" data-action="start-render">${icon('play', 16)} Start render</button>`}
            <p class="readiness-note">${activeJob ? 'A render is already running. Pause, cancel, or wait for it to finish.' : 'Proofs are optional. Start render now, or review frames later.'}</p>
          </div>
          <div class="render-cost" data-render-estimate aria-live="polite">${renderEstimateHtml()}</div>
          <div class="render-facts">
            <div class="fact"><span>Proofs</span><strong>${checked}/${proofTotal} text scenes</strong></div>
            <div class="fact"><span>Clean</span><strong>${cleanOn.length ? `${cleanFill} fill · ${cleanBlur} blur · ${movingFill} moving` : 'No text layers'}</strong></div>
            <div class="fact"><span>Captions</span><strong>${captions ? '1 track' : 'None'}</strong></div>
            <div class="fact"><span>Voice</span><strong>${dub ? 'Dub track' : voice ? 'Voice-over track' : 'None'}</strong></div>
            <div class="fact"><span>Music</span><strong>${music ? '1 track' : 'None'}</strong></div>
            <div class="fact"><span>Leftover</span><strong class="${lastCheck && (lastCheck.check_hits || Number(lastCheck.check_unchecked)) ? 'is-warn' : ''}">${esc(leftover)}</strong></div>
            ${roughLines ? `<p class="small" style="margin:0;color:var(--amber-ink)">${roughLines} line${roughLines === 1 ? '' : 's'} above flicker 2.2.</p>` : ''}
            ${movingBlur ? `<p class="small muted" style="margin:0">${movingBlur} line${movingBlur === 1 ? '' : 's'} use Blur instead of AI fill.</p>` : ''}
          </div>
        </section>
      </aside>

      <section class="render-right">
        <section class="panel render-queue">
          <div class="render-queue-head"><h2>Render queue · ${queue.length} ${queue.length === 1 ? 'job' : 'jobs'}</h2><div style="display:flex;gap:6px">${elsewhere ? `<button class="btn small" type="button" data-action="queue-scope">${state.queueScope === 'all' ? 'This project' : `All projects · ${state.queue.length}`}</button>` : ''}${queue.some((item) => ['done', 'failed', 'cancelled'].includes(item.state)) ? `<button class="btn small" type="button" data-action="clear-queue">Clear finished</button>` : ''}${state.queuePaused ? `<button class="btn small" type="button" data-action="resume-queue">${icon('play', 12)} Resume</button>` : activeJobs ? `<button class="btn small" type="button" data-action="pause-queue">${icon('pause', 12)} Pause</button>` : `<button class="btn small" type="button" disabled>Queue idle</button>`}</div></div>
          <div class="queue-head-row"><span>Project / Story</span><span>Edit</span><span>Duration</span><span>Resolution</span><span>State</span><span>Progress</span><span>Output</span></div>
          ${queue.length ? queue.map((item) => renderQueueRow(item)).join('') : `<div class="queue-empty">${elsewhere ? `No renders for this project. ${elsewhere} job${elsewhere === 1 ? '' : 's'} in other projects.` : 'No jobs yet. Start a render from Preview.'}</div>`}
        </section>
        ${done.length ? `<section class="panel render-done">
          <div class="panel-head"><h2>Finished renders</h2><span class="meta">${done.length}</span></div>
          <div class="done-grid">${done.map((item) => doneCard(item)).join('')}</div>
        </section>` : ''}
      </section>
    </div>
  </main>`;
}

function doneCard(item) {
  const real = item.elapsed_seconds ? `real ${fmtDuration(item.elapsed_seconds)}` : '';
  const estimate = item.estimate_seconds ? `est ${fmtDuration(item.estimate_seconds)}` : '';
  return `<article class="done-card">
    <img src="${frameUrl(0.5, item.project_id)}" alt="">
    <strong title="${esc(item.title || 'Render')}">${esc(item.title || 'Render')}</strong>
    <span>${esc(item.project_name || 'Project')} · ${real}${real && estimate ? ' · ' : ''}${estimate}</span>
    <div class="done-actions">
      <button class="btn small" type="button" data-action="play-render" data-project="${esc(item.project_id)}" data-edit="${esc(item.edit_id)}">${icon('play', 11)} Play</button>
      <button class="btn small" type="button" data-action="reveal" data-path="${esc(item.output || '')}">${icon('folderOpen', 11)} Show</button>
    </div>
  </article>`;
}

function renderQueueRow(item) {
  const pct = Math.round((Number(item.progress) || 0) * 100);
  const active = item.state === 'running' || item.state === 'rendering' || item.state === 'queued' || item.state === 'paused';
  const duration = item.duration ? fmtDuration(item.duration) : (item.edit_id === state.edit?.id ? fmtDuration(state.edit?.end || 0) : '—');
  return `<div class="queue-item${active ? ' is-active' : ''}">
    <div class="queue-story"><img src="${frameUrl(0.5, item.project_id)}" alt=""><div><strong title="${esc(item.project_name || 'Project')} · ${esc(item.title || 'Render')}">${esc(item.title || 'Render')}</strong><span>${esc(item.project_name || 'Project')} · ${duration} · ${item.width && item.height ? `${item.width}×${item.height}` : '1080p'} · v1${item.state === 'done' && item.elapsed_seconds ? ` · est ${fmtDuration(item.estimate_seconds || 0)} · real ${fmtDuration(item.elapsed_seconds)}` : ''}</span></div></div>
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
    <div class="modal-body"><video data-app-player autoplay src="${url}"></video>${playerBar()}</div>
  </dialog>`);
}

function openAudioModal(url, title = 'Voice-over') {
  openModal(`<dialog class="modal" aria-label="${esc(title)}">
    <div class="modal-head"><h2>${esc(title)}</h2><button class="icon-btn" type="button" data-action="close-modal" aria-label="Close">${icon('close', 16)}</button></div>
    <div class="modal-body"><audio controls autoplay style="width:100%" src="${url}"></audio></div>
  </dialog>`);
}

function openSearch() {
  const project = state.project;
  openModal(`<dialog class="modal search-modal" aria-label="Search">
    <div class="modal-head"><h2>Search</h2><button class="icon-btn" type="button" data-action="close-modal" aria-label="Close">${icon('close', 16)}</button></div>
    <div class="modal-body">
      <input id="global-search" class="search-field" type="search" autofocus placeholder="${project ? 'Search scenes and transcript' : 'Search projects'}" aria-label="Search">
      <div id="search-results" class="search-results"></div>
    </div>
  </dialog>`);
  const input = document.getElementById('global-search');
  if (!input) return;
  const draw = () => {
    const query = input.value.trim().toLowerCase();
    const box = document.getElementById('search-results');
    if (!box) return;
    if (!project) {
      const rows = state.projects.filter((item) => item.name.toLowerCase().includes(query)).slice(0, 20);
      box.innerHTML = rows.length
        ? rows.map((item) => `<button class="search-result" type="button" data-action="search-project" data-project="${esc(item.id)}"><span class="chip">Project</span><span><strong>${esc(item.name)}</strong><small>${esc(relDate(item.updated))} · ${fmtBytes(item.source_bytes)}</small></span></button>`).join('')
        : '<p class="small muted">No projects match.</p>';
      return;
    }
    const scenes = getScenes();
    const sceneRows = scenes
      .map((scene, index) => ({ index, text: sceneTitle(scene, index), start: Number(scene.start || 0), end: Number(scene.end || 0) }))
      .filter((row) => row.text.toLowerCase().includes(query));
    const segmentRows = getSegments()
      .filter((segment) => String(segment.text || '').toLowerCase().includes(query))
      .map((segment) => ({
        text: segment.text,
        start: Number(segment.start || 0),
        end: Number(segment.end || 0),
        index: Math.max(0, scenes.findIndex((scene) => Number(scene.end || 0) > Number(segment.start || 0) && Number(scene.start || 0) < Number(segment.end || 0))),
      }));
    const rows = [...sceneRows, ...segmentRows].slice(0, 24);
    box.innerHTML = rows.length
      ? rows.map((row) => `<button class="search-result" type="button" data-action="search-scene" data-index="${row.index}"><span class="chip">Scene ${pad(row.index + 1)}</span><span><strong>${esc(truncate(row.text, 90))}</strong><small>${fmtTC(row.start, 24)} – ${fmtTC(row.end, 24)}</small></span></button>`).join('')
      : `<p class="small muted">${query ? 'No scenes or transcript lines match.' : 'Type to search this project.'}</p>`;
  };
  input.addEventListener('input', draw);
  draw();
  input.focus();
}

async function setCaptionSrt(value) {
  if (!state.project || !state.edit) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/captions`, {
      method: 'PATCH',
      body: JSON.stringify({ srt: Boolean(value) }),
    });
    state.edit.captions = data.captions || state.edit.captions;
    render();
    toast(value ? 'A .srt file will be written next to the render.' : 'No .srt file will be written.');
  } catch (error) {
    toast(`Caption file: ${error.message}`, 'bad');
  }
}

async function setFillDevice(device) {
  if (device !== 'cpu' && device !== 'gpu') return;
  try {
    const data = await api('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify({ fill_device: device }),
    });
    state.settings = data;
    state.renderEstimateKey = '';
    state.renderEstimate = null;
    render();
    toast(device === 'gpu' ? 'AI fill will use the GPU.' : 'AI fill will use the CPU.');
  } catch (error) {
    toast(`Fill engine: ${error.message}`, 'bad');
  }
}

async function saveTranslationSettings() {
  try {
    const engine = document.querySelector('#translation-engine')?.value || 'auto';
    const path = document.querySelector('#translation-path')?.value || '';
    if (engine === 'custom' && !path) {
      toast('Choose a model folder first.', 'bad');
      return;
    }
    const data = await api('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify({ translation_engine: engine, translation_model_path: path }),
    });
    state.settings = data;
    const status = await api('/api/translation/model').catch(() => null);
    if (status && !status.ready) {
      toast(`Saved, but missing: ${(status.missing || []).join(', ') || 'model files'}.`, 'bad');
      return;
    }
    toast('Translation settings saved.');
  } catch (error) {
    toast(`Translation settings: ${error.message}`, 'bad');
  }
}

function chooseModelFolder() {
  if (window.webkit?.messageHandlers?.duck) {
    window.webkit.messageHandlers.duck.postMessage({ type: 'chooseModelFolder' });
    return;
  }
  toast('The folder picker is only available in the app.', 'bad');
}

function chooseFillModelFolder() {
  if (window.webkit?.messageHandlers?.duck) {
    window.webkit.messageHandlers.duck.postMessage({ type: 'chooseModelFolder', target: 'fill' });
    return;
  }
  toast('The folder picker is only available in the app.', 'bad');
}

async function saveFillModel(path) {
  try {
    const data = await api('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify({ fill_model_path: path || '' }),
    });
    state.settings = data;
    const model = data?.fill?.model || {};
    toast(path
      ? (model.ready ? 'Fill will use your model.' : `Saved, but: ${model.problem || 'that folder cannot be used.'}`)
      : 'Fill will use the default engine.');
    if (typeof openSettings === 'function') await openSettings();
  } catch (error) {
    toast(`Fill model: ${error.message}`, 'bad');
  }
}

window.duckModelFolder = async (path, target) => {
  if (target === 'fill') {
    await saveFillModel(path || '');
    return;
  }
  const input = document.querySelector('#translation-path');
  if (input) input.value = path || '';
  const engine = document.querySelector('#translation-engine');
  if (engine) engine.value = 'custom';
  await saveTranslationSettings();
  if (typeof openSettings === 'function') await openSettings();
};

window.duckModelFolderError = (message) => toast(String(message || 'Could not use that folder.'), 'bad');

function packListMarkup() {
  return (state.packs || []).map((pack) => {
    const pct = pack.size_bytes ? Math.min(100, Math.round((Number(pack.downloaded_bytes || 0) / pack.size_bytes) * 100)) : 0;
    return `<div class="pack-row"><div><strong>${esc(pack.name)}</strong><span>${fmtBytes(pack.size_bytes)} · ${esc(pack.license)} · ${esc(pack.detail)}</span>${pack.downloading ? `<div class="progress"><span style="width:${pct}%"></span></div>` : ''}${pack.error ? `<span class="pack-error">${esc(pack.error)}</span>` : ''}</div>${pack.installed ? `<button class="btn small" type="button" data-action="remove-pack" data-pack="${esc(pack.id)}">Remove</button>` : pack.downloading ? `<span class="small muted">${pct}%</span>` : `<button class="btn small" type="button" data-action="download-pack" data-pack="${esc(pack.id)}">Download</button>`}</div>`;
  }).join('') || '<p class="small muted">No optional packs.</p>';
}

async function openSettings() {
  try {
    if (!state.voices.length) await loadVoices();
    const [models, settings, packs] = await Promise.all([
      api('/api/models').catch(() => ({ models: [] })),
      api('/api/settings').catch(() => state.settings),
      api('/api/packs').catch(() => ({ packs: [] })),
    ]);
    state.models = models.models || [];
    state.settings = settings || state.settings;
    state.packs = packs.packs || [];
  } catch (_) { /* keep current */ }
  const storage = state.settings?.storage || {};
  const translationEngine = state.settings?.translation?.engine || 'auto';
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

          <div class="kv"><span>Voices</span><strong>${state.voices.length ? `${state.voices.length} local` : '—'}</strong></div>
          <div class="kv"><span>Rewrite</span><strong>${state.engine?.rewrite?.available ? 'Ready' : 'Off'}</strong></div>
          ${state.engine?.rewrite?.available ? '' : `<p class="small muted">${esc(
            state.engine?.rewrite?.reason === 'appleIntelligenceNotEnabled'
              ? 'Apple Intelligence is off. Turn it on in System Settings → Apple Intelligence & Siri to enable Rewrite.'
              : `Rewrite: ${state.engine?.rewrite?.reason || 'Apple Intelligence is unavailable.'}`
          )}</p>`}
          <h3 style="margin-top:12px">Translation</h3>
          <div class="field"><label for="translation-engine">Engine</label>
            <select id="translation-engine">
              <option value="auto" ${(state.settings?.translation?.engine || 'auto') === 'auto' ? 'selected' : ''}>Apple Translation</option>
              <option value="custom" ${state.settings?.translation?.engine === 'custom' ? 'selected' : ''}>A model I provide</option>
            </select>
          </div>
          <div class="field"><label for="translation-path">Model folder</label>
            <div class="path-row">
              <input id="translation-path" type="text" value="${esc(state.settings?.translation?.custom_path || '')}" placeholder="Choose a CTranslate2 folder" ${translationEngine === 'custom' ? '' : 'disabled'}>
              <button class="btn small" type="button" data-action="choose-model-folder">${icon('folder', 12)} Choose</button>
            </div>
          </div>
          <button class="btn small" type="button" data-action="save-translation">Save translation</button>
          <p class="small muted">DuckSuite ships no translation model and downloads none. Point it at a CTranslate2 folder you obtained yourself: it needs model.bin, config.json and sentencepiece.bpe.model. The folder is copied into DuckSuite.</p>
          <h3 style="margin-top:10px">Models</h3>
          ${state.models.map((model) => `<div class="kv"><span>${esc(model.label || model.id)}</span><strong>${model.ready ? 'Ready' : 'Missing'} <button class="btn small" type="button" data-action="verify-model" data-model="${esc(model.id)}">Verify</button>${model.file ? `<button class="btn small" type="button" data-action="reveal" data-path="${esc(model.file)}">Show</button>` : ''}</strong></div>`).join('') || '<p class="small muted">No models reported.</p>'}
          ${(() => {
            const fillModel = state.settings?.fill?.model || {};
            const stateText = fillModel.path
              ? (fillModel.ready ? `In use · ${fillModel.file}` : `Not usable · ${fillModel.problem || 'unknown reason'}`)
              : 'None';
            return `<div class="kv"><span>Your fill model</span><strong>${esc(stateText)} <button class="btn small" type="button" data-action="choose-fill-model">${icon('folder', 11)} ${fillModel.path ? 'Replace' : 'Choose'}</button>${fillModel.path ? `<button class="btn small" type="button" data-action="clear-fill-model">Clear</button>` : ''}</strong></div>`;
          })()}
          <p class="small muted">A fill model you obtained yourself runs in place of the default engine. DuckSuite ships none and downloads none; the folder is copied into DuckSuite.</p>
          ${state.engine?.fill?.ready ? '' : `<p class="small muted">AI fill ships inside the app. If the file is missing, reinstall DuckSuite (or run the dev build) to restore it.</p>`}
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
          <h3 style="margin-top:12px">Optional downloads</h3>
          <div class="pack-list">${packListMarkup()}</div>
          <p class="small muted" style="margin-top:8px">System packs live in macOS: <a href="x-apple.systempreferences:com.apple.Localization-Settings.extension">Translation languages</a> (English, Vietnamese, Chinese), Apple Intelligence for rewrite, and extra voices. DuckSuite never downloads executable code.</p>
        </section>
      </div>
    </div>
  </dialog>`);
}

/* ------------------------------------------------------------------ import */

async function triggerImport() {
  if (state.importing) return;
  if (state.project) {
    if (['queued', 'running', 'cancelling'].includes(state.check?.state)) {
      toast('Wait for Check to finish before importing.', 'bad');
      return;
    }
    if (state.queue.some((item) => item.project_id === state.project.id && ['queued', 'running', 'cancelling'].includes(item.state))) {
      toast('Wait for the render to finish before importing.', 'bad');
      return;
    }
    openImportChoice();
    return;
  }
  beginImport('new');
}

function openImportChoice() {
  const name = state.project?.name || 'this project';
  openModal(`<dialog class="modal import-modal" aria-label="Import video">
    <div class="modal-head"><h2>Add video to ${esc(name)}</h2><button class="icon-btn" type="button" data-action="close-modal" aria-label="Close">${icon('close', 16)}</button></div>
    <div class="modal-body import-choice">
      <button class="import-option" type="button" data-action="import-scenes">
        <span class="import-icon">${icon('film', 20)}</span>
        <span><strong>Add scenes</strong><small>Find the cuts in the new video and append every scene. Existing scenes and edits stay.</small></span>
      </button>
      <button class="import-option" type="button" data-action="import-full">
        <span class="import-icon">${icon('upload', 20)}</span>
        <span><strong>Use full video</strong><small>Append the whole new file as one clip after the current video.</small></span>
      </button>
      <p class="small muted">The new video is joined to this project. Nothing replaces your current work.</p>
    </div>
  </dialog>`);
}

function beginImport(mode) {
  closeModal();
  state.pendingImportMode = mode;
  if (window.webkit?.messageHandlers?.duck) {
    window.webkit.messageHandlers.duck.postMessage({
      type: 'import',
      mode,
      projectId: state.project?.id || '',
    });
    toast(state.project ? 'Choose a video to add to this project.' : 'Choose a video to import.');
    return;
  }
  const input = document.querySelector('#import-file-input');
  if (input) {
    input.value = '';
    input.click();
  }
}

async function waitForAppendJob(projectId, jobId) {
  const deadline = Date.now() + 2 * 60 * 60 * 1000;
  let errors = 0;
  while (Date.now() < deadline) {
    let data = null;
    try {
      data = await api(`/api/projects/${encodeURIComponent(projectId)}/append/job/${encodeURIComponent(jobId)}`);
      errors = 0;
    } catch (error) {
      errors += 1;
      if (errors >= 8) throw error;
    }
    if (data) {
      const job = data.job || {};
      if (job.stage) toast(`${job.stage}…`);
      if (job.state === 'done') return job;
      if (job.state === 'failed') throw new Error(job.error || 'Import failed.');
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  throw new Error('The import is taking too long. Reopen the project to check its scenes.');
}

async function handleFile(file) {
  if (!file || state.importing) return;
  const mode = state.pendingImportMode;
  const projectId = state.project?.id || '';
  state.importing = true;
  toast(projectId ? `Adding ${file.name}…` : `Importing ${file.name}…`);
  try {
    if (projectId && (mode === 'scenes' || mode === 'full')) {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/append/upload/job`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${state.token}`,
          'X-Filename': file.name,
          'X-Mode': mode,
        },
        body: file,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
      const started = await response.json();
      const data = await waitForAppendJob(projectId, started.job?.id || '');
      await openProject(projectId);
      state.screen = 'edit';
      state.selectedScene = Math.max(0, (state.check?.result?.scenes?.length || 1) - 1);
      const appendedScene = state.check?.result?.scenes?.[state.selectedScene];
      if (appendedScene) {
        state.previewTime = Number(appendedScene.start || 0) + 0.1;
        state.timelineTime = sourceToTimeline(state.previewTime);
      }
      navigate(projectPath('edit'));
      const added = mode === 'scenes'
        ? `Added ${data.scenes} scene${data.scenes === 1 ? '' : 's'}.`
        : 'Full video added.';
      toast(data.warning ? `${added} ${data.warning}` : added);
      return;
    }
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
    state.pendingImportMode = 'new';
    render();
  }
}

/* ------------------------------------------------------------------ preview cleaning */

function prioritizeScenes(scenes) {
  if (!scenes.length) return [];
  const index = Math.min(state.selectedScene, scenes.length - 1);
  return [...scenes.slice(index), ...scenes.slice(0, index)];
}

async function startPreviewClean(forceSceneId = '', { mode = 'blur' } = {}) {
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
  const forced = forceSceneId !== '' && forceSceneId !== null && forceSceneId !== undefined;
  state.previewRunning = true;
  state.previewRun += 1;
  const run = state.previewRun;
  const order = forced ? scenes.filter((scene) => String(scene.id) === String(forceSceneId)) : prioritizeScenes(scenes);
  for (const scene of order) {
    if (run !== state.previewRun) break;
    if (!forced && state.previewCache.has(scene.id)) {
      state.previewStatus.set(scene.id, 'ready');
      continue;
    }
    state.previewStatus.set(scene.id, 'cleaning');
    updatePreviewUI();
    try {
      const url = cleanPreviewUrl(proofTime(scene), mode);
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
      state.previewStatus.set(scene.id, 'pending');
    }
    if (state.previewRunning) {
      state.previewRun += 1;
      state.previewRunning = false;
    }
    render();
    toast(`Clean set to ${action === 'exclude' ? 'Off' : action}.`);
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

async function slipClip(delta) {
  if (!state.project || !state.edit || !delta) return;
  const index = clipIndexForScene(currentScene(), state.selectedScene);
  if (index < 0) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clips/${index}/slip`, {
      method: 'POST',
      body: JSON.stringify({ delta }),
    });
    state.edit = data.edit;
    render();
    toast(`Clip slipped ${delta > 0 ? '+' : ''}${delta.toFixed(1)}s.`);
  } catch (error) {
    toast(`Slip: ${error.message}`, 'bad');
  }
}

async function splitAtPlayhead() {
  if (!state.project || !state.edit) return;
  if (!(state.timelineTime > 0.02)) {
    toast('Move the playhead inside a clip first.', 'bad');
    return;
  }
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clips/split`, {
      method: 'POST',
      body: JSON.stringify({ time: state.timelineTime }),
    });
    state.edit = data.edit;
    render();
    toast('Clip split.');
  } catch (error) {
    toast(`Split: ${error.message}`, 'bad');
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

function confirmCleanAll() {
  if (!state.project || !state.edit) {
    toast('Finish Check first.', 'bad');
    return;
  }
  const layers = state.edit.clean?.length || 0;
  const userSet = (state.edit.clean || []).filter((layer) => layer.auto === false).length;
  ensureRenderEstimate();
  openModal(`<dialog class="modal clean-all-modal" aria-label="Clean all scenes">
    <div class="modal-head"><h2>Clean all scenes</h2><button class="icon-btn" type="button" data-action="close-modal" aria-label="Close">${icon('close', 16)}</button></div>
    <div class="modal-body clean-all-body">
      <p>This re-reads the Check result and rebuilds the clean layers.</p>
      <ul class="clean-all-list">
        <li>${layers ? `${layers} layer${layers === 1 ? '' : 's'} on this edit` : 'One layer per text block Check found'}</li>
        <li>${userSet ? `${userSet} you set yourself keep their Fill, Blur or Off` : 'Layers DuckSuite planned are re-decided'}</li>
        <li>A line that only flashes on screen gets Blur, because a fill has nothing to rebuild from</li>
      </ul>
      <p class="small muted">Your clips, captions, story, and audio stay as they are.</p>
      <div class="render-cost in-modal"><span class="render-cost-label">Rendering the layers as they are now</span><div data-render-estimate aria-live="polite">${renderEstimateHtml()}</div></div>
      <div class="modal-actions">
        <button class="btn" type="button" data-action="close-modal">Cancel</button>
        <button class="btn primary" type="button" data-action="clean-all-confirm">${icon('sparkle', 14)} Clean all</button>
      </div>
    </div>
  </dialog>`);
}

async function cleanAll() {
  if (!state.project || !state.edit) {
    toast('Finish Check first.', 'bad');
    return;
  }
  closeModal();
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/from-check`, { method: 'POST' });
    state.edit = data.edit;
    state.cleanVersion += 1;
    state.previewCache.clear();
    state.previewStatus.clear();
    render();
    const plan = data.plan || {};
    const count = data.layers || (state.edit.clean || []).length;
    const parts = [`${count} clean layer${count === 1 ? '' : 's'}`];
    if (plan.fill) parts.push(`${plan.fill} fill`);
    if (plan.blur) parts.push(`${plan.blur} blur`);
    if (plan.off) parts.push(`${plan.off} off`);
    // The new layers have a new cost; say it with the counts.
    let cost = '';
    try {
      const payload = await fetchRenderEstimate();
      state.renderEstimateKey = renderEstimateKey();
      state.renderEstimate = payload;
      paintRenderEstimate();
      const estimate = payload.estimate || {};
      cost = estimate.text ? ` ${estimate.text}` : '';
    } catch (_) { /* the Render screen asks again */ }
    toast(`${parts.join(' · ')}.${plan.moving ? ` ${plan.moving} sit over a moving background.` : ''}${cost}`);
  } catch (error) {
    toast(`Clean failed: ${error.message}`, 'bad');
  }
}

async function retryTranscript() {
  if (!state.project || state.transcriptBusy) return;
  state.transcriptBusy = true;
  render();
  toast('Reading speech again…');
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/transcript/retry`, { method: 'POST' });
    state.check.result = data.check || state.check.result;
    await refreshTranscript();
    state.edit = null;
    await ensureEdit();
    await ensureCaptions();
    toast(`Transcript ready · ${data.transcript?.segments || 0} lines.`);
  } catch (error) {
    toast(`Transcript: ${error.message}`, 'bad');
  } finally {
    state.transcriptBusy = false;
    render();
  }
}

async function ensureCaptions() {
  if (!state.project || !state.edit || state.edit.captions?.cues?.length) return;
  if (!getSegments().length) await refreshTranscript();
  if (!getSegments().length) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/captions/generate`, { method: 'POST' });
    state.edit.captions = data.captions;
    state.cleanVersion += 1;
  } catch (_) { /* Script stays empty; the user can retry from Captions */ }
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
    if (data.edit) state.edit = data.edit;
    else state.edit.voice = data.voice;
    render();
    toast(`Voice-over ready: ${data.voice.voice}.`);
  } catch (error) {
    toast(`Voice failed: ${error.message}`, 'bad');
  }
}

function previewVoice() {
  if (!state.project || (!state.edit?.voice && !state.edit?.dub)) return;
  state.voicePreview = mediaUrl(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/voice/audio`);
  render();
}

async function previewLine(cueId) {
  if (!state.project || !state.edit) return;
  const cue = scriptCues().find((item) => String(item.id) === String(cueId));
  if (!cue) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/voice/preview`, {
      method: 'POST',
      body: JSON.stringify({ text: cue.text || '', voice: state.voiceName }),
    });
    state.voicePreview = mediaUrl(`/api/projects/${encodeURIComponent(state.project.id)}/voice/preview/${encodeURIComponent((data.preview?.audio || '').split('/').pop())}`);
    render();
  } catch (error) {
    toast(`Preview failed: ${error.message}`, 'bad');
  }
}

async function translateScript() {
  if (!state.project || !state.edit) return;
  state.scriptBusy = true;
  state.scriptStatusKind = 'working';
  state.scriptStatus = 'Working on the script';
  render();
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/script/translate`, {
      method: 'POST',
      body: JSON.stringify({ target: state.scriptTarget, source: scriptLanguage() }),
    });
    state.edit.captions = data.captions;
    if (data.script) state.edit.script = data.script;
    state.scriptStatusKind = 'ready';
    state.scriptStatus = `Translated to ${({ en: 'English', vi: 'Vietnamese', zh: 'Chinese' })[state.scriptTarget] || state.scriptTarget}`;
    toast(state.scriptStatus);
  } catch (error) {
    state.scriptStatusKind = 'error';
    state.scriptStatus = `Translation failed: ${error.message}`;
    toast(`Translate: ${error.message}`, 'bad');
  } finally {
    state.scriptBusy = false;
    render();
  }
}

async function rewriteScript() {
  if (!state.project || !state.edit) return;
  state.scriptBusy = true;
  state.scriptStatusKind = 'working';
  state.scriptStatus = 'Working on the script';
  render();
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/script/rewrite`, {
      method: 'POST',
      body: JSON.stringify({ mode: state.scriptMode }),
    });
    state.edit.captions = data.captions;
    if (data.script) state.edit.script = data.script;
    const engine = data.script?.engine || 'apple-intelligence';
    const engineLabel = engine === 'apple-intelligence' ? 'Apple Intelligence' : 'basic cleanup';
    state.scriptStatusKind = engine === 'basic-cleanup' ? 'warn' : 'ready';
    state.scriptStatus = `Rewritten · ${data.script?.rewrite || state.scriptMode} · ${engineLabel}`;
    toast(state.scriptStatus);
  } catch (error) {
    state.scriptStatusKind = 'error';
    state.scriptStatus = `Rewrite failed: ${error.message}`;
    toast(`Rewrite: ${error.message}`, 'bad');
  } finally {
    state.scriptBusy = false;
    render();
  }
}

async function resetScript() {
  if (!state.project || !state.edit) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/script/reset`, { method: 'POST' });
    state.edit.captions = data.captions;
    if (data.script) state.edit.script = data.script;
    state.scriptStatusKind = 'ready';
    state.scriptStatus = 'Script reset to source';
    render();
    toast('Script reset to source.');
  } catch (error) {
    toast(`Reset: ${error.message}`, 'bad');
  }
}

async function buildDub() {
  if (!state.project || !state.edit) return;
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/dub`, {
      method: 'POST',
      body: JSON.stringify({ voice: state.voiceName, language: state.scriptTarget }),
    });
    if (data.edit) state.edit = data.edit;
    else state.edit.dub = data.dub;
    render();
    toast('Dub built. Original audio will be muted on render.');
  } catch (error) {
    toast(`Dub failed: ${error.message}`, 'bad');
  }
}

async function removeMusic() {
  if (!state.project || !state.edit) return;
  try {
    await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/music`, { method: 'DELETE' });
    delete state.edit.music;
    render();
  } catch (error) {
    toast(`Music: ${error.message}`, 'bad');
  }
}

async function uploadMusic(file) {
  if (!file || !state.project || !state.edit) return;
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/music`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${state.token}`, 'X-Filename': file.name },
      body: file,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
    if (body.edit) state.edit = body.edit;
    else state.edit.music = body.music;
    render();
    toast('Background music added.');
  } catch (error) {
    toast(`Music: ${error.message}`, 'bad');
  }
}

function startRecording() {
  if (!window.webkit?.messageHandlers?.duck) {
    toast('Recording needs the Mac app.', 'bad');
    return;
  }
  state.recording = true;
  render();
  window.webkit.messageHandlers.duck.postMessage({ type: 'recordStart' });
}

function stopRecording() {
  if (!state.recording) return;
  window.webkit?.messageHandlers?.duck?.postMessage({ type: 'recordStop' });
}

async function startRender(projectId = '', editId = '') {
  const active = activeRenderJob();
  if (active) {
    toast('Render already running.');
    await refreshQueue();
    return;
  }
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


async function refreshPacks() {
  const data = await api('/api/packs').catch(() => ({ packs: [] }));
  state.packs = data.packs || [];
  const list = document.querySelector('.pack-list');
  if (list) list.innerHTML = packListMarkup();
  if (state.packs.some((pack) => pack.downloading)) {
    window.setTimeout(refreshPacks, 1500);
  }
}

async function downloadPack(packId) {
  try {
    await api(`/api/packs/${encodeURIComponent(packId)}/download`, { method: 'POST' });
    await refreshPacks();
    await openSettings();
    toast('Download started.');
  } catch (error) {
    toast(`Pack: ${error.message}`, 'bad');
  }
}

async function removePack(packId) {
  try {
    await api(`/api/packs/${encodeURIComponent(packId)}`, { method: 'DELETE' });
    await refreshPacks();
    await openSettings();
    toast('Pack removed.');
  } catch (error) {
    toast(`Pack: ${error.message}`, 'bad');
  }
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

document.addEventListener('pointerdown', (event) => {
  if (event.button !== 0) return;
  const bar = event.target.closest?.('.toolbar');
  if (!bar) return;
  if (event.target.closest('button, a, input, select, textarea, [data-action]')) return;
  window.webkit?.messageHandlers?.duck?.postMessage({ type: 'windowDrag' });
});

document.addEventListener('click', async (event) => {
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
    else if (action === 'import-scenes') beginImport('scenes');
    else if (action === 'import-full') beginImport('full');
    else if (action === 'settings') await openSettings();
    else if (action === 'save-translation') await saveTranslationSettings();
    else if (action === 'choose-model-folder') chooseModelFolder();
    else if (action === 'choose-fill-model') chooseFillModelFolder();
    else if (action === 'clear-fill-model') saveFillModel('');
    else if (action === 'fill-device') await setFillDevice(target.dataset.device || 'cpu');
    else if (action === 'clean-filter') { state.cleanFilter = target.dataset.filter === 'mine' ? 'mine' : 'all'; render(); }
    else if (action === 'search') openSearch();
    else if (action === 'search-scene') { closeModal(); state.selectedScene = Math.max(0, Number(target.dataset.index || 0)); state.previewTime = Number(getScenes()[state.selectedScene]?.start || 0) + 0.1; state.timelineTime = sourceToTimeline(state.previewTime); navigate(projectPath('edit')); }
    else if (action === 'search-project') { const id = target.dataset.project || ''; closeModal(); if (id) { await openProject(id); navigate(`project/${id}/${state.check?.state === 'done' ? 'edit' : 'check'}`); } }
    else if (action === 'close-modal') closeModal();
    else if (action === 'start-check') await startCheck();
    else if (action === 'retry-transcript') await retryTranscript();
    else if (action === 'open-editor') navigate(projectPath('edit'));
    else if (action === 'nav') navigate(projectPath(target.dataset.screen || 'edit'));
    else if (action === 'proof-tab') { state.proofTab = target.dataset.tab || 'scenes'; render(); }
    else if (action === 'inspector-tab') {
      state.inspectorTab = target.dataset.tab || 'clean';
      state.scriptOpen = false;
      render();
    }
    else if (action === 'toggle-story-select') {
      state.storySelect = !state.storySelect;
      if (!state.storySelect) state.storyScenes = [];
      render();
    }
    else if (action === 'story-toggle') {
      const index = Number(target.dataset.index || 0);
      const scene = getScenes()[index];
      if (!scene) return;
      if (state.storyScenes.includes(scene.id)) state.storyScenes = state.storyScenes.filter((id) => id !== scene.id);
      else state.storyScenes.push(scene.id);
      render();
    }
    else if (action === 'build-story') await buildStory();
    else if (action === 'back-to-full') await backToFullVideo();
    else if (action === 'story-add-image') document.querySelector('#story-image-input')?.click();
    else if (action === 'story-add-video') document.querySelector('#story-video-input')?.click();
    else if (action === 'story-add-scene') await addStoryScene();
    else if (action === 'story-remove-beat') await removeStoryBeat(Number(target.dataset.index));
    else if (action === 'story-move-beat') await moveStoryBeat(Number(target.dataset.index), Number(target.dataset.delta));
    else if (action === 'select-scene') {
      const index = Number(target.dataset.index || 0);
      const scenes = getScenes();
      state.selectedScene = Math.max(0, Math.min(index, scenes.length - 1));
      state.previewTime = Number(scenes[state.selectedScene]?.start || 0) + 0.1;
      state.timelineTime = sourceToTimeline(state.previewTime);
      state.selectedLayerId = '';
      state.inlinePlaying = false;
      state.showAllLayers = false;
      state.showAllCues = false;
      const selected = scenes[state.selectedScene];
      state.previewStatus.set(selected?.id, state.previewCache.has(selected?.id) ? 'ready' : (state.previewStatus.get(selected?.id) || 'pending'));
      state.proofStep = 1;
      render();
      if (Number(state.timelineZoom || 1) > 1) centerTimelineOnPlayhead();
    } else if (action === 'select-story') {
      const index = Number(target.dataset.scene || 0);
      state.proofTab = 'stories';
      state.selectedScene = Math.max(0, Math.min(index, getScenes().length - 1));
      state.previewTime = Number(getStories()[Number(target.dataset.index || 0)]?.start || 0) + 0.1;
      state.timelineTime = sourceToTimeline(state.previewTime);
      render();
    } else if (action === 'select-layer') { state.selectedLayerId = target.dataset.layer || ''; render(); }
    else if (action === 'toggle-layers') { state.showAllLayers = !state.showAllLayers; render(); }
    else if (action === 'toggle-cues') { state.showAllCues = !state.showAllCues; render(); }
    else if (action === 'strip-scroll') {
      const strip = document.getElementById(target.dataset.target || '');
      if (strip) strip.scrollBy({ left: Number(target.dataset.dir || 1) * Math.max(180, strip.clientWidth * 0.75), behavior: 'smooth' });
    }
    else if (action === 'trim-apply') await applyTrim();
    else if (action === 'split-at-playhead') await splitAtPlayhead();
    else if (action === 'slip-clip') await slipClip(Number(target.dataset.delta || 0));
    else if (action === 'clear-queue') await clearQueue();
    else if (action === 'clean-action') await cleanAction(target.dataset.layer || '', target.dataset.kind || 'fill');
    else if (action === 'clean-all') confirmCleanAll();
    else if (action === 'clean-all-confirm') await cleanAll();
    else if (action === 'queue-scope') { state.queueScope = state.queueScope === 'all' ? 'project' : 'all'; render(); }
    else if (action === 'proof-all') await startPreviewClean();
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
    else if (action === 'open-script') { state.focusMode = 'script'; state.scriptOpen = false; render(); }
    else if (action === 'close-script') { state.scriptOpen = false; render(); }
    else if (action === 'script-translate') await translateScript();
    else if (action === 'script-rewrite') await rewriteScript();
    else if (action === 'script-reset') await resetScript();
    else if (action === 'script-seek') { seekToTime(Number(target.dataset.time || 0) + 0.01); document.querySelectorAll('.focus-cue').forEach((row) => row.classList.toggle('is-current', Number(row.dataset.time || 0) <= state.timelineTime)); }
    else if (action === 'timeline-seek') { seekToTime(Number(target.dataset.time || 0) + 0.01); updateGhostActive(); if (Number(state.timelineZoom || 1) > 1) centerTimelineOnPlayhead(); }
    else if (action === 'overlay-position') { state.overlayTop = !state.overlayTop; render(); }
    else if (action === 'trim-focus') document.querySelector('.timeline-trim')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    else if (action === 'voice-tab') { state.inspectorTab = 'voice'; state.scriptOpen = false; render(); }
    else if (action === 'add-music') document.querySelector('#music-input')?.click();
    else if (action === 'remove-music') await removeMusic();
    else if (action === 'record-start') startRecording();
    else if (action === 'record-stop') stopRecording();
    else if (action === 'dub-build') await buildDub();
    else if (action === 'voice-line') await previewLine(target.dataset.cue || '');
    else if (action === 'nav-clean-brush') { state.brushMode = true; state.brushStrokes = []; navigate(projectPath('clean')); }
    else if (action === 'brush-toggle') { state.brushMode = !state.brushMode; if (!state.brushMode) state.brushStrokes = []; render(); }
    else if (action === 'brush-kind') { state.brushKind = target.dataset.kind || 'fill'; render(); }
    else if (action === 'brush-undo') { state.brushStrokes.pop(); render(); }
    else if (action === 'brush-clear') { state.brushStrokes = []; render(); }
    else if (action === 'brush-apply') await applyBrush();
    else if (action === 'set-scope') { state.editScope = target.dataset.scope === 'project' ? 'project' : 'scene'; render(); }
    else if (action === 'open-focus') {
      const focus = target.dataset.focus || 'script';
      if (focus === 'clean') navigate(projectPath('clean'));
      else { state.focusMode = focus; state.scriptOpen = false; render(); }
    }
    else if (action === 'close-focus') { stopAudioPlayback(); state.focusMode = ''; render(); }
    else if (action === 'toggle-transcript-overlay') { state.transcriptOverlay = !state.transcriptOverlay; render(); }
    else if (action === 'sfx-add') startSfxUpload(target.dataset.kind || 'sound');
    else if (action === 'sfx-text') openSfxTextModal();
    else if (action === 'sfx-filter-add') await addSfxFilter(target.dataset.preset || 'warm', target.dataset.start, target.dataset.end);
    else if (action === 'sfx-text-add') await addSfxText();
    else if (action === 'sfx-remove') await removeSfx(target.dataset.effect || '');
    else if (action === 'audio-remove') await removeAudioTrack(target.dataset.track || '');
    else if (action === 'audio-audition') await auditionAudioTrack(target.dataset.track || '');
    else if (action === 'audio-mix-preview') await toggleAudioMixPreview();
    else if (action === 'audio-mute' || action === 'audio-solo') await toggleAudioTrack(target.dataset.track || '', action === 'audio-mute' ? 'muted' : 'solo');
    else if (action === 'reveal') await revealPath(target.dataset.path || '');
    else if (action === 'preview-view') { state.previewView = target.dataset.view || 'compare'; render(); }
    else if (action === 'write-story') { await writeStory(); }
    else if (action === 'play-sequence') { startSequence(); }
    else if (action === 'sequence-play') {
      const video = document.querySelector('[data-sequence-player]');
      if (video) { if (video.paused) video.play().catch(() => {}); else video.pause(); }
    }
    else if (action === 'sequence-close') {
      const video = document.querySelector('[data-sequence-player]');
      if (video) video.pause();
      state.sequenceActive = false;
      state.sequencePlaying = false;
      render();
    }
    else if (action === 'safe-zone-toggle') { state.safeZoneOpen = !state.safeZoneOpen; render(); }
    else if (action === 'safe-zone') {
      state.safeZone = target.dataset.zone || 'off';
      if (state.safeZone === 'off') state.safeZoneOpen = false;
      render();
    }
    else if (action === 'preview-reclean') {
      const scenes = getScenes();
      const scene = currentScene();
      state.selectedScene = Math.max(0, scenes.indexOf(scene));
      state.selectedLayerId = sceneLayers(scene)[0]?.id || '';
      state.proofStep = 1;
      state.inlinePlaying = false;
      state.screen = 'clean';
      window.location.hash = `#/project/${state.project.id}/clean`;
      render();
    }
    else if (action === 'cut-aspect') {
      const aspect = target.dataset.aspect || 'source';
      await saveCut({ aspect, ...(aspect === 'source' ? {} : { fit: 'fill' }) });
    }
    else if (action === 'cut-fit') { await saveCut({ fit: target.dataset.fit || 'fit' }); }
    else if (action === 'cut-crop') {
      const value = (id) => Number(document.querySelector(`#${id}`)?.value || 0);
      const crop = { x: value('cut-x'), y: value('cut-y'), w: value('cut-w'), h: value('cut-h') };
      if (![crop.x, crop.y, crop.w, crop.h].every(Number.isFinite) || crop.w <= 0 || crop.h <= 0) {
        toast('Crop needs four numbers; width and height must be above 0.', 'bad');
        return;
      }
      await saveCut({ crop });
    }
    else if (action === 'cut-reset') { await saveCut({ crop: null }); }
    else if (action === 'grade-reset') { await saveCut({ grade: { exposure: 0, contrast: 0, saturation: 0, temperature: 0 } }); }
    else if (action === 'timeline-zoom') {
      const steps = [1, 1.5, 2, 3, 4, 6, 8, 12, 16];
      const dir = Number(target.dataset.dir || 0);
      if (dir === 0) state.timelineZoom = 1;
      else {
        const at = steps.findIndex((value) => value >= Number(state.timelineZoom || 1) - 0.001);
        state.timelineZoom = steps[Math.max(0, Math.min(steps.length - 1, (at < 0 ? 0 : at) + dir))];
      }
      render();
      centerTimelineOnPlayhead();
    }
    else if (action === 'proof-step') { state.proofStep = Number(target.dataset.step || 1); render(); }
    else if (action === 'prove-scene') {
      const index = Number(target.dataset.index ?? state.selectedScene);
      const scene = getScenes()[index];
      if (scene) {
        state.selectedScene = index;
        state.proofStep = 1;
        await startPreviewClean(scene.id);
        render();
      }
    }
    else if (action === 'box-apply') {
      const layerId = target.dataset.layer || '';
      const value = (id) => Number(document.querySelector(`#${id}`)?.value || 0);
      const box = { x: value('box-x'), y: value('box-y'), w: value('box-w'), h: value('box-h') };
      if (![box.x, box.y, box.w, box.h].every(Number.isFinite) || box.w <= 0 || box.h <= 0) {
        toast('Box needs four numbers; width and height must be above 0.', 'bad');
        return;
      }
      const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/${encodeURIComponent(layerId)}/box`, { method: 'PATCH', body: JSON.stringify(box) });
      state.edit = data.edit;
      state.cleanVersion += 1;
      const scene = currentScene();
      if (scene) {
        state.previewCache.delete(scene.id);
        state.previewStatus.set(scene.id, 'pending');
      }
      render();
      toast('Box saved. The next proof and render use it.');
    }
    else if (action === 'recheck-scene') {
      const scene = currentScene();
      try {
        const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/clean/from-check`, { method: 'POST' });
        state.edit = data.edit;
        state.cleanVersion += 1;
        if (scene) {
          state.previewCache.delete(scene.id);
          state.previewStatus.set(scene.id, 'pending');
        }
        render();
        toast('Clean re-checked and re-applied.');
      } catch (error) {
        toast(`Re-check failed: ${error.message}`, 'bad');
      }
    }
    else if (action === 'verify-model') await verifyModel(target.dataset.model || '');
    else if (action === 'download-pack') await downloadPack(target.dataset.pack || '');
    else if (action === 'remove-pack') await removePack(target.dataset.pack || '');
    else if (action === 'seek') {
      seekToTime(Number(target.dataset.time || 0) + 0.01);
    }
    else if (action === 'toggle-transcript-side') {
      state.transcriptSideHidden = !state.transcriptSideHidden;
      state.cueMenu = '';
      render();
    }
    else if (action === 'cue-menu') {
      const id = target.dataset.cue || '';
      state.cueMenu = state.cueMenu === id ? '' : id;
      render();
    }
    else if (action === 'cue-seek') {
      state.cueMenu = '';
      seekToTime(Number(target.dataset.time || 0) + 0.01);
      render();
    }
    else if (action === 'cue-copy') {
      const id = target.dataset.cue || '';
      const cue = (state.edit?.captions?.cues || []).find((item) => String(item.id) === id);
      const text = String(cue?.text || '');
      state.cueMenu = '';
      if (text && navigator.clipboard) navigator.clipboard.writeText(text).then(() => toast('Line copied.'), () => toast('Could not copy.', 'bad'));
      render();
    }
  } catch (error) {
    toast(error.message || 'Action failed.', 'bad');
  }
});

document.addEventListener('change', async (event) => {
  const target = event.target;
  if (target.dataset && target.dataset.grade) {
    const grade = { ...gradeOf() };
    document.querySelectorAll('[data-grade]').forEach((input) => {
      grade[input.dataset.grade] = Number(input.value || 0);
    });
    saveCut({ grade });
    return;
  }
  if (target.id === 'translation-engine') {
    await saveTranslationSettings();
    await openSettings();
    return;
  }
  if (target.id === 'translation-path') {
    await saveTranslationSettings();
    return;
  }
  if (target.id === 'story-edit-select' || target.id === 'edit-select') {
    await openEditById(target.value);
    return;
  }
  if (target.id === 'story-image-input' || target.id === 'story-video-input') {
    const file = target.files?.[0];
    target.value = '';
    if (file) await uploadStoryBeat(target.id === 'story-image-input' ? 'image' : 'video', file);
    return;
  }
  if (target.dataset?.audioField) {
    const field = target.dataset.audioField;
    const value = field === 'volume' ? Number(target.value) : Number(target.value);
    await patchAudioTrack(target.dataset.track || '', { [field]: value });
    return;
  }
  if (target.id === 'sfx-file-input') {
    const file = target.files?.[0];
    target.value = '';
    await handleSfxFile(file);
    return;
  }
  if (target.id === 'file-input' || target.id === 'import-file-input') {
    const file = target.files?.[0];
    target.value = '';
    await handleFile(file);
    return;
  }
  if (target.id === 'brush-size') {
    state.brushSize = Number(target.value || 0.025);
    return;
  }
  if (target.id === 'music-input') {
    const file = target.files?.[0];
    target.value = '';
    await uploadMusic(file);
    return;
  }
  const action = target.dataset?.action;
  if (action === 'script-target') { state.scriptTarget = target.value; render(); await translateScript(); }
  else if (action === 'script-mode') { state.scriptMode = target.value; render(); }
  else if (action === 'caption-burn') await patchCaptions({ burn: target.checked });
  else if (action === 'caption-style') await patchCaptions({ style: target.value });
  else if (action === 'caption-position') await patchCaptions({ position: target.value });
  else if (action === 'cue-save') await saveCue(target.dataset.cue || '', target.value);
  else if (action === 'voice-select') { state.voiceName = target.value; render(); }
  else if (action === 'voice-mode') { state.voiceMode = target.value; render(); }
});

document.addEventListener('input', (event) => {
  if (event.target.dataset && event.target.dataset.grade) {
    const key = event.target.dataset.grade;
    const grade = { ...gradeOf(), [key]: Number(event.target.value || 0) };
    const video = document.querySelector('.cut-video');
    if (video) video.style.filter = gradeFilter(grade);
    const read = event.target.closest('label')?.querySelector('[data-grade-value]');
    if (read) read.textContent = signedValue(event.target.value);
    return;
  }
  if (event.target.id === 'sequence-scrub') {
    sequenceSeek(Number(event.target.value || 0) / 1000);
    return;
  }
  if (event.target.id === 'transcript-alpha') {
    const value = Math.max(30, Math.min(100, Number(event.target.value) || 100));
    state.transcriptAlpha = value;
    const panel = event.target.closest('.transcript-side');
    if (panel) {
      panel.style.setProperty('--ta', String(value / 100));
      const read = panel.querySelector('[data-alpha-value]');
      if (read) read.textContent = `${value}%`;
    }
    try { localStorage.setItem(`duck.transcriptAlpha.${encodeURIComponent(state.project?.id || '')}`, String(value)); } catch (_error) { /* storage off */ }
    return;
  }
  if (event.target.id === 'project-search') {
    state.welcomeQuery = event.target.value;
    render();
    const input = document.querySelector('#project-search');
    if (input) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
  }
});

/* ------------------------------------------------------------------ after render */

function syncLayerFades() {
  const more = (el, axis) => axis === 'x'
    ? el.scrollWidth > el.clientWidth + 4 && el.scrollLeft + el.clientWidth < el.scrollWidth - 4
    : el.scrollHeight > el.clientHeight + 4 && el.scrollTop + el.clientHeight < el.scrollHeight - 4;
  document.querySelectorAll('[data-layer-list]').forEach((el) => el.classList.toggle('has-more', more(el, 'y')));
  document.querySelectorAll('.inspector-body, .proof-list, .clean-scene-list').forEach((el) => {
    el.classList.toggle('has-more', more(el, 'y'));
  });
  document.querySelectorAll('.scene-strip').forEach((el) => {
    el.classList.toggle('has-more-x', more(el, 'x'));
    el.classList.toggle('has-more', more(el, 'y'));
  });
}

document.addEventListener('scroll', (event) => {
  const target = event.target;
  if (target && target.matches && target.matches('[data-layer-list], .inspector-body, .proof-list, .clean-scene-list, .scene-strip')) syncLayerFades();
}, true);

function playerBar() {
  return `<div class="player-bar" data-player-bar>
    <button class="player-play" type="button" data-action="player-play" aria-label="Play or pause">${icon('play', 13)}</button>
    <span class="player-time" data-player-time>00:00 / 00:00</span>
    <input class="player-scrub" type="range" min="0" max="1000" value="0" step="1" aria-label="Seek">
    <button class="player-mute" type="button" aria-label="Mute" aria-pressed="false">${icon('volume', 13)}</button>
    <input class="player-volume" type="range" min="0" max="1" step="0.01" value="1" aria-label="Volume">
    <button class="player-full" type="button" aria-label="Full screen">${icon('expand', 13)}</button>
  </div>`;
}

function clockText(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
}

function setupPlayerBars() {
  document.querySelectorAll('[data-app-player]').forEach((video) => {
    const bar = video.parentElement?.querySelector('[data-player-bar]');
    if (!bar) return;
    const play = bar.querySelector('.player-play');
    const time = bar.querySelector('[data-player-time]');
    const scrub = bar.querySelector('.player-scrub');
    const mute = bar.querySelector('.player-mute');
    const volume = bar.querySelector('.player-volume');
    const full = bar.querySelector('.player-full');
    const paint = () => {
      if (time) time.textContent = `${clockText(video.currentTime)} / ${clockText(video.duration)}`;
      if (scrub && Number.isFinite(video.duration) && video.duration > 0) {
        scrub.value = String(Math.round((video.currentTime / video.duration) * 1000));
      }
    };
    play?.addEventListener('click', () => {
      if (video.paused) video.play().catch(() => {});
      else video.pause();
      play.innerHTML = video.paused ? icon('play', 13) : icon('pause', 13);
    });
    scrub?.addEventListener('input', () => {
      if (Number.isFinite(video.duration) && video.duration > 0) {
        video.currentTime = (Number(scrub.value) / 1000) * video.duration;
      }
    });
    mute?.addEventListener('click', () => {
      video.muted = !video.muted;
      mute.setAttribute('aria-pressed', String(video.muted));
      mute.classList.toggle('is-muted', video.muted);
    });
    volume?.addEventListener('input', () => {
      video.volume = Math.max(0, Math.min(1, Number(volume.value)));
      if (video.volume > 0 && video.muted) {
        video.muted = false;
        mute?.setAttribute('aria-pressed', 'false');
        mute?.classList.remove('is-muted');
      }
    });
    full?.addEventListener('click', () => {
      const stage = video.closest('.media-card, .split-stage, .modal-body') || video.parentElement;
      if (stage && stage.requestFullscreen) stage.requestFullscreen().catch(() => {});
    });
    video.addEventListener('timeupdate', paint);
    video.addEventListener('loadedmetadata', paint);
    video.addEventListener('play', () => { play.innerHTML = icon('pause', 13); });
    video.addEventListener('pause', () => { play.innerHTML = icon('play', 13); });
    paint();
  });
}

function afterRender() {
  setupBrushCanvas();
  setupTimelineRuler();
  setupAudioRows();
  loadAudioWaveforms();
  setupAudioDrag();
  setupPlayerBars();
  syncLayerFades();
  const inline = document.querySelector('video[data-inline-player]');
  if (inline) {
    const start = Number(inline.dataset.start || 0);
    if (start > 0 && Math.abs(inline.currentTime - start) > 0.5) {
      try { inline.currentTime = start; } catch (_) { /* metadata not ready */ }
    }
    inline.play().catch(() => {});
    inline.addEventListener('timeupdate', () => { state.previewTime = inline.currentTime; state.timelineTime = sourceToTimeline(inline.currentTime); updateTimelinePlayhead(state.timelineTime); syncSceneForTime(); refreshTranscriptOverlay(); }, { passive: true });
  }
  const video = document.querySelector('video[data-preview]');
  if (video) {
    if (state.previewTime > 0 && Math.abs(video.currentTime - state.previewTime) > 0.35) {
      try { video.currentTime = state.previewTime; } catch (_) { /* metadata not ready */ }
    }
    video.addEventListener('timeupdate', () => { state.previewTime = video.currentTime; state.timelineTime = sourceToTimeline(video.currentTime); updateTimelinePlayhead(state.timelineTime); syncSceneForTime(); refreshTranscriptOverlay(); }, { passive: true });
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

  setupInlineDetectionReview();

  const sceneSearch = document.querySelector('#scene-search');
  if (sceneSearch) {
    const filter = () => {
      state.sceneQuery = sceneSearch.value;
      const query = sceneSearch.value.trim().toLowerCase();
      document.querySelectorAll('.proof-row[data-search]').forEach((row) => {
        row.classList.toggle('is-hidden', Boolean(query) && !row.dataset.search.includes(query));
      });
    };
    sceneSearch.addEventListener('input', filter);
    filter();
  }

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
    if (['queued', 'running', 'cancelling'].includes(state.check?.state) || state.check?.result?.append?.analysis === 'pending') {
      try { await refreshCheck(); } catch (_) { /* keep last */ }
    }
  }, 1500);
  window.setInterval(async () => {
    if (['welcome', 'render'].includes(state.screen)) await refreshQueue();
  }, 2500);
}

window.duckProjectId = () => state.project?.id || '';

window.duckImportError = (message) => {
  state.importing = false;
  render();
  toast(message || 'Import failed.', 'bad');
};

window.duckRecordingStarted = (path) => {
  state.recordingPath = path;
  toast('Recording. Press Stop when finished.');
};

window.duckRecordingStopped = async (path) => {
  state.recording = false;
  if (!path) { render(); toast('Recording was empty.', 'bad'); return; }
  try {
    const data = await api(`/api/projects/${encodeURIComponent(state.project.id)}/edits/${encodeURIComponent(state.edit.id)}/voice/record`, {
      method: 'POST',
      body: JSON.stringify({ path }),
    });
    if (data.edit) state.edit = data.edit;
    else state.edit.voice = data.voice;
    render();
    toast('Recorded voice-over saved.');
  } catch (error) {
    toast(`Recording: ${error.message}`, 'bad');
  }
};

window.duckRecordingError = (message) => {
  state.recording = false;
  render();
  toast(`Recording: ${message}`, 'bad');
};

async function boot() {
  state.token = readToken();
  if (!state.token) {
    app.innerHTML = `<div class="boot"><div class="boot-mark"></div><p>DuckSuite needs the local launch token.</p><p class="small" style="max-width:380px;text-align:center">Open DuckSuite from the Mac app. The web preview alone cannot reach the local core.</p></div>`;
    return;
  }
  try {
    await api('/api/session', { method: 'POST' });
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
