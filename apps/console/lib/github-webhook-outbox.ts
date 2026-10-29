/** Service-role-only durable wake intent, never the actual task claimant. */
import {getSupabaseServerConfig} from "./supabase-server";
import type {GitHubExternalEvent} from "./github-webhook-security";

export type WebhookClaim={status:"claimed";attempt:number;run_id:string}|{status:"duplicate"|"ignored"|"deferred"|"exhausted"};
const CONTROL_PLANE="https://fjplmxfcshhbmzgvyqlm.supabase.co";

async function rpc(name:string,body:Record<string,unknown>):Promise<Record<string,unknown>>{
 const cfg=getSupabaseServerConfig();
 if(!cfg||cfg.url.replace(/\/$/,"")!==CONTROL_PLANE)throw Error("control_plane_unavailable");
 const response=await fetch(cfg.url+"/rest/v1/rpc/"+name,{
  method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},
  body:JSON.stringify(body),cache:"no-store",signal:AbortSignal.timeout(3500),
 });
 if(!response.ok)throw Error("event_ledger_unavailable");
 const record=await response.json();
 if(!record||typeof record!=="object"||Array.isArray(record))throw Error("event_ledger_invalid");
 return record as Record<string,unknown>;
}

export async function claimExternalWebhookWake(e:GitHubExternalEvent):Promise<WebhookClaim>{
 const result=await rpc("factory_claim_external_webhook_wake_v1",{
  p_delivery_id:e.deliveryId,p_event_type:e.eventType,p_action:e.action,
  p_repository_id:e.repositoryId,p_repository:e.repository,
  p_installation_id:e.installationId,p_candidate_commit:e.candidateCommit,p_pr_number:e.prNumber,
 });
 if(result.status==="claimed"&&typeof result.run_id==="string"&&/^[0-9a-f-]{36}$/.test(result.run_id)
   &&typeof result.attempt==="number"&&Number.isSafeInteger(result.attempt)&&result.attempt>=1&&result.attempt<=3){
  return {status:"claimed",run_id:result.run_id,attempt:result.attempt};
 }
 if(["duplicate","ignored","deferred","exhausted"].includes(String(result.status))){
  return {status:result.status as "duplicate"|"ignored"|"deferred"|"exhausted"};
 }
 throw Error("event_ledger_invalid");
}
export async function acknowledgeExternalWebhookWake(deliveryId:string,attempt:number,outcome:"requested"|"failed"){
 const result=await rpc("factory_ack_external_webhook_wake_v1",{
  p_delivery_id:deliveryId,p_attempt:attempt,p_outcome:outcome,
 });
 if(!["requested","retryable","exhausted","suppressed"].includes(String(result.status))){
  throw Error("event_ack_invalid");
 }
 return result.status as string;
}