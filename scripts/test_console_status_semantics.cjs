/* Behavior tests of the actual TSX StatusPill, not a copied mock.
   Runs under Console validation with npm-ci-pinned TypeScript. No secrets,
   network calls, database writes, paid LLMs or test-only production UI. */
"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const source=fs.readFileSync(path.join(root,"apps/console/app/ui.tsx"),"utf8");
const emitted=ts.transpileModule(source,{
  fileName:"ui.tsx",
  compilerOptions:{
    module:ts.ModuleKind.CommonJS,
    target:ts.ScriptTarget.ES2022,
    jsx:ts.JsxEmit.ReactJSX,
    esModuleInterop:true,
  },
  reportDiagnostics:true,
});
assert.equal((emitted.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
const jsx=(type,props)=>({type,props});
const exportsObject={};
vm.runInNewContext(emitted.outputText,{
  exports:exportsObject,
  require(id){
    if(id==="react/jsx-runtime")return {jsx,jsxs:jsx,Fragment:"fragment"};
    if(id==="next/link")return {__esModule:true,default:()=>null};
    throw new Error("Unexpected module import in offline status contract");
  },
},{timeout:10000});
const {statusTone,humanizeStatus,StatusPill}=exportsObject;
assert.equal(typeof statusTone,"function");
assert.equal(typeof StatusPill,"function");

test("verified success is an explicit allowlist, not a substring",()=>{
  for(const value of ["passed","success","succeeded","complete","completed",
    "merged","released","ready","verified","healthy","active","approved","integrated"]){
    assert.equal(statusTone(value),"success",value);
  }
  for(const value of ["successful_but_unverified","inactive_but_ready",
    "unhealthy_but_active","not_ready","not_verified","unverified",
    "not_released","unknown_ready","not_passed","provider_status_success_unverified"]){
    assert.notEqual(statusTone(value),"success",value);
  }
});

test("negative, incomplete and ambiguous states cannot render green",()=>{
  const cases=[
    ["inactive",""],["unhealthy","danger"],["not_ready","warning"],
    ["not-ready","warning"],[" NOT READY ","warning"],
    ["not_verified","warning"],["unverified","warning"],
    ["not_released","warning"],["not_assessed","warning"],
    ["not_reported","warning"],["not_applicable",""],
    ["provider_reported_ready","warning"],
    ["provider_status_success_unverified","warning"],
    ["failed_but_ready","danger"],["ci_failed","danger"],
    ["credit_balance_exhausted","danger"],["budget_exhausted","danger"],
    ["error","danger"],["blocked","danger"],["rejected","danger"],
    ["unknown","warning"],["skipped",""],["disabled",""],
    ["cancelled",""],["stopped",""],["paused","warning"],
    ["stalled_ci","warning"],["review_ready","warning"],
    ["preview_ready","accent"],["running","accent"],
    ["in_progress","accent"],["routing","accent"],
    ["some_future_status",""],["",""],["success#unverified",""],
  ];
  for(const [value,expected] of cases){
    assert.equal(statusTone(value),expected,value);
    const pill=StatusPill({status:value});
    assert.equal(pill.props.className,expected?"pill "+expected:"pill",value);
  }
});

test("statuses remain readable in Brazilian Portuguese",()=>{
  for(const [value,expected] of [
    ["inactive","inativo"],
    ["unhealthy","não saudável"],
    ["not_ready","não pronto"],
    ["not_verified","não verificado"],
    ["unverified","não verificado"],
    ["not_assessed","não avaliado"],
    ["not_reported","não informado"],
    ["not_applicable","não aplicável"],
    ["provider_status_success_unverified","sucesso do provedor não verificado"],
    ["credit_balance_exhausted","créditos esgotados"],
    ["failed","falhou"],
    ["approved","aprovado"],
  ]){
    assert.equal(humanizeStatus(value),expected,value);
    assert.equal(StatusPill({status:value}).props.children,expected,value);
  }
});

test("a forced green tone cannot hide failure, uncertainty or inactivity",()=>{
  for(const [status,expected] of [
    ["failed","danger"],
    ["unhealthy","danger"],
    ["not_ready","warning"],
    ["unverified","warning"],
    ["not_applicable",""],
    ["inactive",""],
  ]){
    const result=StatusPill({status,tone:"success"});
    assert.equal(result.props.className,expected?"pill "+expected:"pill",status);
  }
  assert.equal(StatusPill({status:"passed",tone:"success"}).props.className,"pill success");
});

test("custom visible labels preserve underlying state in accessible name",()=>{
  const blocked=StatusPill({status:"not_ready",label:"Revisar evidências"});
  assert.equal(blocked.props.className,"pill warning");
  assert.equal(blocked.props.children,"Revisar evidências");
  assert.equal(blocked.props["aria-label"],"não pronto: Revisar evidências");
  const healthy=StatusPill({status:"healthy",label:"nenhuma pendência"});
  assert.equal(healthy.props.className,"pill success");
  assert.equal(healthy.props["aria-label"],"saudável: nenhuma pendência");
  const ordinary=StatusPill({status:"failed"});
  assert.equal(ordinary.props["aria-label"],undefined);
  const richLabel=jsx("strong",{children:"Atenção"});
  assert.equal(StatusPill({status:"pending",label:richLabel}).props.children,richLabel);
});
