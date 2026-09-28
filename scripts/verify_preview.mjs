import { chromium } from "playwright";

const previewUrl = process.env.FACTORY_PREVIEW_URL;
const expectedText = (process.env.FACTORY_PREVIEW_EXPECTED_TEXT || "").trim();
const trustedOidcToken = (process.env.FACTORY_VERCEL_TRUSTED_OIDC_TOKEN || "").trim();
const checks = [];
const errors = [];
const observed = { finalUrl: null, title: null, statusCode: null, bodySample: null };

function emit(status, detail = null) {
  process.stdout.write(JSON.stringify({ status, checks, detail, observed }));
}

if (!previewUrl || !/^https:\/\//.test(previewUrl)) {
  emit("failure", "FACTORY_PREVIEW_URL must be an https URL");
  process.exit(0);
}

let browser;
try {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    extraHTTPHeaders: trustedOidcToken
      ? { "x-vercel-trusted-oidc-idp-token": trustedOidcToken }
      : {},
  });
  const page = await context.newPage();
  page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });

  const response = await page.goto(previewUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  if (!response) throw new Error("navigation did not return an HTTP response");
  checks.push("page_load");

  const status = response.status();
  observed.statusCode = status;
  observed.finalUrl = page.url();
  observed.title = await page.title();
  if (status >= 400) throw new Error(`preview returned HTTP ${status}`);
  checks.push("http_status");

  await page.waitForTimeout(750);
  const bodyText = (await page.locator("body").innerText()).trim();
  observed.bodySample = bodyText.replace(/\s+/g, " ").slice(0, 300);
  if (!bodyText) throw new Error("preview rendered an empty body");
  checks.push("body_visible");

  if (expectedText) {
    if (!bodyText.includes(expectedText)) {
      throw new Error(`preview did not contain expected text: ${expectedText}`);
    }
    checks.push("expected_text");
  }

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
