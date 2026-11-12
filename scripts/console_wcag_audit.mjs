// Executed axe-core/Chromium WCAG checks; no private page data are retained.
import {CONSOLE_ROUTES} from "./console_surface_coverage_contract.mjs";
export const WCAG_TAGS=Object.freeze(["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]);
export const ENGINE="@axe-core/playwright@4.14.0";
const routes=new Set(CONSOLE_ROUTES.map(r=>r.name));
const SHA=/^[0-9a-f]{40}$/;

// The browser screenshot contract intentionally labels mobile captures with
// "-mobile". Axe evidence uses canonical route names, so normalize by *both*
// the exact source name and path. Unknown or mismatched routes fail closed.
export function canonicalMobileWcagRoute(captureName, path){
  const matches=CONSOLE_ROUTES.filter(r=>
    captureName===r.name+"-mobile" && path===r.path);
  if(matches.length!==1)throw Error("wcag_mobile_route_identity_invalid");
  return matches[0].name;
}

export function sanitizeAxeScan({results,route,viewport}){
  const routeOK=(routes.has(route)&&["desktop","mobile","mobile-menu"].includes(viewport))||
    (route==="project-detail"&&["detail-desktop","detail-mobile"].includes(viewport));
  if(!routeOK)throw Error("wcag_scan_unknown_surface");
  if(!results||typeof results!=="object"||
     !["violations","passes","incomplete"].every(k=>Array.isArray(results[k])))
    throw Error("wcag_scan_missing_result");
  if(results.violations.length){
    const ids=[...new Set(results.violations.map(r=>String(r?.id||"unknown")
      .replace(/[^a-z0-9-]/g,"").slice(0,50)))].sort();
    throw Error("wcag_violations:"+route+":"+viewport+":"+ids.join(",").slice(0,300));
  }
  if(results.incomplete.length){
    const unresolved=[...new Set(results.incomplete.map(r=>String(r?.id||"unknown")
      .replace(/[^a-z0-9-]/g,"").slice(0,50)))].sort();
    throw Error("wcag_unresolved_rules:"+route+":"+viewport+":"+unresolved.join(",").slice(0,200));
  }
  const contrasts=results.passes.filter(r=>r?.id==="color-contrast");
  const contrastNodes=contrasts.reduce((n,r)=>n+(Array.isArray(r.nodes)?r.nodes.length:0),0);
  if(!results.passes.length||contrastNodes<1)
    throw Error("wcag_contrast_not_executed:"+route+":"+viewport);
  return {route,viewport,axeRulesPassed:results.passes.length,contrastNodes,
    violations:0,unresolvedContrast:0};
}

export function finishAxeAudit({scans,runId,sourceCommit,targetCommit,keyboardSkip}){
  if(!Number.isSafeInteger(Number(runId))||Number(runId)<1||
     !SHA.test(String(sourceCommit))||!SHA.test(String(targetCommit))||
     !Array.isArray(scans))throw Error("wcag_identity_invalid");
  const names=CONSOLE_ROUTES.map(r=>r.name);
  const expected=[...names.map(n=>n+"|desktop"),...names.map(n=>n+"|mobile"),
    ...names.map(n=>n+"|mobile-menu"),"project-detail|detail-desktop","project-detail|detail-mobile"];
  if(scans.length!==expected.length||
      JSON.stringify(scans.map(s=>s.route+"|"+s.viewport).sort())!==JSON.stringify(expected.sort())||
      scans.some(s=>!Number.isSafeInteger(s.axeRulesPassed)||s.axeRulesPassed<1||
        !Number.isSafeInteger(s.contrastNodes)||s.contrastNodes<1||
        s.violations!==0||s.unresolvedContrast!==0)||
      !keyboardSkip||keyboardSkip.reachedWithTab!==true||
      keyboardSkip.visibleOnFocus!==true||keyboardSkip.landedOnMain!==true)
    throw Error("wcag_coverage_incomplete");
  return {schema:"factory-b3-wcag22-aa-keyboard-audit-v1",
    runId:Number(runId),sourceCommit,targetCommit,routeNames:names,
    engine:ENGINE,tags:[...WCAG_TAGS],desktopScans:names.length,
    mobileScans:names.length,mobileMenuScans:names.length,projectDetailScans:2,
    contrastNodes:scans.reduce((sum,s)=>sum+s.contrastNodes,0),
    axeRulePasses:scans.reduce((sum,s)=>sum+s.axeRulesPassed,0),
    keyboardSkipVerified:true,keyboardFocusVisible:true,
    productionWrites:0,paidCalls:0,personalDataRetained:false,
    fullWcagCertified:false,allRolesCertified:false};
}
