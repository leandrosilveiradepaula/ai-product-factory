/* Runtime policy regression: business readiness is different from code/Preview. */
"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.resolve(__dirname,".."),ts=require(path.join(root,"apps/console/node_modules/typescript"));
function load(name){
 const input=fs.readFileSync(path.join(root,"apps/console/lib",name),"utf8");
 const compiled=ts.transpileModule(input,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const ctx={exports:{}};vm.runInNewContext(compiled,ctx,{timeout:10000});return ctx.exports;
}
const {explainRunBlocker}=load("product-blocker.ts");
const {diagnoseProduct}=load("product-diagnosis.ts");
const p=(changes={})=>({
 key:"client-project",name:"Client project",stage:"operations",projectKind:"greenfield",
 isActive:true,controlState:"running",state:"investigate",
 proof:{productReady:false,hasHumanMerge:true,hasPreviewRecord:true},
 blocker:explainRunBlocker("blocked","Cannot safely implement because authoritative AGENTS.md content is not present in exact SHA context"),
 databaseEvidence:{state:"not_recorded",linked:0,lastVerifiedAt:null},
 requirementCount:57,specStatus:"candidate",sourceIssueUrl:"https://github.com/example/repo/issues/42",
 lastRun:{id:"11111111-2222-4333-8444-555555555555",status:"blocked",taskTitle:"Repair security",at:"2026-11-18T00:00:00Z"},
 ...changes
});
test("missing AGENTS.md context has specific safe correction without echoing raw error",()=>{
 const d=explainRunBlocker("blocked","Cannot safely implement the patch because the authoritative AGENTS.md content is not present in the supplied exact-SHA context.");
 assert.equal(d.code,"source_context");assert.match(d.title,/Instruções/);
 assert.match(d.resolution,/instruções reais/);
 assert.equal(explainRunBlocker("completed","AGENTS.md missing"),null);
});
test("a merged greenfield with an unlinked database is not declared usable",()=>{
 const d=diagnoseProduct(p());
 assert.equal(d.status,"blocked");assert.match(d.headline,/não entregue/);
 assert.match(d.findings.find(x=>x.label==="Banco no inventário da Factory").value,/não significa ausência de banco/);
 assert.ok(d.steps.some(x=>/Conferir o banco dedicado/.test(x.title)));
 assert.equal(d.steps[0].title,"Instruções do repositório não verificadas","A falha técnica ativa deve vir antes de integrações que ainda precisam ser conferidas");
 assert.equal(d.steps[1].title,"Conferir o banco dedicado e a conexão");
 assert.ok(d.steps.some(x=>/Instruções do repositório/.test(x.title)));
 assert.ok(d.steps.some(x=>/usuários autenticados/.test(x.title)));
 assert.ok(!JSON.stringify(d).includes("Studio"),"No client-specific status hardcoded");
});
test("a verified database alone never promotes functional readiness",()=>{
 const d=diagnoseProduct(p({databaseEvidence:{state:"verified",linked:1,lastVerifiedAt:"2026-11-16T00:00:00Z"},blocker:null,state:"idle"}));
 assert.equal(d.status,"unverified");
 assert.match(d.findings.find(x=>x.label==="Uso real do produto").value,/Sem fluxo completo comprovado/);
 assert.ok(d.steps.some(x=>/fluxo com usuários autenticados/.test(x.title)));
});
test("human attention must be an actual gate, not a blocked task",()=>{
 const d=diagnoseProduct(p({state:"decision",blocker:null}));
 assert.equal(d.steps[0].href,"/gates");
 const b=diagnoseProduct(p());
 assert.ok(b.steps.every(s=>s.href!=="/gates"));
});
test("existing project without a database binding is not forced into provisioning",()=>{
 const d=diagnoseProduct(p({projectKind:"existing",databaseEvidence:{state:"not_recorded",linked:0,lastVerifiedAt:null},state:"idle",blocker:null}));
 assert.ok(!d.steps.some(x=>/banco dedicado/.test(x.title)));
});
test("certification and intentionally stopped projects are distinct",()=>{
 const ready=diagnoseProduct(p({proof:{productReady:true,hasHumanMerge:true},state:"idle",blocker:null}));
 assert.equal(ready.status,"assessed");assert.equal(ready.steps.length,1);
 const stopped=diagnoseProduct(p({isActive:false,controlState:"stopped",state:"stopped",blocker:null}));
 assert.equal(stopped.status,"stopped");assert.equal(stopped.steps.length,1);
});
