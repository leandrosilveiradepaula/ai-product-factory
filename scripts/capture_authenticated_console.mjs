import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";

const required = ["FACTORY_CONSOLE_URL","SUPABASE_URL","SUPABASE_SECRET_KEY","FACTORY_VISUAL_EVIDENCE_DIR"];
for (const name of required) {
  if (!process.env[name]) throw new Error(`missing ${name}`);
}

const consoleUrl = process.env.FACTORY_CONSOLE_URL.replace(/\/$/, "");
const supabaseUrl = process.env.SUPABASE_URL.replace(/\/$/, "");
const secretKey = process.env.SUPABASE_SECRET_KEY;
const outDir = process.env.FACTORY_VISUAL_EVIDENCE_DIR;
const runId = process.env.GITHUB_RUN_ID || "local";
const sourceCommit = process.env.GITHUB_SHA || "unknown";

const adminHeaders = {
  apikey: secretKey,
  "Content-Type": "application/json",
};
if (!secretKey.startsWith("sb_secret_")) adminHeaders.Authorization = `Bearer ${secretKey}`;

async function adminFetch(url, init = {}) {
  const response = await fetch(url, {
    ...init,
    headers: {...adminHeaders, ...(init.headers || {})},
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`admin request failed ${response.status}: ${body.slice(0, 800)}`);
  }
  return response;
}

const password = `V!sual-${crypto.randomUUID()}-9aZ!`;
const email = `factory-visual-${runId}@visual.invalid`;
let userId = null;
const consoleErrors = [];
const pageErrors = [];

await fs.mkdir(outDir, {recursive:true});

try {
  const created = await adminFetch(`${supabaseUrl}/auth/v1/admin/users`, {
    method:"POST",
    body:JSON.stringify({email,password,email_confirm:true}),
  });
  const user = await created.json();
  userId = String(user.id);

  await adminFetch(`${supabaseUrl}/rest/v1/factory_console_operators`, {
    method:"POST",
    headers:{Prefer:"return=minimal"},
    body:JSON.stringify({user_id:userId,role:"operator",is_active:true}),
  });

  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({
    viewport:{width:1296,height:900},
    deviceScaleFactor:1,
  });
  const page = await context.newPage();
  page.on("console", msg => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", err => pageErrors.push(String(err)));

  const login = await page.goto(`${consoleUrl}/login`, {waitUntil:"networkidle", timeout:60000});
  if (!login || login.status() >= 400) throw new Error(`login page status ${login?.status()}`);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha").fill(password);
  await Promise.all([
    page.waitForURL(url => !url.pathname.startsWith("/login"), {timeout:60000}),
    page.getByRole("button", {name:"Entrar"}).click(),
  ]);
  await page.waitForLoadState("networkidle");

  const routes = [
    {name:"overview",path:"/",width:1296},
    {name:"human-gates",path:"/gates",width:1980},
    {name:"run-detail",path:"/runs/93fd8cdc-f000-4a01-978e-463798628e4e",width:1296},
    {name:"work-queue",path:"/queue",width:1296},
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
    const size = await page.evaluate(() => ({width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight}));
    captured.push({...route,status:response.status(),finalUrl:page.url(),documentSize:size});
  }

  await fs.writeFile(path.join(outDir,"manifest.json"), JSON.stringify({
    status:"success",
    workflowRunId:runId,
    sourceCommit,
    captured,
    consoleErrors,
    pageErrors,
  }, null, 2));

  await browser.close();

  if (consoleErrors.length || pageErrors.length) {
    throw new Error(`browser errors: console=${consoleErrors.length} page=${pageErrors.length}`);
  }

  console.log(JSON.stringify({status:"success",captured:captured.map(x=>x.name)}));
} finally {
  if (userId) {
    try {
      await adminFetch(`${supabaseUrl}/rest/v1/factory_console_operators?user_id=eq.${encodeURIComponent(userId)}`, {method:"DELETE"});
    } catch (error) {
      console.error("operator cleanup failed", error instanceof Error ? error.message : String(error));
    }
    try {
      await adminFetch(`${supabaseUrl}/auth/v1/admin/users/${encodeURIComponent(userId)}`, {method:"DELETE"});
    } catch (error) {
      console.error("auth user cleanup failed", error instanceof Error ? error.message : String(error));
    }
  }
}
