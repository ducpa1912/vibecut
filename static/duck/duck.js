const status = document.querySelector("#core-status");
const statusText = document.querySelector("#core-status-text");

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

const token = readToken();

async function health() {
  if (!token) {
    setStatus("No launch token", "bad");
    return;
  }
  try {
    const response = await fetch("/api/health", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    setStatus(`Local core ${data.version}`, "ok");
  } catch (error) {
    setStatus("Local core unavailable", "bad");
    console.error(error);
  }
}

health();
