/* Run actual Console operator-policy functions through the pinned TS compiler.
   No network, credentials, product runs or paid models. */
"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const translate=src=>ts.transpileModule(src,{compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
}}).outputText;

const page=fs.readFileSync(path.join(root,"apps/console/app/projects/[key]/page.tsx"),"utf8");
const start=page.indexOf("function nextAction(");
const end=page.indexOf("\nfunction controlNextAction(",start);
assert.ok(start>=0&&end>start,"real project nextAction policy is present");
const policyScope={exports:{}};
vm.runInNewContext(translate(page.slice(start,end)+"\nexports.policy=nextAction;"),policyScope,{timeout:10000});
const choose=policyScope.exports.policy;

test("assessed readiness shows its SHA and never promises production release",()=>{
 const r=choose("operations",false,0,{ready:true,assessedCommit:"a".repeat(40)});
 assert.match(r.title,/aprovada no SHA registrado/);
 assert.match(r.body,/a{12}/);
 assert.match(r.body,/não autoriza merge ou release/);
 assert.equal(r.href,"#product-readiness");
 assert.doesNotMatch(r.body,/domínios pendentes/);
});
test("open tasks are not called an active worker or a completed release",()=>{
 const r=choose("operations",false,2,{ready:true,assessedCommit:"a".repeat(40)});
 assert.match(r.title,/tarefas abertas/);
 assert.equal(r.href,"/runs");
 assert.match(r.body,/não significa que o worker esteja executando/);
});
test("missing readiness is evidence pending, not a fabricated certification",()=>{
 const r=choose("operations",false,0,{ready:false,assessedCommit:null});
 assert.match(r.title,/Verificar a prontidão global do produto/);
 assert.equal(r.href,"#product-readiness");
});
test("pending database and actual human gate take precedence",()=>{
 const ready={ready:true,assessedCommit:"a".repeat(40)};
 assert.equal(choose("operations",true,0,ready).href,"#databases");
 assert.equal(choose("human_gate",false,1,ready).href,"/gates");
 assert.equal(choose("planning",false,1,ready).href,"/queue");
});

const source=fs.readFileSync(path.join(root,"apps/console/app/api/human-attention/route.ts"),"utf8");
const core=source.slice(source.indexOf('export const dynamic="force-dynamic";'));
assert.ok(core.startsWith("export const dynamic"));
let data={gates:[],installs:[],configured:false,fail:false};
const sandbox={
 exports:{},
 NextResponse:{json:(body,options={})=>({body,status:options.status||200})},
 requireConsoleOperator:async()=>({role:"operator"}),
 getHumanGates:async()=>{if(data.fail)throw Error("unavailable");return data.gates;},
 getGitHubAppInstallActions:async()=>data.installs,
 getGitHubAppStatus:async()=>({configured:data.configured}),
};
vm.runInNewContext(translate(core),sandbox,{timeout:10000});
const call=()=>sandbox.exports.GET();
test("optional global GitHub App does not fabricate a pending production gate",async()=>{
 data={gates:[],installs:[],configured:false,fail:false};
 const r=await call();
 assert.equal(r.status,200);
 assert.equal(r.body.status,"ok");
 assert.equal(r.body.count,0);
 assert.equal(r.body.pendingHumanGateCount,0);
});
test("stale pending gates are excluded; genuine actionable gates count",async()=>{
 data={gates:[
  {status:"pending",actionable:false},
  {status:"pending",actionable:true,projectKey:"factory"},
  {status:"approved",actionable:true}
 ],installs:[],configured:false,fail:false};
 const r=await call();
 assert.equal(r.body.count,1);
 assert.equal(r.body.pendingHumanGateCount,1);
 assert.deepEqual(Array.from(r.body.projects),["factory"]);
});
test("verified GitHub App project installation is a distinct human action",async()=>{
 data={gates:[],installs:[{projectKey:"crm"},{projectKey:"studio"}],configured:true,fail:false};
 const r=await call();
 assert.equal(r.body.count,2);
 assert.equal(r.body.pendingHumanGateCount,0);
});
test("unavailable Control Plane fails closed, not reported as zero actions",async()=>{
 data={gates:[],installs:[],configured:true,fail:true};
 const r=await call();
 assert.equal(r.status,503);
 assert.equal(r.body.status,"unavailable");
 assert.equal(r.body.count,undefined);
});
