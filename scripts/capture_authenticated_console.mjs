import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";

const required = [
  "FACTORY_CONSOLE_URL",
  "FACTORY_VISUAL_EMAIL",
  "FACTORY_VISUAL_PASSWORD",
  "FACTORY_VISUAL_EVIDENCE_DIR",
  "FACTORY_VISUAL_TARGET_COMMIT",
];
for (const name of required) {
  if (!process.env[name]) throw new Error(`missing ${name}`);
}

const consoleUrl = process.env.FACTORY_CONSOLE_URL.replace(/\/$/, "");
const email = process.env.FACTORY_VISUAL_EMAIL;
const password = process.env.FACTORY_VISUAL_PASSWORD;
const outDir = process.env.FACTORY_VISUAL_EVIDENCE_DIR;
const runId = process.env.GITHUB_RUN_ID || "local";
const targetCommit = process.env.FACTORY_VISUAL_TARGET_COMMIT;
const workflowSourceCommit = process.env.GITHUB_SHA || "unknown";
const consoleErrors = [];
const pageErrors = [];

await fs.mkdir(outDir, {recursive:true});
const browser = await chromium.launch({headless:true});
try {
  const trustedOidc=process.env.FACTORY_VERCEL_TRUSTED_OIDC_TOKEN;
  const context = await browser.newContext({
    viewport:{width:1296,height:900},
    deviceScaleFactor:1,
    extraHTTPHeaders:trustedOidc?{"x-vercel-trusted-oidc-idp-token":trustedOidc}:{},
  });
  const page = await context.newPage();
  page.on("console", msg => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", err => pageErrors.push(String(err)));

  const login = await page.goto(`${consoleUrl}/login`, {waitUntil:"networkidle", timeout:60000});
  if (!login || login.status() >= 400) throw new Error(`login page status ${login?.status()}`);
  const emailInput=page.locator('input[name="email"]');
  const passwordInput=page.locator('input[name="password"]');
  try {
    await emailInput.waitFor({state:"visible",timeout:60000});
    await passwordInput.waitFor({state:"visible",timeout:60000});
  } catch (error) {
    const bodySample=(await page.locator("body").innerText().catch(()=>"")).replace(/\\s+/g," ").slice(0,500);
    throw new Error(`login form unavailable at ${page.url()} title=${await page.title()} body=${bodySample}: ${error}`);
  }
  await emailInput.fill(email);
  await passwordInput.fill(password);
  const submitResponsePromise=page.waitForResponse(response => {
    try {
      const url=new URL(response.url());
      return response.request().method()==="POST" && url.pathname==="/login";
    } catch {
      return false;
    }
  }, {timeout:60000});
  await page.getByRole("button", {name:"Entrar"}).click();
  const submitResponse=await submitResponsePromise;
  if (submitResponse.status() >= 400) throw new Error(`login submit status ${submitResponse.status()}`);
  const landing=await page.goto(`${consoleUrl}/`, {waitUntil:"networkidle", timeout:60000});
  if (!landing || landing.status() >= 400) throw new Error(`authenticated landing status ${landing?.status()}`);
  if (new URL(page.url()).pathname.startsWith("/login")) {
    const bodySample=(await page.locator("body").innerText().catch(()=>"")).replace(/\\s+/g," ").slice(0,500);
    throw new Error(`authenticated landing redirected to login at ${page.url()} body=${bodySample}`);
  }

  const routes = [
    {name:"overview",path:"/",width:1296},
    {name:"human-gates",path:"/gates",width:1980},
    {name:"run-detail",path:"/runs/93fd8cdc-f000-4a01-978e-463798628e4e",width:1296},
    {name:"work-queue",path:"/queue",width:1296},
    {name:"agents",path:"/agents",width:1296},
    {name:"orchestration",path:"/orchestration",width:1296},
    {name:"evals",path:"/evals",width:1296},
    {name:"deployments",path:"/deployments",width:1296},
    {name:"models-usage",path:"/usage",width:1296},
    {name:"audit-log",path:"/audit",width:1308},
    {name:"configuration",path:"/configuration",width:1296},
  ];

  const captured = [];
  for (const route of routes) {
    await page.setViewportSize({width:route.width,height:900});
    const response = await page.goto(`${consoleUrl}${route.path}`, {waitUntil:"networkidle", timeout:60000});
    if (!response || response.status() >= 400) throw new Error(`${route.path} returned ${response?.status()}`);
    if (new URL(page.url()).pathname.startsWith("/login")) throw new Error(`${route.path} redirected to login`);
    await page.screenshot({path:path.join(outDir,`${route.name}.png`), fullPage:true});
    const size = await page.evaluate(() => ({
      width:document.documentElement.scrollWidth,
      height:document.documentElement.scrollHeight,
    }));
    captured.push({...route,status:response.status(),finalUrl:page.url(),documentSize:size});
  }

  await fs.writeFile(path.join(outDir,"manifest.json"), JSON.stringify({
    status:"success",
    workflowRunId:runId,
    targetCommit,
    targetUrl:consoleUrl,
    workflowSourceCommit,
    captured,
    consoleErrors,
    pageErrors,
  }, null, 2));

  if (consoleErrors.length || pageErrors.length) {
    throw new Error(`browser errors: console=${consoleErrors.length} page=${pageErrors.length}`);
  }

  console.log(JSON.stringify({status:"success",captured:captured.map(x=>x.name)}));
} finally {
  await browser.close();
}
