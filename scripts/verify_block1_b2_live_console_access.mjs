/**
 * B2: live HTTP authorization boundary observations on the exact verified
 * Console deployment. No model, write, admin API, or synthetic PASS.
 * Only status, route and boolean results are retained; never tokens/cookies.
 */
import {CONSOLE_ROUTES} from "./console_surface_coverage_contract.mjs";

// The same fourteen authenticated Console surfaces must reject anonymous users,
// plus the privileged operator-admin route. Changes to the Console inventory
// automatically expand this negative authorization audit.
export const B2_PROTECTED_ROUTES=Object.freeze([
  ...new Set([...CONSOLE_ROUTES.map(route=>route.path),"/admin/operators"]),
]);

export async function verifyLiveConsoleAccess({browser,operatorContext,baseUrl,trustedOidc}) {
  const base=new URL(baseUrl);
  if(base.protocol!=="https:" || base.username || base.password || base.search || base.hash)
    throw Error("b2_invalid_console_origin");
  const origin=base.origin;
  const noAuth=await browser.newContext({
    viewport:{width:1280,height:800},
    extraHTTPHeaders:trustedOidc?{"x-vercel-trusted-oidc-idp-token":trustedOidc}:{},
  });
  try {
    const anonymous=await noAuth.newPage();
    const protectedRoutes=B2_PROTECTED_ROUTES;
    const anonymousDenials=[];
    for(const route of protectedRoutes) {
      const response=await anonymous.goto(origin+route,{waitUntil:"domcontentloaded",timeout:60000});
      const landed=new URL(anonymous.url());
      if(!response || landed.origin!==origin || landed.pathname!=="/login")
        throw Error("b2_anonymous_route_not_denied:"+route);
      anonymousDenials.push({route,denied:true});
    }
    const anonymousApi=await noAuth.request.get(origin+"/api/human-attention",{
      maxRedirects:0,timeout:30000,
    });
    if(![301,302,303,307,308,401,403].includes(anonymousApi.status()))
      throw Error("b2_anonymous_api_not_denied");
    if([301,302,303,307,308].includes(anonymousApi.status())) {
      const location=anonymousApi.headers()["location"]||"";
      const target=new URL(location,origin);
      if(target.origin!==origin || target.pathname!=="/login")
        throw Error("b2_anonymous_api_redirect_not_login");
    }
    // A tampered cookie must not be accepted as an authenticated operator.
    // Never copy, decode, persist or log a real operator token for this check.
    await noAuth.addCookies([{name:"factory_access_token",value:"invalid-unsigned-factory-session",url:origin}]);
    const invalidSessionPage=await noAuth.newPage();
    const invalidPageResponse=await invalidSessionPage.goto(origin+"/projects",{
      waitUntil:"domcontentloaded",timeout:60000,
    });
    if(!invalidPageResponse || new URL(invalidSessionPage.url()).pathname!=="/login")
      throw Error("b2_invalid_session_route_accepted");
    const invalidApi=await noAuth.request.get(origin+"/api/human-attention",{
      maxRedirects:0,timeout:30000,
    });
    if(![301,302,303,307,308,401,403].includes(invalidApi.status()))
      throw Error("b2_invalid_session_api_accepted");
    if([301,302,303,307,308].includes(invalidApi.status())){
      const destination=new URL(invalidApi.headers()["location"]||"",origin);
      if(destination.origin!==origin || destination.pathname!=="/login")
        throw Error("b2_invalid_session_api_redirect_unsafe");
    }
    await invalidSessionPage.close();
    const operatorApi=await operatorContext.request.get(origin+"/api/human-attention",{
      maxRedirects:0,timeout:30000,
    });
    if(operatorApi.status()!==200)throw Error("b2_operator_read_only_api_unavailable");
    const operatorBody=await operatorApi.json();
    if(operatorBody?.status!=="ok" || !Number.isSafeInteger(operatorBody.count)
      || !Array.isArray(operatorBody.projects))
      throw Error("b2_operator_api_schema_invalid");
    const operatorAdmin=await operatorContext.newPage();
    const adminResponse=await operatorAdmin.goto(origin+"/admin/operators",{
      waitUntil:"domcontentloaded",timeout:60000,
    });
    const adminLanded=new URL(operatorAdmin.url());
    if(!adminResponse)throw Error("b2_operator_admin_page_response_missing");
    if(adminLanded.origin!==origin)throw Error("b2_operator_admin_page_cross_origin_redirect");
    // Keep these errors path-free except for fixed, allowlisted destinations.
    // A lost session and an authorization escalation are different defects and
    // must not be merged into one opaque browser-capture failure.
    if(adminLanded.pathname==="/login")
      throw Error("b2_operator_admin_session_lost");
    if(adminLanded.pathname==="/admin/operators")
      throw Error("b2_operator_admin_page_exposed");
    if(adminLanded.pathname!=="/unauthorized")
      throw Error("b2_operator_admin_redirect_unexpected");
    await operatorAdmin.close();
    await anonymous.close();
    return {
      schema:"factory-b2-live-console-access-boundaries-v1",
      scope:"real_ephemeral_operator_http_auth_and_route_denials_not_full_tenant_or_jwt_claim_proof",
      anonymousRouteDenials:anonymousDenials,
      anonymousApiDenied:true,
      operatorReadOnlyApiAllowed:true,
      operatorAdminPageDenied:true,
      invalidSessionRouteDenied:true,
      invalidSessionApiDenied:true,
      mutatingRequests:0,
      productionWrites:0,
      signedJwtClaimsIndependentlyVerified:false,
      crossTenantIsolationCertified:false,
      fullAuthnAuthzCertified:false,
      fullDataBoundariesCertified:false,
    };
  } finally {
    await noAuth.close();
  }
}
