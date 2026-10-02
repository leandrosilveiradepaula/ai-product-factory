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
const ALLOWED_WORKFLOW_REFS = new Set([
  "leandrosilveiradepaula/ai-product-factory/.github/workflows/autonomous-runner.yml@refs/heads/main",
  "leandrosilveiradepaula/ai-product-factory/.github/workflows/control-plane-oidc-preflight.yml@refs/heads/main",
]);
const APP_PERMISSIONS = {
  actions: "read",
  checks: "read",
  contents: "write",
  issues: "write",
  pull_requests: "write",
  statuses: "read",
};

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
  if(!ALLOWED_WORKFLOW_REFS.has(String(payload.workflow_ref??""))) throw new Error("GitHub OIDC workflow_ref not allowed");
  const event=String(payload.event_name??"");
  if(!["schedule","workflow_dispatch","push","issue_comment"].includes(event)) throw new Error("GitHub OIDC event not allowed");
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

async function readJson(response:Response, label:string) {
  const text=await response.text();
  let body:unknown=null;
  if(text) {
    try { body=JSON.parse(text); } catch { body=null; }
  }
  if(!response.ok) throw new Error(label+" failed with HTTP "+response.status);
  return body;
}

async function mintGithubInstallationToken(req:Request, supabaseUrl:string, key:string) {
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

  const signingKey=await importPKCS8(privateKey,"RS256");
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
      body:JSON.stringify({repository_ids:[repositoryId],permissions:APP_PERMISSIONS}),
    },
  );
  const tokenBody=await readJson(githubResponse,"GitHub installation token mint") as Record<string,unknown>|null;
  const token=String(tokenBody?.token||"");
  if(!token) throw new Error("GitHub installation token response was incomplete");

  return json(200,{
    token,
    expires_at:tokenBody?.expires_at||null,
    installation_id:installationId,
    repository_id:repositoryId,
    token_persisted:false,
  });
}

Deno.serve(async(req:Request)=>{
  try {
    await verifyGithub(req);
    const requestUrl=new URL(req.url);
    const supabaseUrl=(Deno.env.get("SUPABASE_URL")||"").replace(/\/$/,"");
    if(!supabaseUrl) throw new Error("SUPABASE_URL unavailable");
    const key=getSecretKey();

    if(requestUrl.pathname.endsWith("/github-app/token")) {
      return await mintGithubInstallationToken(req,supabaseUrl,key);
    }

    if(!["GET","POST","PATCH"].includes(req.method)) return json(405,{error:"method_not_allowed"});
    const suffix=allowedSuffix(requestUrl);
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
    console.error("factory runtime control-plane broker rejected request:",detail);
    return json(403,{error:"forbidden",detail});
  }
});
