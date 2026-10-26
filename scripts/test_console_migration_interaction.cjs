/* Actual TS/TSX modules tested with controlled hooks and offline REST data.
 * No production migration, browser account, external fetch or paid model. */
"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const jsx=(type,props,key)=>({type,props:props||{},key});
function load(file,imports={},globals={}){
  const source=fs.readFileSync(path.join(root,file),"utf8");
  const out=ts.transpileModule(source,{fileName:file,reportDiagnostics:true,
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
      jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}});
  assert.equal((out.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  const exports={};
  vm.runInNewContext(out.outputText,{exports,require(name){
    if(name==="react/jsx-runtime")return{jsx,jsxs:jsx,Fragment:"fragment"};
    if(Object.hasOwn(imports,name))return imports[name];
    throw new Error("unexpected import "+name);
  },...globals},{filename:file,timeout:10000});
  return exports;
}
function visit(tree,callback){
  if(Array.isArray(tree)){for(const node of tree)visit(node,callback);return;}
  if(!tree||typeof tree!=="object"||!("type" in tree))return;
  callback(tree);visit(tree.props.children,callback);
}
function find(tree,predicate){let result;visit(tree,node=>{if(!result&&predicate(node))result=node;});return result;}
function textOf(node){
  if(typeof node==="string"||typeof node==="number")return String(node);
  if(!node||typeof node!=="object")return "";
  return Array.isArray(node)?node.map(textOf).join(" "):textOf(node.props?.children);
}
const pending={value:false};
const {GateDecisionPending}=load("apps/console/app/gates/gate-decision-form.tsx",
  {"react-dom":{useFormStatus:()=>({pending:pending.value})}});
const busyMessage="Aplicando a migration e verificando o histórico no Supabase. Não envie a operação novamente.";
function form(){return GateDecisionPending({pendingMessage:busyMessage,children:jsx("button",{type:"submit",children:"Aplicar migration"})});}
test("real pending TSX renders busy, disables fieldset and announces migration",()=>{
  pending.value=false;
  assert.equal(form().props.disabled,false);
  assert.equal(find(form(),n=>n.props.role==="status"),undefined);
  pending.value=true;
  const ui=form();
  assert.equal(ui.type,"fieldset");
  assert.equal(ui.props.disabled,true);
  assert.equal(ui.props["aria-busy"],true);
  const live=find(ui,n=>n.props.role==="status");
  assert.ok(live);
  assert.equal(live.props["aria-live"],"polite");
  assert.ok(textOf(live).includes(busyMessage));
  assert.ok(find(ui,n=>n.type==="button"));
  pending.value=false;
  assert.equal(find(form(),n=>n.props.role==="status"),undefined);
});
const GATE="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa";
const FOREIGN="bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb";
const RUN="cccccccc-cccc-4ccc-cccc-cccccccccccc";
const SHA="f".repeat(40);
const NAME="20261026010101_controlled_migration";
const makeEvent=(kind="human_migration.console_apply_succeeded")=>({
  event_type:kind,payload:{gate_id:GATE,candidate_commit:SHA,migration_name:NAME,
    source_integrity:"exact_sql_verified"}
});
function reader(options={}){
  const gate={id:GATE,run_id:RUN,status:"approved",...options.gate};
  const run={id:RUN,candidate_commit:SHA,metadata:{requested_action:"apply_control_plane_migration",migration_name:NAME},...options.run};
  const events=options.events===undefined?[makeEvent()]:options.events;
  const calls=[];
  const fetch=async(url,init)=>{
    calls.push({url,init});
    assert.ok(url.startsWith("https://control.invalid/rest/v1/"));
    assert.equal(init.cache,"no-store");
    assert.equal(init.headers.apikey,"fixture-only");
    if(options.networkFailure)throw new Error("offline network failure");
    const stage=url.includes("factory_human_gates?")?"gates":
      url.includes("factory_runs?")?"runs":url.includes("factory_audit_events?")?"events":null;
    assert.ok(stage,"unknown REST endpoint");
    if(stage===options.httpFailure)return{ok:false,status:503};
    return{ok:true,json:async()=>{
      if(stage===options.invalidJson)throw Error("invalid JSON");
      return stage==="gates"?[gate]:stage==="runs"?[run]:events;
    }};
  };
  let authCount=0;
  const {getVerifiedMigrationOutcome}=load("apps/console/lib/migration-feedback.ts",{
    "./auth-server":{requireConsoleOperator:async()=>{
      authCount++;if(options.denied)throw Error("operator_required");
    }},
    "./supabase-server":{getSupabaseServerConfig:()=>options.noConfig?null:{
      url:"https://control.invalid",headers:{apikey:"fixture-only"}
    }}
  },{fetch});
  return{get:getVerifiedMigrationOutcome,calls,get authCount(){return authCount;}};
}
test("server-only outcome requires approved gate, exact run, SHA and verified audit",async()=>{
  const subject=reader();
  const outcome=await subject.get(GATE);
  assert.equal(outcome?.migrationName,NAME);
  assert.equal(outcome?.alreadyApplied,false);
  assert.equal(subject.authCount,1);
  assert.equal(subject.calls.length,3);
  assert.ok(subject.calls[0].url.includes("id=eq."+GATE));
  assert.ok(subject.calls[1].url.includes("id=eq."+RUN));
  assert.ok(subject.calls[2].url.includes("run_id=eq."+RUN));
});
test("idempotent exact SQL receipt is explicitly labeled already applied",async()=>{
  const result=await reader({events:[makeEvent("human_migration.console_already_applied")]}).get(GATE);
  assert.equal(result?.alreadyApplied,true);
});
test("forged gate, old audit, bad integrity and network errors fail closed",async()=>{
  const negative=[
    ["no event",{events:[]}],
    ["other gate",{events:[{...makeEvent(),payload:{...makeEvent().payload,gate_id:FOREIGN}}]}],
    ["old unbound event",{events:[{...makeEvent(),payload:{candidate_commit:SHA,migration_name:NAME}}]}],
    ["wrong SHA",{events:[{...makeEvent(),payload:{...makeEvent().payload,candidate_commit:"0".repeat(40)}}]}],
    ["wrong migration",{events:[{...makeEvent(),payload:{...makeEvent().payload,migration_name:"other"}}]}],
    ["unverified integrity",{events:[{...makeEvent(),payload:{...makeEvent().payload,source_integrity:"unverified"}}]}],
    ["failed event",{events:[makeEvent("human_migration.console_apply_failed")]}],
    ["pending gate",{gate:{status:"pending"}}],
    ["different returned gate",{gate:{id:FOREIGN}}],
    ["different returned run",{run:{id:FOREIGN}}],
    ["other action",{run:{metadata:{requested_action:"release",migration_name:NAME}}}],
    ["different metadata name",{run:{metadata:{requested_action:"apply_control_plane_migration",migration_name:"other"}}}],
    ["missing config",{noConfig:true}],
    ["network unavailable",{networkFailure:true}],
    ["invalid gate response",{invalidJson:"gates"}],
    ["invalid run response",{invalidJson:"runs"}],
    ["invalid audit response",{invalidJson:"events"}],
    ["HTTP gate failure",{httpFailure:"gates"}],
    ["HTTP run failure",{httpFailure:"runs"}],
    ["HTTP audit failure",{httpFailure:"events"}],
  ];
  for(const [name,opts] of negative)assert.equal(await reader(opts).get(GATE),null,name);
  const fake=reader();
  assert.equal(await fake.get("not-a-uuid"),null);
  assert.equal(fake.calls.length,0);
});
test("operator authentication is mandatory before reading proof",async()=>{
  const subject=reader({denied:true});
  await assert.rejects(subject.get(GATE),/operator_required/);
  assert.equal(subject.calls.length,0);
});
function bannerHarness(href){
  let visible=true;
  const effects=[];
  const window={location:{href},history:{state:{example:1},replaceState:(state,_title,next)=>{
    window.location.href=new URL(next,window.location.href).toString();
    window.history.state=state;
  }}};
  const {GateActionSuccessBanner}=load("apps/console/app/gates/gate-action-success-banner.tsx",{
    react:{useState:()=>[visible,value=>{visible=value}],useEffect:fn=>effects.push(fn)}
  },{window,URL});
  return{render:props=>GateActionSuccessBanner(props),effects,window};
}
test("real TSX success banner clears lookup URL and supports dismissal",async()=>{
  const outcome=await reader().get(GATE);
  assert.ok(outcome);
  const view=bannerHarness("https://console.invalid/gates?migration_result="+GATE+"&tab=pending#focus");
  const node=view.render(outcome);
  assert.equal(node.props.role,"status");
  assert.equal(node.props["aria-live"],"polite");
  assert.ok(textOf(node).includes("Migration aplicada e confirmada no Supabase"));
  assert.ok(textOf(node).includes(NAME));
  for(const effect of view.effects)effect();
  const url=new URL(view.window.location.href);
  assert.equal(url.searchParams.has("migration_result"),false);
  assert.equal(url.searchParams.get("tab"),"pending");
  assert.equal(url.hash,"#focus");
  find(node,n=>n.type==="button"&&n.props["aria-label"]).props.onClick();
  assert.equal(view.render(outcome),null);
});
test("controlled delayed operation stays busy then shows only verified outcome",async()=>{
  let release;
  const controlled=new Promise(resolve=>{release=resolve;});
  pending.value=true;
  assert.equal(form().props.disabled,true);
  const work=controlled.then(async()=>reader().get(GATE));
  let resolved=false;work.then(()=>{resolved=true;});
  await Promise.resolve();
  assert.equal(resolved,false);
  assert.equal(form().props["aria-busy"],true);
  release();
  const outcome=await work;
  pending.value=false;
  assert.equal(form().props.disabled,false);
  assert.equal(bannerHarness("https://console.invalid/gates").render(outcome).props.role,"status");
  const forged=await reader({events:[]}).get(GATE);
  assert.equal(forged,null,"no verified audit must never render success");
});
