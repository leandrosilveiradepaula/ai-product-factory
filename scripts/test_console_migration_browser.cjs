/* Genuine Chromium + React 19 interaction proof of the ACTUAL Console components.
 * Isolated 127.0.0.1 fixture, no production credentials, no mutations, no model calls.
 * Does not claim the production human migration action or authenticated E2E ran.
 */
"use strict";
const {test,before,after}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const os=require("node:os");
const path=require("node:path");
const http=require("node:http");
const root=path.resolve(__dirname,"..");
const modules=path.join(root,"apps","console","node_modules");
const esbuild=require(path.join(modules,"esbuild"));
const {chromium}=require(path.join(modules,"playwright"));

const fixture=path.join(root,"scripts","fixtures","migration-browser-entry.tsx");
const css=fs.readFileSync(path.join(root,"apps","console","app","globals.css"),"utf8");
const work=fs.mkdtempSync(path.join(os.tmpdir(),"factory-migration-browser-"));
const bundle=path.join(work,"fixture.js");
let server,browser,origin,mutations=0,untrusted=[];
const errors=[];
before(async()=>{
 await esbuild.build({
  entryPoints:[fixture],outfile:bundle,absWorkingDir:root,
  bundle:true,platform:"browser",format:"iife",target:["chrome120"],
  // Production TSX uses the React 19 automatic JSX runtime, not React.createElement.
  jsx:"automatic",jsxImportSource:"react",
  nodePaths:[modules],logLevel:"warning",
  define:{"process.env.NODE_ENV":'"production"'},
 });
 const html='<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">'
  +'<meta name="viewport" content="width=device-width,initial-scale=1">'
  +'<title>Migration — isolated browser proof</title>'
  +'<link rel="stylesheet" href="/globals.css"></head>'
  +'<body><div id="root"></div><script src="/fixture.js" defer></script></body></html>';
 server=http.createServer((req,res)=>{
  if(req.method!=="GET"){mutations++;res.writeHead(405);res.end();return;}
  const url=new URL(req.url,"http://127.0.0.1");
  if(url.pathname==="/globals.css"){
   res.writeHead(200,{"Content-Type":"text/css; charset=utf-8","Cache-Control":"no-store"});res.end(css);
  }else if(url.pathname==="/fixture.js"){
   res.writeHead(200,{"Content-Type":"application/javascript; charset=utf-8","Cache-Control":"no-store"});
   res.end(fs.readFileSync(bundle));
  }else if(url.pathname==="/gates"){
   res.writeHead(200,{"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store"});res.end(html);
  }else{res.writeHead(404);res.end();}
 });
 await new Promise((resolve,reject)=>{server.once("error",reject);server.listen(0,"127.0.0.1",resolve);});
 origin="http://127.0.0.1:"+server.address().port;
 const executablePath=process.env.FACTORY_BROWSER_EXECUTABLE_PATH||"/usr/bin/google-chrome";
 browser=await chromium.launch({headless:true,executablePath,args:["--no-sandbox"]});
});
after(async()=>{
 await browser?.close();
 if(server)await new Promise(resolve=>server.close(resolve));
 fs.rmSync(work,{recursive:true,force:true});
 assert.equal(mutations,0,"browser fixture must never issue a POST");
 assert.deepEqual(untrusted,[],"fixture must never use external origins");
 if(errors.length)assert.fail("Browser errors: "+errors.slice(0,3).join(" | "));
});
async function pageAt(options={}){
 const context=await browser.newContext({viewport:options.viewport||{width:1280,height:900},
   reducedMotion:options.reducedMotion||"no-preference"});
 await context.route("**/*",async route=>{
  const url=new URL(route.request().url());
  if(url.origin!==origin){untrusted.push(url.origin);await route.abort("blockedbyclient");return;}
  await route.continue();
 });
 const page=await context.newPage();
 // Broken JSX bundles should fail within seconds rather than consume minutes.
 page.setDefaultTimeout(8500);
 page.on("pageerror",e=>errors.push(String(e)));
 page.on("console",msg=>{if(msg.type()==="error")errors.push(msg.text());});
 const response=await page.goto(origin+(options.path||"/gates"),{waitUntil:"networkidle"});
 assert.equal(response.status(),200);
 await page.waitForFunction(()=>!!window.__factoryMigrationProof);
 return {page,context};
}
async function submit(page,{confirm=true,keyboard=false}={}){
 const button=page.getByRole("button",{name:"Aplicar migration em produção"});
 page.once("dialog",dialog=>confirm?dialog.accept():dialog.dismiss());
 if(keyboard){await button.focus();await page.keyboard.press("Enter");}
 else await button.click();
 return button;
}
async function busy(page){
 await page.locator("fieldset.gatePendingFieldset[aria-busy='true']").waitFor();
 const button=page.getByRole("button",{name:"Aplicar migration em produção"});
 assert.equal(await button.isEnabled(),false,"the whole fieldset must be disabled");
 const live=page.locator(".gateBusyStatus[role='status'][aria-live='polite']");
 await live.waitFor();
 assert.match(await live.innerText(),/Aplicando a migration|Operação em andamento/);
 assert.equal(await page.evaluate(()=>window.__factoryMigrationProof.submissions()),1);
 return button;
}
test("no forged URL can render a success banner before an authorized action",async()=>{
 const {page,context}=await pageAt({path:"/gates?migration_result=aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"});
 assert.equal(await page.locator(".gateSuccessNotice").count(),0);
 assert.equal(await page.evaluate(()=>window.__factoryMigrationProof.submissions()),0);
 await context.close();
});
test("native confirm rejection never submits or shows pending/success",async()=>{
 const {page,context}=await pageAt();
 await submit(page,{confirm:false});
 assert.equal(await page.evaluate(()=>window.__factoryMigrationProof.submissions()),0);
 assert.equal(await page.locator(".gateBusyStatus").count(),0);
 assert.equal(await page.locator(".gateSuccessNotice").count(),0);
 await context.close();
});
test("real React form remains busy during delay and prevents repeat clicks",async()=>{
 const {page,context}=await pageAt();
 await submit(page);
 const button=await busy(page);
 await button.evaluate(el=>el.click()); // HTML fieldset disabled suppresses submit.
 assert.equal(await page.evaluate(()=>window.__factoryMigrationProof.submissions()),1);
 await page.evaluate(()=>window.__factoryMigrationProof.complete("verified"));
 await page.locator(".gateSuccessNotice[role='status']").waitFor();
 assert.match(await page.locator(".gateSuccessNotice").innerText(),/Migration aplicada e confirmada no Supabase/);
 assert.equal(await page.locator(".gateBusyStatus").count(),0);
 await page.waitForFunction(()=>!new URL(location.href).searchParams.has("migration_result"));
 const url=new URL(page.url());
 assert.equal(url.searchParams.has("migration_result"),false);
 assert.equal(url.searchParams.get("tab"),"controlled");
 assert.equal(url.hash,"#focus");
 assert.equal(await page.evaluate(()=>window.__factoryMigrationProof.submissions()),1);
 await page.getByRole("button",{name:"Fechar confirmação"}).click();
 assert.equal(await page.locator(".gateSuccessNotice").count(),0);
 await context.close();
});
test("already-applied verified receipt has distinct visible confirmation",async()=>{
 const {page,context}=await pageAt();
 await submit(page);
 await busy(page);
 await page.evaluate(()=>window.__factoryMigrationProof.complete("already_applied"));
 await page.locator(".gateSuccessNotice").waitFor();
 assert.match(await page.locator(".gateSuccessNotice").innerText(),/Migration já aplicada, estado confirmado/);
 await context.close();
});
test("missing evidence and backend failure never produce false success",async()=>{
 for(const verdict of ["missing_evidence","failed"]){
  const {page,context}=await pageAt();
  await submit(page);
  await busy(page);
  await page.evaluate(result=>window.__factoryMigrationProof.complete(result),verdict);
  await page.getByRole("alert").waitFor();
  assert.match(await page.getByRole("alert").innerText(),/O gate continua pendente/);
  assert.equal(await page.locator(".gateSuccessNotice").count(),0);
  await context.close();
 }
});
test("mobile, keyboard and reduced motion preserve accessible busy state",async()=>{
 const {page,context}=await pageAt({viewport:{width:390,height:844},reducedMotion:"reduce"});
 await submit(page,{keyboard:true});
 await busy(page);
 const viewport=await page.evaluate(()=>({
  width:window.innerWidth,scrollWidth:document.documentElement.scrollWidth,
  animation:getComputedStyle(document.querySelector(".gateBusySpinner")).animationName
 }));
 assert.equal(viewport.width,390);
 assert.ok(viewport.scrollWidth<=390,"overflow on mobile test fixture: "+viewport.scrollWidth);
 assert.equal(viewport.animation,"none","spinner must respect prefers-reduced-motion");
 await page.evaluate(()=>window.__factoryMigrationProof.complete("verified"));
 await page.locator(".gateSuccessNotice").waitFor();
 assert.equal(await page.locator(".gateSuccessNotice").getAttribute("aria-live"),"polite");
 await context.close();
});
