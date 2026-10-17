// Drawn into every page of the recording browser by scripts/video/record_demo.ts. None of this is
// part of the app: the cursor and its click ring, the zoom, title cards, the file picker and the
// smooth scrolling exist only in the video, so the viewer can follow what the recorder does.
(() => {
  if (window.__video) return;
  const TOP = 2147483000;
  const INK = "#0F1E2E";
  const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const frame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  /** Runs `step(k)` with k eased from 0 to 1 over `ms`. */
  function animate(ms, step) {
    return new Promise((resolve) => {
      const start = performance.now();
      const tick = (now) => {
        const t = Math.min(1, (now - start) / ms);
        step(ease(t));
        if (t < 1) requestAnimationFrame(tick);
        else resolve();
      };
      requestAnimationFrame(tick);
    });
  }

  // The cursor: a black arrow with a white outline. Its tip is the pointer's position.
  const at = { x: 720, y: 405 };
  let cursor = null;
  function ensureCursor() {
    if (cursor && cursor.isConnected) return cursor;
    cursor = document.createElement("div");
    cursor.setAttribute("aria-hidden", "true");
    cursor.style.cssText = `position:fixed;left:0;top:0;width:26px;height:34px;z-index:${TOP + 10};pointer-events:none;will-change:transform;transition:opacity 200ms ease;`;
    cursor.innerHTML =
      '<svg width="26" height="34" viewBox="0 0 26 34"><path d="M3 2 L3 27 L9.5 21 L14 31.5 L18.5 29.5 L14 19.5 L22.5 19.5 Z" ' +
      'fill="#0F1E2E" stroke="#FFFFFF" stroke-width="2" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(cursor);
    place(at.x, at.y);
    return cursor;
  }
  function place(x, y) {
    at.x = x;
    at.y = y;
    if (cursor) cursor.style.transform = `translate(${x - 3}px, ${y - 2}px)`;
  }
  function moveTo(x, y, ms) {
    ensureCursor();
    const from = { x: at.x, y: at.y };
    return animate(ms, (k) => place(from.x + (x - from.x) * k, from.y + (y - from.y) * k));
  }
  function showCursor(shown) {
    ensureCursor().style.opacity = shown ? "1" : "0";
  }

  /** A soft ring where the click lands. */
  function ring(x, y) {
    const el = document.createElement("div");
    el.style.cssText =
      `position:fixed;left:${x - 24}px;top:${y - 24}px;width:48px;height:48px;border-radius:50%;` +
      `border:3px solid rgba(18,128,111,0.6);background:rgba(18,128,111,0.12);z-index:${TOP + 9};pointer-events:none;` +
      "transform:scale(0.25);opacity:1;transition:transform 420ms cubic-bezier(.2,.7,.3,1),opacity 420ms ease-out;";
    document.documentElement.appendChild(el);
    frame().then(frame).then(() => {
      el.style.transform = "scale(1)";
      el.style.opacity = "0";
    });
    setTimeout(() => el.remove(), 600);
  }

  /** Scrolls `el` (or the page) so that its scrollTop becomes `top`, eased. */
  function scrollTo(el, top, ms) {
    const box = el || document.scrollingElement;
    const from = box.scrollTop;
    const to = Math.max(0, Math.min(top, box.scrollHeight - box.clientHeight));
    return animate(ms, (k) => {
      box.scrollTop = from + (to - from) * k;
    });
  }

  /** The nearest ancestor of `el` that scrolls vertically (or the page). */
  function scroller(el) {
    for (let node = el.parentElement; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1) return node;
    }
    return document.scrollingElement;
  }

  /** Brings `el` into view with an eased scroll, so that its top sits at `fraction` of the visible height. */
  async function reveal(el, fraction, ms) {
    const box = scroller(el);
    const page = box === document.scrollingElement;
    const view = page ? { top: headerBottom(), bottom: innerHeight } : box.getBoundingClientRect();
    const rect = el.getBoundingClientRect();
    const height = view.bottom - view.top;
    const target = box.scrollTop + (rect.top - view.top) - height * fraction;
    await scrollTo(box, target, ms);
  }

  /** Whether `el` is fully visible inside its scrolling box (and below the header). */
  function isVisible(el) {
    const box = scroller(el);
    const dialog = el.closest('[role="dialog"]');
    const page = box === document.scrollingElement;
    const view = page ? { top: dialog ? 0 : headerBottom(), bottom: innerHeight } : box.getBoundingClientRect();
    const rect = el.getBoundingClientRect();
    return rect.top >= view.top + 4 && rect.bottom <= view.bottom - 4;
  }

  function headerBottom() {
    const header = document.querySelector("header");
    return header ? header.getBoundingClientRect().bottom : 0;
  }

  // Zoom: the content under the header (or inside an open sheet) grows by `scale` around the
  // target, clipped to its own box, so the header with "Sandbox demo" and "Agent" stays as it is.
  let zoomed = null;
  async function zoomTo(el, scale, ms) {
    if (zoomed) await unzoom(0);
    const dialog = el.closest('[role="dialog"]');
    const host = dialog ? dialog.querySelector(".overflow-y-auto") : document.querySelector("main");
    if (!host) return null;
    const box = host.getBoundingClientRect();
    const left = Math.max(box.left, 0);
    const right = Math.min(box.right, innerWidth);
    const top = Math.max(box.top, dialog ? 0 : headerBottom());
    const bottom = Math.min(box.bottom, innerHeight);
    const target = el.getBoundingClientRect();
    // Never so far that the target itself is cut off; not worth it below 1.08x.
    scale = Math.min(scale, (right - left - 48) / target.width, (bottom - top - 48) / target.height);
    if (scale < 1.08) return { x: at.x, y: at.y };
    const c = { x: target.left + target.width / 2, y: target.top + target.height / 2 };
    // The origin that moves the target to the middle of the visible area, kept inside it so no edge shows.
    const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
    const o = {
      x: clamp((scale * c.x - (left + right) / 2) / (scale - 1), left, right),
      y: clamp((scale * c.y - (top + bottom) / 2) / (scale - 1), top, bottom),
    };
    const layers = [...host.children].filter((child) => child !== cursor);
    const transition = `transform ${ms}ms cubic-bezier(.65,0,.35,1)`;
    for (const layer of layers) {
      const r = layer.getBoundingClientRect();
      layer.style.transformOrigin = `${o.x - r.left}px ${o.y - r.top}px`;
      layer.style.transition = transition;
    }
    if (!dialog) host.style.clipPath = "inset(0)";
    await frame();
    for (const layer of layers) layer.style.transform = `scale(${scale})`;
    zoomed = { host, layers, o, scale, dialog };
    // The cursor stays on what it points at.
    const cx = o.x + scale * (at.x - o.x);
    const cy = o.y + scale * (at.y - o.y);
    await moveTo(cx, cy, ms);
    return { x: cx, y: cy };
  }
  async function unzoom(ms) {
    if (!zoomed) return;
    const { host, layers, o, scale, dialog } = zoomed;
    zoomed = null;
    for (const layer of layers) {
      layer.style.transition = `transform ${ms}ms cubic-bezier(.65,0,.35,1)`;
      layer.style.transform = "scale(1)";
    }
    await moveTo(o.x + (at.x - o.x) / scale, o.y + (at.y - o.y) / scale, Math.max(ms, 1));
    await wait(30);
    for (const layer of layers) {
      layer.style.transform = "";
      layer.style.transformOrigin = "";
      layer.style.transition = "";
    }
    if (!dialog) host.style.clipPath = "";
  }

  // Title cards cover everything under the header, so the header's sandbox note and agent label stay in view.
  async function card({ title, sub, color }) {
    const el = document.createElement("div");
    el.id = "__video-card";
    el.style.cssText =
      `position:fixed;left:0;right:0;bottom:0;top:${headerBottom()}px;z-index:${TOP};background:#F6F4EE;` +
      "display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;opacity:0;transition:opacity 250ms ease;";
    const bar = `<div style="width:64px;height:4px;border-radius:2px;background:${color}"></div>`;
    const heading = `<div style="font-family:var(--font-space-grotesk),sans-serif;font-weight:600;font-size:60px;line-height:1.1;letter-spacing:-0.01em;color:${color}">${title}</div>`;
    const below = sub ? `<div style="font-family:var(--font-plex-sans),sans-serif;font-size:24px;color:#5A6573">${sub}</div>` : "";
    el.innerHTML = bar + heading + below;
    document.documentElement.appendChild(el);
    await frame();
    el.style.opacity = "1";
    await wait(260);
  }
  async function closeCard() {
    const el = document.getElementById("__video-card");
    if (!el) return;
    el.style.opacity = "0";
    await wait(260);
    el.remove();
  }

  // The file picker. The browser's own picker is a separate window that a page recording cannot
  // show, so this one is drawn in its place; choosing the file hands the real file to the app.
  function picker({ name, size }) {
    const el = document.createElement("div");
    el.id = "__video-picker";
    el.style.cssText =
      `position:fixed;inset:0;z-index:${TOP + 1};background:rgba(15,30,46,0.28);display:flex;align-items:center;justify-content:center;` +
      "opacity:0;transition:opacity 200ms ease;font-family:var(--font-plex-sans),sans-serif;color:#0F1E2E;";
    const folder = (label, on) =>
      `<div style="padding:8px 12px;border-radius:8px;font-size:15px;${on ? "background:#E3F3EF;color:#0F1E2E;font-weight:600" : "color:#4A5568"}">${label}</div>`;
    el.innerHTML = `
      <div style="width:720px;border:1px solid #DDD9CC;border-radius:12px;background:#FFFFFC;box-shadow:0 24px 60px rgba(15,30,46,0.25);overflow:hidden;transform:translateY(8px);transition:transform 200ms ease" id="__video-picker-window">
        <div style="padding:16px 20px;border-bottom:1px solid #DDD9CC;font-size:18px;font-weight:600">Choose a file to upload</div>
        <div style="display:flex;min-height:260px">
          <div style="width:180px;padding:12px;border-right:1px solid #DDD9CC;display:flex;flex-direction:column;gap:4px">
            ${folder("Recent", false)}${folder("Desktop", false)}${folder("Documents", false)}${folder("Downloads", true)}
          </div>
          <div style="flex:1;padding:12px 16px">
            <div style="display:flex;font-size:13px;color:#5A6573;padding:0 12px 8px;border-bottom:1px solid #DDD9CC">
              <span style="flex:1">Name</span><span style="width:90px;text-align:right">Size</span><span style="width:110px;text-align:right">Kind</span>
            </div>
            <div id="__video-picker-file" style="display:flex;align-items:center;gap:12px;margin-top:8px;padding:10px 12px;border-radius:8px;font-size:15px;cursor:default">
              <svg width="22" height="28" viewBox="0 0 22 28" aria-hidden="true"><path d="M2 1h12l7 7v19H2z" fill="#FFFFFC" stroke="#5A6573" stroke-width="1.5"/><path d="M14 1v7h7" fill="none" stroke="#5A6573" stroke-width="1.5"/><rect x="4" y="15" width="14" height="7" rx="1.5" fill="#A1261B"/><text x="11" y="20.6" font-size="5.5" font-family="sans-serif" font-weight="700" fill="#fff" text-anchor="middle">PDF</text></svg>
              <span style="flex:1">${name}</span><span style="width:90px;text-align:right;color:#4A5568">${size}</span><span style="width:110px;text-align:right;color:#4A5568">PDF document</span>
            </div>
          </div>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:8px;padding:16px 20px;border-top:1px solid #DDD9CC">
          <div id="__video-picker-cancel" style="padding:10px 18px;border:1px solid #DDD9CC;border-radius:8px;font-size:15px;font-weight:500">Cancel</div>
          <div id="__video-picker-open" style="padding:10px 22px;border-radius:8px;font-size:15px;font-weight:600;background:#DDD9CC;color:#5A6573">Open</div>
        </div>
      </div>`;
    document.documentElement.appendChild(el);
    const file = el.querySelector("#__video-picker-file");
    const open = el.querySelector("#__video-picker-open");
    file.addEventListener("click", () => {
      file.style.background = "#E3F3EF";
      file.style.outline = "2px solid #12806F";
      open.style.background = "#12806F";
      open.style.color = "#FFFFFC";
    });
    frame().then(() => {
      el.style.opacity = "1";
      el.querySelector("#__video-picker-window").style.transform = "translateY(0)";
    });
  }
  async function closePicker() {
    const el = document.getElementById("__video-picker");
    if (!el) return;
    el.style.opacity = "0";
    await wait(220);
    el.remove();
  }

  // Nothing is drawn until the recorder first asks, after the page has loaded, so the app's own
  // start-up (and React's hydration) never sees these elements.
  window.__video = { ensureCursor, place, moveTo, showCursor, ring, scrollTo, reveal, isVisible, zoomTo, unzoom, card, closeCard, picker, closePicker, at };
})();
