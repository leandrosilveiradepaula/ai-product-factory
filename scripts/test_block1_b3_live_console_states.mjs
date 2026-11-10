import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {safeB3StateWitness,verifyConsoleStatesReadOnly} from "./verify_block1_b3_live_console_states.mjs";
const source="a".repeat(40),target="b".repeat(40);
function sample(){return {blocked:false,browserErrors:0,mutatingRequests:0,
 pending:true,unavailable:true,cleared:true,malformed:true,
 hits:{pending:1,unavailable:1,cleared:1,malformed:1}};}
function build(observed=sample(),changes={}){
 return safeB3StateWitness({observed,runId:42824989568,
  sourceCommit:source,targetCommit:target,...changes});
}
test("retain only bounded UI checks and no personal data or false PASS",()=>{
 const sampleData=sample();
 sampleData.email="private@example.invalid";sampleData.token="private-token";
 const got=build(sampleData),raw=JSON.stringify(got);
 assert.deepEqual(got.checks,{pending:true,unavailable:true,cleared:true,malformed:true});
 assert.equal(got.actualBackendStateCertified,false);
 assert.equal(got.fullUserExperienceCertified,false);
 assert.equal(got.independentCriterionCertified,false);
 assert.equal(got.visualAuditPassed,false);
 assert.equal(got.productionWrites,0);
 assert.equal(raw.includes("private"),false);
});
test("negative transitions, missing requests, mutations and browser errors fail",()=>{
 for(const change of [{pending:false},{unavailable:false},{cleared:false},{malformed:false},
  {browserErrors:1},{mutatingRequests:1},{blocked:true},
  {hits:{pending:0,unavailable:1,cleared:1,malformed:1}},
  {hits:{pending:1,unavailable:1,cleared:1,malformed:"1"}}]){
  assert.throws(()=>build({...sample(),...change}),/b3_state_witness_incomplete/);
 }
});
test("source/target SHA and run identity fail closed",()=>{
 for(const change of [{runId:0},{runId:"bad"},
  {sourceCommit:"not-sha"},{targetCommit:"z".repeat(40)}])
   assert.throws(()=>build(sample(),change),/b3_state_witness_incomplete/);
 assert.throws(()=>build(null),/b3_state_witness_incomplete/);
});
test("reject unsafe origins before creating page or accessing credentials",async()=>{
 let count=0;
 const context={async newPage(){count++;throw Error("unexpected page");}};
 for(const baseUrl of ["http://console.example.invalid","https://u:p@console.example.invalid",
  "https://console.example.invalid/other","https://console.example.invalid/?token=secret",
  "javascript:alert(1)"]){
  await assert.rejects(verifyConsoleStatesReadOnly({
   context,baseUrl,runId:1,sourceCommit:source,targetCommit:target,
  }),/b3_invalid_console_origin/);
 }
 assert.equal(count,0);
});
test("capture preserves bounded B3 evidence before later hydration failure",()=>{
 const capture=fs.readFileSync(new URL("./capture_authenticated_console.mjs",import.meta.url),"utf8");
 const workflow=fs.readFileSync(new URL("../.github/workflows/authenticated-visual-evidence.yml",import.meta.url),"utf8");
 assert.ok(capture.indexOf("verifyConsoleStatesReadOnly({")>capture.indexOf("safeB2Witness({"));
 assert.ok(capture.indexOf("block1-b3-console-state-witness.json")<capture.indexOf("const routes = CONSOLE_ROUTES;"));
 assert.ok(capture.includes("browser errors: console="));
 assert.ok(workflow.includes("Retain bounded B3 state witness even on later hydration failure"));
 assert.ok(workflow.includes("path: block1-b3-console-state-witness.json"));
 assert.ok(workflow.includes("if: always()"));
 assert.ok(workflow.includes("Finalize registry and remove ephemeral operator"));
});
