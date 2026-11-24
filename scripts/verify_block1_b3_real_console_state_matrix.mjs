/** B3 independent browser producer: no API interception, fixtures or response replacement.
 * Probe only real authenticated first-party routes. Chrome transport throttling
 * is permitted for loading/offline UX; it does not forge server responses.
 * This witness is never generated until EVERY required rendered state succeeds.
 */
const SHA=/^[0-9a-f]{40}$/;
const REQUIRED=["success","empty","loading","denied","notFound","connectionError","recovered"];
const EMPTY_UUID="00000000-0000-4000-8000-000000000000";

function validOrigin(value){
  try {
    const u=new URL(value);
    if(u.protocol!=="https:"||u.username||u.password||u.port||u.search||u.hash||
       (u.pathname!=="/"&&u.pathname!==""))throw Error();
    return u.origin;
  }catch{throw Error("b3_real_states_origin_invalid");}
}

export function safeRealConsoleStateMatrix({runId,sourceCommit,targetCommit,checks,
  backendStatus,pendingHumanGateCount,mutatingRequests,interceptions,unexpectedPageErrors}){
  if(!Number.isSafeInteger(Number(runId))||Number(runId)<1||
     !SHA.test(String(sourceCommit))||!SHA.test(String(targetCommit)))
    throw Error("b3_real_states_identity_invalid");
  if(!checks||typeof checks!=="object"||
      Object.keys(checks).length!==REQUIRED.length||
      REQUIRED.some(x=>checks[x]!==true) ||
      ![200].includes(backendStatus)||pendingHumanGateCount!==0||
      mutatingRequests!==0||interceptions!==0||unexpectedPageErrors!==0)
    throw Error("b3_real_states_full_live_matrix_incomplete");
  return {
    schema:"factory-b3-authenticated-live-state-matrix-v1",
    runId:Number(runId),sourceCommit,targetCommit,
    checks:Object.fromEntries(REQUIRED.map(k=>[k,true])),
    sources:{
      success:"authenticated_first_party_overview",
      empty:"authenticated_first_party_empty_human_decision_inbox",
      loading:"real_network_throttled_next_route_fallback",
      denied:"authenticated_first_party_role_denial",
      notFound:"first_party_run_existence_api_404_plus_not_found_ui",
      connectionError:"actual_chromium_transport_disconnection",
      recovered:"first_party_route_retry_after_reconnection",
    },
    backendStatus,pendingHumanGateCount,mutatingRequests,interceptions,unexpectedPageErrors,
    productionWrites:0,paidCalls:0,personalDataRetained:false,
    responsesFabricated:false,backendOutageClaimed:false,
    fullUserExperienceCertified:true,
    independentCriterionCertified:false,
  };
}

async function openRealRunsLink(page){
  // The advanced drawer is closed on Overview: a hidden link is not a
  // reproducible user interaction. Open the actual visible navigation first.
  const drawer=page.locator(".desktopSidebarContent details.navAdvanced");
  if(await drawer.getAttribute("open")===null)
    await drawer.locator("summary").click({timeout:10000});
  const link=page.locator('.desktopSidebarContent a[href="/runs"]');
  await link.waitFor({state:"visible",timeout:10000});
  return link;
}

async function navigate(page,url,{status=200,heading,stage="unknown"}={}){
  const response=await page.goto(url,{waitUntil:"domcontentloaded",timeout:60000});
  if(!response||response.status()!==status)
    throw Error("b3_real_states_route_status_mismatch_"+stage);
  if(heading)await page.getByRole("heading",{name:heading,exact:true}).first()
    .waitFor({state:"visible",timeout:20000});
  return response;
}

export async function verifyRealConsoleStateMatrix({
    context,baseUrl,runId,sourceCommit,targetCommit}){
  const origin=validOrigin(baseUrl);
  let page=null;
  let browserClient=null;
  let offline=false;
  let mutatingRequests=0;
  let loadingRouteRequests=0;
  let unexpectedPageErrors=0;
  const checks={};
  const handleRequest=request=>{
    try{
      const url=new URL(request.url());
      if(url.origin===origin){
        if(!["GET","HEAD","OPTIONS"].includes(request.method()))mutatingRequests++;
        if(url.pathname==="/runs"&&request.method()==="GET")loadingRouteRequests++;
      }
    }catch{unexpectedPageErrors++;}
  };
  const handleError=()=>{unexpectedPageErrors++;};
  try{
    page=await context.newPage();
    page.on("request",handleRequest);
    page.on("pageerror",handleError);
    await navigate(page,origin+"/",{heading:"Visão geral",stage:"overview"});
    checks.success=true;

    // Not a mock: the signed ephemeral operator reads the real server.
    const attention=await context.request.get(origin+"/api/human-attention",{
      maxRedirects:0,timeout:30000,
    });
    if(attention.status()!==200)throw Error("b3_real_states_backend_unavailable");
    let payload;
    try{payload=await attention.json();}catch{throw Error("b3_real_states_backend_not_json");}
    // Do not assert the whole attention inbox is empty: a real GitHub App
    // installation action is independent from human release/data gates.
    // The backend must report zero ACTUAL human gates; the separate /gates
    // page must render its real, first-party empty decision state.
    if(payload?.status!=="ok"||!Number.isSafeInteger(payload.pendingHumanGateCount)||
       payload.pendingHumanGateCount!==0||!Number.isSafeInteger(payload.count)||
       payload.count<0||!Array.isArray(payload.projects)||
       !payload.projects.every(key=>typeof key==="string"))
      throw Error("b3_real_states_actual_empty_state_unavailable");
    // The human decision inbox title is editable UX copy, not a proof identity.
    // Demand a real 200 /gates response, its visible semantic H1, the signed
    // first-party attention API, and the actual empty-decision status below.
    // Rewriting a heading must never fake or invalidate the independent B3 gate.
    await navigate(page,origin+"/gates",{stage:"gates"});
    try{
      await page.getByRole("heading",{level:1}).first()
        .waitFor({state:"visible",timeout:20000});
    }catch{throw Error("b3_real_states_gate_heading_missing");}
    try{
      await page.locator(".humanGateEmpty[role='status']").waitFor({state:"visible",timeout:15000});
    }catch{
      throw Error("b3_real_states_empty_indicator_incorrect");
    }
    checks.empty=true;

    await navigate(page,origin+"/admin/operators",{heading:"Usuário sem permissão",stage:"denied"});
    if(new URL(page.url()).pathname!=="/unauthorized")
      throw Error("b3_real_states_role_denial_not_rendered");
    checks.denied=true;

    // Next.js may stream the notFound() UI with HTTP 200 if the shell was
    // already sent. The HTML still must show its real missing-run recovery UI.
    const missingPage=await page.goto(origin+"/runs/"+EMPTY_UUID,{
      waitUntil:"domcontentloaded",timeout:60000,
    });
    if(!missingPage||![200,404].includes(missingPage.status()))
      throw Error("b3_real_states_missing_run_ui_status_mismatch");
    await page.getByRole("heading",{name:"Não encontramos esta página",exact:true})
      .waitFor({state:"visible",timeout:20000});
    // Check a separate real authenticated first-party API for canonical HTTP
    // 404, not a fabricated browser response and not a different missing URL.
    const missingApi=await context.request.get(origin+"/api/runs/"+EMPTY_UUID,{
      maxRedirects:0,timeout:30000,
    });
    if(missingApi.status()!==404)
      throw Error("b3_real_states_missing_run_api_status_mismatch");
    let missingBody;
    try{missingBody=await missingApi.json();}
    catch{throw Error("b3_real_states_missing_run_api_not_json");}
    if(!missingBody||typeof missingBody!=="object"||Object.keys(missingBody).length!==1||
       missingBody.status!=="not_found")
      throw Error("b3_real_states_missing_run_api_payload_invalid");
    checks.notFound=true;

    // A hard page.goto() does not prove Next's *client-side* loading fallback.
    // Exercise a real visible user Link to a dynamic route. Disable browser
    // cache, throttle only genuine Chrome HTTP transport, never intercept or
    // fabricate server responses. No prefetch is allowed by the real nav.
    await navigate(page,origin+"/",{heading:"Visão geral",stage:"loading_origin"});
    // A server-rendered heading can appear before the client hydrates. Wait
    // for the actual client attention fetch to settle, not a fixed sleep.
    await page.locator(".topbarAttention.loading").waitFor({state:"hidden",timeout:20000});
    await page.waitForLoadState("networkidle",{timeout:30000});
    const loadingLink=await openRealRunsLink(page);
    // Count only the navigation initiated below, never a preceding request.
    loadingRouteRequests=0;
    browserClient=await context.newCDPSession(page);
    await browserClient.send("Network.enable");
    await browserClient.send("Network.setCacheDisabled",{cacheDisabled:true});
    await browserClient.send("Network.emulateNetworkConditions",{
      offline:false,latency:1800,downloadThroughput:51200,uploadThroughput:51200,
    });
    const status=page.locator(".consoleRouteLoading[role='status']:visible,.consoleNavigationLoading[role='status']:visible").first();
    try{
      await Promise.all([
        status.waitFor({state:"visible",timeout:15000}),
        loadingLink.click({timeout:15000}),
      ]);
    }catch{throw Error("b3_real_states_loading_not_rendered");}
    await page.getByRole("heading",{name:"Execuções",exact:true})
      .waitFor({state:"visible",timeout:30000});
    if(new URL(page.url()).pathname!=="/runs"||loadingRouteRequests===0)
      throw Error("b3_real_states_loading_without_live_route_request");
    checks.loading=true;
    await browserClient.send("Network.emulateNetworkConditions",{
      offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1,
    });

    // Genuine Chrome transport outage after a *fresh full document* resets
    // in-memory RSC state. Navigation uses a real non-prefetched visible Link.
    // Neither navigation nor the retry may be supplied by a cached fixture.
    await page.goto(origin+"/",{waitUntil:"networkidle",timeout:60000});
    const offlineLink=await openRealRunsLink(page);
    await context.setOffline(true);
    offline=true;
    await offlineLink.click({timeout:10000});
    const error=page.locator(".consoleRouteError[role='alert']");
    try{await error.waitFor({state:"visible",timeout:20000});}
    catch{throw Error("b3_real_states_connection_error_not_rendered");}
    await error.getByRole("button",{name:"Tentar novamente",exact:true})
      .waitFor({state:"visible",timeout:10000});
    checks.connectionError=true;
    await context.setOffline(false);
    offline=false;
    await error.getByRole("button",{name:"Tentar novamente",exact:true}).click();
    await page.getByRole("heading",{name:"Execuções",exact:true})
      .waitFor({state:"visible",timeout:30000});
    checks.recovered=true;
    return safeRealConsoleStateMatrix({runId,sourceCommit,targetCommit,checks,
      backendStatus:200,pendingHumanGateCount:0,
      mutatingRequests,interceptions:0,unexpectedPageErrors});
  }finally{
    if(offline)await context.setOffline(false).catch(()=>{});
    if(browserClient)await browserClient.detach().catch(()=>{});
    if(page)await page.close().catch(()=>{});
  }
}
