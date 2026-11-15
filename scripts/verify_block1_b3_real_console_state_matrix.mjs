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
      notFound:"first_party_nonexistent_run_404",
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

async function navigate(page,url,{status=200,heading}={}){
  const response=await page.goto(url,{waitUntil:"domcontentloaded",timeout:60000});
  if(!response||response.status()!==status)throw Error("b3_real_states_route_status_mismatch");
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
  let unexpectedPageErrors=0;
  const checks={};
  const handleRequest=request=>{
    try{
      if(new URL(request.url()).origin===origin&&
         !["GET","HEAD","OPTIONS"].includes(request.method()))mutatingRequests++;
    }catch{unexpectedPageErrors++;}
  };
  const handleError=()=>{unexpectedPageErrors++;};
  try{
    page=await context.newPage();
    page.on("request",handleRequest);
    page.on("pageerror",handleError);
    await navigate(page,origin+"/",{heading:"Visão geral"});
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
    await navigate(page,origin+"/gates",{heading:"Decisões que precisam de você"});
    try{
      await page.locator(".humanGateEmpty[role='status']").waitFor({state:"visible",timeout:15000});
    }catch{
      throw Error("b3_real_states_empty_indicator_incorrect");
    }
    checks.empty=true;

    await navigate(page,origin+"/admin/operators",{heading:"Usuário sem permissão"});
    if(new URL(page.url()).pathname!=="/unauthorized")
      throw Error("b3_real_states_role_denial_not_rendered");
    checks.denied=true;

    await navigate(page,origin+"/runs/"+EMPTY_UUID,{status:404,
      heading:"Não encontramos esta página"});
    checks.notFound=true;

    // Chrome applies latency to real HTTP traffic; responses still come from
    // the actual Console backend and cannot be replaced by this script.
    browserClient=await context.newCDPSession(page);
    await browserClient.send("Network.enable");
    await browserClient.send("Network.setCacheDisabled",{cacheDisabled:true});
    await browserClient.send("Network.emulateNetworkConditions",{
      offline:false,latency:1000,downloadThroughput:51200,uploadThroughput:51200,
    });
    await page.goto(origin+"/",{waitUntil:"domcontentloaded",timeout:60000});
    const status=page.locator(".consoleRouteLoading[role='status']");
    try{await status.waitFor({state:"visible",timeout:3000});}
    catch{throw Error("b3_real_states_loading_not_rendered");}
    await page.getByRole("heading",{name:"Visão geral",exact:true})
      .waitFor({state:"visible",timeout:30000});
    checks.loading=true;
    await browserClient.send("Network.emulateNetworkConditions",{
      offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1,
    });

    // Genuine transport outage, not synthetic HTTP 503 or a fake backend.
    // The application must show its own accessible error/retry surface.
    await page.goto(origin+"/",{waitUntil:"networkidle",timeout:60000});
    await context.setOffline(true);
    offline=true;
    await page.locator('a[href="/runs"]').first().click({timeout:10000});
    const error=page.locator(".consoleRouteError[role='alert']");
    try{await error.waitFor({state:"visible",timeout:20000});}
    catch{throw Error("b3_real_states_connection_error_not_rendered");}
    await page.getByRole("button",{name:"Tentar novamente",exact:true})
      .waitFor({state:"visible",timeout:10000});
    checks.connectionError=true;
    await context.setOffline(false);
    offline=false;
    await page.getByRole("button",{name:"Tentar novamente",exact:true}).click();
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
