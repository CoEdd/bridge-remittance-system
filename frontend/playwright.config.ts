import { defineConfig } from "@playwright/test";

/**
 * One end-to-end test of the whole demo (make e2e). It needs the app running in scripted
 * mode on localhost:3000 and :8000. It uses the Chrome installed on the machine; set
 * E2E_BROWSER_CHANNEL="" to use Playwright's own Chromium (npx playwright install chromium).
 */
const channel = process.env.E2E_BROWSER_CHANNEL ?? "chrome";

export default defineConfig({
  testDir: "./e2e",
  timeout: 240_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    viewport: { width: 1440, height: 900 },
    ...(channel ? { channel } : {}),
    trace: "retain-on-failure",
  },
});
