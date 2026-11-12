import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {safeB3StateWitness,verifyConsoleStatesReadOnly,isExpectedFixture503ResourceError,B3SyntheticTransitionTimeout} from "./verify_block1_b3_live_console_states.mjs";
import {collectBoundedB3Fixture} from "./b3_optional_fixture_capture.mjs";
const source="a".repeat(40),target="b".repeat(40);
function sample(){return {blocked:false,browserErrors:0,mutatingRequests:0,expected503ResourceErrors:0,
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


test("Chromium expected synthetic 503 is identified ONLY for exact API URL",()=>{
 const origin="https://ai-product-factory-console.vercel.app";
 const diagnostic="Failed to load resource: the server responded with a status of 503 (Service Unavailable)";
 const msg=(text,url,type="error")=>({
   type:()=>type,text:()=>text,location:()=>({url,lineNumber:0,columnNumber:0}),
 });
 assert.equal(isExpectedFixture503ResourceError(msg(diagnostic,origin+"/api/human-attention"),origin),true);
 assert.equal(isExpectedFixture503ResourceError(msg(diagnostic,origin+"/api/other"),origin),false);
 assert.equal(isExpectedFixture503ResourceError(msg(diagnostic,origin+"/api/human-attention?token=private"),origin),false);
 assert.equal(isExpectedFixture503ResourceError(msg(diagnostic,"https://evil.example/api/human-attention"),origin),false);
 assert.equal(isExpectedFixture503ResourceError(msg("Minified React error #418",origin+"/api/human-attention"),origin),false);
 assert.equal(isExpectedFixture503ResourceError(msg("Failed to load resource: the server responded with a status of 500 (Internal Server Error)",origin+"/api/human-attention"),origin),false);
 assert.equal(isExpectedFixture503ResourceError(msg(diagnostic,origin+"/api/human-attention","warning"),origin),false);
 assert.equal(isExpectedFixture503ResourceError({type:()=> "error",text:()=>diagnostic,location:()=>({url:"not-a-url"})},origin),false);
});
test("a counted fixture resource 503 is transparent, bounded, and never certifies B3",()=>{
 const row={...sample(),expected503ResourceErrors:1};
 const proof=build(row);
 assert.equal(proof.expected503ResourceConsoleErrors,1);
 assert.equal(proof.visualAuditPassed,false);
 assert.equal(proof.independentCriterionCertified,false);
 assert.equal(proof.actualBackendStateCertified,false);
 for(const changes of [
  {expected503ResourceErrors:2},
  {expected503ResourceErrors:-1},
  {expected503ResourceErrors:"1"},
  {browserErrors:1},
  {mutatingRequests:1},
 ]){
  assert.throws(()=>build({...row,...changes}),/b3_state_witness_incomplete/);
 }
});
test("source prevents silencing genuine hydration errors and enforces 503 allowance",()=>{
 const source=fs.readFileSync(new URL("./verify_block1_b3_live_console_states.mjs",import.meta.url),"utf8");
 assert.match(source,/page.on\("pageerror",\(\)=>\{observed.browserErrors\+\+;/);
 assert.match(source,/observed.expected503ResourceErrors<observed.hits.unavailable/);
 assert.match(source,/observed.browserErrors\+\+;/);
 assert.match(source,/isExpectedFixture503ResourceError\(m,origin\)/);
});

test("actual authenticated decision-link DOM survives all four B3 state transitions",async()=>{
  // #43138746238 timed out because a stale aria-label selector disagreed
  // with the accessible visible name delivered by PR #1380.
  // Exercise the real production waitForFunction callbacks, not a duplicate.
  const origin="https://ai-product-factory-console.vercel.app";
  const savedDocument=globalThis.document;
  let state=null, handler=null, phase=0;
  const selectors=[];
  const page={
    on(){},
    async route(_pattern,callback){handler=callback;},
    async goto(url){
      assert.equal(url,origin+"/");
      await requestState();
      return {status:()=>200};
    },
    url:()=>origin+"/",
    async waitForFunction(callback){
      const result=callback();
      assert.equal(result,true,"rendered control did not match state "+JSON.stringify(state));
      phase++;
    },
    async evaluate(callback){
      assert.match(String(callback),/dispatchEvent/);
      await requestState();
    },
    async close(){},
  };
  const context={async newPage(){return page;}};
  async function requestState(){
    assert.equal(typeof handler,"function");
    await handler({
      request:()=>({method:()=>"GET",url:()=>origin+"/api/human-attention"}),
      fulfill:async({status,body})=>{
        state={status,body:JSON.parse(body)};
      },
      abort:async()=>{throw Error("unexpected abort");},
    });
  }
  globalThis.document={querySelector(selector){
    selectors.push(selector);
    const pending=state?.body?.status==="ok"&&state.body.count===2;
    const unavailable=state?.status===503||
      (state?.body?.status==="ok"&&state.body.count===-1);
    if(selector==='a.topbarAttention.active[href="/gates"]'&&pending)
      return {textContent:"2 decisões pendentes",hasAttribute:()=>false};
    if(selector===".desktopSidebarContent .humanAttentionCount"&&pending)
      return {textContent:"2"};
    if(selector==='.topbarAttention[role="status"]'&&unavailable)
      return {textContent:"Aprovações indisponíveis"};
    return null;
  }};
  try{
    const result=await verifyConsoleStatesReadOnly({
      context,baseUrl:origin,runId:43138746238,
      sourceCommit:source,targetCommit:target,
    });
    assert.deepEqual(result.checks,{pending:true,unavailable:true,cleared:true,malformed:true});
    assert.equal(result.visualAuditPassed,false);
    assert.equal(result.actualBackendStateCertified,false);
    assert.equal(phase,4);
    assert.ok(selectors.includes('a.topbarAttention.active[href="/gates"]'));
    assert.ok(!selectors.some(s=>s.includes("aria-label=") && s.includes("aprovações humanas")));
  }finally{
    if(savedDocument===undefined)delete globalThis.document;
    else globalThis.document=savedDocument;
  }
});

test("the real independent WCAG capture is not blocked by missing SYNTHETIC B3 state",async()=>{
  const transitions=["pending","unavailable","cleared","malformed"];
  for(const transition of transitions){
    let writes=0;
    const reports=[];
    const result=await collectBoundedB3Fixture({
      observe:async()=>{throw new B3SyntheticTransitionTimeout(transition);},
      save:async()=>{writes++;},
      report:message=>reports.push(message),
    });
    assert.equal(result,null);
    assert.equal(writes,0,"no invented state witness can be persisted");
    assert.deepEqual(reports,[{
      status:"b3_synthetic_ui_transition_not_observed",transition,
      actualBackendStateCertified:false,fullUserExperienceCertified:false,
      independentCriterionCertified:false,visualAuditPassed:false,
    }]);
  }
});

test("valid bounded synthetic state remains durable but never grants accessibility PASS",async()=>{
  const witness=build();
  const persisted=[];
  const result=await collectBoundedB3Fixture({
    observe:async()=>witness,
    save:async row=>persisted.push(row),
    report:()=>{throw Error("unexpected partial report");},
  });
  assert.equal(result,witness);
  assert.deepEqual(persisted,[witness]);
  assert.equal(result.actualBackendStateCertified,false);
  assert.equal(result.independentCriterionCertified,false);
  assert.equal(result.visualAuditPassed,false);
});

test("real navigation, authorization, browser, malformed state and persistence errors remain fatal",async()=>{
  const errors=[
    new Error("b3_authenticated_landing_unavailable"),
    Object.assign(new Error("navigation timeout"),{name:"TimeoutError"}),
    new Error("b3_state_witness_incomplete:unexpected_browser_error"),
    new Error("b3_state_witness_incomplete:unexpected_mutation"),
    new TypeError("unexpected script failure"),
  ];
  for(const original of errors){
    let reported=false, saved=false;
    await assert.rejects(collectBoundedB3Fixture({
      observe:async()=>{throw original;},
      save:async()=>{saved=true;},
      report:()=>{reported=true;},
    }),error=>error===original);
    assert.equal(reported,false);
    assert.equal(saved,false);
  }
  const persistenceError=new Error("artifact storage failed");
  await assert.rejects(collectBoundedB3Fixture({
    observe:async()=>build(),
    save:async()=>{throw persistenceError;},
    report:()=>{},
  }),error=>error===persistenceError);
});

test("only a synthetic DOM wait timeout gets the dedicated failure classification",async()=>{
  const origin="https://ai-product-factory-console.vercel.app";
  const timeout=()=>Object.assign(new Error("Timeout 20000ms exceeded"),{name:"TimeoutError"});
  const failedPage={
    on(){},
    async route(){},
    async goto(){return {status:()=>200};},
    url:()=>origin+"/",
    async waitForFunction(){throw timeout();},
    async close(){},
  };
  await assert.rejects(verifyConsoleStatesReadOnly({
    context:{async newPage(){return failedPage;}},baseUrl:origin,
    runId:123,sourceCommit:source,targetCommit:target,
  }),error=>error instanceof B3SyntheticTransitionTimeout &&
    error.transition==="pending" && error.message==="b3_synthetic_transition_not_observed:pending");

  const navigationTimeout=timeout();
  const inaccessiblePage={...failedPage,async goto(){throw navigationTimeout;}};
  await assert.rejects(verifyConsoleStatesReadOnly({
    context:{async newPage(){return inaccessiblePage;}},baseUrl:origin,
    runId:123,sourceCommit:source,targetCommit:target,
  }),error=>error===navigationTimeout);
});

test("WCAG is independent of synthetic states while the actual browser gate remains strict",()=>{
  const capture=fs.readFileSync(new URL("./capture_authenticated_console.mjs",import.meta.url),"utf8");
  const observer=fs.readFileSync(new URL("./verify_block1_b3_live_console_states.mjs",import.meta.url),"utf8");
  assert.ok(capture.includes('import {collectBoundedB3Fixture} from "./b3_optional_fixture_capture.mjs"'));
  assert.ok(capture.indexOf("collectBoundedB3Fixture({") <
    capture.indexOf("const routes = CONSOLE_ROUTES;"));
  assert.ok(capture.indexOf("const routes = CONSOLE_ROUTES;") <
    capture.indexOf("const results=await new AxeBuilder({page})"));
  assert.ok(capture.includes('await scanCurrentPage(route.name,"desktop")'));
  assert.ok(capture.includes("await fs.writeFile(\"block1-b3-wcag-accessibility-witness.json\""));
  assert.ok(capture.includes("const wcag=finishAxeAudit("));
  assert.match(observer,/await requireSyntheticTransition\(page,"pending"/);
  assert.match(observer,/await requireSyntheticTransition\(page,"malformed"/);
  assert.match(observer,/if\(error\?\.name!=="TimeoutError"\)throw error;/);
});

test("synthetic transition timeout cannot mask real browser hydration or mutation failures",async()=>{
  const origin="https://ai-product-factory-console.vercel.app";
  const timeout=()=>Object.assign(new Error("Timeout 20000ms exceeded"),{name:"TimeoutError"});
  for(const eventName of ["pageerror","request"]){
    const page={
      on(event,handler){
        if(event!==eventName)return;
        if(eventName==="pageerror")handler(new Error("hydration error"));
        else handler({url:()=>origin+"/api/human-attention",method:()=>"POST"});
      },
      async route(){},
      async goto(){return {status:()=>200};},
      url:()=>origin+"/",
      async waitForFunction(){throw timeout();},
      async close(){},
    };
    await assert.rejects(verifyConsoleStatesReadOnly({
      context:{async newPage(){return page;}},baseUrl:origin,
      runId:123,sourceCommit:source,targetCommit:target,
    }),/b3_state_witness_incomplete:unexpected_browser_error_or_mutation/);
  }
});
