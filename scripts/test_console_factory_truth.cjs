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
 assert.match(page,/Última etapa registrada/);
 assert.match(page,/funcionamento do produto não comprovado nesta tela/);
 assert.match(page,/p.key==="ai-product-factory"&&factoryCert.state==="certified"/);
 assert.match(page,/Prontidão da Factory verificada/);
 assert.match(page,/portfolioProjectControlLabel\(p\)/);
 assert.match(page,/portfolio\.historicalFailureRecords/);
 assert.doesNotMatch(page,/health\.failedRuns\+health\.blockedRuns/);
 assert.doesNotMatch(page,/Onde começar|Escolha um produto para acompanhar|overviewAction/);
 assert.match(page,/\{requiresDecision\?<section className="homeFocus warning"/);
 assert.match(page,/id="home-decisions-heading"/);
 assert.match(page,/<ActionLink href="\/gates" variant="primary">Revisar decisões/);
 assert.match(page,/const hasIncident=pendingProjects\.length>0\|\|health\.expiredLeases>0\|\|unverifiedControls\.length>0/);
 assert.match(page,/const pendingProjects=trackedProjects\.filter\(p=>p\.pendingTasks\.length>0\)/);
 assert.match(page,/const blocked=portfolio\.trackedPendingTasks/);
 assert.match(page,/Projetos parados ou inativos/);
 assert.match(page,/Tarefas a reconciliar/);
 assert.doesNotMatch(page,/attentionCard danger/);
 assert.match(page,/!requiresDecision&&!hasIncident/);
 assert.doesNotMatch(page,/:hasIncident\s*\?/);
 assert.doesNotMatch(page,/Abrir projetos/);
 assert.equal((page.match(/href="\/projects\/new"/g)||[]).length,1);
 assert.match(page,/trackedProjects.length===0\?\s*<div className="homeEmptyProject"/);
 assert.match(shell,/attention\.pendingHumanGateCount>0/);
 assert.match(shell,/pendingIntegrationActionCount/);
 assert.match(shell,/configuração de integração/);
 assert.doesNotMatch(shell,/\{attention\.count\} \{attention\.count===1\?"decisão pendente"/);
 assert.match(route,/pendingHumanGateCount,pendingIntegrationActionCount,projects/);
});

test("approval inbox never counts GitHub integration setup as a human release gate",()=>{
 const pathToHelper=path.join(root,"apps/console/lib/gate-attention.ts");
 const helperSource=fs.readFileSync(pathToHelper,"utf8");
 const output=ts.transpileModule(helperSource,{compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
 },reportDiagnostics:true});
 assert.equal((output.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
 const helper={};
 vm.runInNewContext(output.outputText,{exports:helper},{timeout:5000});
 const count=helper.countGateAttention;
 assert.equal(typeof count,"function");
 const cases=[
  {human:0,install:1,configured:true,expectedHuman:0,expectedIntegration:1},
  {human:2,install:0,configured:true,expectedHuman:2,expectedIntegration:0},
  {human:0,install:4,configured:false,expectedHuman:0,expectedIntegration:1},
  {human:3,install:2,configured:true,expectedHuman:3,expectedIntegration:2},
 ];
 for(const row of cases){
  const result=count(row.human,row.install,row.configured);
  assert.equal(result.pendingHumanGateCount,row.expectedHuman);
  assert.equal(result.pendingIntegrationActionCount,row.expectedIntegration);
 }
 for(const args of [[-1,1,true],[0,-1,true],[1.5,0,true],[0,0,null]]){
  assert.throws(()=>count(...args),/Invalid gate-attention counters/);
 }
 const gates=fs.readFileSync(path.join(root,"apps/console/app/gates/page.tsx"),"utf8");
 const api=fs.readFileSync(path.join(root,"apps/console/app/api/human-attention/route.ts"),"utf8");
 assert.match(gates,/countGateAttention\(pending\.length,githubInstallActions\.length,githubApp\.configured\)/);
 assert.match(gates,/pendingHumanGateCount>0\?"attention":"healthy"/);
 assert.match(gates,/0 decisões humanas pendentes/);
 assert.match(gates,/Configurações de integração/);
 assert.match(gates,/pendingIntegrationActionCount>0/);
 assert.match(gates,/className="card gateCard integration"/);
 assert.match(gates,/pending\.length===0\?<div className="humanGateEmpty"/);
 assert.doesNotMatch(gates,/const pendingCount=/);
 assert.doesNotMatch(gates,/críticas pendentes/);
 assert.match(api,/const pendingHumanGateCount=pending\.length/);
 assert.match(api,/const pendingIntegrationActionCount=githubApp\.configured\?installActions\.length:1/);
 assert.match(api,/pendingHumanGateCount,pendingIntegrationActionCount,projects/);
});
