import test from "node:test";
import assert from "node:assert/strict";
import {verifyAccessibilitySnapshot} from "./console_accessibility_contract.mjs";
import {sanitizeAxeScan,finishAxeAudit,canonicalMobileWcagRoute} from "./console_wcag_audit.mjs";
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

test("real mobile screenshot IDs normalize to canonical WCAG scan identities",()=>{
  const results={violations:[],incomplete:[],
    passes:[{id:"color-contrast",nodes:[{}]},{id:"label",nodes:[{}]}]};
  const desktop=CONSOLE_ROUTES.map(r=>sanitizeAxeScan({
    results,route:r.name,viewport:"desktop",
  }));
  const mobileCaptures=CONSOLE_ROUTES.map(r=>({name:r.name+"-mobile",path:r.path}));
  const scans=[...desktop];
  for(const capture of mobileCaptures){
    const canonical=canonicalMobileWcagRoute(capture.name,capture.path);
    scans.push(sanitizeAxeScan({results,route:canonical,viewport:"mobile"}));
    scans.push(sanitizeAxeScan({results,route:canonical,viewport:"mobile-menu"}));
    assert.throws(()=>sanitizeAxeScan({results,route:capture.name,viewport:"mobile"}),/wcag_scan_unknown_surface/);
    assert.throws(()=>canonicalMobileWcagRoute(capture.name,capture.path+"/mismatch"),/wcag_mobile_route_identity_invalid/);
  }
  scans.push(sanitizeAxeScan({results,route:"project-detail",viewport:"detail-desktop"}));
  scans.push(sanitizeAxeScan({results,route:"project-detail",viewport:"detail-mobile"}));
  const witness=finishAxeAudit({
    scans,runId:1374,sourceCommit:"a".repeat(40),targetCommit:"b".repeat(40),
    keyboardSkip:{reachedWithTab:true,visibleOnFocus:true,landedOnMain:true},
  });
  assert.equal(scans.length,CONSOLE_ROUTES.length*3+2);
  assert.equal(witness.mobileScans,CONSOLE_ROUTES.length);
  assert.equal(witness.mobileMenuScans,CONSOLE_ROUTES.length);
  assert.equal(witness.contrastNodes,scans.length);
  for(const alias of ["overview","overview-mobile-mobile","../overview-mobile","projects-mobile/"])
    assert.throws(()=>canonicalMobileWcagRoute(alias,"/"),/wcag_mobile_route_identity_invalid/);
});

test("real Overview WCAG contrast and decision accessible name regressions",async()=>{
  // This guards code after the real authenticated axe finding #43132580946.
  // It is not a replacement for a real WCAG browser run.
  const fs=await import("node:fs");
  const path=await import("node:path");
  const root=path.resolve(import.meta.dirname,"..");
  const theme=fs.readFileSync(path.join(root,"apps/console/app/theme.css"),"utf8");
  const css=fs.readFileSync(path.join(root,"apps/console/app/globals.css"),"utf8");
  const shell=fs.readFileSync(path.join(root,"apps/console/app/shell.tsx"),"utf8");
  const token=(name)=>{
    const match=theme.match(new RegExp(name+":\\s*(#[0-9a-f]{6});","i"));
    assert.ok(match,"missing color token "+name);
    return match[1];
  };
  const luminance=(color)=>{
    const channels=[1,3,5].map(i=>Number.parseInt(color.slice(i,i+2),16)/255);
    return channels.map(v=>v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4))
      .reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
  };
  const contrast=(a,b)=>{
    const x=luminance(a),y=luminance(b);
    return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);
  };
  const backgrounds=["#0f131c","#181b25","#202530","#262a34","#273b5d"];
  for(const key of ["--color-text-subtle","--color-text-faint","--color-control-subtle"]){
    for(const bg of backgrounds){
      assert.ok(contrast(token(key),bg)>=4.5,"insufficient contrast: "+key+" against "+bg);
    }
  }
  const lowContrast=new Set([
    "#6f7a89","#677384","#697484","#596577","#657082","#73798a",
    "#555c6d","#747b8c","#7b8293","#767d8f","#697386",
    "#687386","#737e90","#6f7a8b","#777e90","#656c7c"
  ]);
  for(const match of css.matchAll(/(?:[;{]\s*)color\s*:\s*(#[0-9a-f]{6})(?=\s*[;}])/gi))
    assert.ok(!lowContrast.has(match[1].toLowerCase()),"low-contrast source foreground "+match[1]);
  assert.ok(shell.includes('className="topbarAttention active">{attention.count}'),
    "Attention link name must derive from its visible operator decision label");
  assert.ok(!/topbarAttention active"\s+aria-label=/.test(shell),
    "A contradictory aria-label must not override the visible label");
});
