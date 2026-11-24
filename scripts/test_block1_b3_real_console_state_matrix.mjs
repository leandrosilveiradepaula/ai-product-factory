import test from "node:test";
import assert from "node:assert/strict";
import {safeRealConsoleStateMatrix} from "./verify_block1_b3_real_console_state_matrix.mjs";

const SHA="a".repeat(40);
const SERVED="b".repeat(40);
const checks={success:true,empty:true,loading:true,denied:true,notFound:true,
              connectionError:true,recovered:true};
function params(){
  return {runId:987654,sourceCommit:SHA,targetCommit:SERVED,
          checks:{...checks},backendStatus:200,pendingHumanGateCount:0,mutatingRequests:0,
          interceptions:0,unexpectedPageErrors:0};
}
test("full real state matrix retains only bounded SHA-bound telemetry",()=>{
  const result=safeRealConsoleStateMatrix(params());
  assert.equal(result.schema,"factory-b3-authenticated-live-state-matrix-v1");
  assert.deepEqual(result.checks,checks);
  assert.equal(result.fullUserExperienceCertified,true);
  assert.equal(result.pendingHumanGateCount,0);
  assert.equal(result.sources.empty,"authenticated_first_party_empty_human_decision_inbox");
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
    x=>{x.pendingHumanGateCount=1;},
    x=>{delete x.pendingHumanGateCount;},
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
  assert.ok(script.includes("loadingLink.click("),"loading must be verified on a real client transition");
  assert.ok(script.includes('url.pathname==="/runs"'),"real route GET must be observed");
  assert.ok(script.includes("loadingRouteRequests===0"),"cached fixture must not certify loading");
  assert.ok(script.includes("await openRealRunsLink(page)"),"advanced navigation must be genuinely opened");
  assert.ok(!script.includes('await page.goto(origin+"/",{waitUntil:"domcontentloaded"'));
  const nav=await fs.readFile(new URL("../apps/console/app/nav.tsx",import.meta.url),"utf8");
  assert.ok(nav.includes("<Link prefetch={false}"),"authenticated dynamic nav must not prefetch");
  assert.ok(nav.includes("onNavigate?.(href)"),"real offline nav intent must be kept");
  const shell=await fs.readFile(new URL("../apps/console/app/shell.tsx",import.meta.url),"utf8");
  assert.ok(shell.includes('window.addEventListener("offline",handleOffline)'));
  assert.ok(shell.includes('pendingTransportRoute.current=href'));
  assert.ok(shell.includes('router.push(requested)'));
  assert.ok(shell.includes('className="card consoleRouteError" role="alert"'));
  assert.ok(shell.includes("onClick={retryTransport}"));
  assert.ok(script.includes("context.setOffline(true)"));
  assert.ok(script.includes("context.setOffline(false)"));
  assert.ok(script.includes("/api/human-attention"));
  assert.ok(script.includes('".humanGateEmpty[role=\'status\']"'));
  assert.ok(script.includes('origin+"/gates"'));
  assert.ok(!script.includes("payload.count!==0"));
  assert.ok(script.includes('origin+"/api/runs/"+EMPTY_UUID'));
  assert.ok(script.includes('missingApi.status()!==404'));
  assert.ok(script.includes('missingPage.status()'));
  assert.ok(script.includes('missingBody.status!=="not_found"'));
  assert.ok(script.includes("Usuário sem permissão"));
  assert.ok(script.includes('error.getByRole("button"'),"transport retry must be scoped to its actual error alert");
  assert.ok(!/\.route\s*\(|\.fulfill\s*\(|\.intercept\s*\(/.test(script));
  assert.ok(!script.includes("credentials:"));
  const api=await fs.readFile(new URL("../apps/console/app/api/runs/[id]/route.ts",import.meta.url),"utf8");
  assert.ok(api.includes("requireConsoleOperator()"));
  assert.ok(api.includes("getRunExistenceForOperator(id)"));
  assert.ok(api.includes('status:exists?200:404'));
  assert.ok(api.includes('status:503'));
  assert.ok(!api.includes("route.fulfill"));
});

test("overview and shared action links do not prefetch authenticated dynamic routes",async()=>{
 const fs=await import("node:fs/promises");
 const home=await fs.readFile(new URL("../apps/console/app/page.tsx",import.meta.url),"utf8");
 const ui=await fs.readFile(new URL("../apps/console/app/ui.tsx",import.meta.url),"utf8");
 const proof=await fs.readFile(new URL("./verify_block1_b3_real_console_state_matrix.mjs",import.meta.url),"utf8");
 assert.ok(!/<Link\s+(?!prefetch=)/.test(home),"all Home links must be explicitly non-prefetched");
 assert.ok(ui.includes('href={href} prefetch={false}'));
 assert.ok(proof.includes('page.waitForLoadState("networkidle"'));
 assert.ok(proof.includes('loadingRouteRequests=0;\n    browserClient='));
});
