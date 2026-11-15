import { chromium } from "playwright";
import matcher from "./preview_text_match.cjs";
import {firstPartyPreviewHeaders} from "./preview_first_party_headers.mjs";
import {isVercelExternalTelemetryPing403,isCorrelatedVercelPingConsoleError} from "./preview_browser_integrity.mjs";
const { normalizeVisibleText, containsExpectedText } = matcher;

const previewUrl = process.env.FACTORY_PREVIEW_URL;
const expectedText = (process.env.FACTORY_PREVIEW_EXPECTED_TEXT || "").trim();
const trustedOidcToken = (process.env.FACTORY_VERCEL_TRUSTED_OIDC_TOKEN || "").trim();
const browserExecutablePath = (process.env.FACTORY_BROWSER_EXECUTABLE_PATH || "").trim();
const checks = [];
const errors = [];
const consoleErrors = [];
const ignoredTelemetryPings = new Set();
const failedResources = [];
const observed = { finalUrl: null, title: null, statusCode: null, bodySample: null, failedResources };
const previewOrigin = previewUrl && /^https:\/\//.test(previewUrl) ? new URL(previewUrl).origin : null;

function safeResourcePath(rawUrl) {
  try {
    const url = new URL(rawUrl);
    // Only show our own resource paths; no query strings, fragments, or other hosts.
    if (url.origin !== previewOrigin) return "[external]";
    return url.pathname.slice(0, 160);
  } catch {
    return "[invalid]";
  }
}


function emit(status, detail = null) {
  process.stdout.write(JSON.stringify({ status, checks, detail, observed }));
}

if (!previewUrl || !/^https:\/\//.test(previewUrl)) {
  emit("failure", "FACTORY_PREVIEW_URL must be an https URL");
  process.exit(0);
}

if (!expectedText || expectedText.length > 120 || /[\r\n]/.test(expectedText)) {
  emit("failure", "preview_application_marker_required");
  process.exit(0);
}

let browser;
try {
  browser = await chromium.launch({
    headless: true,
    ...(browserExecutablePath ? { executablePath: browserExecutablePath } : {}),
  });
  const context = await browser.newContext();
  // Exact-origin request headers suppress Vercel's injected toolbar.
  // Never forward OIDC to third-party resources, and never mock responses.
  await context.route(previewOrigin + "/**", route => route.continue({
    headers:firstPartyPreviewHeaders({
      requestUrl:route.request().url(),previewOrigin,trustedOidcToken,
      currentHeaders:route.request().headers(),
    }),
  }));
  const page = await context.newPage();
  page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
  page.on("response", response => {
    if(response.status() >= 400){
      if(isVercelExternalTelemetryPing403({
        requestUrl:response.url(),previewOrigin,
        resourceType:response.request().resourceType(),status:response.status(),
      })){
        ignoredTelemetryPings.add(response.url());
        return;
      }
      if(failedResources.length < 12){
        failedResources.push({
          status:response.status(),
          path:safeResourcePath(response.url()),
          type:response.request().resourceType(),
        });
      }
    }
  });

  page.on("console", message => {
    if(message.type()==="error")
      consoleErrors.push({text:message.text(),sourceUrl:message.location().url || ""});
  });

  const response = await page.goto(previewUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  if (!response) throw new Error("navigation did not return an HTTP response");
  checks.push("page_load");

  const status = response.status();
  observed.statusCode = status;
  observed.finalUrl = page.url();
  observed.title = await page.title();
  if (status >= 400) throw new Error(`preview returned HTTP ${status}`);
  if (new URL(page.url()).origin !== previewOrigin)
    throw new Error("preview_application_origin_mismatch");
  checks.push("http_status");

  await page.waitForTimeout(750);
  const bodyText = (await page.locator("body").innerText()).trim();
  // Preserve status/path diagnostics only; never retain arbitrary customer page text.
  observed.bodySample = null;
  if (!bodyText) throw new Error("preview rendered an empty body");
  checks.push("body_visible");

  // Vercel SSO/login may have HTTP 200 and nonempty HTML. Require actual app
  // main content with a project-bound marker before declaring browser success.
  const appMain = await page.locator("main").first().innerText({timeout:10000});
  if (!containsExpectedText(normalizeVisibleText(appMain), expectedText))
    throw new Error("preview_application_identity_unverified");
  checks.push("expected_text");

  for(const entry of consoleErrors){
    if(!isCorrelatedVercelPingConsoleError({
      ...entry,previewOrigin,ignoredPingUrls:ignoredTelemetryPings,
    }))errors.push("console: "+entry.text);
  }
  if (errors.length || failedResources.length) {
    const resourceDetails = failedResources.map(item => `http_${item.status}: ${item.type} ${item.path}`);
    emit("failure", [...errors.slice(0, 10), ...resourceDetails].slice(0, 16).join(" | "));
  } else {
    checks.push("console_clean");
    emit("success", null);
  }
} catch (error) {
  emit("failure", error instanceof Error ? error.message : String(error));
} finally {
  if (browser) await browser.close();
}
