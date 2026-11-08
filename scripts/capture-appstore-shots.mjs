#!/usr/bin/env node
// Capture App Store screenshots from the local DuckSuite web core.
//
// Usage:
//   node scripts/capture-appstore-shots.mjs --base "http://127.0.0.1:8765/?t=token" \
//     --project prj_... --out docs/appstore/screenshots
//
// Requires Google Chrome. Drives it through the DevTools protocol so routes that
// keep polling or generating proofs still capture after a bounded wait.

import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  args.set(process.argv[i].replace(/^--/, ""), process.argv[i + 1]);
}

const base = args.get("base");
const project = args.get("project");
const out = path.resolve(args.get("out") || "docs/appstore/screenshots");
const chrome = args.get("chrome") || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const port = Number(args.get("port") || 9333);
if (!base || !project) {
  console.error("need --base and --project");
  process.exit(2);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForEndpoint() {
  for (let i = 0; i < 100; i += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) return;
    } catch {}
    await sleep(100);
  }
  throw new Error("Chrome DevTools endpoint did not start");
}

class CDP {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message));
        else resolve(message.result);
      }
    });
  }

  async open() {
    if (this.socket.readyState === WebSocket.OPEN) return;
    await new Promise((resolve, reject) => {
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket.close();
  }
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  return result?.result?.value;
}

async function capture(cdp, file, width, height, scale) {
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: scale,
    mobile: false,
  });
  await sleep(700);
  const shot = await cdp.send("Page.captureScreenshot", { format: "png", fromSurface: true });
  await writeFile(file, Buffer.from(shot.data, "base64"));
  console.log(path.basename(file));
}

const routes = [
  ["01-welcome", "welcome"],
  ["02-check", `project/${project}/check`],
  ["05-preview", `project/${project}/preview`],
  ["03-edit", `project/${project}/edit`],
  ["04-clean-focus", `project/${project}/clean`],
  ["06-render", `project/${project}/render`],
];

await mkdir(out, { recursive: true });

const chromeProcess = spawn(chrome, [
  "--headless=new",
  "--disable-gpu",
  "--hide-scrollbars",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=/tmp/duck-shots-chrome-${port}`,
  "--window-size=1280,800",
  "about:blank",
], { stdio: "ignore" });

try {
  await waitForEndpoint();
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
  const cdp = new CDP(target.webSocketDebuggerUrl);
  await cdp.open();
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");

  for (const [name, route] of routes) {
    await cdp.send("Page.navigate", { url: `${base}#/${route}` });
    await sleep(2500);

    if (route.endsWith("/preview")) {
      for (let i = 0; i < 1800; i += 1) {
        const done = await evaluate(
          cdp,
          `(() => {
            const labels = [...document.querySelectorAll('.scene-tile .scene-label')];
            return labels.length > 0 && labels.every((node) => node.textContent.trim() === 'Proof');
          })()`,
        );
        if (done) break;
        await sleep(1000);
      }
    }
    await sleep(1200);

    await capture(cdp, path.join(out, `${name}-1280x800@2x.png`), 1280, 800, 2);
    await capture(cdp, path.join(out, `${name}-1440x900@2x.png`), 1440, 900, 2);
  }

  cdp.close();
} finally {
  chromeProcess.kill("SIGTERM");
}
