/** Conservative evidence and diagnostics: no cookies, tokens, IDs or page contents. */
const SHA=/^[0-9a-f]{40}$/;
const B2_ROUTES=["/projects","/gates","/admin/operators"];
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
export function safeBrowserError(error,currentUrl){
  let route="unknown";
  try{
    const url=new URL(currentUrl);
    if(url.protocol==="https:" && url.pathname.length<=256
      && /^\/[a-zA-Z0-9_\/.-]*$/.test(url.pathname))
      route=url.pathname;
  }catch{}
  const raw=String(error?.message||error||"");
  let code="browser_runtime_error";
  if(/Minified React error #418/.test(raw))code="react_hydration_418";
  else if(/Minified React error #[0-9]+/.test(raw))code="react_other_minified_error";
  else if(/hydration/i.test(raw))code="react_hydration_unclassified";
  return {route,code};
}
