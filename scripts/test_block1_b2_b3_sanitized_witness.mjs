import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {safeB2Witness,safeBrowserError,safeConsoleError,safeHttpFailure} from "./block1_b2_b3_sanitized_witness.mjs";
import {B2_PROTECTED_ROUTES} from "./verify_block1_b2_live_console_access.mjs";

const source="a".repeat(40),target="b".repeat(40);
function allowedObservation() {
  return {
    schema:"factory-b2-live-console-access-boundaries-v1",
    anonymousRouteDenials:B2_PROTECTED_ROUTES.map(route=>({route,denied:true})),
    anonymousApiDenied:true,operatorReadOnlyApiAllowed:true,
    operatorAdminPageDenied:true,invalidSessionRouteDenied:true,
    invalidSessionApiDenied:true,mutatingRequests:0,productionWrites:0,
    signedJwtClaimsIndependentlyVerified:false,
    crossTenantIsolationCertified:false,fullAuthnAuthzCertified:false,
    fullDataBoundariesCertified:false,
  };
}
const build=observation=>safeB2Witness({
  observation,runId:42824989568,sourceCommit:source,targetCommit:target,
});
test("retain only strict B2 facts, not secrets, browser content or fake B3 success",()=>{
  const observed=allowedObservation();
  observed.secret="should-never-appear";
  observed.userId="sensitive-id";
  observed.html="<div>user content</div>";
  const receipt=build(observed);
  const raw=JSON.stringify(receipt);
  for(const forbidden of ["should-never-appear","sensitive-id","user content"]){
    assert.equal(raw.includes(forbidden),false);
  }
  assert.equal(receipt.runId,42824989568);
  assert.equal(receipt.sourceCommit,source);
  assert.equal(receipt.targetCommit,target);
  assert.equal(receipt.visualAuditPassed,false);
  assert.equal(receipt.authorizationBoundaryCertified,false);
  assert.equal(receipt.credentialOrUserDataRetained,false);
  assert.equal(receipt.productionWrites,0);
});
test("reject incomplete or unsafe B2 observations",()=>{
  for(const changed of [
    {anonymousApiDenied:false},
    {operatorReadOnlyApiAllowed:false},
    {operatorAdminPageDenied:false},
    {invalidSessionRouteDenied:false},
    {invalidSessionApiDenied:false},
    {mutatingRequests:1},
    {productionWrites:1},
    {signedJwtClaimsIndependentlyVerified:true},
    {crossTenantIsolationCertified:true},
    {fullAuthnAuthzCertified:true},
    {fullDataBoundariesCertified:true},
    {anonymousRouteDenials:[{route:"/projects",denied:true}]},
    {anonymousRouteDenials:B2_PROTECTED_ROUTES.map((route,i)=>({route,denied:i!==1}))},
    {schema:"unknown"},
  ]){
    assert.throws(()=>build({...allowedObservation(),...changed}),/b2_witness_incomplete/);
  }
});
test("reject malformed source and target SHAs and run IDs",()=>{
  for(const fields of [
    {sourceCommit:"not-a-sha"},{targetCommit:"c".repeat(39)},
    {runId:-1},{runId:0},{runId:"not-a-run"},
  ]){
    assert.throws(()=>safeB2Witness({
      observation:allowedObservation(),runId:42824989568,
      sourceCommit:source,targetCommit:target,...fields,
    }),/b2_witness_incomplete/);
  }
});
test("sanitize React hydration errors: retain route and code, never URL query or stack",()=>{
  const err=new Error("Minified React error #418; token=secret stack=private");
  const result=safeBrowserError(err,"https://ai-product-factory-console.vercel.app/configuration?token=secret#private");
  assert.deepEqual(result,{route:"/configuration",code:"react_hydration_418"});
  assert.equal(JSON.stringify(result).includes("secret"),false);
  assert.equal(JSON.stringify(result).includes("private"),false);
});
test("sanitize unknown and unsafe browser errors without leaking URLs",()=>{
  assert.deepEqual(safeBrowserError(Error("password=secret"),"https://example.invalid/?password=secret"),
    {route:"/",code:"browser_runtime_error"});
  assert.deepEqual(safeBrowserError(Error("oops"),"javascript:alert('private')"),
    {route:"unknown",code:"browser_runtime_error"});
});
test("redact dynamic project/run identities from browser errors",()=>{
  assert.deepEqual(
    safeBrowserError(Error("hydration failed for private project"),"https://console.example.invalid/projects/confidential-client?token=secret"),
    {route:"/projects/[key]",code:"react_hydration_unclassified"},
  );
  assert.deepEqual(
    safeBrowserError(Error("oops"),"https://console.example.invalid/runs/secret-run-identifier"),
    {route:"/runs/[id]",code:"browser_runtime_error"},
  );
  assert.deepEqual(
    safeBrowserError(Error("oops"),"https://console.example.invalid/secret-sensitive-path"),
    {route:"other",code:"browser_runtime_error"},
  );
});
test("capture retains B2 witness before visual route loop and preserves B3 failing gate",()=>{
  const source=fs.readFileSync(new URL("./capture_authenticated_console.mjs",import.meta.url),"utf8");
  assert.ok(source.indexOf("safeB2Witness({")>source.indexOf("verifyLiveConsoleAccess({"));
  assert.ok(source.indexOf("block1-b2-live-boundary-witness.json")<source.indexOf("const routes = CONSOLE_ROUTES;"));
  assert.ok(source.includes("throw new Error(`browser errors: console="));
  assert.ok(source.includes('page.on("pageerror", err => pageErrors.push(safeBrowserError'));
});
test("workflow never turns a failed B3 capture into success or skips cleanup",()=>{
  const workflow=fs.readFileSync(new URL("../.github/workflows/authenticated-visual-evidence.yml",import.meta.url),"utf8");
  assert.ok(workflow.includes("Retain sanitized B2 boundary witness even when B3 capture fails"));
  assert.ok(workflow.includes("if: always()"));
  assert.ok(workflow.includes("path: block1-b2-live-boundary-witness.json"));
  assert.ok(workflow.includes("if-no-files-found: ignore"));
  assert.ok(workflow.includes('if: steps.capture_console.outcome == \'success\''));
  assert.ok(workflow.includes('if [ "$CAPTURE_OUTCOME" = "success" ]'));
  assert.ok(workflow.includes("Finalize registry and remove ephemeral operator"));
});


test("console error retains only route class, no private text, user IDs or query",()=>{
  const value=safeConsoleError(
    "Minified React error #418 secret=private-user",
    "https://ai-product-factory-console.vercel.app/configuration?email=private@example.com"
  );
  assert.deepEqual(value,{route:"/configuration",code:"react_hydration_418"});
  const generic=safeConsoleError(
    "payment token sensitive content",
    "https://ai-product-factory-console.vercel.app/projects/private-id"
  );
  assert.deepEqual(generic,{route:"/projects/[key]",code:"console_error"});
  assert.ok(!JSON.stringify(generic).includes("private-id"));
});
test("HTTP failure retains status and safe route taxonomy, no private URL",()=>{
  const output=safeHttpFailure({
    status:403,
    requestUrl:"https://ai-product-factory-console.vercel.app/api/private?token=secret",
    pageUrl:"https://ai-product-factory-console.vercel.app/configuration?email=private"
  });
  assert.deepEqual(output,{route:"/configuration",resource:"other",status:403});
  assert.equal(JSON.stringify(output).includes("secret"),false);
  assert.equal(JSON.stringify(output).includes("email"),false);
  for(const status of [200,399,600,NaN,"500"]){
    assert.throws(()=>safeHttpFailure({
      status,requestUrl:"https://example.invalid",pageUrl:"https://example.invalid"
    }),/http_diagnostic_invalid/);
  }
});
test("capture records only allowlisted browser error and failed HTTP fields",()=>{
  const source=fs.readFileSync(new URL("./capture_authenticated_console.mjs",import.meta.url),"utf8");
  assert.ok(source.includes('consoleErrors.push(safeConsoleError(msg.text(),page.url()))'));
  assert.ok(source.includes('badResponses.push(safeHttpFailure({status:response.status(),requestUrl:response.url(),pageUrl:page.url()}))'));
  assert.ok(source.includes('pageErrors.push(safeBrowserError(err,page.url()))'));
  assert.ok(!source.includes('consoleErrors.push({url:page.url(),text:msg.text()})'));
  assert.ok(!source.includes('badResponses.push({pageUrl:page.url(),status:response.status(),url:response.url()})'));
});
