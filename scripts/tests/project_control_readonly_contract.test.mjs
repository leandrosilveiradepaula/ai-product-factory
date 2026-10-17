import test from "node:test";
import assert from "node:assert/strict";
import {LIFECYCLE_COMMANDS, validateProjectLifecycleReadOnly} from "../project_control_readonly_contract.mjs";

const key="example-project";
const labels={start:"Iniciar projeto",pause:"Pausar",stop:"Parar",resume:"Retomar",restart:"Reiniciar"};
const id=n=>"00000000-0000-4000-8000-"+String(n).padStart(12,"0");
const makeForm=(command,n)=>({command,projectKey:key,version:"4",commandId:id(n),label:labels[command]});
const evaluate=(label,forms)=>validateProjectLifecycleReadOnly({
  heading:"Execução do projeto: "+label,forms,expectedProjectKey:key,
});

for(const [state,commands] of Object.entries(LIFECYCLE_COMMANDS)){
  test("state-bound authorized controls: "+state,()=>{
    const forms=commands.map((command,i)=>makeForm(command,i+1));
    assert.deepEqual(evaluate(state,forms).availableCommands,[...commands].sort());
  });
}
test("pausing requires STOP and cannot resume",()=>{
  assert.throws(()=>evaluate("Pausando",[]),/command\/state mismatch/);
  assert.throws(()=>evaluate("Pausando",[makeForm("resume",1)]),/command\/state mismatch/);
});
test("running cannot expose restart even though it is valid elsewhere",()=>{
  assert.throws(()=>evaluate("Em execução",[makeForm("restart",1)]),/command\/state mismatch/);
});
test("unknown and missing states fail closed",()=>{
  assert.throws(()=>evaluate("Concluído",[]),/unknown project execution state/);
  assert.throws(()=>validateProjectLifecycleReadOnly({heading:"No state",forms:[],expectedProjectKey:key}),/unknown project execution state/);
});
test("project, version, UUID and label must be canonical",()=>{
  const pause=makeForm("pause",1), stop=makeForm("stop",2);
  for(const bad of [
    {...pause,projectKey:"other"}, {...pause,version:"4.1"},
    {...pause,version:"9007199254740993"}, {...pause,commandId:"not-a-uuid"},
    {...pause,label:"Iniciar projeto"}
  ]){
    assert.throws(()=>evaluate("Em execução",[bad,stop]),/invalid project\/version\/command\/idempotency identity/);
  }
});
test("duplicate UUID and inconsistent versions fail closed",()=>{
  const pause=makeForm("pause",1);
  assert.throws(()=>evaluate("Em execução",[pause,{...makeForm("stop",2),commandId:pause.commandId}]),/identity/);
  assert.throws(()=>evaluate("Em execução",[pause,{...makeForm("stop",2),version:"5"}]),/inconsistent/);
});
