"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {evidenceRunTitle,selectBrowserRun} = require("../browser_run_correlation.cjs");
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
