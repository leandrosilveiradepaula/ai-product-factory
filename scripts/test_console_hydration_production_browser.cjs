/* Actual production Next.js 15 + React 19 hydration, with STRICTLY local, inert
 * Supabase API fixture. No operator provision, production access, model, DB
 * connection or mutation. Detects HTML #418 (not just a green Next build).
 * This is isolated reproduction/regression evidence, NOT a real B2/B3 PASS.
 */
"use strict";
const {test,before,after}=require("node:test");
const assert=require("node:assert/strict");
const {spawn}=require("node:child_process");
const http=require("node:http");
const path=require("node:path");
const fs=require("node:fs");
const root=path.resolve(__dirname,"..");
const consoleDir=path.join(root,"apps","console");
const {chromium}=require(path.join(consoleDir,"node_modules","playwright"));
const UUID="11111111-1111-4111-8111-111111111111";
const AUTH_TOKEN="offline-fixture-auth-token";
const FRESH_TOKEN="offline-fixture-renewed-access";
const EXPIRED_TOKEN="offline-fixture-expired-access";
const REFRESH_TOKEN="offline-fixture-refresh";
let refreshCalls=0;
const MOCK_KEY="sb_secret_offline_fixture_not_real";
const PUB_KEY="offline-fixture-publishable";
let mock,nextProcess,browser,appOrigin,mockOrigin;
const violations=[];
const driverErrors=[];
const fixtureProjects=[{
  project_key:"ai-product-factory",name:"AI Product Factory",
  repository:"leandrosilveiradepaula/ai-product-factory",
  project_kind:"existing",lifecycle_stage:"validation",
  is_active:true,manifest:{preview:{mode:"github"}},
}];

function send(res,code,value){
 res.writeHead(code,{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"});
 res.end(JSON.stringify(value));
}
function requireLocalAuth(req,route){
 if(route.pathname==="/auth/v1/user"){
  return req.headers.apikey===PUB_KEY&&(req.headers.authorization==="Bearer "+AUTH_TOKEN||
   req.headers.authorization==="Bearer "+FRESH_TOKEN);
 }
 if(route.pathname==="/rest/v1/factory_console_operators"){
  return req.headers.apikey===PUB_KEY&&
    (req.headers.authorization==="Bearer "+AUTH_TOKEN||req.headers.authorization==="Bearer "+FRESH_TOKEN);
 }
 return req.headers.apikey===MOCK_KEY;
}
function localApi(req,res){
 let u;
 try{u=new URL(req.url,"http://127.0.0.1");}
 catch {violations.push("invalid_internal_route");send(res,400,{});return;}
 // The only write-shaped fixture is Supabase Auth's local token-renewal
 // handshake. It changes no data and rejects every other POST.
 if(req.method==="POST"&&u.pathname==="/auth/v1/token"&&
    u.searchParams.get("grant_type")==="refresh_token"){
  if(req.headers.apikey!==PUB_KEY){violations.push("invalid_refresh_key");send(res,403,{});return;}
  let raw="";
  req.on("data",chunk=>{raw+=chunk.toString();if(raw.length>1024)req.destroy();});
  req.on("end",()=>{
   let payload;
   try{payload=JSON.parse(raw);}catch{payload=null;}
   if(payload?.refresh_token!==REFRESH_TOKEN){
    violations.push("invalid_refresh_token");send(res,403,{});return;
   }
   refreshCalls++;
   send(res,200,{access_token:FRESH_TOKEN,refresh_token:REFRESH_TOKEN,
    expires_in:3600,user:{id:UUID,email:"browser-fixture@example.invalid"}});
  });
  return;
 }
 if(req.method==="POST"&&u.pathname==="/rest/v1/rpc/factory_get_github_app_status"&&req.headers.apikey===MOCK_KEY){
  // Read-only status RPC, not a write; no external GitHub or database access.
  send(res,200,{configured:false,status:"unavailable"});return;
 }
 if(req.method!=="GET"){
  violations.push("mutation_attempt:"+req.method+":"+u.pathname);send(res,405,{});return;
 }
 if(u.pathname==="/auth/v1/user"&&
    req.headers.authorization==="Bearer "+EXPIRED_TOKEN&&req.headers.apikey===PUB_KEY){
  send(res,401,{message:"expired_fixture_token"});return;
 }
 if(!requireLocalAuth(req,u)){violations.push("unauthorized_internal_fetch");send(res,403,{});return;}
 if(u.pathname==="/auth/v1/user"){
  send(res,200,{id:UUID,email:"browser-fixture@example.invalid"});
 }else if(u.pathname==="/rest/v1/factory_console_operators"){
  send(res,200,[{role:"operator",is_active:true}]);
 }else if(u.pathname==="/rest/v1/factory_projects"){
  send(res,200,fixtureProjects);
 }else if(u.pathname==="/rest/v1/factory_runs"){
  // Inert, empty run inventory for credential-free B3 browser diagnostics.
  send(res,200,[]);
 }else if(u.pathname==="/rest/v1/factory_primary_cost_policy"){
  send(res,200,[{policy_key:"primary",budget_usd:"10.0000",reserve_usd:"0.5000",
    version:1,updated_at:"2026-10-30T15:44:00Z",updated_by:null}]);
 }else if(u.pathname==="/rest/v1/factory_audit_events"||
          u.pathname==="/rest/v1/factory_tool_usage"||
          u.pathname==="/rest/v1/factory_human_gates"||
          u.pathname==="/rest/v1/factory_release_reports"||
          u.pathname==="/rest/v1/factory_project_github_access"){
  send(res,200,[]);
 }else{
  violations.push("unmocked_internal_route:"+req.method+":"+u.pathname);
  send(res,404,{error:"not_available"});
 }
}
async function freePort(){
 const server=http.createServer();
 await new Promise((resolve,reject)=>{server.once("error",reject);server.listen(0,"127.0.0.1",resolve);});
 const port=server.address().port;
 await new Promise(resolve=>server.close(resolve));
 return port;
}
async function waitForNext(origin,child){
 const start=Date.now();
 while(Date.now()-start<50000){
  if(child.exitCode!==null)throw Error("isolated_next_died_before_ready");
  try{const response=await fetch(origin+"/login",{signal:AbortSignal.timeout(1000)});
   if(response.status===200)return;
  }catch{}
  await new Promise(r=>setTimeout(r,400));
 }
 throw Error("isolated_next_start_timeout");
}
before(async()=>{
 // This runner requires a successfully built, exact local production tree.
 assert.ok(fs.existsSync(path.join(consoleDir,".next","BUILD_ID")),"run npm run build first");
 mock=http.createServer(localApi);
 await new Promise((resolve,reject)=>{mock.once("error",reject);mock.listen(0,"127.0.0.1",resolve);});
 mockOrigin="http://127.0.0.1:"+mock.address().port;
 const appPort=await freePort();
 appOrigin="http://127.0.0.1:"+appPort;
 nextProcess=spawn(process.execPath,
  [path.join(consoleDir,"node_modules","next","dist","bin","next"),"start",
   "-H","127.0.0.1","-p",String(appPort)],{
  cwd:consoleDir,stdio:["ignore","pipe","pipe"],
  env:{
    ...process.env,NODE_ENV:"production",NEXT_TELEMETRY_DISABLED:"1",
    SUPABASE_URL:mockOrigin,
    SUPABASE_SECRET_KEY:MOCK_KEY,
    SUPABASE_PUBLISHABLE_KEY:PUB_KEY,
    FACTORY_BOOTSTRAP_ADMIN_EMAIL:"",
    FACTORY_PRIMARY_MODEL_ENABLED:"false",
    FACTORY_CODEX_ENABLED:"false",
  },
 });
 let lines=0;
 const collect=chunk=>{const s=chunk.toString();if(/error|failure|failed/i.test(s)&&lines++<10){
   driverErrors.push("next_server_error_detected");
 }};
 nextProcess.stdout.on("data",collect);nextProcess.stderr.on("data",collect);
 await waitForNext(appOrigin,nextProcess);
 browser=await chromium.launch({headless:true,executablePath:
   process.env.FACTORY_BROWSER_EXECUTABLE_PATH||"/usr/bin/google-chrome",
   args:["--no-sandbox"]});
});
after(async()=>{
 await browser?.close();
 if(nextProcess){
  nextProcess.kill("SIGTERM");
  await new Promise(resolve=>{
   if(nextProcess.exitCode!==null||nextProcess.signalCode!==null)return resolve();
   const tid=setTimeout(()=>{nextProcess.kill("SIGKILL");resolve();},3500);
   nextProcess.once("exit",()=>{clearTimeout(tid);resolve();});
  });
 }
 if(mock)await new Promise(resolve=>mock.close(resolve));
 assert.deepEqual(violations,[],"local-only fake backend must have no unauthorized, mutating or unmocked calls");
 assert.deepEqual(driverErrors,[],"isolated Next server must be free of runtime errors");
});
async function hydrationRound({throttled=false,repeats=3}={}){
 const context=await browser.newContext({
  viewport:{width:1280,height:900},locale:"pt-BR",
  timezoneId:"America/Sao_Paulo",
 });
 await context.addCookies([{name:"factory_access_token",value:AUTH_TOKEN,url:appOrigin}]);
 const browserErrors=[];
 await context.route("**/*",async route=>{
  const url=new URL(route.request().url());
  const request=route.request();
  if(url.origin!==appOrigin || request.method()!=="GET"){
    violations.push(url.origin===appOrigin?"browser_mutation":"external_browser_origin");
    await route.abort("blockedbyclient");return;
  }
  if(url.pathname==="/api/human-attention"){
    await route.fulfill({status:200,contentType:"application/json",
      body:JSON.stringify({status:"ok",count:0,projects:[]})});return;
  }
  await route.continue();
 });
 const page=await context.newPage();
 page.on("pageerror",err=>browserErrors.push(
  /Minified React error #418/.test(String(err))?"react_418_hydration":"other_page_error"));
 page.on("console",msg=>{
  if(msg.type()==="error")browserErrors.push(
   /hydration|#418/i.test(msg.text())?"react_418_console":"other_console_error");
 });
 let cdp;
 if(throttled){
  cdp=await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions",{
   offline:false,latency:20,downloadThroughput:192000,uploadThroughput:192000,
   connectionType:"cellular4g",
  });
 }
 try{
  for(let i=0;i<repeats;i++){
   // Cache the actual Next client bundles, then reload full SSR documents;
   // this is the same network/browser sequence that surfaced #418.
   const response=await page.goto(appOrigin+"/configuration",{
    waitUntil:"networkidle",timeout:45000});
   assert.equal(response?.status(),200,"actual protected configuration route must return 200");
   assert.equal(new URL(page.url()).pathname,"/configuration");
   assert.equal(await page.locator("h1.title").innerText(),"Configuração");
   assert.equal(await page.locator("#orcamento").count(),1);
   assert.equal(await page.locator("nav.configTabs").count(),1);
   assert.equal(browserErrors.length,0,
    "real React/Next server HTML must hydrate cleanly (no #418 or console errors)");
  }
 }finally{
  await cdp?.detach();
  await context.close();
 }
 return repeats;
}
test("real Next production SSR hydration of authenticated /configuration is clean with cached JS",async()=>{
 const n=await hydrationRound({repeats:4});assert.equal(n,4);
});
test("real Next production SSR hydration remains clean under streaming network throttling",async()=>{
 const n=await hydrationRound({throttled:true,repeats:4});assert.equal(n,4);
});

test("B2: expired token refresh reaches same-request Server Components without unauthorized redirect",async()=>{
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 await context.addCookies([
  {name:"factory_access_token",value:EXPIRED_TOKEN,url:appOrigin},
  {name:"factory_refresh_token",value:REFRESH_TOKEN,url:appOrigin},
 ]);
 // The refresh occurs server-side via the strict local auth fixture.
 const beforeCount=refreshCalls;
 const page=await context.newPage();
 const errors=[];
 page.on("pageerror",()=>errors.push("pageerror"));
 try{
  const response=await page.goto(appOrigin+"/configuration",{waitUntil:"domcontentloaded",timeout:45000});
  assert.equal(response?.status(),200);
  assert.equal(new URL(page.url()).pathname,"/configuration");
  assert.equal(await page.locator("h1.title").innerText(),"Configuração");
  assert.ok(refreshCalls>beforeCount,"middleware must renew expired access");
  // Production cookies are Secure; Chromium intentionally does not persist
  // Secure Set-Cookie on this isolated plain-HTTP origin. Verify the server
  // emitted the renewed cookie instead of weakening production cookie flags.
  const setCookies=(await response.headersArray()).filter(h=>h.name.toLowerCase()==="set-cookie").map(h=>h.value);
  assert.ok(setCookies.some(v=>v.startsWith("factory_access_token=")&&v.includes(FRESH_TOKEN)&&/;\s*secure/i.test(v)),
    "middleware must emit the fresh Secure access cookie");
  assert.deepEqual(errors,[]);
 }finally{await context.close();}
});

test("B3: stale attention request cannot overwrite a newer successful operator snapshot",async()=>{
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 await context.addCookies([{name:"factory_access_token",value:AUTH_TOKEN,url:appOrigin}]);
 let calls=0;
 let pending=null;
 const violationsBefore=violations.length;
 await context.route("**/*",async route=>{
  const req=route.request(),url=new URL(req.url());
  if(url.origin!==appOrigin||req.method()!=="GET"){
   violations.push("browser_mutation_or_external_origin");
   await route.abort("blockedbyclient");return;
  }
  if(url.pathname==="/api/human-attention"){
   calls++;
   if(calls===1){pending=route;return;}
   await route.fulfill({status:200,contentType:"application/json",
    body:JSON.stringify({status:"ok",count:2,projects:[]})});return;
  }
  await route.continue();
 });
 const page=await context.newPage();
 const errors=[];
 page.on("pageerror",()=>errors.push("pageerror"));
 try{
  const response=await page.goto(appOrigin+"/configuration",{waitUntil:"domcontentloaded",timeout:45000});
  assert.equal(response?.status(),200);
  await page.waitForFunction(()=>document.querySelector("h1.title")?.textContent==="Configuração");
  await page.waitForFunction(()=>document.querySelector("a.skipToMain")!==null);
  // First request must be pending; the second event must commit newer data.
  await page.waitForFunction(()=>document.querySelector("nav.sidebarNav")!==null);
  for(let i=0;i<100&&calls<1;i++)await new Promise(r=>setTimeout(r,50));
  assert.equal(calls,1,"initial snapshot should be pending");
  await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
  await page.waitForFunction(()=>document.querySelector(".desktopSidebarContent .humanAttentionCount")?.textContent?.trim()==="2",null,{timeout:15000});
  await pending.fulfill({status:200,contentType:"application/json",
   body:JSON.stringify({status:"ok",count:0,projects:[]})});
  pending=null;
  await page.waitForTimeout(150);
  assert.equal(await page.locator(".desktopSidebarContent .humanAttentionCount").innerText(),"2");
  assert.deepEqual(errors,[]);
  assert.equal(violations.length,violationsBefore);
 }finally{
  if(pending)await pending.fulfill({status:200,contentType:"application/json",
   body:JSON.stringify({status:"ok",count:0,projects:[]})}).catch(()=>{});
  await context.close();
 }
});

test("B2: expired token without refresh stays denied, never accesses protected Console",async()=>{
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 await context.addCookies([{name:"factory_access_token",value:EXPIRED_TOKEN,url:appOrigin}]);
 const page=await context.newPage();
 const count=refreshCalls;
 try{
  const response=await page.goto(appOrigin+"/configuration",{waitUntil:"networkidle",timeout:45000});
  assert.equal(response?.status(),200,"safe login destination");
  assert.equal(new URL(page.url()).pathname,"/login");
  assert.equal(await page.locator("h1.title").innerText(),"Entrar na Factory");
  assert.equal(await page.locator("#orcamento").count(),0);
  assert.equal(refreshCalls,count,"no refresh credential means no refresh call");
 }finally{await context.close();}
});

test("B2: public login prefix never bypasses authentication middleware",async()=>{
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 const page=await context.newPage();
 try{
  const response=await page.goto(appOrigin+"/login-unprotected-canary",{
   waitUntil:"networkidle",timeout:45000});
  assert.equal(response?.status(),200);
  const u=new URL(page.url());
  assert.equal(u.pathname,"/login");
  assert.equal(u.searchParams.get("next"),"/login-unprotected-canary");
  assert.equal(await page.locator("h1.title").innerText(),"Entrar na Factory");
 }finally{await context.close();}
});

test("B2/B3: real authenticated intake advances to review without a server action or backend mutation",async()=>{
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 await context.addCookies([{name:"factory_access_token",value:AUTH_TOKEN,url:appOrigin}]);
 const page=await context.newPage();
 const blocked=[];
 await context.route("**/*",async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.origin!==appOrigin||request.method()!=="GET"){
   blocked.push(request.method()+":"+url.pathname);
   await route.abort("blockedbyclient");return;
  }
  if(url.pathname==="/api/human-attention"){
   await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({status:"ok",count:0,projects:[]})});return;
  }
  await route.continue();
 });
 try{
  const response=await page.goto(appOrigin+"/projects/new",{waitUntil:"networkidle",timeout:45000});
  assert.equal(response?.status(),200);
  await page.locator('input[name="name"]').fill("Offline intake regression");
  await page.locator('textarea[name="summary"]').fill("Verify review without privileged storage access");
  await page.getByRole("button",{name:"Revisar e iniciar Descoberta"}).click();
  await page.waitForURL(url=>url.pathname==="/projects/new/review"&&url.searchParams.has("intake"),{timeout:15000});
  assert.ok(await page.getByText("Offline intake regression",{exact:true}).count());
  assert.deepEqual(blocked,[],"review navigation must not POST or contact external services");
  await page.getByRole("link",{name:"Editar"}).click();
  await page.waitForURL(url=>url.pathname==="/projects/new"&&url.searchParams.has("intake"),{timeout:15000});
  assert.equal(await page.locator('input[name="name"]').inputValue(),"Offline intake regression");
 }finally{await context.close();}
});

test("B3: login and unauthorized routes never poll privileged attention API",async()=>{
 const context=await browser.newContext({viewport:{width:1280,height:900}});
 const page=await context.newPage();
 const requests=[];
 await context.route("**/api/human-attention",async route=>{
  requests.push(route.request().url());
  await route.fulfill({status:503,contentType:"application/json",body:'{"status":"unavailable"}'});
 });
 try{
  for(const route of ["/login","/unauthorized"]){
   const response=await page.goto(appOrigin+route,{waitUntil:"networkidle",timeout:45000});
   assert.equal(response?.status(),200);
   assert.equal(new URL(page.url()).pathname,route);
   assert.equal(requests.length,0,"auth-only route must not fetch operator attention");
   assert.equal(await page.locator(".topbarAttention").count(),0);
  }
 }finally{await context.close();}
});


test("B3: the real /runs sidebar color-contrast is determinable in an isolated Chromium + axe-core",async()=>{
 // The browser executes actual Next/React CSS/layout and the same axe family,
 // with only fabricated local backend records. NO operator or production data.
 const context=await browser.newContext({viewport:{width:1296,height:900},locale:"pt-BR"});
 await context.addCookies([{name:"factory_access_token",value:AUTH_TOKEN,url:appOrigin}]);
 const page=await context.newPage();
 try{
  await context.route("**/api/human-attention",async route=>
   route.fulfill({status:200,contentType:"application/json",
    body:JSON.stringify({status:"ok",count:0,projects:[]})}));
  const response=await page.goto(appOrigin+"/runs",{waitUntil:"networkidle",timeout:45000});
  assert.equal(response?.status(),200,"isolated real /runs must load");
  assert.equal(new URL(page.url()).pathname,"/runs");
  assert.equal(await page.locator("h1.title").innerText(),"Execuções");
  assert.equal(await page.locator(".desktopSidebarContent .navAdvanced[open]").count(),1);
  await page.addScriptTag({path:path.join(consoleDir,"node_modules","axe-core","axe.min.js")});
  const result=await page.evaluate(async()=>{
    const root=document.querySelector(".desktopSidebarContent .sidebarNav");
    if(!root)throw Error("sidebar_nav_missing");
    const r=await window.axe.run(root,{runOnly:{type:"rule",values:["color-contrast"]}});
    const known=new Set(["/","/projects","/gates","/runs","/queue","/agents","/orchestration",
      "/evals","/deployments","/usage","/audit","/configuration","/admin/operators"]);
    const reasonNames=new Set(["bgOverlap","elmPartiallyObscured","elmPartiallyObscuring",
     "outsideViewport","pseudoContent","bgImage","bgGradient","shortTextContent","nonBmp","equalRatio"]);
    const navRect=root.getBoundingClientRect();
    const findings=r.incomplete.flatMap(rule=>(rule.nodes||[]).slice(0,15).map(node=>{
      let element=null;
      for(const selector of Array.isArray(node.target)?node.target:[]){
        try{element=document.querySelector(selector);if(element)break}catch{}
      }
      const anchor=element?.closest("a"),href=anchor?.getAttribute("href")||"";
      const rect=element?.getBoundingClientRect();
      return {rule:rule.id,link:known.has(href)?href:"unclassified",
       checks:["any","all","none"].flatMap(key=>node[key]||[]).map(check=>({
        id:check.id,
        reason:reasonNames.has(check.data?.messageKey)?check.data.messageKey:
          reasonNames.has(check.data?.reason)?check.data.reason:"unknown"})),
       elementRect:rect?{top:Math.round(rect.top),bottom:Math.round(rect.bottom)}:null};
    }));
    return {incomplete:r.incomplete.reduce((sum,rule)=>sum+rule.nodes.length,0),
      violations:r.violations.reduce((sum,rule)=>sum+rule.nodes.length,0),
      navRect:{top:Math.round(navRect.top),bottom:Math.round(navRect.bottom)},
      navScroll:{height:root.clientHeight,content:root.scrollHeight},
      findings};
  });
  // Only fixed /runs, static nav routes, bounds and enum reason codes leave
  // the browser; HTML, selectors, text, private IDs and tokens never do.
  assert.equal(result.violations,0,"Unexpected authentic UI contrast violation in offline fixture");
  assert.equal(result.incomplete,0,
    "Isolated real sidebar axe result (no PII): "+JSON.stringify(result));
 }finally{await context.close();}
});
