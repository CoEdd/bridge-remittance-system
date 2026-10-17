/**
 * Records the Bridge demo video from the real app on localhost, used the way a person would:
 * a drawn cursor glides to each target, clicks and typing are real, and every screen state is
 * waited for, never assumed. Frames come from Chrome's DevTools screencast (1920 x 1080) and are
 * encoded to H.264 at 30 fps. The start of every narration line is logged for the subtitles.
 *
 *   make demo-video [MODE=scripted|live]   starts the app in that mode, then runs this file
 *   node scripts/video/record_demo.ts      records whatever app is running on :3000 and :8000
 *
 * Needs Node 22.18 or later (it runs this TypeScript as is), the frontend's Playwright
 * (cd frontend && npm install), Google Chrome, ffmpeg with libx264, and poppler (pdftoppm, pdftotext).
 * Writes evidence/video/bridge-demo-clean.mp4 and scripts/video/timeline.json.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import type { CDPSession, Locator, Page } from "@playwright/test";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const { chromium } = createRequire(join(ROOT, "frontend/package.json"))("@playwright/test") as typeof import("@playwright/test");

const APP = process.env.APP_URL ?? "http://localhost:3000";
const API = process.env.API_URL ?? "http://localhost:8000";
const CHANNEL = process.env.VIDEO_BROWSER_CHANNEL ?? "chrome";
const VIEW = { width: 1440, height: 810 }; // CSS pixels: the width the app is designed for
const PIXEL_RATIO = 4 / 3; // so each frame is 1920 x 1080 device pixels
const FPS = 30;
const OUT_VIDEO = join(ROOT, "evidence/video/bridge-demo-clean.mp4");
const OUT_TIMELINE = join(ROOT, "scripts/video/timeline.json");
const INVOICE = join(ROOT, "demo-docs/tuition_invoice.pdf");
const AGENT_MESSAGE = readFileSync(join(ROOT, "demo-docs/agent_offer_message_ms.txt"), "utf8").trim();
const AGENT_SENDER = "Lim Wei Jie";
const TYPE_DELAY_MS = 60;
const ZOOM = 1.3;
const ZOOM_MS = 400;
const WORDS_PER_SECOND = 2.3; // a calm reading pace for the voice-over
const WAIT_LIMIT_MS = 240_000; // the longest the recorder waits for a screen state (live mode)
const SPEED_UP_AFTER_S = 3.5; // a wait longer than this is played faster, with a "Sped up" badge
const INK = "#0F1E2E";
const CARD_COLOURS = { deadline: "#2563A6", agent: "#A1261B", mule: "#A65F00", proof: "#12806F" };

interface Frame { file: string; t: number }
interface Line { scene: string; text: string; start: number }
interface Scene { id: string; title: string; start: number; end: number }
interface Wait { what: string; start: number; end: number }
interface SpeedUp { start: number; end: number; factor: number }
interface Box { left: number; top: number; width: number; height: number }

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const round = (seconds: number) => Math.round(seconds * 1000) / 1000;
const wordCount = (text: string) => text.trim().split(/\s+/).length;
const NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];

/** The DevTools screencast of one page at a time, written to numbered JPEG files with their times. */
class Film {
  frames: Frame[] = [];
  dir: string;
  t0 = 0;
  session: CDPSession | null = null;

  constructor(dir: string) {
    this.dir = dir;
  }

  /** Seconds since the first frame. */
  now(): number {
    return this.t0 ? Date.now() / 1000 - this.t0 : 0;
  }

  /** Films `page` from now on (the page shown on screen). */
  async follow(page: Page): Promise<void> {
    await this.stop();
    const session = await page.context().newCDPSession(page);
    session.on("Page.screencastFrame", (frame) => {
      const at = frame.metadata.timestamp ?? Date.now() / 1000;
      if (!this.t0) this.t0 = at;
      const file = join(this.dir, `${String(this.frames.length).padStart(6, "0")}.jpg`);
      writeFileSync(file, Buffer.from(frame.data, "base64"));
      this.frames.push({ file, t: at - this.t0 });
      session.send("Page.screencastFrameAck", { sessionId: frame.sessionId }).catch(() => undefined);
    });
    await session.send("Page.startScreencast", { format: "jpeg", quality: 92 });
    this.session = session;
    while (this.frames.length === 0) await sleep(20);
  }

  async stop(): Promise<void> {
    if (!this.session) return;
    await this.session.send("Page.stopScreencast").catch(() => undefined);
    await this.session.detach().catch(() => undefined);
    this.session = null;
  }
}

/** What the recorder says, does and waits for, on the video's clock. */
class Director {
  film: Film;
  lines: Line[] = [];
  scenes: Scene[] = [];
  waits: Wait[] = [];
  values: Record<string, string | number> = {};
  scene = "";
  lineEnds = 0; // when the current narration line has had time to be read out

  constructor(film: Film) {
    this.film = film;
  }

  async until(t: number): Promise<void> {
    const ms = (t - this.film.now()) * 1000;
    if (ms > 0) await sleep(ms);
  }

  /** Starts a narration line once the previous one has had time to be read out. */
  async say(text: string): Promise<void> {
    await this.until(this.lineEnds);
    const start = this.film.now();
    this.lines.push({ scene: this.scene, text, start: round(start) });
    this.lineEnds = start + Math.max(2, wordCount(text) / WORDS_PER_SECOND + 0.6);
  }

  async run(id: string, title: string, body: () => Promise<void>): Promise<void> {
    this.scene = id;
    const start = this.film.now();
    console.log(`${id.padEnd(4)} ${title}`);
    await body();
    await this.until(this.lineEnds + 0.4);
    this.scenes.push({ id, title, start: round(start), end: round(this.film.now()) });
  }

  /** Waits for a real screen state. A long wait is logged, so the video can play it faster. */
  async waitFor(what: string, target: Locator, timeout = WAIT_LIMIT_MS): Promise<void> {
    const start = this.film.now();
    await target.waitFor({ state: "visible", timeout });
    this.waits.push({ what, start: round(Math.max(start, this.lineEnds)), end: round(this.film.now()) });
  }

  async enabled(what: string, target: Locator): Promise<void> {
    const start = this.film.now();
    const until = Date.now() + WAIT_LIMIT_MS;
    await target.waitFor({ state: "visible", timeout: WAIT_LIMIT_MS });
    while (!(await target.isEnabled())) {
      if (Date.now() > until) throw new Error(`${what} never became clickable`);
      await sleep(100);
    }
    this.waits.push({ what, start: round(Math.max(start, this.lineEnds)), end: round(this.film.now()) });
  }

  /** Records a value read from the screen, so every number in the narration can be checked. */
  check(name: string, value: string | number): void {
    this.values[name] = value;
  }
}

/** The drawn cursor and the real mouse and keyboard behind it. */
class Hand {
  page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async place(x: number, y: number): Promise<void> {
    await this.page.evaluate(([px, py]) => {
      const video = (window as any).__video;
      video.ensureCursor();
      video.place(px, py);
    }, [x, y]);
    await this.page.mouse.move(x, y);
  }

  async where(): Promise<{ x: number; y: number }> {
    return this.page.evaluate(() => ({ ...(window as any).__video.at }));
  }

  async show(shown: boolean): Promise<void> {
    await this.page.evaluate((on) => (window as any).__video.showCursor(on), shown);
  }

  /** An eased move of 600 to 900 ms, then the real pointer follows so hover states show. */
  async glide(x: number, y: number): Promise<void> {
    const from = await this.where();
    const ms = Math.round(Math.min(900, Math.max(600, 450 + Math.hypot(x - from.x, y - from.y) * 0.45)));
    await this.page.evaluate(([px, py, pms]) => (window as any).__video.moveTo(px, py, pms), [x, y, ms]);
    await this.page.mouse.move(x, y);
  }

  /** Moves to `target` (scrolled into view first, if needed) and rests there. */
  async to(target: Locator, rest = 300, at = { x: 0.5, y: 0.5 }): Promise<void> {
    await target.waitFor({ state: "visible", timeout: 20_000 }); // long waits go through Director.waitFor
    if (!(await target.evaluate((el) => (window as any).__video.isVisible(el)))) {
      await target.evaluate((el) => (window as any).__video.reveal(el, 0.3, 700));
    }
    const box = await target.boundingBox();
    if (!box) throw new Error(`Nothing on screen for ${target}`);
    await this.glide(box.x + box.width * at.x, box.y + box.height * at.y);
    await sleep(rest);
  }

  async click(target: Locator, rest = 300): Promise<void> {
    await this.to(target, rest);
    const { x, y } = await this.where();
    await this.page.evaluate(([px, py]) => (window as any).__video.ring(px, py), [x, y]);
    await this.page.mouse.down();
    await sleep(70);
    await this.page.mouse.up();
    await sleep(250);
  }

  async type(text: string): Promise<void> {
    await this.page.keyboard.type(text, { delay: TYPE_DELAY_MS });
  }

  /** Zooms about 1.3x on something small, holds, and zooms back out. */
  async zoom(target: Locator, seconds: number): Promise<void> {
    await target.evaluate((el, [scale, ms]) => (window as any).__video.zoomTo(el, scale, ms), [ZOOM, ZOOM_MS]);
    await sleep(seconds * 1000);
    await this.page.evaluate((ms) => (window as any).__video.unzoom(ms), ZOOM_MS);
    await sleep(80);
  }

  async scrollTo(target: Locator, fraction: number, ms = 900): Promise<void> {
    await target.evaluate((el, [f, d]) => (window as any).__video.reveal(el, f, d), [fraction, ms]);
  }
}

async function getJson(url: string, init?: RequestInit): Promise<any> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

/** The model named in .env (never the key), for the record of a live run. */
function envModel(): string | null {
  try {
    const line = readFileSync(join(ROOT, ".env"), "utf8").split("\n").find((row) => row.startsWith("LLM_MODEL="));
    return line ? line.slice("LLM_MODEL=".length).trim() || null : null;
  } catch {
    return null;
  }
}

/** Makes the page's window exactly 1440 x 810 CSS pixels inside. */
async function fit(page: Page): Promise<void> {
  const session = await page.context().newCDPSession(page);
  const { windowId, bounds } = await session.send("Browser.getWindowForTarget");
  const [width, height] = await page.evaluate(() => [innerWidth, innerHeight]);
  if (width !== VIEW.width || height !== VIEW.height) {
    await session.send("Browser.setWindowBounds", {
      windowId,
      bounds: { width: (bounds.width ?? width) + VIEW.width - width, height: (bounds.height ?? height) + VIEW.height - height },
    });
  }
  await session.detach();
  const inner = await page.evaluate(() => [innerWidth, innerHeight, devicePixelRatio]);
  if (inner[0] !== VIEW.width || inner[1] !== VIEW.height) throw new Error(`The window is ${inner[0]}x${inner[1]}, not 1440x810`);
}

/**
 * The invoice in its own tab: a plain PDF viewer page showing the real PDF, rendered by poppler,
 * with invisible anchors over the parts the cursor points at (found from the PDF's own text layer).
 */
function invoiceViewer(dir: string): string {
  const pageWidth = 860;
  execFileSync("pdftoppm", ["-png", "-r", "200", "-singlefile", INVOICE, join(dir, "invoice")]);
  // Word boxes in PDF points, from the PDF's own text layer (pdftotext -tsv: level 5 rows are words).
  execFileSync("pdftotext", ["-tsv", INVOICE, join(dir, "words.tsv")]);
  const rows = readFileSync(join(dir, "words.tsv"), "utf8").trim().split("\n").slice(1).map((row) => row.split("\t"));
  const page = rows.find((row) => row[0] === "1");
  if (!page) throw new Error("pdftotext found no page");
  const scale = pageWidth / Number(page[8]);
  const words = rows
    .filter((row) => row[0] === "5")
    .map((row) => {
      const [left, top, width, height] = row.slice(6, 10).map(Number);
      return { box: [left, top, left + width, top + height], text: row[11] };
    });
  const find = (phrase: string): Box => {
    const parts = phrase.split(" ");
    for (let i = 0; i + parts.length <= words.length; i++) {
      if (parts.every((part, j) => words[i + j].text === part)) {
        const hit = words.slice(i, i + parts.length).map((word) => word.box);
        const [x0, y0] = [Math.min(...hit.map((b) => b[0])), Math.min(...hit.map((b) => b[1]))];
        const [x1, y1] = [Math.max(...hit.map((b) => b[2])), Math.max(...hit.map((b) => b[3]))];
        return { left: x0 * scale - 6, top: y0 * scale - 4, width: (x1 - x0) * scale + 12, height: (y1 - y0) * scale + 8 };
      }
    }
    throw new Error(`"${phrase}" is not in the invoice`);
  };
  const anchors: Record<string, Box> = {
    title: find("Tuition Fee Invoice"),
    number: find("SPIU-FIN-2026-104417"),
    total: find("Total amount due"),
    amount: find("CNY 12,000.00"),
    pay: find("How to pay"),
    due: find("15 November 2026"),
    account: find("4100 2026 0000 8815"),
  };
  const spans = Object.entries(anchors)
    .map(([id, b]) => `<div id="a-${id}" style="position:absolute;left:${b.left}px;top:${b.top}px;width:${b.width}px;height:${b.height}px"></div>`)
    .join("");
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>tuition_invoice.pdf</title><style>
    html,body{margin:0;background:#E7E5DF;font-family:"Helvetica Neue",Arial,sans-serif;color:${INK}}
    .bar{position:sticky;top:0;z-index:2;height:48px;display:flex;align-items:center;gap:12px;padding:0 20px;background:#FFFFFC;border-bottom:1px solid #DDD9CC;font-size:14px}
    .muted{color:#5A6573}
    .page{position:relative;width:${pageWidth}px;margin:28px auto 56px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.12),0 6px 18px rgba(0,0,0,.10)}
    .page img{display:block;width:100%}
  </style></head><body>
    <div class="bar"><svg width="16" height="20" viewBox="0 0 22 28" aria-hidden="true"><path d="M2 1h12l7 7v19H2z" fill="#FFFFFC" stroke="#5A6573" stroke-width="1.5"/><path d="M14 1v7h7" fill="none" stroke="#5A6573" stroke-width="1.5"/></svg>
      <span>tuition_invoice.pdf</span><span class="muted" style="margin-left:auto">Page 1 of 1</span><span class="muted">100%</span></div>
    <div class="page"><img src="invoice.png" alt="tuition_invoice.pdf, page 1">${spans}</div>
  </body></html>`;
  const file = join(dir, "invoice.html");
  writeFileSync(file, html);
  return pathToFileURL(file).href;
}

/** A small "Sped up" badge, drawn by the browser so it uses the same type as the app. */
async function badge(page: Page, file: string): Promise<void> {
  await page.setContent(
    `<html><body style="margin:0;background:transparent"><div id="b" style="display:inline-flex;align-items:center;gap:8px;padding:8px 14px;border-radius:999px;` +
      `background:rgba(15,30,46,0.78);color:#FFFFFC;font:600 15px/1 'Helvetica Neue',Arial,sans-serif">` +
      `<svg width="14" height="14" viewBox="0 0 14 14"><path d="M1 2l6 5-6 5zM7 2l6 5-6 5z" fill="#FFFFFC"/></svg>Sped up</div></body></html>`,
  );
  await page.locator("#b").screenshot({ path: file, omitBackground: true });
}

/** Plays every long wait faster: its first 1 s and last 0.8 s at normal speed, the middle in about 1.2 s. */
function speedUps(waits: Wait[]): SpeedUp[] {
  return waits
    .filter((wait) => wait.end - wait.start > SPEED_UP_AFTER_S)
    .map((wait) => {
      const start = wait.start + 1.0;
      const end = wait.end - 0.8;
      return { start: round(start), end: round(end), factor: Math.round(((end - start) / 1.2) * 10) / 10 };
    })
    .filter((part) => part.factor > 1.5);
}

/** Where a moment of the recording lands in the video, once the long waits are played faster. */
function videoTime(t: number, parts: SpeedUp[]): number {
  let shift = 0;
  for (const part of parts) {
    const inside = Math.max(0, Math.min(t, part.end) - part.start);
    shift += inside * (1 - 1 / part.factor);
  }
  return round(t - shift);
}

/** Frames to a 30 fps H.264 file (CRF 18), each frame shown until the next one arrived. */
function encode(frames: Frame[], end: number, parts: SpeedUp[], badgeFile: string | null, work: string): void {
  const sorted = [...frames].sort((a, b) => a.t - b.t);
  const list = ["ffconcat version 1.0"];
  sorted.forEach((frame, i) => {
    const next = i + 1 < sorted.length ? sorted[i + 1].t : end;
    const duration = Math.max(0.001, videoTime(next, parts) - videoTime(frame.t, parts));
    list.push(`file '${frame.file}'`, `duration ${duration.toFixed(4)}`);
  });
  list.push(`file '${sorted[sorted.length - 1].file}'`);
  const listFile = join(work, "frames.ffconcat");
  writeFileSync(listFile, list.join("\n") + "\n");
  const base = `[0:v]fps=${FPS},scale=1920:1080:flags=lanczos:in_range=pc:out_range=tv`;
  const shown = parts.map((part) => `between(t,${videoTime(part.start, parts)},${videoTime(part.end, parts)})`).join("+");
  const graph = badgeFile && parts.length
    ? `${base}[base];[base][1:v]overlay=x=48:y=H-h-48:enable='${shown}',format=yuv420p[v]`
    : `${base},format=yuv420p[v]`;
  mkdirSync(dirname(OUT_VIDEO), { recursive: true });
  execFileSync("ffmpeg", [
    "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listFile,
    ...(badgeFile && parts.length ? ["-i", badgeFile] : []),
    // Stop exactly where the recording ended; otherwise ffmpeg can hold the last frame several seconds too long.
    "-filter_complex", graph, "-map", "[v]", "-r", String(FPS), "-t", videoTime(end, parts).toFixed(3),
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-color_range", "tv", "-movflags", "+faststart", OUT_VIDEO,
  ], { stdio: "inherit" });
}

function probeDuration(file: string): number {
  return Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file]).toString().trim());
}

async function main(): Promise<void> {
  const health = await getJson(`${API}/health`);
  const mode: string = health.agent_mode;
  const model = mode === "live" ? envModel() : null;
  const { otp } = await getJson(`${API}/demo/settings`);
  await getJson(`${API}/demo/reset`, { method: "POST" });
  console.log(`Recording in ${mode} mode${model ? ` (${model})` : ""}${health.agent_note ? `, ${health.agent_note}` : ""}`);

  const work = mkdtempSync(join(tmpdir(), "bridge-video-"));
  const frameDir = join(work, "frames");
  mkdirSync(frameDir);
  const viewerUrl = invoiceViewer(work);
  const invoiceSize = `${Math.round(statSync(INVOICE).size / 1024)} KB`;

  const browser = await chromium.launch({
    channel: CHANNEL || undefined,
    headless: true,
    args: [`--force-device-scale-factor=${PIXEL_RATIO}`, `--window-size=${VIEW.width},${VIEW.height + 87}`, "--hide-scrollbars"],
  });
  const context = await browser.newContext({ viewport: null, colorScheme: "light", locale: "en-GB" });
  await context.addInitScript({ path: join(ROOT, "scripts/video/overlay.js") });
  const film = new Film(frameDir);
  const director = new Director(film);
  const say = (text: string) => director.say(text);
  const hold = (seconds: number) => sleep(seconds * 1000);

  const app = await context.newPage();
  await fit(app);
  const hand = new Hand(app);
  const nav = (name: string) => app.getByRole("navigation", { name: "Main" }).getByRole("link", { name });
  const dialog = app.getByRole("dialog");
  const blocked = app.locator("[aria-label='Payment blocked']");

  /** A full-screen title card under the header: 2.5 s in all, fades included. */
  const titleCard = (id: string, title: string, colour: string) =>
    director.run(id, title, async () => {
      await hand.show(false);
      await app.evaluate((card) => (window as any).__video.card(card), { title, sub: "", color: colour });
      await hold(2.0);
      await app.evaluate(() => (window as any).__video.closeCard());
      await hand.show(true);
    });

  try {
    await app.goto(`${APP}/`);
    await app.getByText("MYR 9,850.00").first().waitFor();
    await hand.place(900, 560);
    await hand.show(false);
    await app.evaluate((card) => (window as any).__video.card(card), { title: "Bridge", sub: "Team Malai Ren", color: INK });
    await film.follow(app);

    await director.run("S0", "Opening", async () => {
      await say("Good day, everyone. We are team Malai Ren, from Malaysia.");
      await say("We built Bridge, an AI money agent for international students.");
      await say("It plans and pays bills across currencies, only after the student approves.");
      await say("Today you will see it solve three real problems.");
      await director.until(director.lineEnds);
      await app.evaluate(() => (window as any).__video.closeCard());
      await hand.show(true);
    });

    await director.run("S1", "Home", async () => {
      await say("Meet Ahmad, a Malaysian student in Shenzhen.");
      await hand.to(app.getByRole("banner").getByText("Ahmad Faris"), 700);
      await say("He gets his scholarship in ringgit, but his bills are in yuan.");
      await hand.to(app.getByText("MYR 9,850.00").first(), 900);
      await hand.to(app.getByText("CNY 3,420.00").first(), 700);
      await hand.to(app.getByText("PearlTel Mobile").first(), 500);
      await hand.to(app.getByText("Lingnan Student Housing").first(), 500);
      await say("Everything you see runs in a sandbox, so no real money moves.");
      await hand.to(app.getByText("Sandbox demo: no real money moves"), 1100);
      await hand.to(app.getByRole("banner").getByText(/^Agent: /), 900);
      director.check("agentLabel", await app.getByRole("banner").getByText(/^Agent: /).innerText());
    });

    await titleCard("C1", "Problem 1 · Deadline", CARD_COLOURS.deadline);

    await director.run("S2", "Invoice", async () => {
      // The invoice opens in its own tab.
      const pdf = await context.newPage();
      await fit(pdf);
      await pdf.goto(viewerUrl);
      await pdf.locator("img").evaluate((img: HTMLImageElement) => img.decode());
      await pdf.bringToFront();
      const pdfHand = new Hand(pdf);
      await pdfHand.place(1180, 380);
      await film.follow(pdf);
      await say("Ahmad has just received his tuition invoice.");
      await hold(0.8);
      await pdfHand.to(pdf.locator("#a-title"), 1200);
      await pdfHand.to(pdf.locator("#a-number"), 600);
      await pdfHand.scrollTo(pdf.locator("#a-total"), 0.42, 1100);
      await say("Twelve thousand yuan, due on the fifteenth of November.");
      await pdfHand.to(pdf.locator("#a-amount"), 900);
      await pdfHand.scrollTo(pdf.locator("#a-pay"), 0.1, 1100);
      await pdfHand.to(pdf.locator("#a-due"), 1000);
      await pdfHand.to(pdf.locator("#a-account"), 1200);
      await director.until(director.lineEnds);
      await hold(0.5);

      // Back to Bridge: Malay first (Ahmad's language), then the upload.
      await app.bringToFront();
      await film.follow(app);
      await hand.click(nav("Assistant"));
      await director.waitFor("Assistant", app.getByText("Suggested next"));
      await hold(0.4);
      await hand.click(app.getByText("Bahasa Melayu", { exact: true }));
      const chooser = app.waitForEvent("filechooser");
      await hand.click(app.getByRole("button", { name: "Upload an invoice" }));
      const fileChooser = await chooser;
      await app.evaluate((file) => (window as any).__video.picker(file), { name: "tuition_invoice.pdf", size: invoiceSize });
      await hold(0.7);
      await hand.click(app.locator("#__video-picker-file"), 400);
      await hand.click(app.locator("#__video-picker-open"));
      await fileChooser.setFiles(INVOICE);
      await app.evaluate(() => (window as any).__video.closePicker());
      await director.waitFor("invoice read", app.locator("[data-demo=document]").filter({ hasText: "tuition_invoice.pdf" }));
      await director.waitFor("Malay summary", app.getByRole("button", { name: "Boleh saya bayar yuran ini sebelum tarikh akhir?" }));
    });

    await director.run("S3", "Read and checked", async () => {
      const row = app.locator("[data-demo=document]").filter({ hasText: "tuition_invoice.pdf" });
      await say("Bridge reads the amount, the due date and the bank account.");
      await hand.to(row.getByText(/\d+\/\d+ verified/), 300);
      director.check("verifiedFields", await row.getByText(/\d+\/\d+ verified/).innerText());
      await hand.zoom(row, 1.8);
      await hand.click(row.getByRole("link", { name: /Open source view/ }));
      const fields = app.locator("[data-demo=fields]");
      await director.waitFor("source view", fields);
      await hold(0.5);
      await hand.scrollTo(app.getByRole("heading", { name: "Original text" }), 0.02, 1000);
      await say("Each one is checked word for word against the invoice.");
      const field = (label: string) => fields.getByRole("button").filter({ has: app.getByText(label, { exact: true }) });
      await hand.to(field("Amount"), 1400);
      await hand.to(field("Due date"), 1400);
      await hand.to(field("Account"), 1400);
      // The registered account, on the Payees page (the same in live and scripted mode).
      await hand.click(nav("Payees"));
      const university = app.getByRole("row").filter({ has: app.getByRole("rowheader", { name: /Shenzhen Polytechnic International University/ }) });
      await director.waitFor("payees", university);
      await say("The account matches the university's registered fee account.");
      await hand.click(university.getByRole("button", { name: /^Show the account number/ }));
      await hand.to(university.getByText("4100 2026 0000 8815"), 900);
      const registry = university.getByText("University registry");
      await hand.to(registry, 300);
      await hand.zoom(registry, 2.0);
      await hand.click(nav("Assistant"));
      await director.waitFor("conversation", app.getByRole("button", { name: "Show English" }).last());
      await say("Ahmad reads the summary in Malay, and judges can switch to English.");
      const showEnglish = app.getByRole("button", { name: "Show English" }).last();
      await hand.to(showEnglish, 900);
      await hand.click(showEnglish);
      await hold(2.8);
      await hand.click(app.getByText("English", { exact: true }));
    });

    await director.run("S4", "Plan", async () => {
      const ask = app.getByRole("button", { name: "Can I pay this fee before the deadline?" });
      await director.enabled("question chip", ask);
      await hand.to(ask, 300);
      await say("He asks if he can pay before the deadline.");
      await hand.click(ask);
      await director.waitFor("plan", dialog.getByText("Step 1 of 2"));
      await hold(1.4);
      await hand.click(dialog.getByRole("button", { name: "Close" }).first());
      await hand.click(app.getByRole("button", { name: /^Plan/ }).last());
      await say("Bridge checks every bill due before the fifteenth, including rent and his phone bill.");
      const plan = app.getByText("Planned how to pay").last();
      await hand.scrollTo(plan, 0.02, 900);
      await hand.to(app.getByText("PearlTel Mobile").filter({ visible: true }).last(), 900);
      await hand.to(app.getByText("Lingnan Student Housing").filter({ visible: true }).last(), 1100);
      // Detail rows are <dt>/<dd> pairs: point at the amount next to the label.
      const short = app.getByText("Short by", { exact: true }).filter({ visible: true }).last().locator("xpath=following-sibling::dd[1]");
      await hand.to(short, 300);
      director.check("shortfall", (await short.innerText()).replace(/\s+/g, " "));
      await say("He is short by almost twelve thousand yuan.");
      await hand.zoom(short, 2.2);
      await say("So Bridge plans one conversion from ringgit.");
      const convert = app.getByRole("button", { name: /^Convert/ }).last();
      await hand.to(convert, 900);
      await say("It is above his limit, so it needs a one-time code.");
      await hand.zoom(convert, 1.8);
    });

    await director.run("S5", "Approve", async () => {
      await hand.click(app.getByRole("button", { name: "Review and approve" }));
      await director.waitFor("approval sheet", dialog.getByText("Step 1 of 2"));
      await say("Nothing moves until Ahmad approves.");
      await hand.to(dialog.getByText(/^Convert MYR/), 600);
      director.check("conversion", await dialog.getByText(/^Convert MYR/).innerText());
      await hand.to(dialog.getByText("You receive", { exact: true }).locator("xpath=following-sibling::dd[1]"), 1800);
      await say("Each step shows its true cost, the fee plus what the exchange rate costs him.");
      await hand.to(dialog.getByText("Fee", { exact: true }), 600);
      await hand.to(dialog.getByText("Cost hidden in the rate"), 700);
      await hand.to(dialog.getByText("True cost", { exact: true }).locator("xpath=following-sibling::dd[1]"), 900);
      await hand.click(dialog.getByText("More details"));
      await hand.to(dialog.getByText("Mid-market rate", { exact: true }), 900);
      await hand.to(dialog.getByText("Offered rate", { exact: true }), 1000);
      await hand.to(dialog.getByText(/^Demo code/), 700);
      await hand.click(app.locator("#one-time-code"));
      await hand.type(otp);
      await hand.click(dialog.getByRole("button", { name: "Approve" }));
      await director.waitFor("payment step", dialog.getByText("Step 2 of 2"));
      await hold(1.5);
      await say("The tuition is above his limit, so it also needs a one-time code.");
      const tier = dialog.getByText("Tier 3", { exact: true }).first();
      await hand.to(tier, 400);
      await hand.zoom(tier, 2.0);
      await hand.click(app.locator("#one-time-code"));
      await hand.type(otp);
      await hand.click(dialog.getByRole("button", { name: "Approve" }));
      await director.waitFor("payment done", app.getByRole("button", { name: "View receipt" }));
    });

    await director.run("S6", "Receipt", async () => {
      await say("Paid. Here is the receipt, and his balances update straight away.");
      await hand.click(app.getByRole("button", { name: "View receipt" }));
      await director.waitFor("receipt", dialog.getByText("Completed (sandbox)"));
      await hold(0.8);
      director.check("receipt", (await dialog.innerText()).replace(/\s+/g, " ").slice(0, 400));
      const amount = dialog.getByText("CNY 12,000.00", { exact: true }).first();
      await hand.to(amount, 300);
      await hand.zoom(amount, 1.8);
      await hand.to(dialog.getByText(/^Verified: /), 900);
      await hand.to(dialog.getByText("SPIU-FIN-2026-104417"), 1000);
      await hand.to(dialog.getByRole("link", { name: "Download PDF" }), 1000);
      await hand.click(dialog.getByRole("button", { name: "Close" }).last());
      const wallets = app.locator("[data-demo=wallets]");
      await hand.to(wallets, 2600);
      director.check("walletsAfterPayment", (await wallets.innerText()).replace(/\s+/g, " "));
    });

    await titleCard("C2", "Problem 2 · Fake agent", CARD_COLOURS.agent);

    await director.run("S7", "Fake agent", async () => {
      await say("Later, Ahmad gets a message from a so-called payment agent.");
      await hand.click(app.getByRole("button", { name: "Add" }));
      await hand.click(app.getByRole("menuitem", { name: "Paste a message" }));
      // No spell-check squiggles under the Malay text in the recording.
      await app.locator("#pasted-sender, #pasted-message").evaluateAll((fields) => fields.forEach((field) => field.setAttribute("spellcheck", "false")));
      await hand.click(app.locator("#pasted-sender"));
      await hand.type(AGENT_SENDER);
      await hand.click(app.locator("#pasted-message"));
      await app.keyboard.insertText(AGENT_MESSAGE); // pasted, not typed
      await hold(1.0);
      await hand.click(dialog.getByRole("button", { name: "Read message" }));
      const message = app.locator(`article[aria-label='Message from ${AGENT_SENDER}']`);
      await director.waitFor("agent message", message);
      await say("Fifteen percent off his tuition, if he pays today.");
      director.check("discount", (await message.getByText(/jimat \d+%/).innerText()).match(/\d+%/)![0]);
      await hand.to(message.getByText(/jimat \d+%/), 400);
      await hand.zoom(message, 2.2);
      const ask = app.getByRole("button", { name: "Can I pay through this agent?" });
      await director.enabled("agent question", ask);
      await hand.click(ask);
      await director.waitFor("agent blocked", blocked.first());
      await say("Bridge refuses, and shows him why.");
      await hand.to(blocked.first().getByText(/Payment blocked/).first(), 3200);
      await say("The university's own records contradict the agent and the account.");
      const contradicted = blocked.first().getByText("Contradicted");
      await hand.to(contradicted.first(), 1100);
      if ((await contradicted.count()) > 1) await hand.to(contradicted.nth(1), 1100);
      await say("Show reasoning reveals exactly which facts and rules decided.");
      const reasoning = blocked.first().getByText("Show reasoning").first();
      await hand.click(reasoning);
      const chain = reasoning.locator("xpath=ancestor::details[1]");
      await hand.scrollTo(chain, 0.08, 900);
      await hand.zoom(chain, 2.6);
      await hand.to(app.locator("[data-demo=wallets]").locator("xpath=preceding::*[normalize-space()='Blocked'][1]"), 1500);
    });

    await titleCard("C3", "Problem 3 · Money mule", CARD_COLOURS.mule);

    await director.run("S8", "Money mule", async () => {
      const transfer = app.getByRole("button", { name: "Use demo: stranger's transfer" });
      await director.enabled("stranger's transfer", transfer);
      await hand.click(transfer);
      const toast = app.getByRole("status").filter({ hasText: "received from Zhou Wei" });
      await director.waitFor("money arrives", toast);
      await say("Then three thousand yuan arrives from a stranger.");
      director.check("inbound", await toast.innerText());
      await hand.to(toast, 1200);
      await hand.to(app.getByText(/^Received/).filter({ visible: true }).last(), 1000);
      const message = app.locator("article[aria-label='Message from Zhou Wei']");
      await director.waitFor("stranger's message", message);
      await say("The sender says it was a mistake and asks Ahmad to forward it.");
      await hand.to(message.getByText("Zhou Wei", { exact: true }), 700);
      await hand.to(message.getByText(/Please forward/), 1300);
      const ask = app.getByRole("button", { name: "Can I forward this money as asked?" });
      await director.enabled("forward question", ask);
      await hand.click(ask);
      await director.waitFor("forward blocked", blocked.nth(1));
      await say("This is how students get pulled into money laundering.");
      await hand.to(blocked.nth(1).getByText(/Payment blocked/).first(), 2800);
      director.check("muleBlocked", (await blocked.nth(1).innerText()).replace(/\s+/g, " ").slice(0, 300));
      await say("Bridge refuses to move it, and tells him to return it through his bank.");
      await hand.zoom(blocked.nth(1), 2.6);
      await hand.click(blocked.nth(1).getByText("Why?", { exact: true }));
      await hand.scrollTo(blocked.nth(1), 0.05, 800);
      await hand.to(blocked.nth(1).locator("li").first(), 2800);
    });

    await titleCard("C4", "The proof", CARD_COLOURS.proof);

    await director.run("S9", "Audit log", async () => {
      await hand.click(nav("Audit log"));
      const verify = app.getByRole("button", { name: "Verify chain" });
      await director.waitFor("audit log", verify);
      await say("Every step was written to an audit log.");
      await hand.to(app.locator("table tbody tr").first(), 700);
      await hand.to(app.locator("table tbody tr").nth(3), 700);
      await hand.click(verify);
      const intact = app.getByText(/Chain intact/);
      await director.waitFor("chain intact", intact);
      await say("Each record is linked to the one before it, so the chain is intact.");
      director.check("chain", await intact.innerText());
      await hand.zoom(intact, 2.2);
      await hand.click(app.getByRole("button", { name: "Simulate tampering" }));
      const broken = app.getByText(/Chain broken at entry/).first();
      await director.waitFor("chain broken", broken);
      await say("If anyone edits a record, the break shows up straight away.");
      director.check("tamper", await broken.innerText());
      await hand.zoom(broken, 2.2);
      await hand.to(app.locator("tr").filter({ hasText: "Broken" }).first(), 1500);
      await hand.click(app.getByRole("button", { name: "Back to real log" }));
      await hold(1.2);
    });

    await director.run("S10", "Red team", async () => {
      await hand.click(nav("Security"));
      const run = app.getByRole("button", { name: "Run red-team suite" });
      await director.waitFor("security page", run);
      await say("Finally, we attacked Bridge ourselves with eleven tricks.");
      await hand.click(run);
      await hand.to(app.getByText("Fake agent discount"), 700);
      await hand.to(app.getByText("Money mule", { exact: true }), 700);
      const score = app.locator("[data-demo=redteam-score]").filter({ hasText: "passed" });
      await director.waitFor("red-team score", score);
      await director.enabled("red-team run finished", run);
      const [passed, total] = (await score.innerText()).match(/(\d+)\s*\/\s*(\d+)/)!.slice(1).map(Number);
      if (total !== 11) throw new Error(`The suite has ${total} cases, but the narration says eleven`);
      director.check("redteam", `${passed} / ${total}`);
      await say(`It stopped ${NUMBER_WORDS[passed] ?? passed} of them.`);
      await hand.to(score, 300);
      await hand.zoom(score, 2.4);
      const agentCase = app.locator("li").filter({ hasText: "Fake agent discount" }).first();
      await hand.click(agentCase.getByText("Details", { exact: true }));
      await hand.to(agentCase, 3000, { x: 0.5, y: 0.7 });
    });

    await director.run("S11", "Closing", async () => {
      await hand.show(false);
      await app.evaluate((card) => (window as any).__video.card(card), { title: "Bridge · Team Malai Ren", sub: "", color: INK });
      await say("Bridge. Pay what you owe across borders, and never pay a scammer.");
      await director.until(director.lineEnds + 1.6);
    });
  } catch (error) {
    await app.screenshot({ path: join(ROOT, "scripts/video/failed.png") }).catch(() => undefined);
    console.error(`The recording stopped in ${director.scene}: ${String(error)}`);
    console.error("A screenshot of the last screen is in scripts/video/failed.png");
    await browser.close();
    rmSync(work, { recursive: true, force: true });
    process.exit(1);
  }

  const end = film.now();
  await film.stop();
  const parts = speedUps(director.waits);
  const badgeFile = parts.length ? join(work, "badge.png") : null;
  if (badgeFile) await badge(await context.newPage(), badgeFile);
  await browser.close();

  console.log(`Encoding ${film.frames.length} frames…`);
  encode(film.frames, end, parts, badgeFile, work);
  const duration = probeDuration(OUT_VIDEO);
  const at = (t: number) => videoTime(t, parts);
  const timeline = {
    video: relative(ROOT, OUT_VIDEO),
    recordedAt: new Date().toISOString(),
    agentMode: mode,
    model,
    duration: round(duration),
    note: "Times are seconds from the start of the video. The cursor, zoom, title cards, file picker and PDF viewer tab are drawn by the recorder; everything else is the app.",
    scenes: director.scenes.map((scene) => ({ ...scene, start: at(scene.start), end: at(scene.end), length: round(at(scene.end) - at(scene.start)) })),
    lines: director.lines.map((line) => ({ ...line, start: at(line.start) })),
    spedUp: parts.map((part) => ({ start: at(part.start), end: at(part.end), factor: part.factor })),
    values: director.values,
  };
  writeFileSync(OUT_TIMELINE, JSON.stringify(timeline, null, 2) + "\n");
  rmSync(work, { recursive: true, force: true });

  console.log("\nScene lengths:");
  for (const scene of timeline.scenes) console.log(`  ${scene.id.padEnd(4)} ${scene.title.padEnd(24)} ${scene.length.toFixed(1).padStart(6)} s`);
  console.log(`  Total ${duration.toFixed(1)} s (${Math.floor(duration / 60)}:${String(Math.round(duration % 60)).padStart(2, "0")})${parts.length ? `, ${parts.length} waits sped up` : ""}`);
  console.log(`Wrote ${relative(ROOT, OUT_VIDEO)} and ${relative(ROOT, OUT_TIMELINE)}`);
  if (duration > 290) console.warn("Warning: the video is longer than 4:50.");
}

await main();
