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
const badResponses = [];

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
    if (msg.type() === "error") consoleErrors.push({url:page.url(),text:msg.text()});
  });
  page.on("pageerror", err => pageErrors.push({url:page.url(),text:String(err),stack:err?.stack||null}));
  page.on("response", response => {
    if (response.status() >= 400) {
      badResponses.push({pageUrl:page.url(),status:response.status(),url:response.url()});
    }
  });

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

  // The visual quality gate covers the authenticated Console routes below.
  // Keep protection/login bootstrap diagnostics as evidence, but do not mix
  // Vercel Preview/Toolbar bootstrap errors into the application route gate.
  // The landing route is captured again as the first gated route, so real
  // application errors on "/" remain fail-closed.
  const bootstrapDiagnostics = {
    consoleErrors:[...consoleErrors],
    pageErrors:[...pageErrors],
    badResponses:[...badResponses],
  };
  consoleErrors.length=0;
  pageErrors.length=0;
  badResponses.length=0;

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

  const oauthAudit = {projectKey:"crm-infodive",databaseId:"5086d662-42eb-43a6-a8da-0da59cb39d75"};
  const projectResponse=await page.goto(`${consoleUrl}/projects/${encodeURIComponent(oauthAudit.projectKey)}`, {waitUntil:"networkidle",timeout:60000});
  if(!projectResponse || projectResponse.status()>=400) throw new Error(`CRM project page returned ${projectResponse?.status()}`);
  if(new URL(page.url()).pathname.startsWith("/login")) throw new Error("CRM project page redirected to login");
  const connectLink=page.getByRole("link",{name:"Conectar Supabase"});
  await connectLink.waitFor({state:"visible",timeout:30000});
  const connectHref=await connectLink.getAttribute("href");
  if(!connectHref || !connectHref.includes(oauthAudit.databaseId)) throw new Error("Supabase connect link missing expected database binding");
  const oauthRequestPromise=page.waitForRequest(request=>{
    try{
      const u=new URL(request.url());
      return u.origin==="https://api.supabase.com" && u.pathname==="/v1/oauth/authorize";
    }catch{return false;}
  },{timeout:60000});
  void page.goto(`${consoleUrl}${connectHref}`,{waitUntil:"domcontentloaded",timeout:60000}).catch(()=>null);
  const oauthRequest=await oauthRequestPromise;
  const oauthUrl=new URL(oauthRequest.url());
  const requiredOauthParams=["client_id","redirect_uri","response_type","state","code_challenge","code_challenge_method"];
  for(const name of requiredOauthParams){
    if(!oauthUrl.searchParams.get(name)) throw new Error(`Supabase OAuth authorize missing ${name}`);
  }
  if(oauthUrl.searchParams.get("response_type")!=="code") throw new Error("Supabase OAuth response_type mismatch");
  if(oauthUrl.searchParams.get("code_challenge_method")!=="S256") throw new Error("Supabase OAuth PKCE method mismatch");
  if(oauthUrl.searchParams.get("redirect_uri")!=="https://ai-product-factory-console.vercel.app/api/integrations/supabase/callback") throw new Error("Supabase OAuth callback mismatch");
  await page.evaluate(()=>window.stop()).catch(()=>{});
  const supabaseOauthInitiation={
    projectKey:oauthAudit.projectKey,
    databaseId:oauthAudit.databaseId,
    authorizeOrigin:oauthUrl.origin,
    authorizePath:oauthUrl.pathname,
    responseType:oauthUrl.searchParams.get("response_type"),
    pkce:oauthUrl.searchParams.get("code_challenge_method"),
    callback:oauthUrl.searchParams.get("redirect_uri"),
    statePresent:Boolean(oauthUrl.searchParams.get("state")),
    challengePresent:Boolean(oauthUrl.searchParams.get("code_challenge")),
  };

  await fs.writeFile(path.join(outDir,"manifest.json"), JSON.stringify({
    status:"success",
    workflowRunId:runId,
    targetCommit,
    targetUrl:consoleUrl,
    workflowSourceCommit,
    captured,
    supabaseOauthInitiation,
    bootstrapDiagnostics,
    consoleErrors,
    pageErrors,
    badResponses,
  }, null, 2));

  if (consoleErrors.length || pageErrors.length) {
    console.error(JSON.stringify({
      status:"browser_error_diagnostic",
      consoleErrorCount:consoleErrors.length,
      pageErrorCount:pageErrors.length,
      consoleErrors:consoleErrors.slice(0,20),
      pageErrors:pageErrors.slice(0,20),
      badResponses:badResponses.slice(0,40)
    }));
    throw new Error(`browser errors: console=${consoleErrors.length} page=${pageErrors.length}`);
  }

  console.log(JSON.stringify({
    status:"success",
    captured:captured.map(x=>x.name),
    supabaseOauthInitiation,
    bootstrapDiagnostics:{
      consoleErrorCount:bootstrapDiagnostics.consoleErrors.length,
      pageErrorCount:bootstrapDiagnostics.pageErrors.length,
      badResponseCount:bootstrapDiagnostics.badResponses.length,
    },
  }));
} finally {
  await browser.close();
}
