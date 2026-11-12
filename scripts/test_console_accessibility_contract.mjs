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

test("real #73 axe: named regions and no prohibited ARIA labels on generic elements",async()=>{
  const fs=await import("node:fs");
  const path=await import("node:path");
  const read=file=>fs.readFileSync(path.resolve(import.meta.dirname,"..",file),"utf8");
  const home=read("apps/console/app/page.tsx"),ui=read("apps/console/app/ui.tsx");
  assert.match(home,/<section className="homeSummary" aria-label="Resumo operacional">/);
  assert.doesNotMatch(home,/<div className="homeSummary" aria-label=/);
  assert.doesNotMatch(ui,/<span className=\{resolved\?"pill "\+resolved:"pill"\} aria-label=/);
  assert.match(ui,/<span className="visuallyHiddenStatus">\{spokenLabel\}<\/span>/);
  for(const [file,selector] of [
    ["apps/console/app/projects/[key]/page.tsx","macroLifecycle"],
    ["apps/console/app/projects/new/page.tsx","intakeSteps"],
    ["apps/console/app/projects/new/review/page.tsx","intakeSteps"],
    ["apps/console/app/runs/[id]/page.tsx","runStageRail"],
  ])assert.ok(read(file).includes('className="'+selector+'" role="group" aria-label='),
    "generic element lacks a permitted ARIA grouping role: "+file);
});

test("real #73 axe: textual surfaces have solid measurable contrast",async()=>{
  const fs=await import("node:fs");
  const path=await import("node:path");
  const css=fs.readFileSync(path.resolve(import.meta.dirname,"../apps/console/app/globals.css"),"utf8");
  const lines=css.split("\n");
  for(const [selector,bg] of [
    [".homeFocus{","#1b2740"],[".homeFocus.warning{","#2c2419"],
    [".gateContextHero{","#151a24"],[".planningDecisionItem{","#101722"],
    [".card{","var(--color-card-start)"],["body{","var(--color-canvas-top)"],
    [".topbar{","var(--color-topbar)"],
  ]){
    const matching=lines.filter(line=>line.startsWith(selector));
    assert.ok(matching.length>0,"missing "+selector);
    assert.ok(matching.some(line=>line.includes("background:"+bg)),"missing solid "+selector);
    assert.ok(matching.every(line=>!/background:[^;}]*gradient|background-image:/.test(line)),
      "cannot automatically assess text over gradient at "+selector);
  }
  // A solid parent can still leave the text-bearing children unresolved by axe.
  // Guard the actual Overview breadcrumb and environment elements separately.
  for(const selector of [".topbarTrail{",".topbarEnvironment{"]){
    const matching=lines.filter(line=>line.startsWith(selector));
    assert.equal(matching.length,1,"expected exactly one "+selector);
    assert.ok(matching[0].includes("background:var(--color-topbar)"),
      "text-bearing topbar surface must paint its own solid background: "+selector);
    assert.ok(!/rgba\(|gradient\(|backdrop-filter/.test(matching[0]),
      "text-bearing topbar surface cannot rely on a composited background: "+selector);
  }
  const topbar=lines.filter(line=>line.startsWith(".topbar{"));
  assert.ok(topbar.every(line=>!line.includes("rgba(")&&!line.includes("backdrop-filter")),
    "the overview trail and environment label require an opaque measurable topbar");
  const L=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255)
    .map(c=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4)
    .reduce((a,c,i)=>a+c*[.2126,.7152,.0722][i],0);
  const contrast=(a,b)=>{const x=L(a),y=L(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
  for(const foreground of ["#a8b5c7","#a9b2c4","#dfe2ef"])
    assert.ok(contrast(foreground,"#171a24")>=4.5,
      "topbar text must meet WCAG AA on the painted solid background");
  for(const [fg,bg]of [["#b8c4d6","#1b2740"],["#adc6ff","#1b2740"],
    ["#ffdf8a","#2c2419"],["#f1f5fd","#2c2419"]])
    assert.ok(contrast(fg,bg)>=4.5,fg+" does not meet AA on "+bg);
  assert.match(css,/\.visuallyHiddenStatus\{[^}]*clip-path:inset\(50%\)/);
});

test("axe unresolved checks stay strict and redact sensitive DOM content",()=>{
  const incomplete={violations:[],passes:[{id:"color-contrast",nodes:[{}]}],
    incomplete:[{id:"color-contrast",nodes:[{target:['[data-id="sensitive@client.example"]'],
      html:"sensitive@client.example",any:[{id:"color-contrast",
        data:{reason:"bgGradient"},message:"sensitive@client.example"}]}]}]};
  assert.throws(()=>sanitizeAxeScan({results:incomplete,route:"overview",viewport:"desktop"}),
    error=>error.message.includes("color-contrast(1:color-contrast/bggradient)") &&
      !error.message.includes("sensitive@client.example") &&
      !error.message.includes("data-id"));
});
