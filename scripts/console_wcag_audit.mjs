// Executed axe-core/Chromium WCAG checks; no private page data are retained.
import {CONSOLE_ROUTES} from "./console_surface_coverage_contract.mjs";
export const WCAG_TAGS=Object.freeze(["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]);
export const ENGINE="@axe-core/playwright@4.14.0";
const routes=new Set(CONSOLE_ROUTES.map(r=>r.name));
const SHA=/^[0-9a-f]{40}$/;
const SAFE_CLASS_NAMES=new Set([
  "topbar","topbarTrail","topbarMeta","topbarAttention","topbarEnvironment",
  "homeFocus","homeFocusContent","homeFocusEyebrow","homeProjects","homeSectionLink",
  "homeProjectCard","homeProjectHeading","homeProjectStage","homeProjectFooter",
  "homeSummary","homeSummaryItem","homeAttention","homeQuietStatus","attentionGrid",
  "attentionCard","attentionBanner","attentionFooter","homeTechnicalDetails",
  "overviewActivityDetails","overviewActivityBody","section","card","muted","mono",
  "pageHeader","eyebrow","title","subtitle","metricCard","metricLabel","metric",
  "metricNote","pill","linkButton","sectionHeader","emptyState","table","tableRow",
  "tableHeader","timeline","timelineItem","timelineMeta","badgeLine","technicalDetails"
]);
const SAFE_TAG_NAMES=new Set(["a","article","b","button","details","div","h1","h2","h3",
  "li","main","nav","p","section","small","span","strong","summary","table","td","th","tr"]);
const token=value=>String(value||"unknown").toLowerCase()
  .replace(/[^a-z0-9_-]/g,"").slice(0,45);

function safeColor(value){
  const text=String(value||"").trim().toLowerCase();
  return /^(transparent|rgb\([0-9, ]+\)|rgba\([0-9, .]+\))$/.test(text)?text:"other";
}
function safeOpacity(value){
  const number=Number(value);
  return Number.isFinite(number)&&number>=0&&number<=1?number:null;
}
function safeNodeSignal(value){
  if(!value||typeof value!=="object")return {resolved:false};
  const classes=Array.isArray(value.classes)?value.classes.filter(name=>SAFE_CLASS_NAMES.has(name)).slice(0,4):[];
  const tag=SAFE_TAG_NAMES.has(value.tag)?value.tag:"other";
  const style=value.style&&typeof value.style==="object"?value.style:{};
  const pseudo=value.pseudo&&typeof value.pseudo==="object"?value.pseudo:{};
  const surface={tag,classes,color:safeColor(style.color),backgroundColor:safeColor(style.backgroundColor),
    backgroundImage:style.backgroundImage==="none"?"none":"present",opacity:safeOpacity(style.opacity),
    filter:style.filter===true,backdropFilter:style.backdropFilter===true,
    mixBlendMode:style.mixBlendMode==="normal"?"normal":"non-normal"};
  const ancestors=Array.isArray(value.ancestors)?value.ancestors.slice(0,4).map(ancestor=>{
    const classes=Array.isArray(ancestor?.classes)?ancestor.classes.filter(name=>SAFE_CLASS_NAMES.has(name)).slice(0,4):[];
    return {tag:SAFE_TAG_NAMES.has(ancestor?.tag)?ancestor.tag:"other",classes,
      backgroundColor:safeColor(ancestor?.backgroundColor),
      backgroundImage:ancestor?.backgroundImage==="none"?"none":"present",opacity:safeOpacity(ancestor?.opacity)};
  }):[];
  return {resolved:value.resolved===true,surface,ancestors,pseudo:{
    before:{present:pseudo.before?.present===true,backgroundColor:safeColor(pseudo.before?.backgroundColor),backgroundImage:pseudo.before?.backgroundImage==="none"?"none":"present",contentPresent:pseudo.before?.contentPresent===true},
    after:{present:pseudo.after?.present===true,backgroundColor:safeColor(pseudo.after?.backgroundColor),backgroundImage:pseudo.after?.backgroundImage==="none"?"none":"present",contentPresent:pseudo.after?.contentPresent===true},
  }};
}

// This report is intentionally narrower than axe's result: raw targets, HTML,
// accessible names, URLs, messages and rule help are never serialised.
export function buildSafeAxeIncompleteDiagnostic({results,route,viewport,nodeSignals=[]}){
  const routeOK=(routes.has(route)&&["desktop","mobile","mobile-menu"].includes(viewport))||
    (route==="project-detail"&&["detail-desktop","detail-mobile"].includes(viewport));
  if(!routeOK||!results||!Array.isArray(results.incomplete)||!Array.isArray(nodeSignals))
    throw Error("wcag_incomplete_diagnostic_invalid");
  let signalIndex=0;
  const unresolved=results.incomplete.map(rule=>{
    const nodes=Array.isArray(rule?.nodes)?rule.nodes:[];
    return {rule:token(rule?.id),nodes:nodes.slice(0,8).map(node=>{
      const checks=[...new Set(["any","all","none"].flatMap(key=>Array.isArray(node?.[key])?node[key]:[])
        .map(check=>token(check?.id)+(typeof check?.data?.reason==="string"?"/"+token(check.data.reason):"")))].sort().slice(0,5);
      return {checks,signal:safeNodeSignal(nodeSignals[signalIndex++])};
    })};
  }).slice(0,8);
  return {schema:"factory-b3-axe-incomplete-diagnostic-v1",route,viewport,
    unresolved,diagnosticOnly:true,visualAuditPassed:false,personalDataRetained:false};
}

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
    // Public axe rule/check/reason IDs only. Never emit DOM targets, HTML,
    // labels or text. An incomplete WCAG check is still a hard failure.
    const token=value=>String(value||"unknown").toLowerCase()
      .replace(/[^a-z0-9_-]/g,"").slice(0,45);
    const unresolved=results.incomplete.map(rule=>{
      const nodes=Array.isArray(rule?.nodes)?rule.nodes:[];
      const checks=[...new Set(nodes.flatMap(node=>
        ["any","all","none"].flatMap(key=>Array.isArray(node?.[key])?node[key]:[])
          .map(check=>token(check?.id)+
            (typeof check?.data?.reason==="string"?"/"+token(check.data.reason):""))
      ))].sort().slice(0,5);
      return token(rule?.id)+"("+nodes.length+(checks.length?":"+checks.join("+"):"")+")";
    }).sort();
    throw Error("wcag_unresolved_rules:"+route+":"+viewport+":"+unresolved.join(",").slice(0,290));
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
