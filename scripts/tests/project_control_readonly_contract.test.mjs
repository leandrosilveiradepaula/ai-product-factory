import test from "node:test";
import assert from "node:assert/strict";
import {LIFECYCLE_COMMANDS,validateProjectLifecycleReadOnly} from "../project_control_readonly_contract.mjs";
const key="example-project",labels={start:"Iniciar projeto",pause:"Pausar",stop:"Parar",resume:"Retomar",restart:"Reiniciar"};
const makeForm=command=>({command,projectKey:key,version:"4",commandId:"",label:labels[command]});
const evaluate=(state,forms)=>validateProjectLifecycleReadOnly({heading:"Execução do projeto: "+state,forms,expectedProjectKey:key});
for(const [state,commands] of Object.entries(LIFECYCLE_COMMANDS)){
 test("authorized controls with unallocated ID: "+state,()=>{
  const result=evaluate(state,commands.map(makeForm));
  assert.deepEqual(result.availableCommands,[...commands].sort());
  assert.equal(result.commandIdAllocatedBeforeSubmit,false);
 });
}
test("unknown/invalid state and commands fail closed",()=>{
 assert.throws(()=>evaluate("Pausando",[]),/command\/state mismatch/);
 assert.throws(()=>evaluate("Pausando",[makeForm("resume")]),/command\/state mismatch/);
 assert.throws(()=>evaluate("Em execução",[makeForm("restart")]),/command\/state mismatch/);
 assert.throws(()=>evaluate("Concluído",[]),/unknown project execution state/);
});
test("bad identity, preallocated UUID, version and label fail closed",()=>{
 const pause=makeForm("pause"),stop=makeForm("stop");
 for(const bad of [{...pause,projectKey:"other"},{...pause,version:"4.1"},{...pause,version:"9007199254740993"},
   {...pause,commandId:"00000000-0000-4000-8000-000000000001"},
   {...pause,commandId:"not-a-uuid"},{...pause,commandId:undefined},{...pause,label:"Iniciar projeto"}])
   assert.throws(()=>evaluate("Em execução",[bad,stop]),/invalid project\/version\/command\/idempotency identity/);
});
test("blank forms may share an empty ID but not conflicting versions",()=>{
 const pause=makeForm("pause"),stop=makeForm("stop");
 assert.deepEqual(evaluate("Em execução",[pause,stop]).availableCommands,["pause","stop"]);
 assert.throws(()=>evaluate("Em execução",[pause,{...stop,version:"5"}]),/inconsistent/);
});

// The exact user-facing states and conditional controls cannot drift apart.
const v2=(controlState,workObservation,recoveryEligibility,state,commands)=>
 validateProjectLifecycleReadOnly({
  heading:"Execução do projeto: "+state, forms:commands.map(makeForm),
  expectedProjectKey:key,controlState,workObservation,recoveryEligibility,
 });
for(const [observation,label] of Object.entries({
 running:"Desenvolvendo",recorded:"Pedido na fila",idle:"Sem execução ativa",unavailable:"Execução não verificável",
})){
 test("V2 running control distinguishes "+observation,()=>{
  assert.deepEqual(v2("running",observation,"not_eligible",label,["pause","stop"]).availableCommands,["pause","stop"]);
  assert.throws(()=>v2("running",observation,"not_eligible",label,["pause","stop","restart"]),/command\/state mismatch/);
 });
}
test("V2 restart requires exact backend eligibility, not a label guess",()=>{
 const result=v2("running","idle","eligible","Sem execução ativa",["pause","stop","restart"]);
 assert.deepEqual(result.availableCommands,["pause","restart","stop"]);
 assert.equal(result.recoveryEligibility,"eligible");
 assert.throws(()=>v2("running","idle","eligible","Sem execução ativa",["pause","stop"]),/command\/state mismatch/);
 assert.throws(()=>v2("running","idle","unavailable","Sem execução ativa",["pause","stop","restart"]),/command\/state mismatch/);
 assert.throws(()=>v2("running","idle","not_eligible","Desenvolvendo",["pause","stop"]),/observation\/label mismatch/);
 assert.throws(()=>v2("running",null,"not_eligible","Sem execução ativa",["pause","stop"]),/invalid lifecycle observation/);
 assert.throws(()=>v2("paused","idle","eligible","Pausado",["resume","stop"]),/cannot be eligible/);
 assert.deepEqual(v2("stopped","idle","not_eligible","Parado",["restart"]).availableCommands,["restart"]);
});
