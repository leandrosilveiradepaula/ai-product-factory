import {createSign,randomBytes} from "node:crypto";
import {getSupabaseServerConfig} from "./supabase-server";

const GITHUB_API_VERSION="2026-03-10";
const APP_PERMISSIONS={
  actions:"read",
  checks:"read",
  contents:"write",
  issues:"write",
  pull_requests:"write",
  statuses:"read",
} as const;

type GitHubAppStoredStatus={
  configured:boolean;
  app_id?:number;
  app_slug?:string;
  client_id?:string;
  status?:string;
  updated_at?:string;
};

type GitHubAppCredentials={
  app_id:number;
  app_slug:string;
  client_id:string;
  status:string;
  private_key:string;
  webhook_secret?:string|null;
  client_secret?:string|null;
};

type ManifestConversion={
  id:number;
  slug:string;
  client_id:string;
  client_secret?:string;
  webhook_secret?:string;
  pem:string;
};

function b64url(value:Buffer|string){
  return Buffer.from(value).toString("base64url");
}

async function rpc(name:string,body:unknown={}){
  const cfg=getSupabaseServerConfig();
  if(!cfg)throw new Error("Control Plane is unavailable");
  const response=await fetch(cfg.url+"/rest/v1/rpc/"+name,{
    method:"POST",
    headers:{...cfg.headers,"Content-Type":"application/json"},
    body:JSON.stringify(body),
    cache:"no-store",
  });
  if(!response.ok)throw new Error("Control Plane GitHub App operation failed");
  if(response.status===204)return null;
  const text=await response.text();
  return text?JSON.parse(text):null;
}

export async function getGitHubAppStatus():Promise<GitHubAppStoredStatus>{
  try{
    const row=await rpc("factory_get_github_app_status");
    if(!row)return{configured:false};
    return{
      configured:Boolean(row.configured),
      app_id:row.app_id==null?undefined:Number(row.app_id),
      app_slug:row.app_slug?String(row.app_slug):undefined,
      client_id:row.client_id?String(row.client_id):undefined,
      status:row.status?String(row.status):undefined,
      updated_at:row.updated_at?String(row.updated_at):undefined,
    };
  }catch{
    return{configured:false};
  }
}

async function getGitHubAppCredentials():Promise<GitHubAppCredentials>{
  const row=await rpc("factory_get_github_app_credentials");
  if(!row?.app_id||!row?.app_slug||!row?.private_key)throw new Error("Factory GitHub App is not configured");
  return{
    app_id:Number(row.app_id),
    app_slug:String(row.app_slug),
    client_id:String(row.client_id||""),
    status:String(row.status||""),
    private_key:String(row.private_key),
    webhook_secret:row.webhook_secret?String(row.webhook_secret):null,
    client_secret:row.client_secret?String(row.client_secret):null,
  };
}

export function createGitHubAppManifestFlow(origin:string,organization?:string|null){
  const state=randomBytes(32).toString("base64url");
  const base=origin.replace(/\/$/,"");
  const manifest={
    name:"Infodive AI Product Factory",
    url:base,
    redirect_url:base+"/api/integrations/github-app/callback",
    setup_url:base+"/projects?github_app=installed",
    setup_on_update:true,
    public:false,
    request_oauth_on_install:false,
    default_permissions:APP_PERMISSIONS,
    default_events:[],
  };
  const target=organization?.trim()
    ?"https://github.com/organizations/"+encodeURIComponent(organization.trim())+"/settings/apps/new"
    :"https://github.com/settings/apps/new";
  return{state,target,manifest};
}

export async function convertGitHubAppManifest(code:string):Promise<ManifestConversion>{
  if(!/^[A-Za-z0-9_-]{8,200}$/.test(code))throw new Error("Invalid GitHub App manifest code");
  const response=await fetch("https://api.github.com/app-manifests/"+encodeURIComponent(code)+"/conversions",{
    method:"POST",
    headers:{
      Accept:"application/vnd.github+json",
      "X-GitHub-Api-Version":GITHUB_API_VERSION,
    },
    cache:"no-store",
  });
  if(!response.ok)throw new Error("GitHub App manifest conversion failed");
  const row=await response.json();
  if(!row?.id||!row?.slug||!row?.client_id||!row?.pem)throw new Error("GitHub App manifest response is incomplete");
  return{
    id:Number(row.id),
    slug:String(row.slug),
    client_id:String(row.client_id),
    client_secret:row.client_secret?String(row.client_secret):undefined,
    webhook_secret:row.webhook_secret?String(row.webhook_secret):undefined,
    pem:String(row.pem),
  };
}

export async function storeGitHubAppConversion(app:ManifestConversion){
  return rpc("factory_store_github_app_config",{
    p_app_id:app.id,
    p_app_slug:app.slug,
    p_client_id:app.client_id,
    p_private_key:app.pem,
    p_webhook_secret:app.webhook_secret||null,
    p_client_secret:app.client_secret||null,
  });
}

export async function resolveGitHubAppRegistrationGate(gateId:string,actorRef:string){
  if(!/^[0-9a-f-]{36}$/i.test(gateId))throw new Error("Invalid GitHub App registration gate");
  const cfg=getSupabaseServerConfig();
  if(!cfg)throw new Error("Control Plane is unavailable");

  const gateResponse=await fetch(
    cfg.url+"/rest/v1/factory_human_gates?select=id,run_id,status&id=eq."+encodeURIComponent(gateId)+"&limit=1",
    {headers:cfg.headers,cache:"no-store"}
  );
  if(!gateResponse.ok)throw new Error("GitHub App registration gate lookup failed");
  const gates=await gateResponse.json();
  const gate=gates[0];
  if(!gate||String(gate.status)!=="pending")throw new Error("GitHub App registration gate is not pending");

  const runResponse=await fetch(
    cfg.url+"/rest/v1/factory_runs?select=id,status,metadata&id=eq."+encodeURIComponent(String(gate.run_id))+"&limit=1",
    {headers:cfg.headers,cache:"no-store"}
  );
  if(!runResponse.ok)throw new Error("GitHub App registration run lookup failed");
  const runs=await runResponse.json();
  const run=runs[0];
  const metadata=run?.metadata&&typeof run.metadata==="object"?run.metadata:{};
  if(!run||String(run.status)!=="awaiting_human"||metadata.requested_action!=="register_github_app"){
    throw new Error("Gate does not authorize GitHub App registration");
  }

  await rpc("factory_resolve_human_gate",{
    p_gate_id:gateId,
    p_resolution:"approved",
    p_resolved_by:actorRef,
    p_note:"GitHub App registrada por ação humana explícita e callback GitHub validado pelo Console.",
  });
}

function createAppJwt(appId:number,privateKey:string){
  const now=Math.floor(Date.now()/1000);
  const header=b64url(JSON.stringify({alg:"RS256",typ:"JWT"}));
  const payload=b64url(JSON.stringify({iat:now-60,exp:now+9*60,iss:String(appId)}));
  const signingInput=header+"."+payload;
  const signer=createSign("RSA-SHA256");
  signer.update(signingInput);
  signer.end();
  const signature=signer.sign(privateKey).toString("base64url");
  return signingInput+"."+signature;
}

async function githubJson(url:string,token:string,init:RequestInit={}){
  const response=await fetch(url,{
    ...init,
    headers:{
      Accept:"application/vnd.github+json",
      Authorization:"Bearer "+token,
      "X-GitHub-Api-Version":GITHUB_API_VERSION,
      ...(init.headers||{}),
    },
    cache:"no-store",
  });
  const text=await response.text();
  const body=text?JSON.parse(text):null;
  if(!response.ok){
    const error=new Error("GitHub API request failed");
    Object.assign(error,{status:response.status});
    throw error;
  }
  return body;
}

async function safeGithubGet(path:string,token:string){
  try{return{state:"verified",body:await githubJson("https://api.github.com"+path,token),status:200};}
  catch(error){
    const status=Number((error as {status?:number}).status||0);
    if([401,403,404].includes(status))return{state:"missing",body:null,status};
    throw error;
  }
}

function permissionAllowsWrite(value:unknown){
  return value==="write"||value==="admin";
}

export async function verifyProjectGitHubApp(projectKey:string){
  const cfg=getSupabaseServerConfig();
  if(!cfg)throw new Error("Control Plane is unavailable");
  const projectResponse=await fetch(
    cfg.url+"/rest/v1/factory_projects?select=id,project_key,repository&project_key=eq."+encodeURIComponent(projectKey)+"&is_active=eq.true&limit=1",
    {headers:cfg.headers,cache:"no-store"}
  );
  if(!projectResponse.ok)throw new Error("Project lookup failed");
  const projects=await projectResponse.json();
  if(!projects.length||!projects[0].repository)throw new Error("Project repository is unavailable");
  const project=projects[0];
  const repository=String(project.repository);
  const parts=repository.split("/");
  if(parts.length!==2||parts.some((x:string)=>!x))throw new Error("Invalid project repository");
  const [owner,name]=parts;

  const app=await getGitHubAppCredentials();
  const appJwt=createAppJwt(app.app_id,app.private_key);
  const installation=await githubJson(
    "https://api.github.com/repos/"+encodeURIComponent(owner)+"/"+encodeURIComponent(name)+"/installation",
    appJwt,
  );
  const installationId=Number(installation?.id||0);
  if(!installationId)throw new Error("GitHub App is not installed for this repository");

  const tokenResponse=await githubJson(
    "https://api.github.com/app/installations/"+installationId+"/access_tokens",
    appJwt,
    {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({repositories:[name],permissions:APP_PERMISSIONS}),
    },
  );
  const token=String(tokenResponse?.token||"");
  if(!token)throw new Error("GitHub installation token was not issued");
  const granted=tokenResponse?.permissions&&typeof tokenResponse.permissions==="object"?tokenResponse.permissions:{};

  const metadata=await safeGithubGet("/repos/"+repository,token);
  const repoBody=metadata.body||{};
  const repositoryId=Number(repoBody.id||0)||null;
  const defaultBranch=String(repoBody.default_branch||"main");
  const contents=await safeGithubGet("/repos/"+repository+"/contents?ref="+encodeURIComponent(defaultBranch)+"&per_page=1",token);
  const issues=await safeGithubGet("/repos/"+repository+"/issues?state=open&per_page=1",token);
  const pulls=await safeGithubGet("/repos/"+repository+"/pulls?state=open&per_page=1",token);
  const actions=await safeGithubGet("/repos/"+repository+"/actions/runs?per_page=1",token);
  const ref=await safeGithubGet("/repos/"+repository+"/git/ref/heads/"+encodeURIComponent(defaultBranch),token);
  const sha=String(ref.body?.object?.sha||"");
  const statuses=sha?await safeGithubGet("/repos/"+repository+"/commits/"+sha+"/status",token):{state:"missing",body:null,status:404};
  const checks=sha?await safeGithubGet("/repos/"+repository+"/commits/"+sha+"/check-runs?per_page=100",token):{state:"missing",body:null,status:404};

  const observed:Record<string,string>={
    metadata_read:metadata.state,
    contents_read:contents.state,
    issues_read:issues.state,
    pull_requests_read:pulls.state,
    actions_read:actions.state,
    commit_statuses_read:statuses.state,
    checks_read:checks.state,
    ci_evidence_read:(checks.state==="verified"||(actions.state==="verified"&&statuses.state==="verified"))?"verified":"missing",
    contents_write:permissionAllowsWrite(granted.contents)?"verified":"missing",
    issues_write:permissionAllowsWrite(granted.issues)?"verified":"missing",
    pull_requests_write:permissionAllowsWrite(granted.pull_requests)?"verified":"missing",
  };
  const required:Record<string,boolean>={
    metadata_read:true,contents_read:true,issues_read:true,pull_requests_read:true,
    actions_read:true,commit_statuses_read:true,ci_evidence_read:true,
    checks_read:false,contents_write:true,issues_write:true,pull_requests_write:true,
  };
  const missing=Object.entries(required).filter(([key,needed])=>needed&&observed[key]!=="verified").map(([key])=>key);
  const status=missing.length?"blocked":"ready";
  const error=missing.length?"Missing GitHub App capabilities: "+missing.join(", "):null;

  await rpc("factory_record_project_github_access",{
    p_project_id:String(project.id),
    p_repository:repository,
    p_auth_mode:"github_app",
    p_required_capabilities:required,
    p_observed_capabilities:observed,
    p_status:status,
    p_last_error:error,
    p_evidence:{
      source:"github_app_installation_token",
      app_slug:app.app_slug,
      installation_token_persisted:false,
      installation_token_expires_at:tokenResponse?.expires_at||null,
      repository_selection:tokenResponse?.repository_selection||installation?.repository_selection||null,
      default_branch:defaultBranch,
    },
    p_installation_id:installationId,
    p_repository_id:repositoryId,
  });

  return{
    projectKey,
    repository,
    status,
    installationId,
    repositoryId,
    observedCapabilities:observed,
    tokenPersisted:false,
  };
}
