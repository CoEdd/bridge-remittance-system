import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * The whole demo, run the way a presenter runs it: the demo bar's Right arrow for every
 * step, and Approve plus the one-time code typed by hand. Scripted mode, 1440x900.
 */

const API = "http://localhost:8000";
const OTP = "246810";
const START = { MYR: 985_000, CNY: 342_000, USD: 18_000 };
const TUITION = 1_200_000;
const STRANGER = 300_000;

type StepKey = "upload" | "verify" | "plan" | "pay" | "agent" | "mule" | "audit" | "redteam" | "sources";

async function done(request: APIRequestContext): Promise<Record<StepKey, boolean>> {
  const state = await (await request.get(`${API}/demo/state`)).json();
  return Object.fromEntries(state.steps.map((step: { key: StepKey; done: boolean }) => [step.key, step.done])) as Record<StepKey, boolean>;
}

async function balances(request: APIRequestContext): Promise<Record<string, number>> {
  const body = await (await request.get(`${API}/accounts`)).json();
  return Object.fromEntries(body.accounts.map((account: { currency: string; balance_minor: number }) => [account.currency, account.balance_minor]));
}

async function waitForStep(request: APIRequestContext, key: StepKey): Promise<void> {
  await expect.poll(async () => (await done(request))[key], { timeout: 60_000, message: `step ${key}` }).toBe(true);
}

/** The bar has moved on: its check mark and "Done" are on the step. */
async function barShowsDone(page: Page, number: number): Promise<void> {
  const pill = page.getByRole("region", { name: "Demo bar" }).getByRole("button", { name: new RegExp(`^${number} .*Done$`) });
  await expect(pill).toBeVisible();
}

/** Right arrow on the page, as the presenter presses it. */
async function next(page: Page): Promise<void> {
  await page.locator("body").press("ArrowRight");
}

test("the whole demo from Home with the demo bar", async ({ page, request }) => {
  expect((await (await request.get(`${API}/health`)).json()).agent_mode).toBe("scripted");

  // Home, open the bar with D, and reset with R and Enter.
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Wallets" })).toBeVisible();
  await page.locator("body").press("d");
  const bar = page.getByRole("region", { name: "Demo bar" });
  await expect(bar).toBeVisible();
  await page.locator("body").press("r");
  await expect(bar.getByText("Reset the demo?")).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("http://localhost:3000/");
  await expect.poll(async () => Object.values(await done(request)).some(Boolean)).toBe(false);
  await expect(bar.getByRole("button", { name: /1\s*Upload invoice/ })).toHaveAttribute("aria-current", "step");
  expect(await balances(request)).toEqual(START);

  // Steps 1 to 3.
  await next(page);
  await waitForStep(request, "upload");
  await barShowsDone(page, 1);
  await expect(page.locator("[data-demo='document']").first()).toBeVisible();
  await next(page);
  await waitForStep(request, "verify");
  await barShowsDone(page, 2);
  await expect(page).toHaveURL(/\/documents\?id=\d+/);
  await expect(page.locator("[data-demo='fields']")).toBeVisible();
  await next(page);
  await waitForStep(request, "plan");
  await barShowsDone(page, 3);

  // Step 4: the sheet opens by itself; the presenter approves both Tier 3 actions with the code.
  const sheet = page.getByRole("dialog");
  await expect(sheet).toBeVisible();
  for (const label of [/^Step 1 of 2/, /^Step 2 of 2/]) {
    await expect(sheet.getByText(label)).toBeVisible();
    await sheet.locator("#one-time-code").fill(OTP);
    await sheet.getByRole("button", { name: "Approve" }).click();
  }
  await waitForStep(request, "pay");
  await barShowsDone(page, 4);
  await expect(sheet).toBeHidden();

  // Bill paid, and the balances moved by exactly the conversion and the tuition.
  const bills = await (await request.get(`${API}/bills`)).json();
  expect(bills.find((bill: { amount_minor: number }) => bill.amount_minor === TUITION).status).toBe("paid");
  const actions = await (await request.get(`${API}/actions`)).json();
  const conversion = actions.find((action: { tool: string }) => action.tool === "convert_currency");
  const { amount_minor: converted, fee_minor: fee, amount_received_minor: received } = conversion.cost_breakdown;
  const paid = { MYR: START.MYR - converted - fee, CNY: START.CNY + received - TUITION, USD: START.USD };
  expect(await balances(request)).toEqual(paid);

  // Step 5: the fake agent's message is blocked, with its claim table and the reasoning open.
  await next(page);
  await waitForStep(request, "agent");
  await barShowsDone(page, 5);
  const panels = page.getByRole("region", { name: "Payment blocked" });
  const scam = panels.first();
  await expect(scam).toBeVisible();
  for (const claim of ["Says it acts for SPIU", "Pay into account 6217 9988 2041 5530", "Offers the fee for less"]) {
    // The claim rows (a list); the reasoning below is a numbered list that mentions the claims too.
    await expect(scam.locator("ul > li", { hasText: claim })).toContainText("Contradicted");
  }
  await expect(scam.locator("details")).toHaveAttribute("open", "");
  await expect(scam.getByText(/^Rule R2: /)).toBeVisible();

  // Step 6: the forward request is blocked as a money-mule pattern; the stranger's money stays put.
  await next(page);
  await waitForStep(request, "mule");
  await barShowsDone(page, 6);
  await expect(panels).toHaveCount(2);
  await expect(panels.last()).toContainText("Looks like money-mule recruitment");
  const refused = (await (await request.get(`${API}/actions`)).json()).filter((action: { status: string }) => action.status === "refused");
  expect(refused.at(-1).reasons.map((reason: { code: string }) => reason.code)).toEqual(["MONEY_MULE_PATTERN"]);
  expect(await balances(request)).toEqual({ ...paid, CNY: paid.CNY + STRANGER });

  // Step 7: the chain is intact, then a changed copy shows where it breaks.
  await next(page);
  await expect(page.getByText(/^Chain intact/)).toBeVisible();
  await waitForStep(request, "audit");
  await barShowsDone(page, 7);
  await expect(page.locator("[data-demo='tamper']")).toContainText(/Chain broken at entry #\d+/);

  // Step 8: eleven attacks, all held.
  await next(page);
  await waitForStep(request, "redteam");
  await barShowsDone(page, 8);
  await expect(page.locator("[data-demo='redteam-score']")).toContainText("11 / 11");

  // Step 9: the rule sources and their approved items.
  await next(page);
  await waitForStep(request, "sources");
  await barShowsDone(page, 9);
  await expect(page.locator("[data-demo='source-items']")).toContainText("Approved by seed");
  await expect(bar.getByText("Done")).toHaveCount(9);
});
