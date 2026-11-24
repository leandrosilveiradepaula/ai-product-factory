/** Regression for actual 2026-11-15 authenticated B3 failure.
 * No database writes, no forged states, no reduced browser quality gate.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";

const source=async path=>readFile(new URL("../"+path,import.meta.url),"utf8");

test("project detail has no random SSR input and control sends stable confirmed UUID",async()=>{
 const page=await source("apps/console/app/projects/[key]/page.tsx");
 const control=await source("apps/console/app/projects/[key]/control-confirm.tsx");
 assert.ok(!page.includes("crypto.randomUUID()"),"Server component must not generate random render values");
 assert.ok(!page.includes('name="command_id"'),"ID is owned by client form");
 assert.match(control,/name="command_id" defaultValue=""/);
 assert.match(control,/useRef<HTMLInputElement>\(null\)/);
 assert.match(control,/onSubmit=\{event=>/);
 assert.ok(!control.includes("onClick={event=>"));
 assert.match(control,/commandId\.current\.value=crypto\.randomUUID\(\)/);
 assert.match(control,/!commandId\.current\.value/);
 const confirmation=control.indexOf("window.confirm(");
 const cancellation=control.indexOf("event.preventDefault()");
 const generate=control.indexOf("commandId.current.value=crypto.randomUUID()");
 assert.ok(confirmation>=0&&cancellation>confirmation&&generate>cancellation);
 assert.match(page,/String\(formData\.get\("command_id"\)\|\|""\)/);
 assert.match(page,/ProjectControlForm/);
 const audit=await source("scripts/project_control_readonly_contract.mjs");
 assert.match(audit,/form.commandId !== ""/);
});
test("empty human decision state is independent of real GitHub integration actions",async()=>{
 const api=await source("apps/console/app/api/human-attention/route.ts");
 const gates=await source("apps/console/app/gates/page.tsx");
 const browser=await source("scripts/verify_block1_b3_real_console_state_matrix.mjs");
 assert.match(api,/const pendingHumanGateCount=pending\.length/);
 assert.match(api,/const pendingIntegrationActionCount=/);
 assert.match(api,/count,pendingHumanGateCount/);
 assert.match(gates,/pending\.length===0\?<div className="humanGateEmpty" role="status">/);
 assert.match(gates,/githubAppActionPending/);
 assert.match(browser,/payload\.pendingHumanGateCount!==0/);
 assert.match(browser,/page\.locator\("\.humanGateEmpty/);
 assert.ok(!browser.includes("payload.count!==0"));
 assert.ok(!browser.includes("context.route("));
 assert.match(browser,/await navigate\(page,origin\+"\/gates"/);
});
test("real decision inbox proof uses current semantic H1, not fixed UX copy",async()=>{
 const page=await source("apps/console/app/gates/page.tsx");
 const browser=await source("scripts/verify_block1_b3_real_console_state_matrix.mjs");
 // A real H1 exists on the first-party inbox, but its words are not a
 // security/health criterion; changing copy must not invalidate real proof.
 assert.match(page,/<PageHeader[^\n]*title="[^"]+"/);
 assert.ok(browser.includes('await navigate(page,origin+"/gates",{stage:"gates"})'));
 assert.ok(browser.includes('getByRole("heading",{level:1}).first()'));
 assert.ok(browser.includes("b3_real_states_gate_heading_missing"));
 assert.ok(!browser.includes('heading:"Decisões que precisam de você"'));
 assert.ok(!browser.includes('heading:"O que depende de você"'));
 assert.ok(browser.includes('payload.pendingHumanGateCount!==0'));
 assert.ok(browser.includes(".humanGateEmpty[role='status']"));
 assert.ok(!browser.includes("context.route("));
});
test("original real-state producer and browser quality gates remain fail closed",async()=>{
 const sourceBrowser=await source("scripts/capture_authenticated_console.mjs");
 const producer=await source("scripts/verify_block1_b3_real_console_state_matrix.mjs");
 assert.match(producer,/REQUIRED=\["success","empty","loading","denied","notFound","connectionError","recovered"\]/);
 assert.match(producer,/mutatingRequests!==0\|\|interceptions!==0\|\|unexpectedPageErrors!==0/);
 assert.match(sourceBrowser,/throw new Error\(`browser errors:/);
 assert.match(sourceBrowser,/block1-b3-real-states-witness\.json/);
 assert.match(sourceBrowser,/independentCriterionCertified:false/); // real witness cannot self-certify
});
