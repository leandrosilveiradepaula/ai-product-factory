/* Offline behavior tests of the actual TypeScript operational-health helper.
   Loaded via the repo's pinned TypeScript dev dependency after npm ci.
   No network, Supabase credentials, paid model or side effect. */
"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const root=path.resolve(__dirname,"..");
const ts=require(path.join(root,"apps/console/node_modules/typescript"));
const source=fs.readFileSync(path.join(root,"apps/console/lib/operational-health-inventory.ts"),"utf8");
const js=ts.transpileModule(source,{
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
}).outputText;
const sandboxExports={};
vm.runInNewContext(js,{exports:sandboxExports,console},{timeout:10000});
const {readCompleteOperationalRows,parseRecordedCost,summarizeOperationalHealth}=sandboxExports;
const runId=n=>"00000000-0000-0000-0000-"+String(n+1).padStart(12,"0");
const time=n=>new Date(Date.parse("2026-10-14T23:00:00Z")-n*1000).toISOString();
const run=n=>({id:runId(n),created_at:time(n),task_id:runId(9000),status:"completed",attempt_count:0,last_error:null,lease_expires_at:null,execution_route:null});
const cost=n=>({id:100000-n,created_at:time(n),tool_family:"github",estimated_cost:0});
function pages(rows,options={}){
 const calls=[];
 const handler=async (uri,init)=>{
  calls.push(uri);
  assert.equal(init.cache,"no-store");
  const u=new URL(uri);
  assert.equal(u.searchParams.get("limit"),"200");
  assert.equal(u.searchParams.get("order"),"created_at.desc,id.desc");
  if(options.httpStatus&&calls.length===options.failAt)
   return {ok:false,status:options.httpStatus,json:async()=>({error:"unavailable"})};
  if(options.malformed)return{ok:true,status:200,json:async()=>({oops:1})};
  const offset=Number(u.searchParams.get("offset"));
  return{ok:true,status:200,json:async()=>rows.slice(offset,offset+200)};
 };
 return {handler,calls};
}
const read=(rows,kind,handler)=>readCompleteOperationalRows({
 url:"https://mock.supabase.co",headers:{apikey:"not-a-real-key"},
 table:kind==="uuid"?"factory_runs":"factory_tool_usage",
 select:"id,created_at",idKind:kind,transport:handler
});
test("runs older than newest 200 are all counted",async()=>{
 const rows=Array.from({length:201},(_,i)=>run(i));
 const p=pages(rows);const value=await read(rows,"uuid",p.handler);
 assert.equal(value.length,201);
 assert.equal(value[200].id,runId(200));
 assert.equal(p.calls.length,2);
});
test("more than 1000 BIGINT usage rows are not silently truncated",async()=>{
 const rows=Array.from({length:1001},(_,i)=>cost(i));
 const p=pages(rows);const value=await read(rows,"bigint",p.handler);
 assert.equal(value.length,1001);
 assert.equal(p.calls.length,6);
});
test("duplicate IDs across offsets fail closed",async()=>{
 const rows=Array.from({length:200},(_,i)=>run(i));
 rows.push({...rows[199]});
 const p=pages(rows);
 await assert.rejects(read(rows,"uuid",p.handler),/repetiu ID/);
});
test("out of order page and malformed response fail closed",async()=>{
 const rows=Array.from({length:201},(_,i)=>run(i));
 rows[200].created_at=rows[0].created_at;
 const p=pages(rows);
 await assert.rejects(read(rows,"uuid",p.handler),/ordenação/);
 const broken=pages([], {malformed:true});
 await assert.rejects(read([],"uuid",broken.handler),/página inválida/);
});
test("HTTP failures after a complete first page fail closed",async()=>{
 const rows=Array.from({length:201},(_,i)=>run(i));
 const p=pages(rows,{httpStatus:503,failAt:2});
 await assert.rejects(read(rows,"uuid",p.handler),/HTTP 503/);
 assert.equal(p.calls.length,2);
});
test("exact 4000 results fail closed without claiming exhaustion",async()=>{
 const rows=Array.from({length:4000},(_,i)=>run(i));
 const p=pages(rows);
 await assert.rejects(read(rows,"uuid",p.handler),/4.000/);
 assert.equal(p.calls.length,20);
});
test("BIGINT malformed and non timezone timestamps fail closed",async()=>{
 await assert.rejects(read([{...cost(0),id:1000000000000000000000}],"bigint",pages([{...cost(0),id:1000000000000000000000}]).handler),/BIGINT/);
 const rows=[{...run(0),created_at:"2026-10-14 21:00:00"}];
 await assert.rejects(read(rows,"uuid",pages(rows).handler),/timezone/);
});
test("invalid or unknown cost stays blocked, never coerced to zero",()=>{
 assert.equal(parseRecordedCost(null),null);
 assert.equal(parseRecordedCost("1.37"),1.37);
 for(const value of ["", "-1", "NaN", "Infinity", true, {}, -1, Infinity]){
  assert.throws(()=>parseRecordedCost(value),/Custo operacional/);
 }
});
test("recovered historical run is not actionable dead-letter",()=>{
 const taskId=runId(9000);
 const failed={...run(0),status:"failed",last_error:"maximum attempts exceeded"};
 const usage=[{...cost(0),tool_family:"openai",estimated_cost:null},
  {...cost(1),tool_family:"github",estimated_cost:"2.50"},
  {...cost(2),tool_family:"github",estimated_cost:null}];
 const recovered=summarizeOperationalHealth([failed],usage,new Map([[taskId,"completed"]]),Date.now());
 assert.equal(recovered.failedRuns,0);
 assert.equal(recovered.deadLetterRuns,0);
 assert.equal(recovered.incidents.length,0);
 assert.equal(recovered.unknownCostEvents,1);
 assert.equal(recovered.knownCost,2.5);
 const active=summarizeOperationalHealth([failed],usage,new Map([[taskId,"failed"]]),Date.now());
 assert.equal(active.failedRuns,1);
 assert.equal(active.deadLetterRuns,1);
 assert.equal(active.incidents.length,1);
});
