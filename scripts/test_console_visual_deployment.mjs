import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {consoleVisualOrigin,consoleVercelDeploymentStatus} from "./console_visual_origin.mjs";
import {PRODUCTION_URL,selectConsoleVisualTarget} from "./resolve_console_visual_target.mjs";
import {validVisualIdentity,isMatchingHealth,verifyConsoleDeployment} from "./verify_console_deployed_sha.mjs";

const OLD_SHA="34c614be92a544bb52c1b2634fc6c82b1be6d25e";
const DEPLOYED_SHA="53bd03b274129925f713f614243093e165f03ed1";
const OWNED_PREVIEW="https://ai-product-factory-console-4sbrw91c5-leandros-projects-102e32ab.vercel.app";
const PINNED={preview_url:PRODUCTION_URL,candidate_sha:OLD_SHA,purpose:"Prior audit"};

test("Console main push MUST override stale source controlled target",()=>{
 const selected=selectConsoleVisualTarget({
  eventName:"push",headSha:DEPLOYED_SHA,consoleChanged:true,pinnedTarget:PINNED,
 });
 assert.deepEqual(selected,{preview_url:PRODUCTION_URL,candidate_sha:DEPLOYED_SHA,source:"production_console_push"});
});

test("workflow-only push intentionally reuses a pinned release without claiming a new deployment",()=>{
 const selected=selectConsoleVisualTarget({
  eventName:"push",headSha:DEPLOYED_SHA,consoleChanged:false,pinnedTarget:PINNED,
 });
 assert.equal(selected.candidate_sha,OLD_SHA);
 assert.equal(selected.source,"source_control_pinned");
});

test("manual audit only uses the explicit target",()=>{
 const selected=selectConsoleVisualTarget({
  eventName:"workflow_dispatch",headSha:DEPLOYED_SHA,
  dispatchUrl:OWNED_PREVIEW,
  dispatchCommit:OLD_SHA,
 });
 assert.equal(selected.candidate_sha,OLD_SHA);
 assert.equal(selected.preview_url,OWNED_PREVIEW);
 assert.equal(selected.source,"manual_exact");
});

test("unsupported trigger, invalid SHA, outside host and dirty URL are rejected",()=>{
 assert.throws(()=>selectConsoleVisualTarget({eventName:"issue_comment",headSha:DEPLOYED_SHA}),/unsupported/);
 assert.throws(()=>selectConsoleVisualTarget({eventName:"push",headSha:"123",consoleChanged:true}),/invalid/);
 for(const url of [
  "https://evil.example","http://ai-product-factory-console.vercel.app",
  "https://foo.vercel.app","https://preview-a.vercel.app",
  "https://ai-product-factory-console-4sbrw91c5-wrong-team.vercel.app",
  "https://ai-product-factory-console-4sbrw91c5-leandros-projects-102e32ab.vercel.app.evil.com",
  "https://ai-product-factory-console-evil-leandros-projects-102e32ab.vercel.app",
  OWNED_PREVIEW+"/login",OWNED_PREVIEW+"?secret=1",
  OWNED_PREVIEW+"#fragment","https://user:pw@ai-product-factory-console.vercel.app",
  "https://ai-product-factory-console.vercel.app:444",
 ]){
  assert.throws(()=>selectConsoleVisualTarget({eventName:"workflow_dispatch",headSha:DEPLOYED_SHA,dispatchUrl:url}),/target/);
 }
 assert.throws(()=>selectConsoleVisualTarget({
  eventName:"push",headSha:DEPLOYED_SHA,consoleChanged:false,pinnedTarget:null,
 }),/pinned/);
 assert.throws(()=>selectConsoleVisualTarget({
  eventName:"push",headSha:DEPLOYED_SHA,consoleChanged:false,
  pinnedTarget:{...PINNED,purpose:"secret supplied"},
 }),/secret-like/);
});

test("health must contain exact service status and exact commit prefix",()=>{
 const prefix=DEPLOYED_SHA.slice(0,12);
 assert.equal(validVisualIdentity({url:PRODUCTION_URL,sha:DEPLOYED_SHA}).expectedPrefix,prefix);
 assert.equal(isMatchingHealth({status:"ok",service:"ai-product-factory-console",commit:prefix},prefix),true);
 for(const value of [null,{status:"ok",service:"wrong",commit:prefix},
  {status:"ok",service:"ai-product-factory-console",commit:null},
  {status:"healthy",service:"ai-product-factory-console",commit:prefix},
  {status:"ok",service:"ai-product-factory-console",commit:OLD_SHA.slice(0,12)}]){
  assert.equal(isMatchingHealth(value,prefix),false);
 }
});

test("verify rejects 200 HTTP from wrong deployed SHA and never manufactures success",async()=>{
 const request=async()=>new Response(JSON.stringify({
  status:"ok",service:"ai-product-factory-console",commit:OLD_SHA.slice(0,12),
 }),{status:200});
 await assert.rejects(verifyConsoleDeployment({
  url:PRODUCTION_URL,sha:DEPLOYED_SHA,attempts:2,waitMs:0,request,sleep:async()=>{},
 }),/returned_commit_or_service_did_not_match/);
});

test("exact returned deployment is accepted and OIDC is header-only",async()=>{
 let observed="";
 const request=async(url,options)=>{
  assert.equal(new URL(url).pathname,"/api/health");
  observed=options.headers["x-vercel-trusted-oidc-idp-token"];
  return new Response(JSON.stringify({
   status:"ok",service:"ai-product-factory-console",commit:DEPLOYED_SHA.slice(0,12),
  }),{status:200});
 };
 const result=await verifyConsoleDeployment({
  url:PRODUCTION_URL,sha:DEPLOYED_SHA,oidcToken:"ephemeral-test",
  attempts:1,request,
 });
 assert.equal(observed,"ephemeral-test");
 assert.equal(result.verified,true);
 assert.equal(result.commitPrefix,DEPLOYED_SHA.slice(0,12));
});

test("invalid verification attempts and missing health fail closed",async()=>{
 await assert.rejects(verifyConsoleDeployment({
  url:PRODUCTION_URL,sha:DEPLOYED_SHA,attempts:0,
 }),/attempts/);
 await assert.rejects(verifyConsoleDeployment({
  url:PRODUCTION_URL,sha:DEPLOYED_SHA,attempts:1,
  request:async()=>new Response("no",{status:503}),
 }),/unexpected_http_status_503/);
});

test("only deployment hosts of the actual Console Vercel project are trusted",()=>{
 assert.equal(consoleVisualOrigin(PRODUCTION_URL),PRODUCTION_URL);
 assert.equal(consoleVisualOrigin(OWNED_PREVIEW+"/"),OWNED_PREVIEW);
 assert.equal(validVisualIdentity({url:OWNED_PREVIEW,sha:DEPLOYED_SHA}).origin,OWNED_PREVIEW);
 for(const url of [
  "https://example.vercel.app",
  "https://ai-product-factory-console-4sbrw91c5-other-team.vercel.app",
  "https://ai-product-factory-console-4sbrw91c5-leandros-projects-102e32ab.vercel.app.other.example",
  "https://ai-product-factory-console-4sbrw91c5-leandros-projects-102e32ab.vercel.app:8443",
  "https://ai-product-factory-console.vercel.app.evil.example",
  "https://ai-product-factory-console-leandros-projects-102e32ab.vercel.app",
 ]){
  assert.throws(()=>consoleVisualOrigin(url),/visual target/);
 }
});

test("a forged health response never receives a Trusted Source OIDC header",async()=>{
 let contacted=false;
 const forgedHealth=async()=>{
  contacted=true;
  return new Response(JSON.stringify({status:"ok",service:"ai-product-factory-console",
                                     commit:DEPLOYED_SHA.slice(0,12)}),{status:200});
 };
 await assert.rejects(verifyConsoleDeployment({
  url:"https://evil-console.vercel.app",sha:DEPLOYED_SHA,
  oidcToken:"sensitive-token-never-sent",attempts:1,request:forgedHealth,
 }),/visual target/);
 assert.equal(contacted,false,"No network call is permitted to an unowned host");
});

test("Vercel status must originate from official project and deployment path",()=>{
 const status={context:"Vercel",state:"success",
  target_url:"https://vercel.com/leandros-projects-102e32ab/ai-product-factory-console/FXR4ohGZ7mgUmVz7n89TM8S8Wqao"};
 assert.equal(consoleVercelDeploymentStatus(status).project,"ai-product-factory-console");
 for(const invalid of [
  {...status,target_url:"https://vercel.com/foreign-team/ai-product-factory-console/FXR4ohGZ7mgUmVz7n89TM8S8Wqao"},
  {...status,target_url:"https://vercel.com/leandros-projects-102e32ab/other-project/FXR4ohGZ7mgUmVz7n89TM8S8Wqao"},
  {...status,target_url:"https://vercel.com/leandros-projects-102e32ab/ai-product-factory-console/../../other"},
  {...status,target_url:"https://vercel.com/leandros-projects-102e32ab/ai-product-factory-console/FXR4ohGZ7mgUmVz7n89TM8S8Wqao?x=1"},
  {...status,target_url:"https://vercel.com/leandros-projects-102e32ab/ai-product-factory-console/FXR4ohGZ7mgUmVz7n89TM8S8Wqao@other.example"},
  {...status,state:"pending"},
 ]){
  assert.throws(()=>consoleVercelDeploymentStatus(invalid),/Vercel/);
 }
});

test("source-only security changes cannot provision operators automatically",()=>{
 const yml=fs.readFileSync(new URL("../.github/workflows/authenticated-visual-evidence.yml",import.meta.url),"utf8");
 const trigger=yml.split("  push:")[1]?.split("\npermissions:")[0];
 assert.ok(trigger,"expected push path filter");
 assert.match(trigger,/apps\/console\/\*\*/);
 for(const path of [
  "scripts/resolve_console_visual_target.mjs",
  "scripts/verify_console_deployed_sha.mjs",
  "scripts/capture_authenticated_console.mjs",
  ".github/workflows/authenticated-visual-evidence.yml",
 ]){
  assert.equal(trigger.includes('"' + path + '"'),false,
   "Source-only changes must not create a production operator: "+path);
 }
 assert.match(yml,/parts\[0\] !== "leandros-projects-102e32ab"/);
 assert.match(yml,/parts\[1\] !== "ai-product-factory-console"/);
});
