"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const source=fs.readFileSync(path.join(root,"apps/console/lib/factory-certification.ts"),"utf8");
const compiled=ts.transpileModule(source,{compilerOptions:{
 module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
},reportDiagnostics:true});
assert.equal((compiled.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
const output={};
vm.runInNewContext(compiled.outputText,{
 exports:output,require(id){
  if(id==="./auth-server")return{requireConsoleOperator:async()=>{}};
  if(id==="./supabase-server")return{getSupabaseServerConfig:()=>null};
  throw Error("unexpected import");
 }
},{timeout:5000});
const classify=output.classifyFactoryCertificate;
assert.equal(typeof classify,"function");
const SHA="a".repeat(40);
const coverage={
 documentation:["setup_configuration","operations","release_rollback"],
 functional_completeness:["requirements_inventory","mock_noop_demo_inventory","critical_journeys"],
 observability_operations:["health","traceability","recovery_alerting"],
 product_experience:["surface_inventory","responsive","accessibility","states"],
 security:["authn_authz","data_access_boundaries","secrets_dependencies"],
 test_strategy:["unit_integration","critical_e2e","regression_gates"],
};
function cert(){
 const criteria={};
 for(const [domain,items] of Object.entries(coverage)){
  criteria[domain]=Object.fromEntries(items.map(key=>[key,{status:"passed"}]));
 }
 return [{assessed_commit:SHA,state:"persisted",persisted_at:"2026-11-23T21:29:27Z",is_current:true,
  report:{assessed_commit:SHA,assessment:{status:"passed",ready:true},criteria}}];
}
const state=(sha,rows)=>classify(sha,rows).state;
test("only independently persisted 19/19 on exact current HEAD is certified",()=>{
 const result=classify(SHA,cert());
 assert.equal(result.state,"certified");
 assert.equal(result.passed,19);
 assert.equal(result.total,19);
 assert.equal(result.sha,SHA);
 assert.equal(result.persistedAt,"2026-11-23T21:29:27Z");
});
test("an old is_current=true row cannot certify a new main",()=>{
 assert.equal(state("b".repeat(40),cert()),"not_certified");
 assert.equal(state(SHA,[]),"not_certified");
});
test("missing, extra and partial criteria fail closed",()=>{
 const a=cert();delete a[0].report.criteria.documentation.setup_configuration;
 assert.equal(state(SHA,a),"not_certified");
 const b=cert();b[0].report.criteria.security.extra={status:"passed"};
 assert.equal(state(SHA,b),"not_certified");
 const c=cert();c[0].report.criteria.observability_operations.health.status="partial";
 assert.equal(state(SHA,c),"not_certified");
});
test("assessment, provenance, time and integrity are mandatory",()=>{
 for(const modify of [
  x=>x[0].report.assessment.ready=false,
  x=>x[0].report.assessment.status="not_ready",
  x=>x[0].report.assessed_commit="b".repeat(40),
  x=>x[0].state="reserved",
  x=>x[0].persisted_at="not-a-date",
 ]){
  const row=cert();modify(row);
  assert.equal(state(SHA,row),"not_certified");
 }
 assert.equal(state(null,cert()),"unavailable");
 assert.equal(state(SHA,{}),"unavailable");
});
test("Console must not confuse administrative stage, approval and integration",()=>{
 const page=fs.readFileSync(path.join(root,"apps/console/app/page.tsx"),"utf8");
 const shell=fs.readFileSync(path.join(root,"apps/console/app/shell.tsx"),"utf8");
 const route=fs.readFileSync(path.join(root,"apps/console/app/api/human-attention/route.ts"),"utf8");
 assert.match(page,/getCurrentFactoryCertificate\(/);
 assert.match(page,/factoryCert.state==="certified"/);
 assert.match(page,/Etapa do cadastro/);
 assert.match(page,/não é certificação/);
 assert.match(page,/heading:"Escolha um produto para acompanhar"/);
 assert.match(page,/const hasIncident=incidents.length>0/);
 assert.match(page,/!requiresDecision&&!hasIncident/);
 assert.doesNotMatch(page,/:hasIncident\s*\?/);
 assert.match(page,/href:"\/projects",label:"Abrir projetos"/);
 assert.match(shell,/attention\.pendingHumanGateCount>0/);
 assert.match(shell,/pendingIntegrationActionCount/);
 assert.match(shell,/configuração de integração/);
 assert.doesNotMatch(shell,/\{attention\.count\} \{attention\.count===1\?"decisão pendente"/);
 assert.match(route,/pendingHumanGateCount,pendingIntegrationActionCount,projects/);
});
