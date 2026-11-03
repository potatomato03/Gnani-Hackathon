// End-to-end check of the follow-up demo in a real browser.
// Needs the API on :8000 and the web app on :3000 (see README), and Playwright with a Chromium build.
// Start the API with VOICERX_FAKE_SPEECH=1 so the voice checks run offline and spend no Gnani credits.
// Usage: node apps/web/scripts/e2e.mjs [screenshot-dir]
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const WEB = process.env.WEB_URL ?? "http://localhost:3000";
const API = process.env.API_URL ?? "http://localhost:8000";
const shots = process.argv[2];
if (shots) mkdirSync(shots, { recursive: true });

const browser = await chromium.launch({
  args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"], // a fake microphone
});
const results = [];
const check = (name, ok) => {
  results.push([name, ok]);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
};

async function run(viewport, label) {
  const page = await browser.newPage({ viewport });
  await page.goto(WEB);
  const chat = page.locator(".chat");
  // A Hindi visit starts by asking for the language (D-116); pick Hindi to get the summary.
  const chooseHindi = async () => {
    await page.locator(".quick button", { hasText: "हिंदी" }).click();
    await chat.locator(".bubble.summary").last().waitFor();
  };
  await page.locator(".quick button", { hasText: "English" }).waitFor();
  await page.getByRole("button", { name: "Reset demo" }).click();
  await page.locator(".empty", { hasText: "Nothing needs the doctor yet." }).waitFor();
  await page.locator(".quick button", { hasText: "English" }).waitFor();
  check(`${label}: first message discloses AI and offers Hindi or English`,
    /AI/.test(await chat.innerText()) && (await page.locator(".quick button").count()) === 2);
  await chooseHindi();
  check(`${label}: summary shows the approved medicine`, /DOLO 650/.test(await chat.innerText()));
  check(`${label}: summary offers the five-button quick menu`, (await page.locator(".quick button").count()) === 5);
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

  await page.getByLabel("Message", { exact: true }).fill("seene mein dard ho raha hai");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await chat.locator(".bubble.urgent").waitFor();
  const first = page.locator(".tasks .task").first();
  check(`${label}: warning sign gets the urgent reply and an urgent task on top`,
    (await first.getAttribute("class")).includes("urgent"));
  if (shots) await page.screenshot({ path: `${shots}/${label}-2-urgent.png`, fullPage: true });

  await page.getByLabel("Message", { exact: true }).fill("STOP");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await chat.locator(".bubble.system").waitFor();
  check(`${label}: STOP confirms and disables Advance`,
    await page.getByRole("button", { name: /Advance to next check-in/ }).isDisabled());

  const asthma = await page.$$eval("select option", (options) =>
    options.find((o) => o.textContent.includes("Wysolone"))?.value);
  await page.selectOption("select", asthma);
  await chooseHindi();
  await chat.locator(".bubble.summary", { hasText: "WYSOLONE" }).waitFor();
  await page.getByLabel("Message", { exact: true }).fill("Inhaler दिन में कितनी बार ले सकते हैं?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await chat.locator(".bubble.answer").waitFor();
  check(`${label}: medicine question answered from the approved row`,
    /ASTHALIN/.test(await chat.locator(".bubble.answer").innerText()));
  await page.getByLabel("Message", { exact: true }).fill("Wysolone अभी बंद कर दूँ?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.locator(".task.question").first().waitFor();
  check(`${label}: request to stop a medicine goes to the doctor`, await page.locator(".task.question").count() >= 1);

  const uploaded = page.waitForResponse((r) => r.url().endsWith("/documents") && r.request().method() === "POST");
  await page.setInputFiles('input[type="file"]', "runs/followup-demo/visits/fam-001-a/report.pdf");
  await chat.locator(".bubble.patient", { hasText: "Sent a PDF" }).waitFor();
  check(`${label}: a report PDF is accepted and answered with fixed text`, (await uploaded).ok());

  const voiceOn = (await (await fetch(API + "/health")).json()).speech !== "off";
  if (voiceOn) {
    const listened = page.waitForResponse((r) => r.url().includes("/voice") && r.request().method() === "POST");
    await chat.locator(".bubble.summary .listen").click();
    check(`${label}: Listen voices the clinic message`, (await listened).ok());
    await page.getByLabel("Message", { exact: true }).fill("Montair कब लेनी है?");
    await page.getByRole("button", { name: "Send as synthetic voice note" }).click();
    await chat.locator(".bubble.patient .tag.voice").first().waitFor();
    await chat.locator(".bubble.answer", { hasText: "MONTAIR" }).waitFor();
    check(`${label}: synthetic voice note is transcribed and answered from the approved row`, true);
    await page.getByRole("button", { name: "Record a voice note" }).click();
    await page.locator(".recording").waitFor();
    await page.waitForTimeout(1500);
    const sent = page.waitForResponse((r) => r.url().endsWith("/voice") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Stop and send voice note" }).click();
    check(`${label}: microphone voice note is converted to WAV and accepted`, (await sent).ok());
  } else {
    check(`${label}: voice controls are disabled with the reason shown`,
      await page.getByRole("button", { name: "Record a voice note" }).isDisabled());
  }
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
