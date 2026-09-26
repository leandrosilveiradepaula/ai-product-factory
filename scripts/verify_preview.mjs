import { chromium } from "playwright";

const previewUrl = process.env.FACTORY_PREVIEW_URL;
const checks = [];
const errors = [];

function emit(status, detail = null) {
  process.stdout.write(JSON.stringify({ status, checks, detail }));
}

if (!previewUrl || !/^https:\/\//.test(previewUrl)) {
  emit("failure", "FACTORY_PREVIEW_URL must be an https URL");
  process.exit(0);
}

let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });

  const response = await page.goto(previewUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  if (!response) throw new Error("navigation did not return an HTTP response");
  checks.push("page_load");

  const status = response.status();
  if (status >= 400) throw new Error(`preview returned HTTP ${status}`);
  checks.push("http_status");

  await page.waitForTimeout(750);
  const bodyText = (await page.locator("body").innerText()).trim();
  if (!bodyText) throw new Error("preview rendered an empty body");
  checks.push("body_visible");

  if (errors.length) {
    emit("failure", errors.slice(0, 10).join(" | "));
  } else {
    checks.push("console_clean");
    emit("success", null);
  }
} catch (error) {
  emit("failure", error instanceof Error ? error.message : String(error));
} finally {
  if (browser) await browser.close();
}
