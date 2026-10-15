import {requestFactoryIntakeWakeViaGitHubApp} from "./github-app";

/**
 * Best-effort wake after durable intake commit. Never returns an API token,
 * claims a worker, or turns an accepted intake into an error.
 */
export async function requestIntakeWorkerWake():Promise<"requested"|"unconfigured"|"failed">{
 const token=process.env.FACTORY_GITHUB_WORKFLOW_DISPATCH_TOKEN;
 let tokenFailed=false;
 if(token){
  try{
   const response=await fetch("https://api.github.com/repos/leandrosilveiradepaula/ai-product-factory/actions/workflows/autonomous-runner.yml/dispatches",{
    method:"POST",
    headers:{Authorization:`Bearer ${token}`,Accept:"application/vnd.github+json",
     "X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"},
    body:JSON.stringify({ref:"main",inputs:{run_direct:false,run_codex:false,run_alerts:false,run_preview:false}}),
    signal:AbortSignal.timeout(3500),cache:"no-store",
   });
   if(response.status===204)return "requested";
   console.warn("intake_worker_token_wake_failed",{status:response.status});
   tokenFailed=true;
  }catch{
   console.warn("intake_worker_token_wake_failed",{reason:"transport"});
   tokenFailed=true;
  }
 }
 // Existing GitHub App is a credentialless-for-the-operator alternative:
 // it uses the app private key already stored in the privileged Control Plane.
 const appResult=await requestFactoryIntakeWakeViaGitHubApp();
 if(appResult==="requested")return "requested";
 return tokenFailed||appResult==="failed"?"failed":"unconfigured";
}
