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
