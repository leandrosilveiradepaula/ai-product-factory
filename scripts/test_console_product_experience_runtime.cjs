"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const model=fs.readFileSync(path.join(root,"apps/console/lib/product-experience-model.ts"),"utf8");
const compiled=ts.transpileModule(model,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
const box={exports:{}};vm.runInNewContext(compiled,box,{timeout:5000});
const summarize=box.exports.summarizeProductExperience;
assert.equal(typeof summarize,"function");
const project={key:"sample-product",name:"Product",stage:"operations",status:"active",updatedAt:"2026-11-18T12:00:00Z"};
const detail={id:"sample",active:true,pendingRun:null,isInternalRecord:false,
 productReadiness:{ready:false,assessedCommit:null}};
const context={objective:"Generate product",snapshot:{sourceStatus:{repair_status:null}}};
const control={state:"running",version:1,generation:1};
const work={kind:"idle",runId:null,at:null};
const params={project,detail,context,control,work,recovery:null,actionableGates:0};
const view=x=>summarize({...params,...x});
test("administrative operations does not imply delivery",()=>{
 const r=view({});
 assert.equal(r.tone,"quiet");assert.match(r.proof,/não comprovado/);
 assert.equal(r.declaredStageLabel,"Operação");
 assert.match(r.execution,/Nenhuma execução ativa/);
});
test("created pending run is not a running worker",()=>{
 const r=view({detail:{...detail,pendingRun:{id:"a",status:"created",createdAt:"2026-11-17",attemptCount:0}}});
 assert.equal(r.tone,"waiting");assert.match(r.headline,/ainda não começou/);
});
test("only a live lease yields working",()=>{
 assert.equal(view({work:{kind:"running",runId:"a",at:"2026-11-18"}}).tone,"working");
 assert.notEqual(view({work:{kind:"recorded",runId:"a",at:"2026-11-18"}}).tone,"working");
});
test("real human gate is distinct from technical repair",()=>{
 const recovery={status:"blocked",cycle:2,maxCycles:3,message:"context",updatedAt:"2026-11-17"};
 const blocked=view({recovery});
 assert.equal(blocked.tone,"blocked");assert.match(blocked.userAction,/Nenhuma aprovação/);
 assert.match(blocked.repairNote,/2 de 3/);assert.match(blocked.description,/Não há prova de recuperação/);
 const human=view({recovery,actionableGates:1});assert.equal(human.tone,"decision");assert.match(human.userAction,/Decisões/);
});
test("stopped internal project and missing detail never look delivered",()=>{
 const stopped=view({control:{state:"stopped",version:1,generation:1}});
 assert.equal(stopped.tone,"paused");
 const unknown=view({detail:null});assert.equal(unknown.tone,"unknown");
});
test("certification must remain bound to the assessed commit",()=>{
 const evaluated=view({detail:{...detail,productReadiness:{ready:true,assessedCommit:"a".repeat(40)} }});
 assert.equal(evaluated.tone,"evaluated");assert.match(evaluated.proof,/aaaaaaaa/);
 assert.match(evaluated.description,/não garante a versão/);
});
test("loss of runtime evidence fails closed",()=>{
 assert.equal(view({work:{kind:"unavailable",runId:null,at:null}}).tone,"unknown");
});
test("runtime reader demands a current lease and never uses lifecycle stage as evidence",()=>{
 const cp=fs.readFileSync(path.join(root,"apps/console/lib/control-plane.ts"),"utf8");
 assert.match(cp,/r\.lease_owner\.length>0/);
 assert.match(cp,/Date\.parse\(r\.lease_expires_at\)>now/);
 assert.match(cp,/r\.status==="running"\|\|r\.status==="implementing"/);
 assert.match(cp,/if\(!response\.ok\)return none\("unavailable"\)/);
 assert.match(cp,/isInternalRecord:p\.manifest\?\.qa_canary===true/);
});

test("new recovery receipt supersedes historical blocked repair without claiming release",()=>{
 const cp=fs.readFileSync(path.join(root,"apps/console/lib/control-plane.ts"),"utf8");
 assert.match(cp,/recoveredAt>=sourceAt/);
 assert.match(cp,/\"completed\",\"blocked\"/);
 const row={cycle:2,maxCycles:3,updatedAt:"2026-11-18"};
 assert.equal(view({recovery:{...row,status:"recovery_queued"}}).tone,"waiting");
 assert.equal(view({recovery:{...row,status:"recovery_claimed"}}).tone,"waiting");
 assert.equal(view({recovery:{...row,status:"recovery_recovering"}}).tone,"waiting");
 const finished=view({recovery:{...row,status:"recovery_completed"}});
 assert.equal(finished.tone,"quiet");
 assert.match(finished.headline,/recuperação terminou/);
 assert.equal(view({recovery:{...row,status:"recovery_blocked"}}).tone,"blocked");
});


test("real recovery failure with released change set shows precise next action",()=>{
 const r=view({
  detail:{...detail,latestRun:{status:"failed",failureKind:"no_actionable_work",
   createdAt:"2026-11-21T10:56:01Z"},
   releaseEvidence:{kind:"released",candidateCommit:"b".repeat(40),
    updatedAt:"2026-11-17T18:08:11Z"}},
  recovery:{status:"recovery_blocked",cycle:2,maxCycles:3,message:null,updatedAt:"2026-11-20T16:46:12Z"},
 });
 assert.equal(r.tone,"blocked");
 assert.match(r.label,/Retomada sem trabalho/);
 assert.match(r.description,/Repetir o mesmo pedido não cria trabalho novo/);
 assert.match(r.nextTitle,/Reconciliar/);
 assert.match(r.proof,/Release registrado/);
 assert.match(r.proof,/não são comprovados/);
 assert.equal(r.declaredStageLabel,"Operação");
});
test("live worker with current lease is not hidden by an old blocked recovery",()=>{
 const r=view({recovery:{status:"recovery_blocked",cycle:2,maxCycles:3},
  work:{kind:"running",runId:"live",at:"2026-11-21T16:50:00Z"},
  detail:{...detail,latestRun:{status:"failed",failureKind:"no_actionable_work",createdAt:"2026-11-21"}}});
 assert.equal(r.tone,"working");
});
test("recorded release does not prove whole-product readiness",()=>{
 const r=view({detail:{...detail,releaseEvidence:{kind:"released",
  candidateCommit:"c".repeat(40),updatedAt:"2026-11-17"}}});
 assert.equal(r.tone,"quiet");
 assert.match(r.proof,/não são comprovados/);
 assert.match(r.proof,/prontidão do produto ainda não certificada/);
});

test("owner portfolio exposes authenticated lifecycle commands without engineering controls",()=>{
 const home=fs.readFileSync(path.join(root,"apps/console/app/page.tsx"),"utf8");
 assert.match(home,/restartBlockedProjectWork\(key,Number\(version\),id\)/);
 assert.match(home,/command="restart" label="Reiniciar"/);
 assert.match(home,/command="pause" label="Pausar"/);
 assert.match(home,/command="stop" label="Parar"/);
 assert.match(home,/Solicitar alteração/);
 assert.match(home,/recovery\?\.status==="blocked"/);
 assert.match(home,/revalidatePath\("\/"\)/);
 assert.match(home,/Fase registrada:/);
 assert.match(home,/view.declaredStageLabel/);
 assert.match(home,/view.nextTitle/);
 assert.match(home,/ownerProductJourneyRail/);
 assert.match(home,/view.proof/);
 assert.match(home,/<summary>Gerenciar execução<\/summary>/);
 assert.doesNotMatch(home,/lease_owner|change_set_id|primary_model|worker_id/i);
});


test("financial blocker requires a real pending-run audit and current policy",()=>{
 const source=fs.readFileSync(path.join(root,"apps/console/lib/owner-financial-blocker.ts"),"utf8");
 const built=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
 const lib={exports:{}};vm.runInNewContext(built,lib,{timeout:5000});
 const check=lib.exports.ownerFinancialBlocker;
 const pending={id:"example",status:"queued",createdAt:"2026-11-18T18:02:48Z"};
 const observed={pendingRun:pending,wakeEvidence:{blockerCode:"budget_exhausted",blockedAt:"2026-11-18T18:03:43Z"}};
 const policy={budgetUsd:15,reserveUsd:0.5,knownSpendUsd:14.5408752,unknownPaidCostEvents:0};
 const blocked=check(observed,policy);
 assert.equal(blocked?.kind,"exhausted");
 assert.equal(blocked?.title,"Parado por limite financeiro");
 assert.match(blocked.detail,/US/);
 assert.match(blocked.detail,/0,50/);
 assert.equal(blocked.href,"/configuration");
 assert.equal(check(observed,{...policy,budgetUsd:20}),null);
 assert.equal(check({...observed,pendingRun:{...pending,status:"completed"}},policy),null);
 assert.equal(check({...observed,wakeEvidence:{...observed.wakeEvidence,blockerCode:"primary_auth_missing"}},policy),null);
 assert.equal(check({...observed,wakeEvidence:{...observed.wakeEvidence,blockedAt:"2026-11-18T17:00:00Z"}},policy),null);
 assert.equal(check(observed,{...policy,knownSpendUsd:null})?.kind,"unverified");
 assert.equal(check(observed,{...policy,unknownPaidCostEvents:1})?.kind,"unverified");
 assert.equal(check(observed,null)?.kind,"unverified");
});

test("owner portfolio only reads classified latest outcome and release facts",()=>{
 const cp=fs.readFileSync(path.join(root,"apps/console/lib/control-plane.ts"),"utf8");
 assert.match(cp,/releaseResponse\.ok/);
 assert.match(cp,/status=eq\.released/);
 assert.match(cp,/planning has no actionable tasks or decisions/);
 assert.match(cp,/latestRun,releaseEvidence,tasks/);
 assert.doesNotMatch(cp,/last_error:String/);
});


test("attention display separates genuine gates from GitHub App registration",()=>{
 const lib=fs.readFileSync(path.join(root,"apps/console/lib/owner-attention-counts.ts"),"utf8");
 const js=ts.transpileModule(lib,{compilerOptions:{target:ts.ScriptTarget.ES2022,
  module:ts.ModuleKind.CommonJS}}).outputText;
 const out={};vm.runInNewContext(js,{exports:out},{timeout:5000});
 const counts=out.ownerAttentionCounts;
 assert.equal(typeof counts,"function");
 const notConfigured=counts({pendingHumanGateCount:0,githubAppConfigured:false,pendingInstallCount:4});
 assert.equal(notConfigured.count,1);
 assert.equal(notConfigured.pendingHumanGateCount,0);
 assert.equal(notConfigured.pendingIntegrationActionCount,1);
 const configured=counts({pendingHumanGateCount:2,githubAppConfigured:true,pendingInstallCount:3});
 assert.equal(configured.count,5);
 assert.equal(configured.pendingHumanGateCount,2);
 assert.equal(configured.pendingIntegrationActionCount,3);
 assert.throws(()=>counts({pendingHumanGateCount:-1,githubAppConfigured:true,pendingInstallCount:0}),/owner_attention_unverifiable/);
 assert.throws(()=>counts({pendingHumanGateCount:0,githubAppConfigured:"yes",pendingInstallCount:0}),/owner_attention_unverifiable/);
 const api=fs.readFileSync(path.join(root,"apps/console/app/api/human-attention/route.ts"),"utf8");
 const shell=fs.readFileSync(path.join(root,"apps/console/app/shell.tsx"),"utf8");
 const gates=fs.readFileSync(path.join(root,"apps/console/app/gates/page.tsx"),"utf8");
 assert.match(api,/ownerAttentionCounts/);
 assert.match(shell,/snapshot\.pendingHumanGateCount\+snapshot\.pendingIntegrationActionCount/);
 assert.match(shell,/ação de integração/);
 assert.match(gates,/counts\.pendingHumanGateCount/);
 assert.match(gates,/counts\.pendingIntegrationActionCount/);
});
