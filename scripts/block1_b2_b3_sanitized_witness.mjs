/** Conservative evidence and diagnostics: no cookies, tokens, IDs or page contents. */
const SHA=/^[0-9a-f]{40}$/;
import {B2_PROTECTED_ROUTES} from "./verify_block1_b2_live_console_access.mjs";
const B2_ROUTES=B2_PROTECTED_ROUTES;
export function safeB2Witness({observation,runId,sourceCommit,targetCommit}){
  if(!observation||observation.schema!=="factory-b2-live-console-access-boundaries-v1"
    || !Number.isSafeInteger(Number(runId))||Number(runId)<1
    || !SHA.test(String(sourceCommit))||!SHA.test(String(targetCommit))
    || !Array.isArray(observation.anonymousRouteDenials)
    || observation.anonymousRouteDenials.length!==B2_ROUTES.length
    || observation.anonymousRouteDenials.some((v,i)=>v?.route!==B2_ROUTES[i]||v?.denied!==true)
    || observation.anonymousApiDenied!==true
    || observation.operatorReadOnlyApiAllowed!==true
    || observation.operatorAdminPageDenied!==true
    || observation.invalidSessionRouteDenied!==true
    || observation.invalidSessionApiDenied!==true
    || observation.mutatingRequests!==0
    || observation.productionWrites!==0
    || observation.signedJwtClaimsIndependentlyVerified!==false
    || observation.crossTenantIsolationCertified!==false
    || observation.fullAuthnAuthzCertified!==false
    || observation.fullDataBoundariesCertified!==false)
    throw Error("b2_witness_incomplete");
  // Construct allowlisted values rather than persisting arbitrary browser output.
  return {
    schema:"factory-b2-live-console-witness-sanitized-v1",
    runId:Number(runId),sourceCommit,targetCommit,
    checks:{
      anonymousRoutes:B2_ROUTES.map(route=>({route,denied:true})),
      anonymousApiDenied:true,
      operatorReadOnlyApiAllowed:true,
      operatorAdminPageDenied:true,
      invalidSessionRouteDenied:true,
      invalidSessionApiDenied:true,
    },
    scope:"authenticated_http_route_witness_only",
    authorizationBoundaryCertified:false,
    crossTenantIsolationCertified:false,
    signedJwtClaimsIndependentlyVerified:false,
    visualAuditPassed:false,
    credentialOrUserDataRetained:false,
    productionWrites:0,
  };
}
// Console messages and HTTP URLs may contain private text or query strings.
// Preserve only a fixed route taxonomy and an error class, never raw strings.
export function safeConsoleError(message,currentUrl){
  const parsed=safeBrowserError(message,currentUrl);
  return {route:parsed.route,code:parsed.code==="browser_runtime_error"
    ?"console_error":parsed.code};
}
export function safeHttpFailure({status,requestUrl,pageUrl}){
  if(!Number.isInteger(status)||status<400||status>599)
    throw Error("http_diagnostic_invalid");
  return {
    route:safeBrowserError(null,pageUrl).route,
    resource:safeBrowserError(null,requestUrl).route,
    status,
  };
}

export function safeBrowserError(error,currentUrl){
  let route="unknown";
  try{
    const url=new URL(currentUrl);
    const publicRoutes=new Set([
      "/","/login","/unauthorized","/configuration","/projects",
      "/gates","/runs","/queue","/agents","/orchestration",
      "/evals","/deployments","/usage","/audit","/admin/operators",
    ]);
    if(url.protocol==="https:"){
      if(publicRoutes.has(url.pathname))route=url.pathname;
      else if(/^\/projects\/[^/]+(?:\/.*)?$/.test(url.pathname))
        route="/projects/[key]";
      else if(/^\/runs\/[^/]+(?:\/.*)?$/.test(url.pathname))
        route="/runs/[id]";
      else route="other";
    }
  }catch{}
  const raw=String(error?.message||error||"");
  let code="browser_runtime_error";
  if(/Minified React error #418/.test(raw))code="react_hydration_418";
  else if(/Minified React error #[0-9]+/.test(raw))code="react_other_minified_error";
  else if(/hydration/i.test(raw))code="react_hydration_unclassified";
  return {route,code};
}
