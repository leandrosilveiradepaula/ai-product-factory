/** Best-effort wake after durable intake commit. Never turns an accepted intake into an error. */
export async function requestIntakeWorkerWake():Promise<"requested"|"unconfigured"|"failed"> {
 const token=process.env.FACTORY_GITHUB_WORKFLOW_DISPATCH_TOKEN;
 if(!token)return "unconfigured";
 try {
  const response=await fetch("https://api.github.com/repos/leandrosilveiradepaula/ai-product-factory/actions/workflows/autonomous-runner.yml/dispatches",{
   method:"POST",headers:{Authorization:`Bearer ${token}`,Accept:"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"},
   body:JSON.stringify({ref:"main",inputs:{run_direct:false,run_codex:false,run_alerts:false,run_preview:false}}),
   signal:AbortSignal.timeout(3500),cache:"no-store",
  });
  if(response.status===204)return "requested";
  console.warn("intake_worker_wake_failed",{status:response.status});
  return "failed";
 }catch {
  console.warn("intake_worker_wake_failed",{reason:"transport"});
  return "failed";
 }
}
