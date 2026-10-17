/**
 * Subtitles for the demo video, made from the narration lines in scripts/video/timeline.json:
 *   evidence/video/bridge-demo.srt            the subtitles, to switch on in a player
 *   evidence/video/bridge-demo-subtitled.mp4  the clean video with them burned in
 *   evidence/video/voiceover-script.md        every line with its start and end, by scene
 * A cue has at most two rows of 42 characters and stays 1.5 to 6 seconds on screen; a line too
 * long for that is split into two cues. Every number in the narration is checked against what
 * the recording read off the screen. The subtitle images are drawn in IBM Plex Sans by the app's
 * own page, so the app must be running (make demo-video runs this file after recording).
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const { chromium } = createRequire(join(ROOT, "frontend/package.json"))("@playwright/test") as typeof import("@playwright/test");

const APP = process.env.APP_URL ?? "http://localhost:3000";
const CHANNEL = process.env.VIDEO_BROWSER_CHANNEL ?? "chrome";
const OUT = join(ROOT, "evidence/video");
const CLEAN = join(OUT, "bridge-demo-clean.mp4");
const ROW = 42; // characters per row
const MIN_S = 1.5;
const MAX_S = 6;
const GAP_S = 0.12; // between one cue and the next
const WORDS_PER_SECOND = 2.3; // the pace the recorder left for each line

interface Line { scene: string; text: string; start: number }
interface Scene { id: string; title: string; start: number; end: number }
interface Timeline { recordedAt: string; agentMode: string; model: string | null; duration: number; scenes: Scene[]; lines: Line[]; values: Record<string, string | number> }
interface Cue { scene: string; rows: string[]; start: number; end: number }

const words = (text: string) => text.trim().split(/\s+/);
const round = (seconds: number) => Math.round(seconds * 1000) / 1000;

/** The text in at most two rows of 42 characters, as even as possible; null if it does not fit. */
function wrap(text: string): string[] | null {
  if (text.length <= ROW) return [text];
  const parts = words(text);
  let best: string[] | null = null;
  for (let i = 1; i < parts.length; i++) {
    const rows = [parts.slice(0, i).join(" "), parts.slice(i).join(" ")];
    if (rows.every((row) => row.length <= ROW) && (!best || Math.max(...rows.map((r) => r.length)) < Math.max(...best.map((r) => r.length)))) {
      best = rows;
    }
  }
  return best;
}

/** A line too long for one cue, split after the comma nearest its middle (or the middle word). */
function split(text: string): string[] {
  const parts = words(text);
  const middle = text.length / 2;
  const breaks = parts.map((_, i) => i).slice(1);
  const commas = breaks.filter((i) => parts[i - 1].endsWith(","));
  const position = (i: number) => parts.slice(0, i).join(" ").length;
  const pick = (candidates: number[]) => candidates.sort((a, b) => Math.abs(position(a) - middle) - Math.abs(position(b) - middle))[0];
  const at = pick(commas.length ? commas : breaks);
  return [parts.slice(0, at).join(" "), parts.slice(at).join(" ")];
}

function cuesFor(timeline: Timeline): Cue[] {
  const cues: Cue[] = [];
  timeline.lines.forEach((line, i) => {
    const scene = timeline.scenes.find((item) => item.id === line.scene)!;
    const next = timeline.lines[i + 1]?.start ?? Infinity;
    const spoken = words(line.text).length / WORDS_PER_SECOND + 0.6;
    const end = Math.min(line.start + Math.min(Math.max(spoken, MIN_S), MAX_S * 2), next - GAP_S, scene.end - 0.05);
    const texts = wrap(line.text) ? [line.text] : split(line.text);
    const total = words(line.text).length;
    let start = line.start;
    texts.forEach((text, j) => {
      const rows = wrap(text);
      if (!rows) throw new Error(`"${text}" does not fit in two rows of ${ROW} characters`);
      const share = j === texts.length - 1 ? end : start + ((end - line.start) * words(text).length) / total;
      const cueEnd = Math.min(share, start + MAX_S);
      if (cueEnd - start < MIN_S) throw new Error(`"${text}" would be on screen for only ${(cueEnd - start).toFixed(2)} s`);
      cues.push({ scene: line.scene, rows, start: round(start), end: round(cueEnd) });
      start = cueEnd;
    });
  });
  return cues;
}

/** Every number the narration says, against the value the recording read off the screen. */
function checkNumbers(timeline: Timeline): string[] {
  const said = timeline.lines.map((line) => line.text).join(" ");
  const v = timeline.values;
  const shortfall = Number(String(v.shortfall).replace(/[^\d.]/g, ""));
  const [passed, total] = String(v.redteam).split("/").map((part) => Number(part.trim()));
  const checks: [string, boolean, string][] = [
    ["Twelve thousand yuan", said.includes("Twelve thousand yuan") && String(v.receipt).includes("CNY 12,000.00"), String(v.receipt).match(/Amount paid (CNY [\d,.]+)/)?.[1] ?? ""],
    ["short by almost twelve thousand yuan", said.includes("short by almost twelve thousand yuan") && shortfall > 11_000 && shortfall < 12_000, String(v.shortfall)],
    ["one conversion", said.includes("one conversion") && /^Convert MYR [\d,.]+ to CNY$/.test(String(v.conversion)), String(v.conversion)],
    ["Fifteen percent", said.includes("Fifteen percent") && v.discount === "15%", String(v.discount)],
    ["three thousand yuan", said.includes("three thousand yuan") && String(v.inbound).startsWith("CNY 3,000.00"), String(v.inbound)],
    ["eleven tricks", said.includes("eleven tricks") && total === 11, String(v.redteam)],
    ["It stopped eleven", said.includes("It stopped eleven of them") && passed === 11, String(v.redteam)],
  ];
  const failed = checks.filter(([, ok]) => !ok);
  if (failed.length) throw new Error(`The narration does not match the screen: ${failed.map(([name, , seen]) => `${name} (screen: ${seen})`).join("; ")}`);
  return checks.map(([name, , seen]) => `${name}: ${seen}`);
}

const clock = (seconds: number, comma = ",") => {
  const ms = Math.round(seconds * 1000);
  const [h, m, s] = [Math.floor(ms / 3_600_000), Math.floor(ms / 60_000) % 60, Math.floor(ms / 1000) % 60];
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}${comma}${String(ms % 1000).padStart(3, "0")}`;
};
const short = (seconds: number) => `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;

function srt(cues: Cue[]): string {
  return cues.map((cue, i) => `${i + 1}\n${clock(cue.start)} --> ${clock(cue.end)}\n${cue.rows.join("\n")}\n`).join("\n");
}

function voiceover(timeline: Timeline, cues: Cue[]): string {
  const lines: string[] = [
    "# Bridge demo video: voice-over script",
    "",
    `Video: bridge-demo-subtitled.mp4 (${short(timeline.duration)}), recorded in ${timeline.agentMode} mode${timeline.model ? ` (${timeline.model})` : ""} on ${timeline.recordedAt.slice(0, 10)}.`,
    "Read each line from its start time; it should be finished by its end time. Title cards have no voice.",
    "",
  ];
  for (const scene of timeline.scenes) {
    lines.push(`## ${scene.id} · ${scene.title} (${short(scene.start)} to ${short(scene.end)})`, "");
    const spoken = timeline.lines.filter((line) => line.scene === scene.id);
    if (!spoken.length) {
      lines.push("Title card, no voice.", "");
      continue;
    }
    lines.push("| Start | End | Line |", "|---|---|---|");
    for (const line of spoken) {
      const own = cues.filter((cue) => cue.scene === line.scene && cue.start >= line.start - 0.001 && line.text.includes(cue.rows.join(" ")));
      lines.push(`| ${short(line.start)} | ${short(own[own.length - 1].end)} | ${line.text} |`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

/** One transparent PNG per cue: white IBM Plex Sans on a dark see-through box, drawn by the app's page. */
async function renderCues(cues: Cue[], dir: string): Promise<string[]> {
  const browser = await chromium.launch({ channel: CHANNEL || undefined, headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto(`${APP}/`);
  await page.evaluate(async () => {
    await document.fonts.ready;
    const style = document.createElement("style");
    style.textContent = "html,body{background:transparent!important} body>*{display:none!important}";
    document.head.appendChild(style);
    const box = document.createElement("div");
    box.id = "cue";
    box.style.cssText =
      "position:fixed;left:50%;top:40px;transform:translateX(-50%);max-width:1400px;padding:10px 28px 12px;border-radius:10px;" +
      "background:rgba(15,30,46,0.76);color:#FFFFFC;font-family:var(--font-plex-sans),sans-serif;font-weight:500;" +
      "font-size:40px;line-height:1.3;text-align:center;white-space:nowrap";
    document.documentElement.appendChild(box);
  });
  const files: string[] = [];
  for (const [i, cue] of cues.entries()) {
    await page.evaluate((rows) => {
      const box = document.getElementById("cue")!;
      box.replaceChildren(...rows.flatMap((row, j) => (j ? [document.createElement("br"), document.createTextNode(row)] : [document.createTextNode(row)])));
    }, cue.rows);
    const file = join(dir, `cue-${String(i).padStart(3, "0")}.png`);
    await page.locator("#cue").screenshot({ path: file, omitBackground: true });
    files.push(file);
  }
  const font = await page.evaluate(() => getComputedStyle(document.getElementById("cue")!).fontFamily);
  await browser.close();
  if (!/IBM Plex Sans/i.test(font)) throw new Error(`The subtitles are not in IBM Plex Sans (${font})`);
  return files;
}

function burn(cues: Cue[], images: string[], out: string): void {
  const inputs = images.flatMap((file) => ["-i", file]);
  const steps = cues.map((cue, i) => {
    const from = i === 0 ? "[0:v]" : `[v${i}]`;
    return `${from}[${i + 1}:v]overlay=x=(W-w)/2:y=H-h-64:enable='between(t,${cue.start},${cue.end})'[v${i + 1}]`;
  });
  execFileSync("ffmpeg", [
    "-y", "-loglevel", "error", "-i", CLEAN, ...inputs,
    "-filter_complex", `${steps.join(";")};[v${cues.length}]format=yuv420p[out]`, "-map", "[out]",
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-color_range", "tv", "-movflags", "+faststart", out,
  ], { stdio: "inherit" });
}

const duration = (file: string) =>
  Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file]).toString().trim());

async function main(): Promise<void> {
  const timeline: Timeline = JSON.parse(readFileSync(join(ROOT, "scripts/video/timeline.json"), "utf8"));
  const numbers = checkNumbers(timeline);
  const cues = cuesFor(timeline);
  const work = mkdtempSync(join(tmpdir(), "bridge-subtitles-"));
  try {
    const images = await renderCues(cues, work);
    writeFileSync(join(OUT, "bridge-demo.srt"), srt(cues));
    writeFileSync(join(OUT, "voiceover-script.md"), voiceover(timeline, cues));
    console.log(`Burning ${cues.length} subtitles into the video…`);
    burn(cues, images, join(OUT, "bridge-demo-subtitled.mp4"));
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
  const length = duration(join(OUT, "bridge-demo-subtitled.mp4"));
  console.log(`${cues.length} subtitles from ${timeline.lines.length} lines; longest row ${Math.max(...cues.flatMap((cue) => cue.rows.map((row) => row.length)))} characters;`);
  console.log(`on screen ${Math.min(...cues.map((cue) => cue.end - cue.start)).toFixed(2)} to ${Math.max(...cues.map((cue) => cue.end - cue.start)).toFixed(2)} s each.`);
  console.log(`Numbers checked against the screen: ${numbers.join("; ")}`);
  console.log(`bridge-demo-subtitled.mp4: ${short(length)} (clean: ${short(duration(CLEAN))})`);
  if (length > 290) throw new Error("The video is longer than 4:50");
}

await main();
