const status = document.querySelector("#core-status");
const statusText = document.querySelector("#core-status-text");
const projectsHost = document.querySelector("#projects");
const importButton = document.querySelector("#import-button");

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

async function health() {
  if (!launchToken) {
    setStatus("No launch token", "bad");
    return;
  }
  try {
    const data = await api("/api/health");
    setStatus(`Local core ${data.version}`, "ok");
    await loadProjects();
  } catch (error) {
    setStatus("Local core unavailable", "bad");
    console.error(error);
  }
}

launchToken = readToken();
baseURL = window.location.origin;
importButton?.addEventListener("click", importVideo);
health();
