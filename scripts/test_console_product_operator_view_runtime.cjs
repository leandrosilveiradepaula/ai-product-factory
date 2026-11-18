"use strict";
const {test}=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const input=fs.readFileSync(path.join(root,"apps/console/lib/product-operator-view.ts"),"utf8");
const js=ts.transpileModule(input,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const context={exports:{}};vm.runInNewContext(js,context,{timeout:10000});
const view=context.exports.summarizeOwnerProduct;
const base={key:"example-product",name:"Example",stage:"operations",isActive:true,controlState:"running",
 projectKind:"greenfield",state:"investigate",unclosedTasks:1,confirmedRunning:0,
 proof:{productReady:false,hasHumanMerge:true},databaseEvidence:{state:"not_recorded"},
 lastRun:{id:"11-22",at:"2026-11-17T14:46:00Z",status:"blocked",taskTitle:"Repair"},
 blocker:{code:"source_context",title:"AGENTS not verified",why:"Exact SHA context unavailable",resolution:"Verify source then retry"},
 latestRepair:{status:"blocked",cycle:2,maxCycles:3,updatedAt:"2026-11-17T15:50:00Z",role:"security"}};
test("blocked repair is owned by Factory and does not pretend work is running",()=>{
 const x=view(base);assert.equal(x.tone,"blocked");assert.equal(x.actionHref,null);
 assert.match(x.activity,/Nenhuma execução ativa/);assert.match(x.reason,/2 de 3/);
 assert.match(x.nextTitle,/contexto do repositório/);assert.match(x.nextDetail,/não uma execução agendada/);
 assert.match(x.yourAction,/Nenhuma aprovação/);
});
test("only a real human gate yields a required action link",()=>{
 const human=view({...base,state:"decision"});assert.equal(human.actionHref,"/gates");assert.equal(human.tone,"human");
 for(const state of ["investigate","queued","verifying","executing","idle","unknown"]){
  assert.equal(view({...base,state}).actionHref,null,state);
 }
});
test("paused or draft control exposes the real control action without release permission",()=>{
 const paused=view({...base,state:"paused",controlState:"paused"});
 assert.equal(paused.actionHref,"/projects/example-product#project-control");
 assert.match(paused.yourAction,/opcional/i);
 const draft=view({...base,state:"unknown",controlState:"draft"});assert.match(draft.actionLabel,/iniciar/);
});
test("live worker requires observed lease-confirmed state",()=>{
 const x=view({...base,state:"executing",confirmedRunning:1,currentWork:"Build main workflow"});
 assert.equal(x.tone,"doing");assert.match(x.activity,/lease vigente/);assert.match(x.reason,/Build main workflow/);
});
test("unproven greenfield and certified release remain distinct",()=>{
 const pending=view({...base,state:"idle",unclosedTasks:0,blocker:null,latestRepair:null});
 assert.equal(pending.tone,"quiet");assert.match(pending.delivery,/não comprovado/);
 assert.match(pending.nextTitle,/ambiente e o fluxo/);
 const ready=view({...base,state:"idle",unclosedTasks:0,proof:{productReady:true,hasHumanMerge:true}});
 assert.equal(ready.tone,"delivered");assert.match(ready.delivery,/avaliado/);assert.equal(ready.actionHref,null);
});
