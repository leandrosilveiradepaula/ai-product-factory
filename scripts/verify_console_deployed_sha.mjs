// Fail-closed source-of-truth check for authenticated UI captures.
// A successful GitHub/Vercel status alone cannot prove the production alias
// serves the target revision; /api/health must report that same exact SHA prefix.
import {pathToFileURL} from "node:url";

export function validVisualIdentity({url,sha}){
 if(!/^[0-9a-f]{40}$/.test(String(sha||"")))throw new Error("expected exact visual target SHA");
 const origin=new URL(String(url||""));
 if(origin.protocol!=="https:"||!(origin.hostname==="ai-product-factory-console.vercel.app"||origin.hostname.endsWith(".vercel.app"))||
  origin.username||origin.password||origin.search||origin.hash||(origin.pathname!=="/"&&origin.pathname!=="")){
  throw new Error("invalid visual Console origin");
 }
 return {origin:origin.origin,expectedPrefix:sha.slice(0,12)};
}

export function isMatchingHealth(payload,expectedPrefix){
 return !!payload&&typeof payload==="object"&&!Array.isArray(payload)&&
  payload.status==="ok"&&payload.service==="ai-product-factory-console"&&
  payload.commit===expectedPrefix;
}

export async function verifyConsoleDeployment({url,sha,oidcToken="",attempts=24,waitMs=5000,request=fetch,sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))}){
 const {origin,expectedPrefix}=validVisualIdentity({url,sha});
 if(!Number.isSafeInteger(attempts)||attempts<1||attempts>30)throw new Error("invalid number of verification attempts");
 let lastFailure="not_yet_verified";
 const target=new URL("/api/health",origin);
 for(let i=0;i<attempts;i++){
  try{
   const headers={"Accept":"application/json","Cache-Control":"no-store"};
   if(oidcToken)headers["x-vercel-trusted-oidc-idp-token"]=oidcToken;
   const resp=await request(target.toString(),{headers,redirect:"error",signal:AbortSignal.timeout(12000)});
   if(resp.status===200){
    const payload=await resp.json();
    if(isMatchingHealth(payload,expectedPrefix)){
     return {verified:true,commitPrefix:expectedPrefix,attempts:i+1,origin};
    }
    lastFailure="returned_commit_or_service_did_not_match";
   }else lastFailure="unexpected_http_status_"+resp.status;
  }catch(_error){
   lastFailure="request_failed";
  }
  if(i<attempts-1)await sleep(waitMs);
 }
 // Do not print health response contents, auth tokens, or session metadata.
 throw new Error("exact Console deployment not verified: "+lastFailure+
  "; expected commit prefix "+expectedPrefix);
}

async function main(){
 const attempts=Number(process.env.FACTORY_VISUAL_VERIFY_ATTEMPTS||24);
 const result=await verifyConsoleDeployment({
  url:process.env.FACTORY_CONSOLE_URL,
  sha:process.env.FACTORY_VISUAL_TARGET_COMMIT,
  oidcToken:process.env.FACTORY_VERCEL_TRUSTED_OIDC_TOKEN||"",
  attempts,
 });
 console.log("Console deployment verified: "+result.origin+
  " SHA "+result.commitPrefix+" attempts="+result.attempts);
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 main().catch(error=>{console.error("::error::"+error.message);process.exitCode=1;});
}
