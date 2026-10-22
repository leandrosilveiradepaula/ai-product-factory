"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {evidenceRunTitle,selectBrowserRun,trustedBrowserJobOutcome} = require("../browser_run_correlation.cjs");
const REQ="8f98edc4-323e-42af-9917-14a7d0a4a1e9";
const SHA="a".repeat(40);
const NOW=Date.parse("2026-10-15T10:00:00Z");
function run(overrides={}) {
  const id=11959047596;
  return {
    id,
    display_title:evidenceRunTitle(REQ),
    path:".github/workflows/console-browser-evidence.yml",
    event:"workflow_dispatch",
    head_branch:"main",
    head_sha:SHA,
    run_attempt:1,
    html_url:"https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/"+id,
    created_at:new Date(NOW).toISOString(),
    status:"completed",conclusion:"success",...overrides,
  };
}
const identity={requestId:REQ,factorySha:SHA,startedAtMs:NOW};
test("matches only exact nonce even when another recent successful run exists",()=>{
  const other=run({id:12,html_url:"https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/12",display_title:"other"});
  assert.equal(selectBrowserRun([other,run()],identity).id,11959047596);
  assert.equal(selectBrowserRun([other],identity),null);
});
test("wrong SHA, workflow, event, branch, attempt, time, URL and id are excluded",()=>{
  const cases=[
    {head_sha:"b".repeat(40)},{path:".github/workflows/other.yml"},
    {event:"push"},{head_branch:"feature"},{run_attempt:2},
    {created_at:new Date(NOW-6000).toISOString()},
    {html_url:"https://attacker.invalid/"},{id:0},{created_at:"invalid"},
  ];
  for(const variant of cases){
    assert.equal(selectBrowserRun([run(variant)],identity),null,JSON.stringify(variant));
  }
});
test("duplicate exact identities fail closed",()=>{
  const id=11959047597;
  assert.throws(()=>selectBrowserRun([run(),run({id,html_url:"https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/"+id})],identity),/ambiguous/);
});
test("invalid nonce, factory sha and over-large listings fail closed",()=>{
  for(const id of ["","../../","other","8f98",REQ.toUpperCase()]){
    assert.throws(()=>evidenceRunTitle(id),/identifier/);
  }
  assert.throws(()=>selectBrowserRun([],{...identity,factorySha:"short"}),/Factory/);
  assert.throws(()=>selectBrowserRun(new Array(101).fill(null),identity),/listing/);
});
test("in-progress correlated child is not implicitly a successful result",()=>{
  const child=selectBrowserRun([run({status:"in_progress",conclusion:null})],identity);
  assert.equal(child.status,"in_progress");
  assert.equal(child.conclusion,null);
});

const child={...run(),status:"in_progress",conclusion:null};
const browserJob={id:913,run_id:child.id,head_sha:SHA,name:"browser-evidence",status:"completed",conclusion:"success"};
const receipt={total_count:1,jobs:[browserJob]};

test("trusted browser job completes even if aggregate workflow status is delayed",()=>{
  assert.equal(trustedBrowserJobOutcome(child,receipt,SHA),"verified");
  assert.equal(trustedBrowserJobOutcome({...child,status:"completed",conclusion:"success"},receipt,SHA),"verified");
});
test("aggregate workflow failure overrides an otherwise successful browser job",()=>{
  assert.equal(trustedBrowserJobOutcome({...child,status:"completed",conclusion:"failure"},receipt,SHA),"failed");
  assert.equal(trustedBrowserJobOutcome({...child,status:"completed",conclusion:"cancelled"},receipt,SHA),"failed");
});
test("browser job must have exact run id, Factory SHA and active browser identity",()=>{
  for(const variant of [{run_id:9},{head_sha:"b".repeat(40)},{name:"test"},{id:0},{status:"skipped"}]){
    assert.throws(()=>trustedBrowserJobOutcome(child,{total_count:1,jobs:[{...browserJob,...variant}]},SHA),/correlated browser job identity invalid/);
  }
});
test("incomplete, unrelated or multiple jobs fail closed",()=>{
  for(const variant of [
    {total_count:0,jobs:[]},
    {total_count:2,jobs:[browserJob,browserJob]},
    {total_count:1,jobs:[]},
    null,
  ]){
    assert.throws(()=>trustedBrowserJobOutcome(child,variant,SHA),/incomplete correlated browser job evidence/);
  }
});
test("nonfinal job cannot greenlight candidate and bad completions fail",()=>{
  assert.equal(trustedBrowserJobOutcome(child,{total_count:1,jobs:[{...browserJob,status:"in_progress",conclusion:null}]},SHA),"pending");
  for(const conclusion of ["failure","skipped","cancelled",null]){
    assert.equal(trustedBrowserJobOutcome(child,{total_count:1,jobs:[{...browserJob,conclusion}]},SHA),"failed");
  }
});
test("future or inconsistent workflow state is not trusted",()=>{
  for(const row of [{...child,status:"garbage"},{...child,conclusion:"success"}]){
    assert.throws(()=>trustedBrowserJobOutcome(row,receipt,SHA),/invalid correlated browser workflow status/);
  }
});
