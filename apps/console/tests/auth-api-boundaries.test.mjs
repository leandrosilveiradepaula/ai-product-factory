import test from "node:test";
import assert from "node:assert/strict";
import {getAuthUser,getConsoleOperator,refreshAuthSession,signInPassword} from "../lib/auth-api.ts";

const USER="1426ab7d-824b-4a2d-a5de-c18823baff26";
const previous={url:process.env.SUPABASE_URL,key:process.env.SUPABASE_PUBLISHABLE_KEY};
process.env.SUPABASE_URL="https://example.invalid";
process.env.SUPABASE_PUBLISHABLE_KEY="public-test-only";
const originalFetch=globalThis.fetch;
function mock(responses){
 let index=0;
 globalThis.fetch=async()=>({ok:true,json:async()=>responses[index++]});
}
test.after(()=>{
 globalThis.fetch=originalFetch;
 if(previous.url===undefined)delete process.env.SUPABASE_URL;else process.env.SUPABASE_URL=previous.url;
 if(previous.key===undefined)delete process.env.SUPABASE_PUBLISHABLE_KEY;else process.env.SUPABASE_PUBLISHABLE_KEY=previous.key;
});
test("reject malformed users and non-UUID identities",async()=>{
 for(const user of [null,[],{}, {id:"attacker"}, {id:USER,email:42}]){
  mock([user]);assert.equal(await getAuthUser("synthetic-token"),null);
 }
});
test("operator authorization fails closed on role escalation, inactive and ambiguous rows",async()=>{
 for(const rows of [null,{},[],[{role:"admin",is_active:false}],
   [{role:"owner",is_active:true}],[{role:"admin",is_active:true},{role:"operator",is_active:true}],
   [{role:"admin"}]]){
  mock([{id:USER,email:"test@example.invalid"},rows]);
  assert.equal(await getConsoleOperator("synthetic-token"),null);
 }
});
test("valid single active operator is returned without role promotion",async()=>{
 mock([{id:USER,email:"test@example.invalid"},[{role:"operator",is_active:true}]]);
 assert.deepEqual(await getConsoleOperator("synthetic-token"),{userId:USER,email:"test@example.invalid",role:"operator"});
});
test("invalid sign-in and refresh payloads cannot create a session",async()=>{
 for(const value of [{}, {access_token:"",refresh_token:"x",expires_in:3600,user:{id:USER}},
   {access_token:"x",refresh_token:"y",expires_in:-1,user:{id:USER}},
   {access_token:"x",refresh_token:"y",expires_in:3600,user:{id:"attacker"}}]){
  mock([value]);await assert.rejects(()=>signInPassword("test@example.invalid","synthetic"));
  mock([value]);assert.equal(await refreshAuthSession("synthetic"),null);
 }
});
test("valid synthetic auth session retains expected shape",async()=>{
 const session={access_token:"synthetic",refresh_token:"synthetic-refresh",expires_in:3600,user:{id:USER,email:"test@example.invalid"}};
 mock([session]);assert.deepEqual(await signInPassword("test@example.invalid","synthetic"),session);
});
