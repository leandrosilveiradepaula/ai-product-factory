import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {reconcileServedConsole} from "./reconcile_console_served_commit.mjs";
const R="/repos/leandrosilveiradepaula/ai-product-factory";
const main="b".repeat(40),deployed="a".repeat(40);
const treeMain="1".repeat(40),treeOld="2".repeat(40);
const appsMain="3".repeat(40),appsOld="4".repeat(40);
const configMain="5".repeat(40),configOld="6".repeat(40);
const consoleTree="7".repeat(40),policy="8".repeat(40);
const entry=(path,sha,type="tree")=>({path,sha,type,mode:type==="tree"?"040000":"100644"});
const tree=arr=>({truncated:false,tree:arr});
const status={context:"Vercel",state:"success",
 target_url:"https://vercel.com/leandros-projects-102e32ab/ai-product-factory-console/FXR4ohGZ7mgUmVz7n89TM8S8Wqao"};
function fixture(override={},healthCommit=deployed.slice(0,12),statusCode=200){
 const lookup={
  [R+"/git/ref/heads/main"]:{object:{sha:main}},
  [R+"/commits/"+deployed.slice(0,12)]:{sha:deployed},
  [R+"/commits/"+main]:{sha:main,commit:{tree:{sha:treeMain}}},
  [R+"/commits/"+deployed]:{sha:deployed,commit:{tree:{sha:treeOld}}},
  [R+"/compare/"+deployed+"..."+main]:{status:"ahead",behind_by:0,
    base_commit:{sha:deployed},merge_base_commit:{sha:deployed}},
  [R+"/git/trees/"+treeMain]:tree([entry("apps",appsMain),entry("config",configMain)]),
  [R+"/git/trees/"+treeOld]:tree([entry("apps",appsOld),entry("config",configOld)]),
  [R+"/git/trees/"+appsMain]:tree([entry("console",consoleTree)]),
  [R+"/git/trees/"+appsOld]:tree([entry("console",consoleTree)]),
  [R+"/git/trees/"+configMain]:tree([entry("factory.release-policy.v1.json",policy,"blob")]),
  [R+"/git/trees/"+configOld]:tree([entry("factory.release-policy.v1.json",policy,"blob")]),
  [R+"/commits/"+deployed+"/status"]:{statuses:[status]},...override,
 };
 const calls=[];
 const githubGet=async path=>{
  calls.push(path);
  if(!Object.hasOwn(lookup,path))throw Error("unexpected "+path);
  return lookup[path];
 };
 const request=async(url,opts)=>{
  calls.push(url);assert.equal(url,"https://ai-product-factory-console.vercel.app/api/health");
  assert.equal(opts.headers["x-vercel-trusted-oidc-idp-token"],"synthetic-oidc");
  assert.equal(opts.redirect,"error");
  return new Response(JSON.stringify({status:"ok",service:"ai-product-factory-console",
   commit:healthCommit}),{status:statusCode});
 };
 return {args:{sourceCommit:main,consoleUrl:"https://ai-product-factory-console.vercel.app",
  oidcToken:"synthetic-oidc",githubGet,request},calls};
}
test("old served commit can be reconciled ONLY when build inputs identical",async()=>{
 const {args,calls}=fixture(),r=await reconcileServedConsole(args);
 assert.equal(r.sourceCommit,main);assert.equal(r.servedCommit,deployed);
 assert.equal(r.consoleTreeSha,consoleTree);assert.equal(r.releasePolicyBlobSha,policy);
 assert.equal(r.sourceEqualsServed,false);assert.equal(r.authenticatedUxCertified,false);
 assert.equal(r.productReadyCertified,false);assert.equal(r.writes,0);assert.equal(r.paidCalls,0);
 assert.equal(JSON.stringify(r).includes("synthetic-oidc"),false);
 assert.equal(calls.filter(x=>x.endsWith("/api/health")).length,2);
});
test("moving branch refuses SHA reuse",async()=>{
 const {args}=fixture({[R+"/git/ref/heads/main"]:{object:{sha:"c".repeat(40)}}});
 await assert.rejects(reconcileServedConsole(args),/console_source_head_changed/);
});
test("changed Console or release policy refuses reuse",async()=>{
 const a=fixture({[R+"/git/trees/"+appsOld]:tree([entry("console","c".repeat(40))])});
 await assert.rejects(reconcileServedConsole(a.args),/console_source_tree_changed_since_deployment/);
 const b=fixture({[R+"/git/trees/"+configOld]:
  tree([entry("factory.release-policy.v1.json","c".repeat(40),"blob")])});
 await assert.rejects(reconcileServedConsole(b.args),/console_source_tree_changed_since_deployment/);
});
test("non-ancestor or ambiguous SHA refuses reuse",async()=>{
 const a=fixture({[R+"/compare/"+deployed+"..."+main]:
  {status:"diverged",behind_by:1,base_commit:{sha:deployed},merge_base_commit:{sha:"c".repeat(40)}}});
 await assert.rejects(reconcileServedConsole(a.args),/console_served_commit_not_ancestor/);
 const b=fixture({[R+"/commits/"+deployed.slice(0,12)]:{sha:"c".repeat(40)}});
 await assert.rejects(reconcileServedConsole(b.args),/console_served_commit_ambiguous/);
});
test("untrusted Vercel deployment and duplicate statuses are rejected",async()=>{
 for(const bad of [{...status,state:"pending"},
  {...status,target_url:"https://vercel.com/other-team/ai-product-factory-console/FXR4ohGZ7mgUmVz7n89TM8S8Wqao"}]){
  const {args}=fixture({[R+"/commits/"+deployed+"/status"]:{statuses:[bad]}});
  await assert.rejects(reconcileServedConsole(args),/Vercel/);
 }
 const {args}=fixture({[R+"/commits/"+deployed+"/status"]:{statuses:[status,status]}});
 await assert.rejects(reconcileServedConsole(args),/console_served_vercel_status_ambiguous/);
});
test("truncated tree, unavailable health and wrong live SHA fail closed",async()=>{
 const a=fixture({[R+"/git/trees/"+appsMain]:{truncated:true,tree:[entry("console",consoleTree)]}});
 await assert.rejects(reconcileServedConsole(a.args),/console_git_tree_incomplete/);
 const b=fixture({},deployed.slice(0,12),503);
 await assert.rejects(reconcileServedConsole(b.args),/console_live_health_unavailable/);
 const c=fixture({[R+"/commits/"+"c".repeat(12)]:{sha:"d".repeat(40)}},"c".repeat(12));
 await assert.rejects(reconcileServedConsole(c.args),/console_served_commit_ambiguous/);
});
test("host is validated before OIDC-bearing request, including owned Preview",async()=>{
 const {args,calls}=fixture();
 for(const consoleUrl of ["https://evil.example","http://ai-product-factory-console.vercel.app",
   "https://ai-product-factory-console.vercel.app/?token=x",
   "https://ai-product-factory-console-4sbrw91c5-leandros-projects-102e32ab.vercel.app"]){
  await assert.rejects(reconcileServedConsole({...args,consoleUrl}),/(console_|visual target)/);
 }
 assert.equal(calls.length,0);
});
test("the workflow reconciles before credentials and never auto-runs for script changes",()=>{
 const yml=fs.readFileSync(new URL("../.github/workflows/authenticated-visual-evidence.yml",import.meta.url),"utf8");
 const ix=yml.indexOf("Resolve served Console SHA from verified live deployment");
 assert.ok(ix>0&&ix<yml.indexOf("Require Vercel success for the exact candidate SHA"));
 assert.ok(ix<yml.indexOf("Provision ephemeral visual operator"));
 assert.match(yml,/node scripts\/reconcile_console_served_commit\.mjs/);
 assert.match(yml,/inputs\.target_commit == ''/);
 assert.ok(yml.split("  push:")[1].split("\npermissions:")[0].includes('"apps/console/**"'));
 assert.ok(yml.includes("Finalize registry and remove ephemeral operator"));
});
