// Render an HTML motion page to MP4, one frame at a time, and mux the voice track.
//
// Usage: node render.mjs scenes.html voice.wav out.mp4 [--fps 30] [--from 0] [--to <seconds>] [--scale 1]
//
// The page must:
//   - lay out a fixed 1920x1080 stage (no CSS fitting while rendering)
//   - expose window.render(t): draw the frame at t seconds, deterministic, no timers or rAF
//   - expose window.TL.total (seconds), or pass --to
// Frames are piped to ffmpeg as JPEG, so there is no folder of 12,000 PNGs.
// Playwright and Chromium are expected to be preinstalled: require("playwright") must work.
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";
import path from "node:path";

// require() honours the preinstalled global Playwright; a bare ESM import does not.
const { chromium } = createRequire(import.meta.url)("playwright");

const [page_, audio, out, ...rest] = process.argv.slice(2);
if (!out) { console.error("usage: node render.mjs scenes.html voice.wav out.mp4 [--fps 30] [--from s] [--to s] [--scale 1]"); process.exit(1); }
const opt = (k, d) => { const i = rest.indexOf("--" + k); return i >= 0 ? Number(rest[i + 1]) : d; };
const fps = opt("fps", 30), from = opt("from", 0), scale = opt("scale", 1);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: scale });
page.on("pageerror", e => { console.error("page error:", e.message); process.exitCode = 1; });
await page.goto(pathToFileURL(path.resolve(page_)).href + "#render");
await page.evaluate(() => document.fonts.ready);
await page.waitForFunction(() => typeof window.render === "function");
const total = opt("to", await page.evaluate(() => window.TL?.total ?? 0));
if (!total) { console.error("no duration: set window.TL.total or pass --to"); process.exit(1); }
const n = Math.ceil((total - from) * fps);

const ff = spawn("ffmpeg", ["-y", "-loglevel", "error",
  "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
  "-ss", String(from), "-t", String(total - from), "-i", audio,
  "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
  "-vf", "scale=1920:1080", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", out],
  { stdio: ["pipe", "inherit", "inherit"] });
const done = new Promise((ok, bad) => ff.on("close", c => (c ? bad(new Error("ffmpeg exit " + c)) : ok())));

const t0 = Date.now();
for (let f = 0; f < n; f++) {
  await page.evaluate(t => window.render(t), from + f / fps);
  const jpg = await page.screenshot({ type: "jpeg", quality: 92 });
  if (!ff.stdin.write(jpg)) await new Promise(r => ff.stdin.once("drain", r));
  if (f % (fps * 10) === 0) process.stdout.write(`\r${f}/${n} frames, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
}
ff.stdin.end();
await done;
await browser.close();
console.log(`\n${n} frames -> ${out}`);
