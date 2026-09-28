import { createRemoteJWKSet, jwtVerify } from "npm:jose@6.1.0";

const ISSUER = "https://token.actions.githubusercontent.com";
const AUDIENCE = "factory-runtime-control-plane";
const JWKS = createRemoteJWKSet(new URL("https://token.actions.githubusercontent.com/.well-known/jwks"));
const EXPECTED = {
  repository: "leandrosilveiradepaula/ai-product-factory",
  repository_id: "1387883686",
  repository_owner_id: "256917842",
  ref: "refs/heads/main",
};
const ALLOWED_WORKFLOW_REFS = new Set([
  "leandrosilveiradepaula/ai-product-factory/.github/workflows/autonomous-runner.yml@refs/heads/main",
  "leandrosilveiradepaula/ai-product-factory/.github/workflows/control-plane-oidc-preflight.yml@refs/heads/main",
]);

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
  if(!["schedule","workflow_dispatch","push"].includes(event)) throw new Error("GitHub OIDC event not allowed");
  return payload;
}

function getSecretKey() {
  const modern=Deno.env.get("SUPABASE_SECRET_KEYS");
  if(modern) {
    const parsed=JSON.parse(modern);
    const key=String(parsed.default||"");
    if(key) return key;
  }
  const legacy=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")||"";
  if(!legacy) throw new Error("Supabase privileged key unavailable");
  return legacy;
}

function allowedSuffix(url:URL) {
  const marker="/functions/v1/factory-runtime-control-plane";
  const index=url.pathname.indexOf(marker);
  if(index<0) throw new Error("unexpected function path");
  const suffix=url.pathname.slice(index+marker.length);
  if(!suffix.startsWith("/rest/v1/")) throw new Error("only PostgREST/RPC access is allowed");
  if(suffix.includes("..")) throw new Error("invalid path");
  const resource=suffix.slice("/rest/v1/".length);
  const allowed =
    resource.startsWith("factory_") ||
    resource.startsWith("rpc/factory_");
  if(!allowed) throw new Error("resource not allowed");
  return suffix;
}

Deno.serve(async(req:Request)=>{
  try {
    await verifyGithub(req);
    if(!["GET","POST","PATCH"].includes(req.method)) return json(405,{error:"method_not_allowed"});
    const requestUrl=new URL(req.url);
    const suffix=allowedSuffix(requestUrl);
    const supabaseUrl=(Deno.env.get("SUPABASE_URL")||"").replace(/\/$/,"");
    if(!supabaseUrl) throw new Error("SUPABASE_URL unavailable");
    const key=getSecretKey();
    const headers=new Headers();
    headers.set("apikey",key);
    headers.set("accept","application/json");
    const contentType=req.headers.get("content-type");
    if(contentType) headers.set("content-type",contentType);
    const prefer=req.headers.get("prefer");
    if(prefer) headers.set("prefer",prefer);
    if(!key.startsWith("sb_secret_")) headers.set("authorization","Bearer "+key);
    const target=supabaseUrl+suffix+requestUrl.search;
    const body=req.method==="GET"?undefined:await req.arrayBuffer();
    const response=await fetch(target,{method:req.method,headers,body});
    const responseHeaders=new Headers();
    const outType=response.headers.get("content-type");
    if(outType) responseHeaders.set("content-type",outType);
    responseHeaders.set("cache-control","no-store");
    return new Response(response.body,{status:response.status,headers:responseHeaders});
  } catch(error) {
    console.error("factory runtime control-plane broker rejected request");
    return json(403,{error:"forbidden",detail:error instanceof Error?error.message:"unknown"});
  }
});
