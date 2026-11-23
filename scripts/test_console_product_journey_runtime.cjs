/* Runtime proof of the actual TS product journey policy. No network or writes. */
"use strict";
const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const file=fs.readFileSync(path.join(root,"apps/console/lib/product-journey.ts"),"utf8");
const compiled=ts.transpileModule(file,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const context={exports:{}};vm.runInNewContext(compiled,context,{timeout:10000});
const describe=context.exports.describeProductJourney;
const p=(changes={})=>({
 key:"factory-example",name:"Test product",stage:"implementation",
 isActive:true,controlState:"running",state:"idle",headline:"No active run",
 explanation:"No run confirmed",nextOwner:"Factory",nextHref:"/runs",nextLabel:"View runs",
 lastRequest:null,lastRequestAt:null,lastRun:null,unclosedTasks:0,confirmedRunning:0,observedAt:"2026-11-18T00:00:00Z",updatedAt:"2026-11-18T00:00:00Z",
 ...changes
});
test("the same six phases guide both the overview and project detail",()=>{
 const a=describe(p());assert.equal(a.phaseSteps.length,6);
 assert.equal(a.phaseSteps.map(x=>x.label).join(">"),"Entender>Planejar>Construir>Testar>Publicar>Operar");
 assert.equal(a.phaseIndex,2);assert.equal(a.phaseLabel,"Construir");assert.equal(a.nextPhaseLabel,"Testar");
 assert.equal(a.phaseSteps.filter(x=>x.mark==="atual").length,1);
 assert.equal(a.phaseSteps.filter(x=>x.mark==="proxima").length,1);
 assert.match(a.conditionToAdvance,/revisado/);
});
test("sub-stages never fabricate another major phase",()=>{
 const expected={discovery:["Entender","Planejar"],specification:["Entender","Planejar"],planning:["Planejar","Construir"],review:["Construir","Testar"],validation:["Testar","Publicar"],preview:["Testar","Publicar"],human_gate:["Publicar","Operar"],release:["Publicar","Operar"],operations:["Operação registrada (não certificada)","Comprovar entrega funcional"]};
 for(const [stage,[current,next]]of Object.entries(expected)){
  const journey=describe(p({stage}));assert.equal(journey.phaseLabel,current,stage);assert.equal(journey.nextPhaseLabel,next,stage);
 }
});
test("project registered as running is not presented as executing",()=>{
 const x=describe(p({state:"idle",unclosedTasks:4}));
 assert.equal(x.action.owner,"Equipe técnica");assert.equal(x.action.humanRequired,false);
 assert.match(x.action.description,/nenhum worker em execução comprovada/);
 assert.equal(x.action.href,"/deliveries?project=factory-example");
});
test("a human decision is mandatory only for a real actionable gate",()=>{
 const gate=describe(p({state:"decision",nextHref:"/gates"}));
 assert.equal(gate.action.humanRequired,true);assert.equal(gate.action.owner,"Você");assert.equal(gate.action.href,"/gates");
 for(const state of ["idle","investigate","queued","executing","verifying","paused","stopped"]){
  const x=describe(p({state,unclosedTasks:1}));
  assert.equal(x.action.humanRequired,false,state);
 }
});
test("blocked repair is technical, not a false approval",()=>{
 const x=describe(p({stage:"operations",state:"investigate",lastRun:{status:"blocked",id:"test",taskTitle:"Repair",at:"2026-11-17T00:00:00Z"}}));
 assert.equal(x.phaseLabel,"Operação registrada (não certificada)");assert.equal(x.nextPhaseLabel,"Comprovar entrega funcional");
 assert.equal(x.action.owner,"Equipe técnica");assert.equal(x.action.humanRequired,false);
});
test("stopped and paused products do not request an unsafe automatic restart",()=>{
 for(const state of ["paused","stopped"]){const x=describe(p({state}));
  assert.equal(x.action.owner,"Nenhuma ação necessária");assert.equal(x.action.humanRequired,false);
  assert.equal(x.action.href,"/projects/factory-example#project-control");
 }
});
test("a newly registered draft tells the user how to start instead of claiming broken control",()=>{
 const x=describe(p({stage:"discovery",controlState:"draft",state:"unknown"}));
 assert.equal(x.phaseLabel,"Entender");assert.equal(x.nextPhaseLabel,"Planejar");
 assert.equal(x.action.owner,"Você");assert.equal(x.action.href,"/projects/factory-example#project-control");
 assert.equal(x.action.label,"Ir para Iniciar projeto");assert.equal(x.action.humanRequired,false);
});
test("new project requests a Start, but unverified operation requires delivery proof",()=>{
 const newProduct=describe(p({stage:"discovery",lastRequest:null,unclosedTasks:0}));
 assert.equal(newProduct.action.owner,"Você");assert.equal(newProduct.action.href,"/projects/factory-example/request");
 const operation=describe(p({stage:"operations"}));
 assert.equal(operation.action.owner,"Equipe técnica");assert.equal(operation.action.humanRequired,false);
 assert.equal(operation.action.label,"Ver evidências de publicação");
});
test("a certified operation is distinct from a merge-only product",()=>{
 const x=describe(p({stage:"operations",proof:{productReady:true}}));
 assert.equal(x.phaseLabel,"Operar");assert.equal(x.nextPhaseLabel,"Evoluir quando solicitado");
 assert.equal(x.action.owner,"Nenhuma ação necessária");
});
test("unknown stages do not fabricate completed steps or a next phase",()=>{
 const x=describe(p({stage:"external_launch"}));
 assert.equal(x.phaseKnown,false);assert.equal(x.phaseIndex,-1);assert.equal(x.nextPhaseLabel,"A confirmar");
 assert.ok(x.phaseSteps.every(y=>y.mark==="desconhecida"));
 assert.equal(x.action.humanRequired,false);
});
