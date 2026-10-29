/** Resolve the existing GitHub App webhook secret from privileged Supabase
 * Vault via the already-restricted credentials RPC; never send to browser. */
import {getSupabaseServerConfig} from "./supabase-server";

const CONTROL_PLANE="https://fjplmxfcshhbmzgvyqlm.supabase.co";
export async function getGitHubWebhookVerificationConfig():Promise<{appId:number;webhookSecret:string}>{
 const cfg=getSupabaseServerConfig();
 if(!cfg||cfg.url.replace(/\/$/,"")!==CONTROL_PLANE)throw Error("webhook_config_unavailable");
 const res=await fetch(cfg.url+"/rest/v1/rpc/factory_get_github_app_credentials",{
  method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},
  body:"{}",cache:"no-store",signal:AbortSignal.timeout(3500),
 });
 if(!res.ok)throw Error("webhook_config_unavailable");
 const result=await res.json();
 if(!Number.isSafeInteger(result?.app_id)||result.app_id<1
   ||result.status!=="registered"||typeof result.webhook_secret!=="string"
   ||result.webhook_secret.length<16){throw Error("webhook_config_unavailable");}
 return{appId:result.app_id,webhookSecret:result.webhook_secret};
}