#!/usr/bin/env node
// Capture the README screenshots in docs/screenshots with headless Chrome.
//
// Drives Chrome over the DevTools protocol so it can open the telemetry
// modal and import a CSV, which a plain `chrome --screenshot` cannot.
// Needs Node 22+ (built-in WebSocket) and google-chrome on the PATH, plus a
// running frontend backed by real data (see "Local development" in the
// README). Nothing is saved: the CSV import stops at the prefilled form.
//
// Usage (repo root):
//   node bin/capture_screenshots.mjs --csv "import_data/My shot #21.csv"
//   node bin/capture_screenshots.mjs --base http://127.0.0.1:5173 telemetry planner
//
// Options:
//   --base URL      Frontend URL (default http://127.0.0.1:5173)
//   --out DIR       Output directory (default docs/screenshots)
//   --csv FILE      Brewmeo CSV for csv-import (skipped when not given)
//   --timezone TZ   Browser timezone (default Europe/London, so the New Shot
//                   form is after 9:30 am and shows Sara's cappuccino default)
//   NAME ...        Capture only these: shots telemetry new-shot csv-import
//                   coffees planner reports
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { parseArgs } from "node:util";

const { values: opts, positionals: only } = parseArgs({
  allowPositionals: true,
  options: {
    base: { type: "string", default: "http://127.0.0.1:5173" },
    out: { type: "string", default: "docs/screenshots" },
    csv: { type: "string" },
    timezone: { type: "string", default: "Europe/London" },
  },
});
const outDir = path.resolve(opts.out);
const PORT = 9339;
const WIDTH = 1280;
const HEIGHT = 900;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = mkdtempSync(path.join(tmpdir(), "capture-chrome-"));
const chrome = spawn(
  "google-chrome",
  [
    "--headless=new",
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`,
    "--hide-scrollbars",
    `--window-size=${WIDTH},${HEIGHT}`,
    "about:blank",
  ],
  { stdio: "ignore" },
);

let targets;
for (let i = 0; i < 50 && !targets; i++) {
  try {
    targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
  } catch {
    await sleep(200);
  }
}
if (!targets) throw new Error("Chrome did not start its DevTools endpoint");
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));

let lastId = 0;
const pending = new Map();
ws.addEventListener("message", (e) => {
  const msg = JSON.parse(e.data);
  if (!msg.id || !pending.has(msg.id)) return;
  const { resolve, reject } = pending.get(msg.id);
  pending.delete(msg.id);
  if (msg.error) reject(new Error(JSON.stringify(msg.error)));
  else resolve(msg.result);
});
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++lastId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
const evaluate = async (expression) =>
  (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }))
    .result.value;
const waitFor = async (expression, ms = 15000) => {
  for (let t = 0; t < ms; t += 250) {
    if (await evaluate(`!!(${expression})`)) return;
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${expression}`);
};
const pageText = (s) => `document.body.innerText.includes(${JSON.stringify(s)})`;
const inputValue = (tag, s) =>
  `[...document.querySelectorAll('${tag}')].some((el) => el.value.includes(${JSON.stringify(s)}))`;
const viewport = (height) =>
  send("Emulation.setDeviceMetricsOverride", {
    width: WIDTH,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
const go = async (route) => {
  await send("Page.navigate", { url: opts.base + route });
  await sleep(1500);
};

// Save the viewport, or the whole page when fullPage, or down to minHeight.
const shoot = async (name, { fullPage = false, minHeight = HEIGHT } = {}) => {
  await sleep(1200); // let charts finish animating
  const height = fullPage
    ? await evaluate(`Math.max(document.documentElement.scrollHeight, ${HEIGHT})`)
    : minHeight;
  if (height !== HEIGHT) {
    await viewport(height);
    await sleep(800);
  }
  const { data } = await send("Page.captureScreenshot", {
    format: "png",
    clip: { x: 0, y: 0, width: WIDTH, height, scale: 1 },
  });
  writeFileSync(path.join(outDir, `${name}.png`), Buffer.from(data, "base64"));
  console.log(`${name}.png ${WIDTH}x${height}`);
  await viewport(HEIGHT);
};

const captures = {
  async shots() {
    await go("/shots");
    await waitFor(`document.querySelector('[aria-label="Open shot telemetry"] img')`);
    await shoot("shots");
  },
  async telemetry() {
    await go("/shots");
    await waitFor(`document.querySelector('[aria-label="Open shot telemetry"]')`);
    await evaluate(`document.querySelector('[aria-label="Open shot telemetry"]').click()`);
    await waitFor(pageText("Estimates from telemetry"));
    await waitFor(pageText("Shot time"));
    const bottom = await evaluate(
      "Math.ceil(document.querySelector('.mantine-Modal-content').getBoundingClientRect().bottom)",
    );
    await shoot("telemetry", { minHeight: Math.max(HEIGHT, bottom + 40) });
  },
  async "new-shot"() {
    await go("/shots/new");
    await waitFor(`document.querySelector('input')`);
    await sleep(2000); // maker, drink and grind defaults fill after loading
    await shoot("new-shot");
  },
  async "csv-import"() {
    if (!opts.csv) {
      console.log("csv-import skipped (no --csv)");
      return;
    }
    await go("/shots");
    await waitFor("document.querySelector('input[type=file]')");
    const { root } = await send("DOM.getDocument");
    const { nodeId } = await send("DOM.querySelector", {
      nodeId: root.nodeId,
      selector: "input[type=file]",
    });
    await send("DOM.setFileInputFiles", { nodeId, files: [path.resolve(opts.csv)] });
    await waitFor("location.pathname === '/shots/new'");
    await waitFor(inputValue("textarea", "Telemetry estimates"));
    // Show the end of the notes, where the telemetry estimates block is.
    await evaluate(
      "document.querySelectorAll('textarea').forEach((t) => { t.scrollTop = t.scrollHeight; })",
    );
    await shoot("csv-import", { fullPage: true });
  },
  async coffees() {
    await go("/coffees");
    await waitFor("document.querySelector('tbody tr')");
    await shoot("coffees");
  },
  async planner() {
    await go("/planner");
    await waitFor(pageText("Model Details"));
    await shoot("planner", { fullPage: true });
  },
  async reports() {
    await go("/reports");
    await waitFor("document.querySelector('.recharts-surface')");
    await shoot("reports");
  },
};

const unknown = only.filter((name) => !(name in captures));
if (unknown.length) throw new Error(`Unknown screenshot: ${unknown.join(", ")}`);

try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("DOM.enable");
  await viewport(HEIGHT);
  await send("Emulation.setTimezoneOverride", { timezoneId: opts.timezone });
  for (const [name, capture] of Object.entries(captures)) {
    if (!only.length || only.includes(name)) await capture();
  }
} finally {
  ws.close();
  chrome.kill();
  await sleep(500);
  rmSync(profile, { recursive: true, force: true });
}
