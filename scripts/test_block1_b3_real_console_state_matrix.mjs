import test from "node:test";
import assert from "node:assert/strict";
import {safeRealConsoleStateMatrix} from "./verify_block1_b3_real_console_state_matrix.mjs";

const SHA="a".repeat(40);
const SERVED="b".repeat(40);
const checks={success:true,empty:true,loading:true,denied:true,notFound:true,
              connectionError:true,recovered:true};
function params(){
  return {runId:987654,sourceCommit:SHA,targetCommit:SERVED,
          checks:{...checks},backendStatus:200,mutatingRequests:0,
          interceptions:0,unexpectedPageErrors:0};
}
test("full real state matrix retains only bounded SHA-bound telemetry",()=>{
  const result=safeRealConsoleStateMatrix(params());
  assert.equal(result.schema,"factory-b3-authenticated-live-state-matrix-v1");
  assert.deepEqual(result.checks,checks);
  assert.equal(result.fullUserExperienceCertified,true);
  assert.equal(result.independentCriterionCertified,false);
  assert.equal(result.responsesFabricated,false);
  assert.equal(result.backendOutageClaimed,false);
  assert.equal(result.productionWrites,0);
  assert.equal(result.paidCalls,0);
  assert.equal(result.personalDataRetained,false);
  assert.deepEqual(Object.keys(result.sources),Object.keys(checks));
});
test("partial simulated or mutating scenarios cannot issue a real-state receipt",()=>{
  const bad=[
    x=>{x.checks.loading=false;},
    x=>{delete x.checks.notFound;},
    x=>{x.checks.fake=true;},
    x=>{x.mutatingRequests=1;},
    x=>{x.interceptions=1;},
    x=>{x.unexpectedPageErrors=1;},
    x=>{x.backendStatus=503;},
    x=>{x.sourceCommit="wrong";},
    x=>{x.targetCommit="wrong";},
    x=>{x.runId="not-an-int";},
  ];
  for(const modify of bad){
    const request=params();modify(request);
    assert.throws(()=>safeRealConsoleStateMatrix(request),/b3_real_states_/);
  }
});
test("browser source cannot intercept or fulfill real responses",async()=>{
  const fs=await import("node:fs/promises");
  const script=await fs.readFile(new URL("./verify_block1_b3_real_console_state_matrix.mjs",import.meta.url),"utf8");
  assert.ok(script.includes("Network.emulateNetworkConditions"));
  assert.ok(script.includes("context.setOffline(true)"));
  assert.ok(script.includes("context.setOffline(false)"));
  assert.ok(script.includes("/api/human-attention"));
  assert.ok(script.includes('status:404'));
  assert.ok(script.includes("Usuário sem permissão"));
  assert.ok(!/\.route\s*\(|\.fulfill\s*\(|\.intercept\s*\(/.test(script));
  assert.ok(!script.includes("credentials:"));
});
