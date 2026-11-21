/* Execute real TypeScript presentation policies through the Console-pinned compiler.
 * Offline: no browser credential, DB mutation, paid model or network. */
"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
function evaluate(source){
 const compiled=ts.transpileModule(source,{compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
 }}).outputText;
 const ctx={exports:{}};
 vm.runInNewContext(compiled,ctx,{timeout:10000});
 return ctx.exports;
}
const operator=fs.readFileSync(path.join(root,"apps/console/lib/operator-home.ts"),"utf8");
const {summarizeOperatorAttention,operatorStageLabel}=evaluate(operator);
const board=fs.readFileSync(path.join(root,"apps/console/lib/delivery-board.ts"),"utf8");
const start=board.indexOf("const completeStatuses=");
const end=board.indexOf("\nasync function allRows",start);
assert.ok(start>=0&&end>start);
const {chooseDeliveryLane,deliveryStatusLabel,deliveryLanes}=evaluate(board.slice(start,end));

test("no actionable decision does not assert product health or demand a click",()=>{
 const state=summarizeOperatorAttention([{status:"pending",actionable:false,projectName:"Antigo"}],[],false);
 assert.equal(state.count,0);
 assert.equal(state.kind,"clear");
 assert.match(state.description,/não significa/);
});
test("GitHub access and release decisions are different operator actions",()=>{
 const access=summarizeOperatorAttention([],[{projectName:"Agente SQL Financeiro",projectKey:"agente-sql-financeiro"}],true);
 assert.equal(access.kind,"access");
 assert.equal(access.count,1);
 assert.match(access.description,/não uma aprovação de publicação/);
 assert.match(access.description,/Agente SQL Financeiro/);
 const gate=summarizeOperatorAttention([{status:"pending",actionable:true,projectName:"Factory"}],
  [{projectName:"CRM",projectKey:"crm"}],true);
 assert.equal(gate.kind,"gate");
 assert.equal(gate.count,2);
 assert.equal(gate.humanGateCount,1);
 assert.equal(gate.accessCount,1);
});
test("optional GitHub App registration does not invent pending approval",()=>{
 const state=summarizeOperatorAttention([],[{projectName:"CRM",projectKey:"crm"}],false);
 assert.equal(state.count,0);
});
test("lifecycle stage describes history, not a running worker",()=>{
 assert.equal(operatorStageLabel("implementation"),"Construção e revisão");
 assert.equal(operatorStageLabel("operations"),"Operação");
 assert.equal(operatorStageLabel("unrecognized"),"Etapa não classificada");
});
test("all six Kanban lanes are distinct and cover every status explicitly",()=>{
 assert.deepEqual(Array.from(deliveryLanes,x=>x.key),["received","working","validating","waiting_human","blocked","closed"]);
 assert.equal(chooseDeliveryLane(["completed"],["completed"],false),"closed");
 assert.equal(chooseDeliveryLane(["cancelled"],["cancelled"],false),"closed");
 assert.equal(deliveryStatusLabel("closed",["cancelled"]),"Cancelado");
 assert.equal(chooseDeliveryLane(["created"],[],false),"received");
 assert.equal(chooseDeliveryLane(["running"],["implementing"],false),"working");
 assert.equal(chooseDeliveryLane(["work_unit_completed"],["preview_ready"],false),"validating");
 assert.equal(chooseDeliveryLane(["blocked"],["failed_gate"],false),"blocked");
 assert.equal(chooseDeliveryLane(["blocked"],["failed_gate"],true),"waiting_human");
});
test("block is never interpreted as permission to approve or publish",()=>{
 assert.equal(chooseDeliveryLane(["failed"],["completed"],false),"blocked");
 assert.match(deliveryStatusLabel("closed",["completed"]),/técnico/);
});
