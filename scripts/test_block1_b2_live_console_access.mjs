import test from "node:test";
import assert from "node:assert/strict";
import {verifyLiveConsoleAccess,B2_PROTECTED_ROUTES} from "./verify_block1_b2_live_console_access.mjs";

const origin="https://console.example.invalid";
function fixture({anonymousAllowed=false,anonymousApiAllowed=false,operatorDenied=false,operatorRole="operator",adminAllowed=false,adminSessionLost=false,
  invalidSessionAllowed=false,invalidSessionApiAllowed=false}={}) {
  const records={anonymousPages:[],operatorPages:[],anonymousApi:0,operatorApi:0,invalidApi:0,invalidPages:[]};
  let forgedCookie=false;
  function page(kind) {
    let url=origin+"/";
    return {
      url:()=>url,
      async goto(target) {
        const path=new URL(target).pathname;
        if(kind==="anon"||kind==="invalid") {
          if(kind==="invalid")records.invalidPages.push(path);
          else records.anonymousPages.push(path);
          url=origin+((kind==="invalid"?invalidSessionAllowed:anonymousAllowed)?path:"/login");
        } else {
          records.operatorPages.push(path);
          url=origin+(adminAllowed?path:adminSessionLost?"/login":"/unauthorized");
        }
        return {status:()=>200};
      },
      async close(){},
    };
  }
  const noAuth={
    async addCookies(cookies){assert.equal(cookies.length,1);assert.equal(cookies[0].name,"factory_access_token");forgedCookie=true;},
    async newPage(){return page(forgedCookie?"invalid":"anon");},
    request:{async get(){if(forgedCookie)records.invalidApi++;else records.anonymousApi++;return {
      status:()=>(forgedCookie?invalidSessionApiAllowed:anonymousApiAllowed)?200:307,
      headers:()=>({location:"/login"}),
    };}},
    async close(){},
  };
  const browser={async newContext(options) {
    assert.equal(options.extraHTTPHeaders["x-vercel-trusted-oidc-idp-token"],"synthetic");
    return noAuth;
  }};
  const operatorContext={
    request:{async get(url){
      if(new URL(url).pathname==="/api/session")return {
        status:()=>operatorDenied?403:200,
        json:async()=>({status:"ok",role:operatorRole}),
      };
      records.operatorApi++;return {
        status:()=>operatorDenied?403:200,
        json:async()=>({status:"ok",count:0,projects:[]}),
      };
    }},
    async newPage(){return page("operator");},
  };
  return {browser,operatorContext,records};
}
test("read-only live boundary contract covers anonymous, operator and admin denial",async()=>{
  const f=fixture();
  const r=await verifyLiveConsoleAccess({...f,baseUrl:origin,trustedOidc:"synthetic"});
  assert.equal(r.anonymousRouteDenials.length,B2_PROTECTED_ROUTES.length);
  assert.deepEqual(r.anonymousRouteDenials.map(v=>v.route),B2_PROTECTED_ROUTES);
  assert.equal(r.invalidSessionRouteDenied,true);
  assert.equal(r.invalidSessionApiDenied,true);
  assert.equal(r.operatorAdminPageDenied,true);
  assert.equal(r.ephemeralOperatorRoleVerified,true);
  assert.equal(r.operatorReadOnlyApiAllowed,true);
  assert.equal(r.productionWrites,0);
  assert.equal(r.fullAuthnAuthzCertified,false);
  assert.equal(r.crossTenantIsolationCertified,false);
  assert.equal(f.records.anonymousApi,1);
  assert.equal(f.records.invalidApi,1);
  assert.deepEqual(f.records.invalidPages,["/projects"]);
  assert.equal(f.records.operatorApi,1);
});
for(const [label,change] of [
  ["anonymous route exposed",{anonymousAllowed:true}],
  ["anonymous API exposed",{anonymousApiAllowed:true}],
  ["operator API denied",{operatorDenied:true}],
  ["ephemeral operator role elevated",{operatorRole:"admin"}],
  ["operator allowed admin page",{adminAllowed:true}],
  ["operator session lost before admin denial",{adminSessionLost:true}],
  ["forged session allowed on page",{invalidSessionAllowed:true}],
  ["forged session allowed on API",{invalidSessionApiAllowed:true}],
]) {
  test("fail closed: "+label,async()=>{
    const f=fixture(change);
    await assert.rejects(
      verifyLiveConsoleAccess({...f,baseUrl:origin,trustedOidc:"synthetic"}),
      /b2_/,
    );
  });
}
test("distinguishes an exposed admin page from a lost operator session",async()=>{
  const exposed=fixture({adminAllowed:true});
  await assert.rejects(
    verifyLiveConsoleAccess({...exposed,baseUrl:origin,trustedOidc:"synthetic"}),
    /b2_operator_admin_page_exposed/,
  );
  const sessionLost=fixture({adminSessionLost:true});
  await assert.rejects(
    verifyLiveConsoleAccess({...sessionLost,baseUrl:origin,trustedOidc:"synthetic"}),
    /b2_operator_admin_session_lost/,
  );
});
test("reject non-HTTPS origin before browser",async()=>{
  const f=fixture();
  await assert.rejects(
    verifyLiveConsoleAccess({...f,baseUrl:"http://console.example.invalid",trustedOidc:"synthetic"}),
    /b2_invalid_console_origin/,
  );
});
