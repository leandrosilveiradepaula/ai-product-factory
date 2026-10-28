/* Exercise the actual TypeScript Route Handler: no credentials, network, or writes. */
"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const source=fs.readFileSync(path.join(root,"apps/console/app/api/integrations/github-app/verify/route.ts"),"utf8");
const out=ts.transpileModule(source,{fileName:"route.ts",reportDiagnostics:true,compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true
}});
assert.equal((out.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
function fixture({deny=false,fail=false,status="ready",cookieProject="crm-infodive"}={}){
  const calls={admin:0,verify:[],deleted:[]};
  const auth={requireConsoleAdmin:async()=>{calls.admin++;if(deny)throw Error("admin required");}};
  const jar={get:name=>name==="factory_github_app_install_project"?{value:cookieProject}:undefined,
    delete:name=>{calls.deleted.push(name);}};
  const nextResponse={
    json:(payload,options={})=>new Response(JSON.stringify(payload),{
      status:options.status||200,headers:{"Content-Type":"application/json",...(options.headers||{})}
    }),
    redirect:(url,status=307)=>new Response(null,{status,headers:{Location:String(url)}}),
  };
  const required={
    "next/headers":{cookies:async()=>jar},
    "next/server":{NextResponse:nextResponse},
    "../../../../../lib/auth-server":auth,
    "../../../../../lib/github-app":{verifyProjectGitHubApp:async project=>{
      calls.verify.push(project);if(fail)throw Error("offline");return{status};
    }},
  };
  const exports={};
  vm.runInNewContext(out.outputText,{exports,URL,Response,
    require:name=>{assert.ok(Object.hasOwn(required,name),"unexpected import: "+name);return required[name];}},
    {filename:"route.ts",timeout:10000});
  function request({origin="https://console.example",type="application/x-www-form-urlencoded",body="project=crm-infodive&return_to=gates",url="https://console.example/api/integrations/github-app/verify"}={}){
    const headers={};
    if(origin!==null)headers.Origin=origin;
    if(type!==null)headers["Content-Type"]=type;
    return new Request(url,{method:"POST",headers,body});
  }
  return{...exports,calls,request};
}
test("safe GET never verifies or mutates even with live administrator session",async()=>{
  const f=fixture();
  const r=f.GET();
  assert.equal(r.status,405);
  assert.equal(r.headers.get("Allow"),"POST");
  assert.equal(r.headers.get("Cache-Control"),"no-store");
  assert.equal((await r.json()).error,"method not allowed");
  assert.equal(f.calls.admin,0);
  assert.deepEqual(f.calls.verify,[]);
  assert.deepEqual(f.calls.deleted,[]);
});
test("foreign or missing Origin, malformed content type and project cannot write",async()=>{
  const requests=[
    [{origin:"https://evil.example"},403],
    [{origin:null},403],
    [{origin:"https://console.example.evil.invalid"},403],
    [{type:"text/plain"},415],
    [{type:"application/json",body:'{"project":"crm-infodive"}'},415],
    [{body:"project=../other&return_to=gates"},400],
    [{body:"project=crm-infodive&return_to=https%3A%2F%2Fevil.example"},400],
    [{body:"return_to=gates"},400],
  ];
  for(const [opts,expected] of requests){
    const f=fixture();
    const r=await f.POST(f.request(opts));
    assert.equal(r.status,expected,JSON.stringify(opts));
    assert.deepEqual(f.calls.verify,[]);
    assert.deepEqual(f.calls.deleted,[]);
  }
});
test("authorized origin and explicit form verify only the posted project",async()=>{
  const f=fixture();
  const r=await f.POST(f.request({
    url:"https://console.example/api/integrations/github-app/verify?project=evil-key",
    body:"project=crm-infodive&return_to=gates"
  }));
  assert.equal(r.status,303);
  assert.equal(r.headers.get("location"),"https://console.example/gates?github_app=verified");
  assert.deepEqual(f.calls.verify,["crm-infodive"]);
  assert.deepEqual(f.calls.deleted,["factory_github_app_install_project"]);
});
test("incomplete grant and network errors remain blocked without leakage",async()=>{
  for(const [settings,result] of [
    [{status:"blocked"},"blocked"],[{fail:true},"verification_failed"]
  ]){
    const f=fixture({...settings,cookieProject:"unrelated-project"});
    const r=await f.POST(f.request({body:"project=crm-infodive"}));
    assert.equal(r.status,303);
    assert.equal(r.headers.get("location"),
      "https://console.example/projects/crm-infodive?github_app="+result);
    assert.deepEqual(f.calls.verify,["crm-infodive"]);
    assert.deepEqual(f.calls.deleted,[],"never clear a different project's pending setup");
  }
});
test("unprivileged operator never reaches the capability verifier",async()=>{
  const f=fixture({deny:true});
  await assert.rejects(f.POST(f.request()),/admin required/);
  assert.equal(f.calls.admin,1);
  assert.deepEqual(f.calls.verify,[]);
  assert.deepEqual(f.calls.deleted,[]);
});
