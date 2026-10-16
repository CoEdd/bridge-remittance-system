// Checks every text colour against the backgrounds it is used on, for WCAG AA (4.5:1 for
// body text). Colours are read from app/globals.css. Run: npm run check:contrast
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
const token = (name) => {
  const found = css.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, "i"));
  if (!found) throw new Error(`No colour token ${name}`);
  return found[1];
};
const rgb = (hex) => [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16));
// The hover shades are the palette colour mixed 85% with ink, as in globals.css.
const mix = (a, b, share) => `#${rgb(a).map((value, i) => Math.round(value * share + rgb(b)[i] * (1 - share)).toString(16).padStart(2, "0")).join("")}`;
const luminance = (hex) => {
  const [r, g, b] = rgb(hex).map((value) => {
    const s = value / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
};

const colours = Object.fromEntries(
  ["ink", "paper", "surface", "body", "muted", "teal", "teal-tint", "amber-ink", "amber-tint", "danger", "danger-tint"].map((name) => [name, token(name)]),
);
colours["teal-hover"] = mix(colours.teal, colours.ink, 0.85);
colours["danger-hover"] = mix(colours.danger, colours.ink, 0.85);

// Text colour -> the backgrounds it appears on in the app.
const PAIRS = {
  ink: ["paper", "surface", "teal-tint", "amber-tint", "danger-tint"],
  body: ["paper", "surface", "teal-tint", "amber-tint", "danger-tint"],
  muted: ["paper", "surface", "teal-tint", "amber-tint"],
  teal: ["surface"], // links and disclosures sit on cards only
  "amber-ink": ["amber-tint", "paper", "surface"],
  danger: ["danger-tint", "paper", "surface"],
  surface: ["teal", "teal-hover", "danger", "danger-hover"], // text on filled buttons
};

// Icons and other graphics need 3:1 (WCAG 1.4.11): teal icons on the page, on cards and on the tint.
const GRAPHICS = { teal: ["paper", "surface", "teal-tint"], muted: ["paper", "surface"] };

let failures = 0;
function check(pairs, minimum, kind) {
  for (const [colour, backgrounds] of Object.entries(pairs)) {
    for (const background of backgrounds) {
      const value = ratio(colours[colour], colours[background]);
      const ok = value >= minimum;
      if (!ok) failures += 1;
      console.log(`${ok ? "pass" : "FAIL"}  ${kind} ${colour.padEnd(10)} on ${background.padEnd(12)} ${value.toFixed(2)}:1 (needs ${minimum}:1)`);
    }
  }
}
check(PAIRS, 4.5, "text ");
check(GRAPHICS, 3, "icon ");
if (failures > 0) {
  console.error(`${failures} pair(s) below WCAG AA.`);
  process.exit(1);
}
console.log("Contrast check passed: text at least 4.5:1, icons at least 3:1 (WCAG AA).");
