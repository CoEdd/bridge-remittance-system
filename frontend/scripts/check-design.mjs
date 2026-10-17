// Fails if the frontend breaks the Bridge design rules: no emoji, no gradients,
// and none of the banned marketing words. Run: npm run check:design
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const FOLDERS = ["app", "components", "lib"];
const EXTENSIONS = /\.(tsx?|css|mjs)$/;

const RULES = [
  { name: "emoji", pattern: /[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}]/u },
  { name: "gradient", pattern: /\b(?:bg-gradient-|bg-linear-|bg-radial-|bg-conic-)|\b(?:linear|radial|conic)-gradient\(/ },
  { name: "banned word", pattern: /\b(?:seamless(?:ly)?|unlock(?:s|ed|ing)?|empower(?:s|ed|ing)?|supercharg\w*|revolutionary|ai-powered|smart|magic(?:al)?)\b/i },
];

function* files(folder) {
  for (const name of readdirSync(folder)) {
    const path = join(folder, name);
    if (statSync(path).isDirectory()) yield* files(path);
    else if (EXTENSIONS.test(name)) yield path;
  }
}

const problems = [];
for (const folder of FOLDERS) {
  for (const path of files(join(ROOT, folder))) {
    readFileSync(path, "utf8")
      .split("\n")
      .forEach((line, index) => {
        for (const rule of RULES) {
          const found = line.match(rule.pattern);
          if (found) problems.push(`${relative(ROOT, path)}:${index + 1}  ${rule.name}: "${found[0]}"`);
        }
      });
  }
}

if (problems.length > 0) {
  console.error(`Design check failed (${problems.length}):\n${problems.join("\n")}`);
  process.exit(1);
}
console.log("Design check passed: no emoji, gradients or banned words.");
