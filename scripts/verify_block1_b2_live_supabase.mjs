/** B2: real Supabase Auth + PostgREST read-only security exercise.
 * Runs ONLY inside the existing trusted, manually dispatchable Console
 * capture after temporary operator provisioning. No tokens, user IDs,
 * response bodies, URLs or credentials are retained in its output.
 * All network requests use GET. A provider/role denial is mandatory.
 */
const SHA=/^[0-9a-f]{40}$/;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export const B2_CONTROL_PLANE_TABLES=Object.freeze([
  "factory_agent_concurrency_decisions",
  "factory_agent_scope_locks",
  "factory_agents",
  "factory_audit_events",
  "factory_change_set_work_units",
  "factory_change_sets",
  "factory_ci_repair_requests",
  "factory_codex_usage",
  "factory_decisions",
  "factory_definition_of_done_evidence",
  "factory_definitions_of_done",
  "factory_deployments",
  "factory_evaluations",
  "factory_execution_team_plans",
  "factory_external_webhook_wakes",
  "factory_github_app_config",
  "factory_human_gates",
  "factory_impact_analyses",
  "factory_improvement_proposals",
  "factory_incidents",
  "factory_journey_source_evidence_v2",
  "factory_journey_supersessions_v2",
  "factory_journeys",
  "factory_policy_decisions",
  "factory_portfolio_decisions",
  "factory_primary_cost_policy",
  "factory_product_readiness_certifications",
  "factory_product_specs",
  "factory_project_attachments",
  "factory_project_brain_edges",
  "factory_project_brain_nodes",
  "factory_project_brain_snapshots",
  "factory_project_control_wakes",
  "factory_project_database_oauth",
  "factory_project_databases",
  "factory_project_execution_commands",
  "factory_project_execution_controls",
  "factory_project_github_access",
  "factory_project_scheduling",
  "factory_project_state_snapshots",
  "factory_projects",
  "factory_release_reports",
  "factory_repair_jobs",
  "factory_replay_requests",
  "factory_requirement_evidence",
  "factory_requirement_task_links",
  "factory_requirements",
  "factory_resource_limit_snapshots",
  "factory_run_agent_assignments",
  "factory_run_provenance",
  "factory_runs",
  "factory_shadow_decisions",
  "factory_specialist_lane_jobs",
  "factory_tasks",
  "factory_tool_usage",
  "factory_visual_evidence_runs",
  "factory_work_unit_context_packets",
]);
const check=(ok,code)=>{if(!ok)throw Error("b2_"+code);};
const object=x=>x&&typeof x==="object"&&!Array.isArray(x);
function jwtValue(segment) {
  check(typeof segment==="string"&&/^[A-Za-z0-9_-]{2,8192}$/.test(segment),"jwt_format_invalid");
  try {
    const data=Buffer.from(segment,"base64url");
    check(data.length>1&&data.length<8192,"jwt_claims_unbounded");
    const val=JSON.parse(data.toString("utf8"));
    check(object(val),"jwt_claims_invalid");
    return val;
  } catch {
    throw Error("b2_jwt_claims_invalid");
  }
}
function tamperSignature(parts) {
  const c=parts[2][0]==="A"?"B":"A";
  return parts[0]+"."+parts[1]+"."+c+parts[2].slice(1);
}
function tamperClaims(parts,replace) {
  const claims={...jwtValue(parts[1]),...replace};
  return parts[0]+"."+Buffer.from(JSON.stringify(claims),"utf8").toString("base64url")+"."+parts[2];
}
async function request(fetchImpl,url,headers,code) {
  let response;
  try {
    response=await fetchImpl(url,{method:"GET",headers,redirect:"manual",cache:"no-store"});
  }catch{
    throw Error("b2_"+code+"_network_unavailable");
  }
  check(response&&Number.isInteger(response.status)&&response.status>=200&&response.status<=599,
    code+"_response_invalid");
  return response;
}
async function denied(fetchImpl,url,headers,code) {
  const response=await request(fetchImpl,url,headers,code);
  check(response.status===401||response.status===403,code+"_not_denied");
}
export async function verifyLiveSupabaseBoundaries({
  operatorContext,consoleOrigin,brokerUrl,publishableKey,expectedUserId,
  runId,sourceCommit,targetCommit,fetchImpl=fetch,
}) {
  check(Number.isSafeInteger(Number(runId))&&Number(runId)>0
    &&SHA.test(sourceCommit)&&SHA.test(targetCommit),"source_identity_invalid");
  check(UUID.test(expectedUserId),"operator_identity_invalid");
  check(typeof publishableKey==="string"&&/^sb_publishable_[A-Za-z0-9_-]{20,80}$/.test(publishableKey),
    "public_key_unavailable");
  const consoleUrl=new URL(consoleOrigin);
  const broker=new URL(brokerUrl);
  check(consoleUrl.protocol==="https:"&&!consoleUrl.username&&!consoleUrl.password
    &&consoleUrl.pathname==="/"&&!consoleUrl.search&&!consoleUrl.hash
    &&broker.protocol==="https:"&&/^[a-z0-9]{20}\.supabase\.co$/.test(broker.hostname)
    &&broker.pathname==="/functions/v1/factory-visual-evidence-broker"
    &&!broker.username&&!broker.password&&!broker.search&&!broker.hash,
    "trusted_provider_or_console_origin_invalid");
  const host=broker.origin;
  // Playwright reads the HttpOnly session cookie only in the trusted
  // GitHub runner's Node process. It is never sent to the application DOM.
  const cookies=await operatorContext.cookies([consoleUrl.origin]);
  check(Array.isArray(cookies),"session_cookies_invalid");
  const sessions=cookies.filter(c=>c.name==="factory_access_token");
  check(sessions.length===1&&sessions[0].httpOnly===true&&sessions[0].secure===true,
    "session_cookie_not_protected");
  const token=sessions[0].value;
  check(typeof token==="string"&&token.length<8192&&token.length>80,"signed_session_missing");
  const parts=token.split(".");
  check(parts.length===3&&parts.every(x=>/^[A-Za-z0-9_-]+$/.test(x)),"signed_session_invalid");
  const header=jwtValue(parts[0]), claims=jwtValue(parts[1]);
  check(["HS256","RS256","ES256"].includes(header.alg)&&header.typ!=="none",
    "jwt_algorithm_untrusted");
  check(claims.iss===host+"/auth/v1"&&claims.sub===expectedUserId
    &&claims.role==="authenticated"
    &&(claims.aud==="authenticated"||(Array.isArray(claims.aud)&&claims.aud.includes("authenticated")))
    &&Number.isInteger(claims.exp)&&claims.exp>Date.now()/1000
    &&Number.isInteger(claims.iat)&&claims.iat<=Date.now()/1000+60,
    "signed_session_claims_mismatched");
  const baseHeaders={apikey:publishableKey,Accept:"application/json"};
  const userEndpoint=host+"/auth/v1/user";
  const user=await request(fetchImpl,userEndpoint,{...baseHeaders,Authorization:"Bearer "+token},
    "provider_authenticated_user");
  check(user.status===200,"provider_signed_jwt_rejected");
  let userBody;
  try {userBody=await user.json();}catch{throw Error("b2_provider_user_invalid");}
  check(object(userBody)&&userBody.id===expectedUserId,"provider_user_not_ephemeral_operator");
  // Forged JWTs use the same real cookie's signed envelope, never a token
  // invented by a mock. Any acceptance is a security failure.
  for(const [name,forged] of [
    ["signature",tamperSignature(parts)],
    ["role",tamperClaims(parts,{role:"service_role"})],
    ["subject",tamperClaims(parts,{sub:"00000000-0000-4000-8000-000000000000"})],
  ]) {
    await denied(fetchImpl,userEndpoint,
      {...baseHeaders,Authorization:"Bearer "+forged}, "forged_"+name);
  }
  const self=await request(fetchImpl,
    host+"/rest/v1/factory_console_operators?select=user_id,role,is_active&limit=100",
    {...baseHeaders,Authorization:"Bearer "+token},"operator_rls_self_only");
  check(self.status===200,"operator_rls_self_unavailable");
  let selfRows;
  try {selfRows=await self.json();}catch{throw Error("b2_operator_rls_json_invalid");}
  check(Array.isArray(selfRows)&&selfRows.length===1
    &&selfRows[0]?.user_id===expectedUserId
    &&selfRows[0]?.role==="operator"&&selfRows[0]?.is_active===true,
    "operator_self_only_rls_failed");
  // No direct data-plane access for this human session. The server-only
  // service-role proxy is a separate, privileged boundary.
  await denied(fetchImpl,host+"/rest/v1/factory_console_operators?select=user_id&limit=1",
    baseHeaders,"anonymous_operator_directory");
  await denied(fetchImpl,host+"/rest/v1/factory_projects?select=id&limit=1",
    baseHeaders,"anonymous_project_data");
  for(const table of B2_CONTROL_PLANE_TABLES) {
    await denied(fetchImpl,host+"/rest/v1/"+table+"?select=*&limit=1",
      {...baseHeaders,Authorization:"Bearer "+token},"untrusted_"+table);
  }
  // Do not emit the JWT, user, provider body, key or a route containing a
  // user identifier. Every output field is an explicit bounded constant.
  return {
    schema:"factory-b2-live-supabase-auth-data-v1",
    runId:Number(runId),sourceCommit,targetCommit,
    scope:"signed_supabase_auth_operator_and_unprivileged_control_plane_boundary",
    checks:{
      providerSignedUserVerified:true,
      providerActorBoundToEphemeralOperator:true,
      forgedSignatureRejected:true,
      forgedRoleRejected:true,
      forgedSubjectRejected:true,
      activeOperatorOwnRowOnly:true,
      anonymousOperatorDirectoryDenied:true,
      anonymousProjectDataDenied:true,
      untrustedControlPlaneTablesDenied:B2_CONTROL_PLANE_TABLES.length,
    },
    checkedTables:[...B2_CONTROL_PLANE_TABLES],
    privilegedRpcDenialSource:"independent_exact_tree_isolated_postgres",
    independentTenantModelClaimed:false,
    productionWrites:0,mutatingRequests:0,paidCalls:0,personalDataRetained:false,
  };
}
