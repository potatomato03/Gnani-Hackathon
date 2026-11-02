// End-to-end check of the follow-up demo in a real browser.
// Needs the API on :8000 and the web app on :3000 (see README), and Playwright with a Chromium build.
// Usage: node apps/web/scripts/e2e.mjs [screenshot-dir]
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const WEB = process.env.WEB_URL ?? "http://localhost:3000";
const shots = process.argv[2];
if (shots) mkdirSync(shots, { recursive: true });

const browser = await chromium.launch();
const results = [];
const check = (name, ok) => {
  results.push([name, ok]);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
};

async function run(viewport, label) {
  const page = await browser.newPage({ viewport });
  await page.goto(WEB);
  const chat = page.locator(".chat");
  await chat.locator(".bubble.summary").waitFor();
  await page.getByRole("button", { name: "Reset demo" }).click();
  await page.locator(".empty", { hasText: "Nothing needs the doctor yet." }).waitFor();
  await chat.locator(".bubble.summary").waitFor();
  check(`${label}: summary discloses AI and shows the approved medicine`,
    /AI/.test(await chat.innerText()) && /DOLO 650/.test(await chat.innerText()));
  check(`${label}: synthetic banner is shown`, await page.getByText("SYNTHETIC DATA").isVisible());
  if (shots) await page.screenshot({ path: `${shots}/${label}-1-summary.png`, fullPage: true });

  await page.getByRole("button", { name: /Advance to next check-in/ }).click();
  await page.locator(".quick button").first().waitFor();
  const buttons = await page.locator(".quick button").allInnerTexts();
  check(`${label}: check-in shows three quick replies`, buttons.length === 3);

  await page.locator(".quick button", { hasText: "कोई दिक्कत नहीं" }).click();
  await page.locator(".quick button", { hasText: "ज़्यादा खराब" }).click();
  await page.locator(".task.worse").first().waitFor();
  check(`${label}: "worse" creates a task for the doctor`, await page.locator(".task.worse").count() >= 1);

  await page.getByLabel("Message").fill("seene mein dard ho raha hai");
  await page.getByRole("button", { name: "Send" }).click();
  await chat.locator(".bubble.urgent").waitFor();
  const first = page.locator(".tasks .task").first();
  check(`${label}: warning sign gets the urgent reply and an urgent task on top`,
    (await first.getAttribute("class")).includes("urgent"));
  if (shots) await page.screenshot({ path: `${shots}/${label}-2-urgent.png`, fullPage: true });

  await page.getByLabel("Message").fill("STOP");
  await page.getByRole("button", { name: "Send" }).click();
  await chat.locator(".bubble.system").waitFor();
  check(`${label}: STOP confirms and disables Advance`,
    await page.getByRole("button", { name: /Advance to next check-in/ }).isDisabled());

  await page.selectOption("select", "fam-010-a");
  await chat.locator(".bubble.summary", { hasText: "WYSOLONE" }).waitFor();
  await page.getByLabel("Message").fill("Inhaler दिन में कितनी बार ले सकते हैं?");
  await page.getByRole("button", { name: "Send" }).click();
  await chat.locator(".bubble.answer").waitFor();
  check(`${label}: medicine question answered from the approved row`,
    /ASTHALIN/.test(await chat.locator(".bubble.answer").innerText()));
  await page.getByLabel("Message").fill("Wysolone अभी बंद कर दूँ?");
  await page.getByRole("button", { name: "Send" }).click();
  await page.locator(".task.question").first().waitFor();
  check(`${label}: request to stop a medicine goes to the doctor`, await page.locator(".task.question").count() >= 1);
  if (shots) await page.screenshot({ path: `${shots}/${label}-3-asthma.png`, fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  check(`${label}: no horizontal scroll`, !overflow);
  await page.close();
}

try {
  await run({ width: 1280, height: 900 }, "desktop");
  await run({ width: 390, height: 844 }, "phone");
} finally {
  await browser.close();
}
const failed = results.filter(([, ok]) => !ok).length;
console.log(`${results.length - failed} of ${results.length} checks passed`);
process.exit(failed ? 1 : 0);
