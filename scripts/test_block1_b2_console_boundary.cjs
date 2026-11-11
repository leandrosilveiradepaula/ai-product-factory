/* B2 executable, credential-free negative tests against actual Console TS.
 * These tests NEVER certify signed JWTs, live tenants or production Auth.
 * Every privileged dependency is replaced by a throwing sentinel.
 */
"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const api=path.join(root,"apps/console/app/api");

const PUBLIC={
  "health/route.ts":["GET"],
  "integrations/github-app/callback/route.ts":["GET"],
  "integrations/github-app/webhook/route.ts":["POST"],
  "integrations/supabase/callback/route.ts":["GET"],
};
const PROTECTED={
  "configuration/cost-policy/route.ts":{POST:"admin"},
  "human-attention/route.ts":{GET:"operator"},
  "integrations/github-app/install/route.ts":{GET:"admin"},
  "integrations/github-app/register/route.ts":{GET:"admin"},
  "integrations/github-app/verify/route.ts":{GET:"safe_405",POST:"admin"},
  "integrations/supabase/connect/route.ts":{GET:"admin"},
  "projects/[key]/attachments/[attachmentId]/route.ts":{GET:"operator"},
  "projects/[key]/link-repository/route.ts":{POST:"admin"},
  "projects/wake-recovery/route.ts":{POST:"admin"},
};
const METHODS=["GET","POST","PUT","PATCH","DELETE"];
const denied="B2_DENIED_AUTH";
function filesAt(dir,relative=""){
  assert.ok(fs.statSync(dir).isDirectory());
  const rows=[];
  for(const item of fs.readdirSync(dir,{withFileTypes:true})){
    assert.ok(!item.isSymbolicLink(),"symlinked API entrypoint");
    if(item.isDirectory())rows.push(...filesAt(path.join(dir,item.name),path.posix.join(relative,item.name)));
    else if(item.isFile()&&item.name==="route.ts")rows.push(path.posix.join(relative,item.name));
  }
  return rows.sort();
}
function transpile(file){
  const source=fs.readFileSync(path.join(root,file),"utf8");
  const emitted=ts.transpileModule(source,{fileName:file,reportDiagnostics:true,
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,
      esModuleInterop:true,jsx:ts.JsxEmit.ReactJSX}});
  assert.deepEqual((emitted.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error),[],
    "TypeScript route must compile: "+file);
  return emitted.outputText;
}
function deniedRoute(rel){
  const calls={auth:[],effects:[]};
  const auth={
    requireConsoleOperator:async()=>{calls.auth.push("operator");throw Error(denied);},
    requireConsoleAdmin:async()=>{calls.auth.push("admin");throw Error(denied);},
  };
  const nextResponse={
    json:(value,opts={})=>new Response(JSON.stringify(value),{
      status:opts.status||200,headers:opts.headers||{}}),
    redirect:(url,status=307)=>new Response(null,{status,headers:{Location:String(url)}}),
  };
  const modules={
    "next/server":{NextResponse:nextResponse},
    "next/headers":{cookies:async()=>{calls.effects.push("cookies");throw Error("B2_SIDE_EFFECT");}},
    "next/navigation":{redirect:()=>{calls.effects.push("redirect");throw Error("B2_SIDE_EFFECT");}},
  };
  const exports={};
  const requireModule=(name)=>{
    if(name.endsWith("/auth-server")||name==="./auth-server")return auth;
    if(Object.hasOwn(modules,name))return modules[name];
    return new Proxy(Object.create(null),{get(_object,key){
      if(key==="__esModule")return true;
      calls.effects.push(name+":"+String(key));
      throw Error("B2_SIDE_EFFECT");
    }});
  };
  vm.runInNewContext(transpile("apps/console/app/api/"+rel),{
    exports,require:requireModule,URL,URLSearchParams,Request,Response,Headers,FormData,
    process:{env:{}},
    fetch:async()=>{calls.effects.push("fetch");throw Error("B2_SIDE_EFFECT");},
  },{timeout:5000,filename:rel});
  return{exports,calls};
}
function req(rel,method){
  return new Request("https://console.example.invalid/api/"+rel.replace(/\/route\.ts$/,""),{
    method,headers:{origin:"https://console.example.invalid",
      "content-type":"application/x-www-form-urlencoded"},
    ...(method==="GET"?{}:{body:"project=crm-infodive"})});
}
test("all current API entrypoints have an explicit security classification",()=>{
  const actual=filesAt(api);
  const expected=[...Object.keys(PUBLIC),...Object.keys(PROTECTED)].sort();
  assert.deepEqual(actual,expected,"new routes must be explicitly classified");
});
test("every protected handler denies before any privileged dependency",async(t)=>{
  for(const [rel,expected] of Object.entries(PROTECTED)){
    await t.test(rel,async()=>{
      const {exports,calls}=deniedRoute(rel);
      assert.deepEqual(Object.keys(exports).filter(x=>METHODS.includes(x)).sort(),
        Object.keys(expected).sort(),"unknown HTTP method cannot bypass inventory");
      for(const [method,role] of Object.entries(expected)){
        calls.auth.length=0;
        calls.effects.length=0;
        const handler=exports[method];
        assert.equal(typeof handler,"function");
        if(role==="safe_405"){
          const result=await handler(req(rel,method),{
            params:Promise.resolve({key:"crm-infodive"})});
          assert.equal(result.status,405,"non-mutation GET must be denied");
          assert.deepEqual(calls.auth,[]);
        }else{
          await assert.rejects(()=>Promise.resolve(handler(req(rel,method),{
            params:Promise.resolve({
              key:"crm-infodive",attachmentId:"11111111-1111-4111-8111-111111111111",
            })})),error=>error&&error.message===denied,
          "handler must propagate authorization denial");
          assert.deepEqual(calls.auth,[role],"guard role must be exact and called once");
        }
        assert.deepEqual(calls.effects,[],"backend/cookie/fetch used before denied guard");
      }
    });
  }
});
test("known public routes remain narrowly enumerated, never treated as authenticated",()=>{
  assert.deepEqual(Object.values(PUBLIC).flat().sort(),["GET","GET","GET","POST"]);
  assert.equal(Object.keys(PUBLIC).length,4);
});

function authServerFixture({token,operator=null,user=null,bootstrapEmail="",bootstrapResult=false,
                           hasConfig=true}={}){
  const calls={operator:0,user:0,rpc:0,redirects:[]};
  const exports={};
  const modules={
    "next/headers":{cookies:async()=>({get:name=>name==="factory_access_token"&&token
      ?{value:token}:undefined,set:()=>{throw Error("B2_COOKIE_WRITE")},
      delete:()=>{throw Error("B2_COOKIE_WRITE")}})},
    "next/navigation":{redirect:target=>{calls.redirects.push(target);
      throw Error("B2_REDIRECT:"+target);}},
    "./auth-api":{
      getAuthUser:async()=>{calls.user++;return user;},
      getConsoleOperator:async()=>{calls.operator++;return operator;},
    },
    "./supabase-server":{getSupabaseServerConfig:()=>hasConfig
      ?{url:"https://control.example.invalid",headers:{apikey:"test-fixture-only"}}:null},
  };
  vm.runInNewContext(transpile("apps/console/lib/auth-server.ts"),{
    exports,require:name=>{assert.ok(Object.hasOwn(modules,name),"unknown auth dependency");return modules[name];},
    process:{env:{NODE_ENV:"test",FACTORY_BOOTSTRAP_ADMIN_EMAIL:bootstrapEmail}},
    fetch:async(url,opts)=>{
      calls.rpc++;
      assert.equal(url,"https://control.example.invalid/rest/v1/rpc/factory_bootstrap_console_admin");
      assert.equal(opts.method,"POST");
      return{ok:true,json:async()=>bootstrapResult};
    },
  },{timeout:5000});
  return{...exports,calls};
}
test("missing cookie rejects before operator lookup or privileged RPC",async()=>{
  const f=authServerFixture({bootstrapEmail:"owner@example.invalid"});
  await assert.rejects(()=>f.requireConsoleOperator(),/B2_REDIRECT:\/login/);
  assert.equal(f.calls.operator,0);assert.equal(f.calls.user,0);assert.equal(f.calls.rpc,0);
});
test("unknown or inactive identities cannot become operators or bootstrap by email alone",async()=>{
  const cases=[
    {token:"synthetic",user:null,bootstrapEmail:"owner@example.invalid"},
    {token:"synthetic",user:{id:"11111111-1111-4111-8111-111111111111",email:"other@example.invalid"},
      bootstrapEmail:"owner@example.invalid"},
    {token:"synthetic",user:{id:"11111111-1111-4111-8111-111111111111",email:"owner@example.invalid"},
      bootstrapEmail:""},
    {token:"synthetic",user:{id:"11111111-1111-4111-8111-111111111111",email:"owner@example.invalid"},
      bootstrapEmail:"owner@example.invalid",hasConfig:false},
  ];
  for(const cfg of cases){
    const f=authServerFixture(cfg);
    await assert.rejects(()=>f.requireConsoleOperator(),/B2_REDIRECT:\/unauthorized/);
    assert.equal(f.calls.rpc,0,"bootstrap must not contact privileged backend");
  }
});
test("operator cannot perform administrator action; valid administrator may",async()=>{
  const operator={userId:"11111111-1111-4111-8111-111111111111",role:"operator"};
  const f=authServerFixture({token:"synthetic",operator});
  assert.equal((await f.requireConsoleOperator()).role,"operator");
  await assert.rejects(()=>f.requireConsoleAdmin(),/B2_REDIRECT:\/unauthorized/);
  assert.equal(f.calls.rpc,0);
  const admin=authServerFixture({token:"synthetic",operator:{...operator,role:"admin"}});
  assert.equal((await admin.requireConsoleAdmin()).role,"admin");
  assert.equal(admin.calls.rpc,0);
});
test("bootstrap path relies on existing privileged RPC, not a forged operator role",async()=>{
  const user={id:"11111111-1111-4111-8111-111111111111",email:"owner@example.invalid"};
  const blocked=authServerFixture({token:"synthetic",user,bootstrapEmail:"owner@example.invalid"});
  await assert.rejects(()=>blocked.requireConsoleAdmin(),/B2_REDIRECT:\/unauthorized/);
  assert.equal(blocked.calls.rpc,1);
  const allowed=authServerFixture({token:"synthetic",user,bootstrapEmail:"owner@example.invalid",
                                  bootstrapResult:true});
  assert.equal((await allowed.requireConsoleAdmin()).role,"admin");
  assert.equal(allowed.calls.rpc,1);
});

test("B2 intake pages and server action deny a signed-in non-operator before rendering or processing input",async()=>{
 const sources=[
  {path:"apps/console/app/projects/new/page.tsx",exportName:"default"},
  {path:"apps/console/app/projects/new/review/page.tsx",exportName:"default"},
  {path:"apps/console/app/projects/new/actions.ts",exportName:"submitIntake"},
 ];
 for(const item of sources){
  const calls={auth:0,effects:[]};
  const modules={
   "../../../lib/auth-server":{requireConsoleOperator:async()=>{calls.auth++;throw Error(denied);}},
   "../../../../lib/auth-server":{requireConsoleOperator:async()=>{calls.auth++;throw Error(denied);}},
   "next/navigation":{redirect:()=>{calls.effects.push("redirect");throw Error("UNEXPECTED_REDIRECT");}},
   "node:crypto":{randomUUID:()=>{calls.effects.push("randomUUID");throw Error("UNEXPECTED_RANDOM");}},
  };
  const requireModule=name=>{
   if(Object.hasOwn(modules,name))return modules[name];
   return new Proxy(Object.create(null),{get(_object,key){
    if(key==="__esModule")return true;
    calls.effects.push(name+":"+String(key));
    throw Error("B2_PRIVILEGED_DEPENDENCY_ACCESSED");
   }});
  };
  const exports={};
  vm.runInNewContext(transpile(item.path),{
   exports,require:requireModule,URL,URLSearchParams,Request,Response,Headers,FormData,
   process:{env:{}},
   fetch:async()=>{calls.effects.push("fetch");throw Error("B2_PRIVILEGED_FETCH");},
  },{timeout:5000,filename:item.path});
  const handler=exports[item.exportName];
  assert.equal(typeof handler,"function",item.path+" must export the guarded entrypoint");
  const args=item.exportName==="submitIntake"
   ?[{errors:{}},new FormData()]
   :[{searchParams:Promise.resolve({intake:"private-user-data"})}];
  await assert.rejects(()=>Promise.resolve(handler(...args)),error=>error?.message===denied,
   item.path+" must deny non-operator before any data processing");
  assert.equal(calls.auth,1,item.path+" must check allowlist exactly once");
  assert.deepEqual(calls.effects,[],item.path+" must not access privileged dependencies");
 }
});
