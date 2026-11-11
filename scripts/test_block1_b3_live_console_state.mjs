import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {safeLiveStateWitness,verifyLiveConsoleStateReadOnly} from "./verify_block1_b3_live_console_state.mjs";

const source="a".repeat(40),target="b".repeat(40);
const ok={status:"ok",count:2,projects:["never-retained"]};

test("live backend witness is bounded and strips response contents",()=>{
 const witness=safeLiveStateWitness({runId:42,sourceCommit:source,targetCommit:target,httpStatus:200,body:ok});
 assert.equal(witness.state,"available");
 assert.equal(witness.countClass,"positive");
 assert.equal(witness.actualBackendStateObserved,true);
 assert.equal(witness.responseBodyRetained,false);
 assert.equal(witness.projectsRetained,false);
 assert.equal(JSON.stringify(witness).includes("never-retained"),false);
 assert.equal(witness.fullUserExperienceCertified,false);
 assert.equal(witness.independentCriterionCertified,false);
 assert.equal(witness.productionWrites,0);
});

test("only safe real endpoint response classes are accepted",()=>{
 const zero=safeLiveStateWitness({runId:1,sourceCommit:source,targetCommit:target,httpStatus:200,body:{status:"ok",count:0,projects:[]}});
 assert.equal(zero.countClass,"zero");
 const unavailable=safeLiveStateWitness({runId:1,sourceCommit:source,targetCommit:target,httpStatus:503,body:{status:"unavailable"}});
 assert.equal(unavailable.state,"unavailable");
 for(const bad of [
  {httpStatus:200,body:{status:"unavailable"}},
  {httpStatus:503,body:{status:"ok",count:0,projects:[]}},
  {httpStatus:200,body:{status:"ok",count:-1,projects:[]}},
  {httpStatus:200,body:{status:"ok",count:0,projects:[1]}},
  {httpStatus:500,body:{status:"unavailable"}},
 ]) assert.throws(()=>safeLiveStateWitness({runId:1,sourceCommit:source,targetCommit:target,...bad}),/b3_live_state_/);
});

test("request uses only validated HTTPS origin and no redirect",async()=>{
 let calls=0;
 const context={request:{async get(url,options){calls++;assert.equal(url,"https://console.example.invalid/api/human-attention");assert.equal(options.maxRedirects,0);return {status:()=>200,json:async()=>({status:"ok",count:0,projects:[]})};}}};
 const witness=await verifyLiveConsoleStateReadOnly({context,baseUrl:"https://console.example.invalid/",runId:1,sourceCommit:source,targetCommit:target});
 assert.equal(calls,1);assert.equal(witness.countClass,"zero");
 for(const unsafe of ["http://console.example.invalid/","https://user:pass@console.example.invalid/","https://console.example.invalid/path","https://console.example.invalid/?private=1"])
  await assert.rejects(verifyLiveConsoleStateReadOnly({context,baseUrl:unsafe,runId:1,sourceCommit:source,targetCommit:target}),/b3_live_state_origin_invalid/);
 assert.equal(calls,1);
});

test("capture and protected workflow retain live observation separately",()=>{
 const capture=fs.readFileSync(new URL("./capture_authenticated_console.mjs",import.meta.url),"utf8");
 const workflow=fs.readFileSync(new URL("../.github/workflows/authenticated-visual-evidence.yml",import.meta.url),"utf8");
 assert.ok(capture.indexOf("verifyLiveConsoleStateReadOnly({")>capture.indexOf("safeB2Witness({"));
 assert.ok(capture.indexOf("block1-b3-live-state-witness.json")<capture.indexOf("verifyConsoleStatesReadOnly({"));
 assert.match(workflow,/name: block1-b3-live-state-\$\{\{ github\.run_id \}\}/);
 assert.match(workflow,/path: block1-b3-live-state-witness\.json/);
});
