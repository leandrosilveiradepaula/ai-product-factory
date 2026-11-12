import test from "node:test";
import assert from "node:assert/strict";
import {verifyAccessibilitySnapshot} from "./console_accessibility_contract.mjs";
import {sanitizeAxeScan,finishAxeAudit} from "./console_wcag_audit.mjs";
import {CONSOLE_ROUTES} from "./console_surface_coverage_contract.mjs";

const good = Object.freeze({
  language:"pt-BR",hasTitle:true,mainCount:1,mainTarget:true,
  skipCount:1,skipHasName:true,h1Count:1,interactiveCount:7,
  unnamedCount:0,missingImageAlt:0,duplicateIds:0,positiveTabOrder:0,
  invalidAriaReferences:0,focusableAriaHidden:0,
});
test("a complete accessibility snapshot emits only safe counts",()=>{
  const result=verifyAccessibilitySnapshot({...good,secret:"do-not-record"},"overview");
  assert.deepEqual(result,{
    checked:true,landmarkCount:1,headingCount:1,interactiveCount:7,
    unnamedCount:0,missingImageAlt:0,duplicateIds:0,positiveTabOrder:0,
    invalidAriaReferences:0,focusableAriaHidden:0,
  });
  assert.equal(JSON.stringify(result).includes("do-not-record"),false);
});
test("fail closed on missing structure, unnamed controls and invalid keyboard order",()=>{
  const invalid={
    language:["en","document_language"],
    hasTitle:[false,"document_title"],
    mainCount:[0,"main_landmark"],
    mainTarget:[false,"main_landmark"],
    skipCount:[0,"skip_link"],
    skipHasName:[false,"skip_link"],
    h1Count:[0,"page_heading"],
    interactiveCount:[0,"interactive_inventory"],
    unnamedCount:[2,"interactive_names"],
    missingImageAlt:[1,"image_alternatives"],
    duplicateIds:[2,"unique_ids"],
    positiveTabOrder:[1,"tab_order"],
    invalidAriaReferences:[1,"aria_references"],
    focusableAriaHidden:[1,"focusable_aria_hidden"],
  };
  for(const [field,[value,code]] of Object.entries(invalid)){
    assert.throws(()=>verifyAccessibilitySnapshot({...good,[field]:value},"projects"),
      error => error.message.includes("accessibility:projects:") && error.message.includes(code),field);
  }
});
test("reject malformed or ambiguous browser data",()=>{
  for(const snapshot of [null,[],{}, {...good,interactiveCount:NaN},
    {...good,unnamedCount:-1},{...good,skipCount:"1"},{...good,mainTarget:"true"}]){
    assert.throws(()=>verifyAccessibilitySnapshot(snapshot,"overview"),/accessibility:/);
  }
  assert.throws(()=>verifyAccessibilitySnapshot(good,"../../secret"),/invalid_route/);
});

test("WCAG result must come from complete 44 live scans with contrast",()=>{
  const result={violations:[],incomplete:[],
    passes:[{id:"color-contrast",nodes:[{}]},{id:"label",nodes:[{}]}]};
  const scan=(route,viewport)=>sanitizeAxeScan({results:result,route,viewport});
  const names=CONSOLE_ROUTES.map(r=>r.name);
  const scans=[...names.map(n=>scan(n,"desktop")),
    ...names.map(n=>scan(n,"mobile")),...names.map(n=>scan(n,"mobile-menu")),
    scan("project-detail","detail-desktop"),scan("project-detail","detail-mobile")];
  const opts={scans,runId:99,sourceCommit:"a".repeat(40),targetCommit:"b".repeat(40),
    keyboardSkip:{reachedWithTab:true,visibleOnFocus:true,landedOnMain:true}};
  const audited=finishAxeAudit(opts);
  assert.equal(audited.contrastNodes,44);
  assert.equal(audited.fullWcagCertified,false);
  assert.deepEqual(audited.routeNames,names);
  assert.throws(()=>finishAxeAudit({...opts,scans:scans.slice(1)}),/coverage_incomplete/);
  for(const bad of [
    {...result,violations:[{id:"color-contrast",nodes:[{html:"private"}]}]},
    {...result,incomplete:[{id:"color-contrast"}]},
    {...result,passes:[{id:"label",nodes:[{}]}]},
  ])assert.throws(()=>sanitizeAxeScan({results:bad,route:"overview",viewport:"desktop"}),/wcag_/);
});
