import test from "node:test";
import assert from "node:assert/strict";
import {verifyLiveSupabaseBoundaries,B2_CONTROL_PLANE_TABLES} from "./verify_block1_b2_live_supabase.mjs";

const SHA="a".repeat(40);
const USER_ID="33333333-3333-4333-8333-333333333333";
const ISSUER="https://fjplmxfcshhbmzgvyqlm.supabase.co/auth/v1";
const BROKER="https://fjplmxfcshhbmzgvyqlm.supabase.co/functions/v1/factory-visual-evidence-broker";
const ORIGIN="https://ai-product-factory-console.vercel.app/";
const PUBLISHABLE="sb_publishable_"+"x".repeat(30);

function token(claimPatch={}) {
 const header={alg:"HS256",typ:"JWT"};
 const body={
   iss:ISSUER,sub:USER_ID,role:"authenticated",aud:"authenticated",
   exp:Math.floor(Date.now()/1000)+3600,iat:Math.floor(Date.now()/1000)-10,
   ...claimPatch,
 };
 return Buffer.from(JSON.stringify(header)).toString("base64url")
   +"."+Buffer.from(JSON.stringify(body)).toString("base64url")+"."+"Z".repeat(43);
}
function fixture(patch={}) {
 const valid=token(patch.claims);
 const seen=[];
 const operatorContext={
  async cookies(urls) {
   assert.deepEqual(urls,[new URL(ORIGIN).origin]);
   return patch.cookieMissing?[]:[{
      name:"factory_access_token",value:valid,
      httpOnly:patch.httpOnlyFalse?false:true,
      secure:patch.secureFalse?false:true,
   }];
  },
 };
 async function fetchImpl(input,options) {
  assert.equal(options.method,"GET","B2 must never mutate any provider resource");
  assert.equal(options.redirect,"manual");
  assert.equal(options.headers.apikey,PUBLISHABLE);
  const url=new URL(input);
  const isAuth=options.headers.Authorization==="Bearer "+valid;
  seen.push({route:url.pathname,method:options.method,authenticated:isAuth});
  if(url.pathname==="/auth/v1/user") {
   return {status:(isAuth||patch.acceptForged)?200:403,
     json:async()=>({id:USER_ID})};
  }
  if(url.pathname==="/rest/v1/factory_console_operators") {
   if(isAuth) return {status:200,json:async()=>patch.extraRow?
       [{user_id:USER_ID,role:"operator",is_active:true},
        {user_id:"11111111-1111-4111-8111-111111111111",role:"admin",is_active:true}]:
       [{user_id:USER_ID,role:patch.elevatedOperator?"admin":"operator",is_active:true}]};
   return {status:patch.anonDirectoryLeaked?200:401};
  }
  if(url.pathname.startsWith("/rest/v1/factory_")) {
   if(patch.untrustedTableLeaked&&url.pathname==="/rest/v1/factory_runs")return {status:200};
   if(patch.anonymousProjectLeaked&&url.pathname==="/rest/v1/factory_projects"&&!isAuth)
     return {status:200};
   return {status:isAuth?403:401};
  }
  throw Error("unexpected synthetic endpoint "+url.pathname);
 }
 return {input:{
   operatorContext,consoleOrigin:ORIGIN,brokerUrl:BROKER,
   publishableKey:PUBLISHABLE,expectedUserId:USER_ID,
   runId:43289096088,sourceCommit:SHA,targetCommit:SHA,fetchImpl,
 },seen,valid};
}
test("real provider/role/RLS probe contract emits only a tiny, sanitized witness",async()=>{
 const f=fixture();
 const out=await verifyLiveSupabaseBoundaries(f.input);
 assert.equal(out.schema,"factory-b2-live-supabase-auth-data-v1");
 assert.equal(out.checks.untrustedControlPlaneTablesDenied,B2_CONTROL_PLANE_TABLES.length);
 assert.deepEqual(out.checkedTables,B2_CONTROL_PLANE_TABLES);
 assert.equal(out.checks.providerSignedUserVerified,true);
 assert.equal(out.checks.forgedSignatureRejected,true);
 assert.equal(out.checks.forgedRoleRejected,true);
 assert.equal(out.checks.forgedSubjectRejected,true);
 assert.equal(out.independentTenantModelClaimed,false);
 assert.equal(out.productionWrites,0);
 assert.equal(out.mutatingRequests,0);
 assert.equal(out.paidCalls,0);
 assert.equal(out.personalDataRetained,false);
 const serialized=JSON.stringify(out);
 assert.ok(!serialized.includes(USER_ID)&&!serialized.includes(f.valid)
   &&!serialized.includes(PUBLISHABLE)&&!serialized.includes(ISSUER));
 assert.equal(f.seen.filter(x=>x.route==="/auth/v1/user").length,4);
 assert.ok(f.seen.length>=B2_CONTROL_PLANE_TABLES.length+7);
 assert.ok(f.seen.every(x=>x.method==="GET"));
});
for(const [name,overrides] of [
 ["forged signature accepted",{acceptForged:true}],
 ["anonymous operator directory exposed",{anonDirectoryLeaked:true}],
 ["anonymous portfolio table exposed",{anonymousProjectLeaked:true}],
 ["privileged data exposed to operator",{untrustedTableLeaked:true}],
 ["cross operator directory leaked",{extraRow:true}],
 ["effective operator escalated",{elevatedOperator:true}],
 ["cookie not HttpOnly",{httpOnlyFalse:true}],
 ["cookie not Secure",{secureFalse:true}],
 ["missing authenticated cookie",{cookieMissing:true}],
 ["wrong JWT issuer",{claims:{iss:"https://attacker.example.invalid/auth/v1"}}],
 ["wrong JWT subject",{claims:{sub:"11111111-1111-4111-8111-111111111111"}}],
 ["privileged JWT claim",{claims:{role:"service_role"}}],
 ["expired signed JWT",{claims:{exp:Math.floor(Date.now()/1000)-20}}],
]) {
 test("B2 fails closed: "+name,async()=>{
  const f=fixture(overrides);
  await assert.rejects(verifyLiveSupabaseBoundaries(f.input),/^Error: b2_|b2_/);
 });
}
test("Preview capture may test real Auth without claiming the candidate is main",async()=>{
 const f=fixture();
 const result=await verifyLiveSupabaseBoundaries({...f.input,targetCommit:"b".repeat(40)});
 assert.equal(result.sourceCommit,SHA);
 assert.equal(result.targetCommit,"b".repeat(40));
});
test("unsafe source or origin fails before touching any provider",async()=>{
 const f=fixture();
 for(const changed of [
   {targetCommit:"bad"},
   {sourceCommit:"bad"},
   {brokerUrl:"https://evil.example.org/functions/v1/factory-visual-evidence-broker"},
   {consoleOrigin:"http://ai-product-factory-console.vercel.app"},
   {publishableKey:"sb_secret_do_not_accept"},
 ]) {
  await assert.rejects(verifyLiveSupabaseBoundaries({...f.input,...changed}),/b2_/);
 }
 assert.deepEqual(f.seen,[]);
});
