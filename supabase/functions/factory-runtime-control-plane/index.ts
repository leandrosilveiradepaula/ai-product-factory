import { createRemoteJWKSet, importPKCS8, jwtVerify, SignJWT } from "npm:jose@6.1.0";

const ISSUER = "https://token.actions.githubusercontent.com";
const AUDIENCE = "factory-runtime-control-plane";
const GITHUB_API_VERSION = "2026-03-10";
const JWKS = createRemoteJWKSet(new URL("https://token.actions.githubusercontent.com/.well-known/jwks"));
const EXPECTED = {
  repository: "leandrosilveiradepaula/ai-product-factory",
  repository_id: "138" + "7883686",
  repository_owner_id: "256" + "917842",
  ref: "refs/heads/main",
};
// Only this trusted workflow may use the six-hour workflow_run backup wake.
const TRUSTED_BACKUP_WORKFLOW_REF = "leandrosilveiradepaula/ai-product-factory/.github/workflows/autonomous-runner.yml@refs/heads/main";
const GENERIC_PROXY_WORKFLOW_REFS = new Set([
  "leandrosilveiradepaula/ai-product-factory/.github/workflows/autonomous-runner.yml@refs/heads/main",
  "leandrosilveiradepaula/ai-product-factory/.github/workflows/control-plane-oidc-preflight.yml@refs/heads/main",
  "leandrosilveiradepaula/ai-product-factory/.github/workflows/cross-repo-preview-browser-evidence.yml@refs/heads/main",
]);
const APP_PERMISSIONS = {
  actions: "read",
  checks: "read",
  contents: "write",
  issues: "write",
  pull_requests: "write",
  statuses: "read",
};
// The B4 certifier cannot mint a GitHub App token from workflow_run.
// A separate, bound read-only comparison runs inside the broker, and never
// returns even this downgraded installation token to GitHub Actions.
const B4_COMPARE_PERMISSIONS = {contents:"read"};

function json(status:number, body:unknown) {
  return new Response(JSON.stringify(body), {status, headers:{"content-type":"application/json","cache-control":"no-store"}});
}

async function verifyGithub(req:Request) {
  const auth=req.headers.get("authorization")||"";
  if(!auth.startsWith("Bearer ")) throw new Error("missing GitHub OIDC token");
  const {payload}=await jwtVerify(auth.slice(7),JWKS,{issuer:ISSUER,audience:AUDIENCE});
  for(const [key,expected] of Object.entries(EXPECTED)) {
    if(String(payload[key]??"")!==expected) throw new Error("GitHub OIDC claim mismatch: "+key);
  }
  const event=String(payload.event_name??"");
  // workflow_run is not a generic identity: only the exact Factory scheduler
  // workflow is eligible, and its job guards independently verify the upstream
  // scheduled OIDC preflight run, repository, main branch and success.
  if(event==="workflow_run") {
    if(String(payload.workflow_ref??"")!==TRUSTED_BACKUP_WORKFLOW_REF) {
      throw new Error("GitHub OIDC workflow_run workflow not allowed");
    }
  } else if(event==="repository_dispatch") {
    // Console intake can wake only the trusted Factory runner on main.
    // The workflow independently verifies the exact dispatch type/source.
    if(String(payload.workflow_ref??"")!==TRUSTED_BACKUP_WORKFLOW_REF ||
       String(payload.actor??"")!=="infodive-ai-product-factory[bot]") {
      throw new Error("GitHub OIDC repository_dispatch identity not allowed");
    }
  } else if(!["schedule","workflow_dispatch","push","issue_comment"].includes(event)) {
    throw new Error("GitHub OIDC event not allowed");
  }
  if(event==="issue_comment" && String(payload.actor_id??"")!==EXPECTED.repository_owner_id) {
    throw new Error("GitHub OIDC issue_comment actor not allowed");
  }
  return payload;
}

function getSecretKey() {
  const modern=Deno.env.get("SUPABASE_SECRET_KEYS");
  if(modern) {
    try {
      const parsed=JSON.parse(modern);
      const key=String(parsed.default||"");
      if(key) return key;
    } catch {
      // Fall through to the legacy managed key. Never log key material.
    }
  }
  const legacy=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")||"";
  if(!legacy) throw new Error("Supabase privileged key unavailable");
  return legacy;
}

function supabaseHeaders(key:string, contentType?:string|null) {
  const headers=new Headers();
  headers.set("apikey",key);
  headers.set("accept","application/json");
  if(contentType) headers.set("content-type",contentType);
  if(!key.startsWith("sb_secret_")) headers.set("authorization","Bearer "+key);
  return headers;
}

function allowedSuffix(url:URL) {
  const restIndex=url.pathname.indexOf("/rest/v1/");
  if(restIndex<0) throw new Error("only PostgREST/RPC access is allowed");
  const suffix=url.pathname.slice(restIndex);
  if(suffix.includes("..")) throw new Error("invalid path");
  const resource=suffix.slice("/rest/v1/".length);
  const allowed =
    resource.startsWith("factory_") ||
    resource.startsWith("rpc/factory_");
  if(!allowed) throw new Error("resource not allowed");
  return suffix;
}

function derLength(length:number) {
  if(length<0x80) return new Uint8Array([length]);
  const bytes:number[]=[];
  let value=length;
  while(value>0) {
    bytes.unshift(value&0xff);
    value=Math.floor(value/256);
  }
  return new Uint8Array([0x80|bytes.length,...bytes]);
}

function concatBytes(...chunks:Uint8Array[]) {
  const total=chunks.reduce((sum,chunk)=>sum+chunk.length,0);
  const out=new Uint8Array(total);
  let offset=0;
  for(const chunk of chunks) {
    out.set(chunk,offset);
    offset+=chunk.length;
  }
  return out;
}

function pemBodyToBytes(pem:string) {
  const base64=pem
    .replace(/-----BEGIN [^-]+-----/g,"")
    .replace(/-----END [^-]+-----/g,"")
    .replace(/\s+/g,"");
  const binary=atob(base64);
  return Uint8Array.from(binary,(char)=>char.charCodeAt(0));
}

function bytesToPem(label:string,bytes:Uint8Array) {
  let binary="";
  for(const byte of bytes) binary+=String.fromCharCode(byte);
  const base64=btoa(binary);
  const lines=base64.match(/.{1,64}/g)||[];
  return "-----BEGIN "+label+"-----\n"+lines.join("\n")+"\n-----END "+label+"-----";
}

function normalizeRsaPrivateKeyToPkcs8(privateKey:string) {
  if(privateKey.includes("-----BEGIN PRIVATE KEY-----")) return privateKey;
  if(!privateKey.includes("-----BEGIN RSA PRIVATE KEY-----")) {
    throw new Error("GitHub App private key format is unsupported");
  }
  const pkcs1=pemBodyToBytes(privateKey);
  const version=new Uint8Array([0x02,0x01,0x00]);
  const rsaAlgorithmIdentifier=new Uint8Array([
    0x30,0x0d,
    0x06,0x09,0x2a,0x86,0x48,0x86,0xf7,0x0d,0x01,0x01,0x01,
    0x05,0x00,
  ]);
  const privateKeyOctetString=concatBytes(
    new Uint8Array([0x04]),
    derLength(pkcs1.length),
    pkcs1,
  );
  const body=concatBytes(version,rsaAlgorithmIdentifier,privateKeyOctetString);
  const pkcs8=concatBytes(new Uint8Array([0x30]),derLength(body.length),body);
  return bytesToPem("PRIVATE KEY",pkcs8);
}

async function readJson(response:Response, label:string) {
  const text=await response.text();
  let body:unknown=null;
  if(text) {
    try { body=JSON.parse(text); } catch { body=null; }
  }
  if(!response.ok) throw new Error(label+" failed with HTTP "+response.status);
  return body;
}

async function mintGithubInstallationToken(req:Request, supabaseUrl:string, key:string, readOnlyCompare=false) {
  if(req.method!=="POST") return json(405,{error:"method_not_allowed"});
  const body=await req.json().catch(()=>null) as {repository?:unknown}|null;
  const repository=String(body?.repository||"").trim();
  if(!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
    return json(400,{error:"invalid_repository"});
  }

  const projects=await readJson(
    await fetch(
      supabaseUrl+"/rest/v1/factory_projects?select=id,repository&repository=eq."+
        encodeURIComponent(repository)+"&is_active=eq.true&limit=1",
      {headers:supabaseHeaders(key)}
    ),
    "project lookup",
  ) as Array<{id?:unknown;repository?:unknown}>|null;
  if(!projects?.length) return json(404,{error:"project_not_found"});

  const projectId=String(projects[0].id||"");
  const access=await readJson(
    await fetch(
      supabaseUrl+"/rest/v1/factory_project_github_access?select=auth_mode,status,installation_id,repository_id"+
        "&project_id=eq."+encodeURIComponent(projectId)+"&limit=1",
      {headers:supabaseHeaders(key)}
    ),
    "GitHub access lookup",
  ) as Array<Record<string,unknown>>|null;
  if(!access?.length) return json(409,{error:"github_app_not_migrated"});

  const row=access[0];
  if(String(row.auth_mode||"")!=="github_app") return json(409,{error:"github_app_not_migrated"});
  if(String(row.status||"")!=="ready") return json(409,{error:"github_app_not_ready"});

  const installationId=Number(row.installation_id||0);
  const repositoryId=Number(row.repository_id||0);
  if(!Number.isInteger(installationId)||installationId<=0||!Number.isInteger(repositoryId)||repositoryId<=0) {
    return json(409,{error:"github_app_installation_metadata_incomplete"});
  }

  const app=await readJson(
    await fetch(
      supabaseUrl+"/rest/v1/rpc/factory_get_github_app_credentials",
      {method:"POST",headers:supabaseHeaders(key,"application/json"),body:"{}"}
    ),
    "GitHub App credentials lookup",
  ) as Record<string,unknown>|null;
  const appId=Number(app?.app_id||0);
  const privateKey=String(app?.private_key||"");
  if(!Number.isInteger(appId)||appId<=0||!privateKey) return json(409,{error:"github_app_not_configured"});

  const signingKey=await importPKCS8(normalizeRsaPrivateKeyToPkcs8(privateKey),"RS256");
  const now=Math.floor(Date.now()/1000);
  const appJwt=await new SignJWT({})
    .setProtectedHeader({alg:"RS256",typ:"JWT"})
    .setIssuedAt(now-60)
    .setExpirationTime(now+9*60)
    .setIssuer(String(appId))
    .sign(signingKey);

  const githubResponse=await fetch(
    "https://api.github.com/app/installations/"+installationId+"/access_tokens",
    {
      method:"POST",
      headers:{
        Accept:"application/vnd.github+json",
        Authorization:"Bearer "+appJwt,
        "Content-Type":"application/json",
        "X-GitHub-Api-Version":GITHUB_API_VERSION,
      },
      body:JSON.stringify({repositories:[repository.split("/")[1]],permissions:readOnlyCompare?B4_COMPARE_PERMISSIONS:APP_PERMISSIONS}),
    },
  );
  const tokenBody=await readJson(githubResponse,"GitHub installation token mint") as Record<string,unknown>|null;
  const token=String(tokenBody?.token||"");
  if(!token) throw new Error("GitHub installation token response was incomplete");

  const repositoryResponse=await fetch(
    "https://api.github.com/repositories/"+repositoryId,
    {
      headers:{
        Accept:"application/vnd.github+json",
        Authorization:"Bearer "+token,
        "X-GitHub-Api-Version":GITHUB_API_VERSION,
      },
    },
  );
  const repositoryBody=await readJson(repositoryResponse,"GitHub installation repository binding") as Record<string,unknown>|null;
  if(Number(repositoryBody?.id||0)!==repositoryId || String(repositoryBody?.full_name||"").toLowerCase()!==repository.toLowerCase()) {
    return json(409,{error:"github_app_repository_binding_mismatch"});
  }

  return json(200,{
    token,
    expires_at:tokenBody?.expires_at||null,
    installation_id:installationId,
    repository_id:repositoryId,
    token_persisted:false,
  });
}


const B4_SHA=/^[0-9a-f]{40}$/;
const B4_REPO=/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const B4_NAME=/^[A-Za-z0-9_.\-/]+$/;

async function b4ReadOnlyComparedSource(
  req:Request, identity:Record<string,unknown>,
  supabaseUrl:string, key:string,
) {
  // This is NOT the token-mint endpoint: it returns only a tiny derived
  // comparison receipt for the already human-released Factory journey.
  if(req.method!=="POST") return json(405,{error:"method_not_allowed"});
  if(String(identity.event_name||"")!=="workflow_run" ||
     String(identity.workflow_ref||"")!==TRUSTED_BACKUP_WORKFLOW_REF ||
     String(identity.run_attempt||"")!=="1") {
    return json(403,{error:"b4_readonly_identity_denied"});
  }
  const input=await req.json().catch(()=>null) as Record<string,unknown>|null;
  if(!input || typeof input!=="object" || Array.isArray(input) ||
     Object.keys(input).sort().join(",")!=="current,predecessor,repository") {
    return json(400,{error:"b4_source_request_invalid"});
  }
  const repository=input.repository,predecessor=input.predecessor,current=input.current;
  if(typeof repository!=="string" || !B4_REPO.test(repository) ||
     repository.toLowerCase()===EXPECTED.repository.toLowerCase() ||
     typeof predecessor!=="string" || !B4_SHA.test(predecessor) ||
     typeof current!=="string" || !B4_SHA.test(current) || predecessor===current) {
    return json(400,{error:"b4_source_request_invalid"});
  }
  // A privileged Control Plane SELECT checks the actual project plus the
  // exact completed Change Set, separately witnessed original browser run
  // and an independently observed human release. No arbitrary repo/commit
  // oracle is available to a workflow_run caller.
  const projects=await readJson(await fetch(
    supabaseUrl+"/rest/v1/factory_projects?select=id,repository,project_kind,lifecycle_stage"+
      "&repository=eq."+encodeURIComponent(repository)+"&is_active=eq.true&limit=2",
    {headers:supabaseHeaders(key)}
  ),"B4 project binding") as Array<Record<string,unknown>>|null;
  if(!projects || projects.length!==1 ||
     projects[0].project_kind!=="greenfield" ||
     projects[0].lifecycle_stage!=="operations" ||
     String(projects[0].repository||"")!==repository) {
    return json(409,{error:"b4_source_not_released"});
  }
  const projectId=String(projects[0].id||"");
  const changes=await readJson(await fetch(
    supabaseUrl+"/rest/v1/factory_change_sets?select=id,release_run_id,status,candidate_commit,metadata"+
      "&project_id=eq."+encodeURIComponent(projectId)+
      "&candidate_commit=eq."+current+"&status=eq.completed&limit=2",
    {headers:supabaseHeaders(key)}
  ),"B4 Change Set binding") as Array<Record<string,unknown>>|null;
  if(!changes || changes.length!==1 ||
     !B4_SHA.test(String(changes[0].candidate_commit||""))) {
    return json(409,{error:"b4_source_not_released"});
  }
  const cs=changes[0], metadata=cs.metadata as Record<string,unknown>|null;
  const request=metadata?.integration_release_request as Record<string,unknown>|null;
  if(request?.candidate_commit!==current ||
     typeof cs.release_run_id!=="string") {
    return json(409,{error:"b4_source_not_released"});
  }
  const reports=await readJson(await fetch(
    supabaseUrl+"/rest/v1/factory_release_reports?select=id,project_id,run_id,status,candidate_commit,report"+
      "&run_id=eq."+encodeURIComponent(cs.release_run_id)+
      "&candidate_commit=eq."+current+"&status=eq.released&limit=2",
    {headers:supabaseHeaders(key)}
  ),"B4 observed release lookup") as Array<Record<string,unknown>>|null;
  const report=reports?.[0],release=report?.report as Record<string,unknown>|null;
  if(!reports || reports.length!==1 || report?.project_id!==projectId ||
     report?.run_id!==cs.release_run_id ||
     release?.released_by!=="observed_manual_merge" ||
     !B4_SHA.test(String(release?.merge_sha||""))) {
    return json(409,{error:"b4_source_not_released"});
  }
  const snapshots=await readJson(await fetch(
    supabaseUrl+"/rest/v1/factory_project_state_snapshots?select=id,project_id,run_id,evidence,source_status,constraints"+
      "&project_id=eq."+encodeURIComponent(projectId)+
      "&observed_stage=eq.verification&order=created_at.desc&limit=30",
    {headers:supabaseHeaders(key)}
  ),"B4 independent visual witness lookup") as Array<Record<string,unknown>>|null;
  if(!snapshots?.some(row=>{
    const witness=row.evidence as Record<string,unknown>|null;
    const preview=witness?.preview as Record<string,unknown>|null;
    const source=row.source_status as Record<string,unknown>|null;
    const limits=row.constraints as Record<string,unknown>|null;
    return row.project_id===projectId && row.run_id===null &&
      witness?.candidate_commit===predecessor &&
      witness?.target_repository===repository &&
      preview?.status==="browser_verified" &&
      preview?.provider==="vercel" &&
      source?.github_target==="verified" &&
      source?.browser_visual_validation==="success" &&
      limits?.product_ready_inferred===false &&
      limits?.production_merge_authorized===false;
  })) return json(409,{error:"b4_source_not_released"});

  // Reuse existing verified App installation binding, but request only
  // CONTENTS:READ. The ephemeral token is used in this Edge invocation;
  // it is not returned, logged, persisted or passed to a CI runner.
  const credentials=await mintGithubInstallationToken(
    new Request(req.url,{
      method:"POST",headers:{"content-type":"application/json"},
      body:JSON.stringify({repository}),
    }),supabaseUrl,key,true,
  );
  if(!credentials.ok) return json(409,{error:"b4_readonly_app_unavailable"});
  const granted=await credentials.json() as Record<string,unknown>;
  const accessToken=String(granted.token||"");
  if(!accessToken || granted.token_persisted!==false) {
    return json(409,{error:"b4_readonly_app_unavailable"});
  }
  const compared=await readJson(await fetch(
    "https://api.github.com/repos/"+repository+"/compare/"+predecessor+"..."+current,
    {headers:{
      Accept:"application/vnd.github+json",
      Authorization:"Bearer "+accessToken,
      "X-GitHub-Api-Version":GITHUB_API_VERSION,
    }}
  ),"B4 GitHub compare") as Record<string,unknown>|null;
  const files=compared?.files;
  const ahead=compared?.ahead_by;
  if(compared?.status!=="ahead" || compared.behind_by!==0 ||
     !Number.isInteger(ahead) || (ahead as number)<1 || (ahead as number)>25 ||
     compared.total_commits!==ahead || compared.truncated===true ||
     !Array.isArray(files) || files.length<1 || files.length>50 ||
     !files.every((item:unknown)=>{
       if(!item || typeof item!=="object") return false;
       const f=item as Record<string,unknown>,name=f.filename,status=f.status;
       return typeof name==="string" && B4_NAME.test(name) &&
         !name.startsWith("/") && !name.split("/").some(x=>!x||x==="."||x==="..") &&
         ["added","modified","removed","renamed"].includes(String(status||"")) &&
         (status!=="renamed" || (
           typeof f.previous_filename==="string" &&
           B4_NAME.test(f.previous_filename) &&
           !f.previous_filename.startsWith("/") &&
           !f.previous_filename.split("/").some(x=>!x||x==="."||x==="..")
         ));
     })) return json(409,{error:"b4_comparison_not_verified"});
  const safeFiles=(files as Array<Record<string,unknown>>).map(f=>({
    filename:f.filename,status:f.status,
    ...(f.status==="renamed"?{previous_filename:f.previous_filename}:{}),
  }));
  return json(200,{
    status:"ahead",behind_by:0,ahead_by:ahead,total_commits:ahead,
    truncated:false,files:safeFiles,
  });
}

Deno.serve(async(req:Request)=>{
  try {
    const identity=await verifyGithub(req);
    const requestUrl=new URL(req.url);
    const supabaseUrl=(Deno.env.get("SUPABASE_URL")||"").replace(/\/$/,"");
    if(!supabaseUrl) throw new Error("SUPABASE_URL unavailable");
    const key=getSecretKey();

    if(requestUrl.pathname.endsWith("/github-app/read-only-compare")) {
      return await b4ReadOnlyComparedSource(req,identity,supabaseUrl,key);
    }

    if(requestUrl.pathname.endsWith("/github-app/token")) {
      const workflowRef=String(identity.workflow_ref||"");
      const eventName=String(identity.event_name||"");
      const tokenWorkflows=new Set([
        "leandrosilveiradepaula/ai-product-factory/.github/workflows/autonomous-runner.yml@refs/heads/main",
        "leandrosilveiradepaula/ai-product-factory/.github/workflows/crm-cross-repo-preflight.yml@refs/heads/main",
        "leandrosilveiradepaula/ai-product-factory/.github/workflows/cross-repo-preview-browser-evidence.yml@refs/heads/main",
      ]);
      if(!tokenWorkflows.has(workflowRef)) return json(403,{error:"github_app_token_workflow_not_allowed"});
      // A Console decision wakes the same trusted main runner via
      // repository_dispatch. The generic OIDC proxy already verifies this
      // runner and bot actor; token minting must enforce that identity again.
      // No other workflow may mint a cross-repo token from repository_dispatch.
      const trustedConsoleWake=eventName==="repository_dispatch"
        && workflowRef===TRUSTED_BACKUP_WORKFLOW_REF
        && String(identity.actor||"")==="infodive-ai-product-factory[bot]";
      const standardTokenEvent=["schedule","workflow_dispatch","issue_comment","push"].includes(eventName);
      if(!standardTokenEvent && !trustedConsoleWake) {
        return json(403,{error:"github_app_token_event_not_allowed"});
      }
      return await mintGithubInstallationToken(req,supabaseUrl,key);
    }

    const workflowRef=String(identity.workflow_ref||"");
    if(!GENERIC_PROXY_WORKFLOW_REFS.has(workflowRef)) {
      return json(403,{error:"github_oidc_proxy_workflow_not_allowed"});
    }
    if(!["GET","POST","PATCH"].includes(req.method)) return json(405,{error:"method_not_allowed"});
    const suffix=allowedSuffix(requestUrl);
    // Only the signed OWNER issue event in the trusted runner may enqueue
    // a new cycle. Generic cron/workflow_dispatch identities are denied.
    // Production rollout order: broker deployment before migration.
    if(suffix==="/rest/v1/rpc/factory_enqueue_github_owner_continuation_v1") {
      if(req.method!=="POST" || requestUrl.search
         || String(identity.event_name||"")!=="issue_comment"
         || String(identity.workflow_ref||"")!==TRUSTED_BACKUP_WORKFLOW_REF
         || String(identity.actor_id||"")!==EXPECTED.repository_owner_id
         || String(identity.actor||"")!=="leandrosilveiradepaula") {
        return json(403,{error:"github_owner_start_oidc_required"});
      }
    }
    if(suffix==="/rest/v1/rpc/factory_enqueue_journey_intake_v2") {
      if(req.method!=="POST" || requestUrl.search
         || String(identity.event_name||"")!=="issue_comment"
         || String(identity.workflow_ref||"")!==TRUSTED_BACKUP_WORKFLOW_REF
         || String(identity.actor_id||"")!==EXPECTED.repository_owner_id
         || String(identity.actor||"")!=="leandrosilveiradepaula") {
        return json(403,{error:"github_owner_start_oidc_required"});
      }
    }
    // Checkpointed planning resume has its own OWNER-only mutation fence.
    // A generic scheduled worker or a different workflow may never enqueue it.
    if(suffix==="/rest/v1/rpc/factory_resume_failed_product_planning_v1") {
      if(req.method!=="POST" || requestUrl.search
         || String(identity.event_name||"")!=="issue_comment"
         || String(identity.workflow_ref||"")!==TRUSTED_BACKUP_WORKFLOW_REF
         || String(identity.actor_id||"")!==EXPECTED.repository_owner_id
         || String(identity.actor||"")!=="leandrosilveiradepaula") {
        return json(403,{error:"github_owner_resume_oidc_required"});
      }
    }
    const headers=supabaseHeaders(key,req.headers.get("content-type"));
    const prefer=req.headers.get("prefer");
    if(prefer) headers.set("prefer",prefer);
    const target=supabaseUrl+suffix+requestUrl.search;
    const body=req.method==="GET"?undefined:await req.arrayBuffer();
    const response=await fetch(target,{method:req.method,headers,body});
    const responseHeaders=new Headers();
    const outType=response.headers.get("content-type");
    if(outType) responseHeaders.set("content-type",outType);
    responseHeaders.set("cache-control","no-store");
    return new Response(response.body,{status:response.status,headers:responseHeaders});
  } catch(error) {
    const detail=error instanceof Error?error.message:"unknown";
    // Bounded diagnostics: never echo arbitrary exception text, JWTs or API responses.
    if(detail.startsWith("GitHub OIDC claim mismatch: ")) {
      const claim=detail.slice("GitHub OIDC claim mismatch: ".length);
      if(Object.prototype.hasOwnProperty.call(EXPECTED,claim)) {
        return json(403,{error:"github_oidc_claim_mismatch",claim});
      }
    }
    if(detail==="missing GitHub OIDC token" || detail.startsWith("JWT")) {
      return json(403,{error:"github_oidc_authentication_failed"});
    }
    if(detail.startsWith("GitHub installation token mint failed with HTTP ") ||
       detail.startsWith("GitHub installation repository binding failed with HTTP ")) {
      return json(403,{error:"github_app_upstream_permission_denied"});
    }
    console.error("factory runtime broker denied request (diagnostic detail redacted)");
    return json(403,{error:"forbidden"});
  }
});
