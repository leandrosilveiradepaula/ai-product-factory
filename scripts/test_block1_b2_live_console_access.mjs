import test from "node:test";
import assert from "node:assert/strict";
import {verifyLiveConsoleAccess} from "./verify_block1_b2_live_console_access.mjs";

const origin="https://console.example.invalid";
function fixture({anonymousAllowed=false,anonymousApiAllowed=false,operatorDenied=false,adminAllowed=false}={}) {
  const records={anonymousPages:[],operatorPages:[],anonymousApi:0,operatorApi:0};
  function page(kind) {
    let url=origin+"/";
    return {
      url:()=>url,
      async goto(target) {
        const path=new URL(target).pathname;
        if(kind==="anon") {
          records.anonymousPages.push(path);
          url=origin+(anonymousAllowed?path:"/login");
        } else {
          records.operatorPages.push(path);
          url=origin+(adminAllowed?path:"/unauthorized");
        }
        return {status:()=>200};
      },
      async close(){},
    };
  }
  const noAuth={
    async newPage(){return page("anon");},
    request:{async get(){records.anonymousApi++;return {
      status:()=>anonymousApiAllowed?200:307,
      headers:()=>({location:"/login"}),
    };}},
    async close(){},
  };
  const browser={async newContext(options) {
    assert.equal(options.extraHTTPHeaders["x-vercel-trusted-oidc-idp-token"],"synthetic");
    return noAuth;
  }};
  const operatorContext={
    request:{async get(){records.operatorApi++;return {
      status:()=>operatorDenied?403:200,
      json:async()=>({status:"ok",count:0,projects:[]}),
    };}},
    async newPage(){return page("operator");},
  };
  return {browser,operatorContext,records};
}
test("read-only live boundary contract covers anonymous, operator and admin denial",async()=>{
  const f=fixture();
  const r=await verifyLiveConsoleAccess({...f,baseUrl:origin,trustedOidc:"synthetic"});
  assert.equal(r.anonymousRouteDenials.length,3);
  assert.equal(r.operatorAdminPageDenied,true);
  assert.equal(r.operatorReadOnlyApiAllowed,true);
  assert.equal(r.productionWrites,0);
  assert.equal(r.fullAuthnAuthzCertified,false);
  assert.equal(r.crossTenantIsolationCertified,false);
  assert.equal(f.records.anonymousApi,1);
  assert.equal(f.records.operatorApi,1);
});
for(const [label,change] of [
  ["anonymous route exposed",{anonymousAllowed:true}],
  ["anonymous API exposed",{anonymousApiAllowed:true}],
  ["operator API denied",{operatorDenied:true}],
  ["operator allowed admin page",{adminAllowed:true}],
]) {
  test("fail closed: "+label,async()=>{
    const f=fixture(change);
    await assert.rejects(
      verifyLiveConsoleAccess({...f,baseUrl:origin,trustedOidc:"synthetic"}),
      /b2_/,
    );
  });
}
test("reject non-HTTPS origin before browser",async()=>{
  const f=fixture();
  await assert.rejects(
    verifyLiveConsoleAccess({...f,baseUrl:"http://console.example.invalid",trustedOidc:"synthetic"}),
    /b2_invalid_console_origin/,
  );
});
