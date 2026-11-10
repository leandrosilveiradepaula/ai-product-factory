/**
 * B2: live HTTP authorization boundary observations on the exact verified
 * Console deployment. No model, write, admin API, or synthetic PASS.
 * Only status, route and boolean results are retained; never tokens/cookies.
 */
export async function verifyLiveConsoleAccess({browser,operatorContext,baseUrl}) {
  const base=new URL(baseUrl);
  if(base.protocol!=="https:" || base.username || base.password || base.search || base.hash)
    throw Error("b2_invalid_console_origin");
  const origin=base.origin;
  const noAuth=await browser.newContext({
    viewport:{width:1280,height:800},
    extraHTTPHeaders:operatorContext._options?.extraHTTPHeaders?.["x-vercel-trusted-oidc-idp-token"]
      ? {"x-vercel-trusted-oidc-idp-token":operatorContext._options.extraHTTPHeaders["x-vercel-trusted-oidc-idp-token"]}
      : {},
  });
  try {
    const anonymous=await noAuth.newPage();
    const protectedRoutes=["/projects","/gates","/admin/operators"];
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
    if(!adminResponse || adminLanded.origin!==origin || adminLanded.pathname!=="/unauthorized")
      throw Error("b2_operator_admin_page_not_denied");
    await operatorAdmin.close();
    await anonymous.close();
    return {
      schema:"factory-b2-live-console-access-boundaries-v1",
      scope:"real_ephemeral_operator_http_auth_and_route_denials_not_full_tenant_or_jwt_claim_proof",
      anonymousRouteDenials:anonymousDenials,
      anonymousApiDenied:true,
      operatorReadOnlyApiAllowed:true,
      operatorAdminPageDenied:true,
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
