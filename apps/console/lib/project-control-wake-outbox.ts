import {randomUUID} from "node:crypto";
import {getSupabaseServerConfig} from "./supabase-server";
import {requestIntakeWorkerWake} from "./intake-worker-wake";

const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type WakeResult="requested"|"failed"|"unconfigured";
async function rpc(name:string,body:unknown):Promise<any>{
 const cfg=getSupabaseServerConfig();
 if(!cfg)throw new Error("Control Plane unavailable");
 const response=await fetch(cfg.url+"/rest/v1/rpc/"+name,{
  method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},
  body:JSON.stringify(body),cache:"no-store",
 });
 if(!response.ok){
  const error=new Error("Project control wake RPC unavailable");
  Object.assign(error,{status:response.status});
  throw error;
 }
 if(response.status===204)return null;
 return response.json();
}
/** Never attempt a wake from draft registration or an uncommitted action. */
export async function deliverProjectControlWake(commandId:string):Promise<WakeResult>{
 if(!uuid.test(commandId))throw new Error("Invalid control command identity");
 const owner="console-"+randomUUID();
 let claim:Record<string,unknown>|null;
 try{
  claim=await rpc("factory_claim_project_control_wake",{p_owner:owner,p_command_id:commandId});
 }catch(error){
  // The schema migration has its own human gate. Until it is applied,
  // preserve the existing post-commit GitHub wake behavior without falsely
  // declaring a durable outbox receipt.
  if(Number((error as {status?:number}).status||0)===404)
   return requestIntakeWorkerWake();
  throw error;
 }
 if(!claim)return "unconfigured";
 if(claim.status==="suppressed"||claim.status==="exhausted")return "failed";
 if(claim.status!=="claimed"||typeof claim.id!=="string"||!uuid.test(claim.id))
   return "unconfigured";
 let status:WakeResult="failed";
 try{status=await requestIntakeWorkerWake();}
 catch{status="failed";}
 const ack=await rpc("factory_ack_project_control_wake",{
   p_id:claim.id,p_owner:owner,p_result:status==="requested"?"dispatched":"failed",
 });
 if(!ack||ack.id!==claim.id||!["pending","dispatched","suppressed","exhausted"].includes(ack.status)
    ||(status==="requested"&&ack.status!=="dispatched"&&ack.status!=="suppressed"))
   throw new Error("Control wake audit receipt mismatch");
 return status;
}
export async function getProjectControlWakeStatus(projectId:string):Promise<{status:string;attempts:number;updatedAt:string|null}|null>{
 if(!uuid.test(projectId))return null;
 const cfg=getSupabaseServerConfig();if(!cfg)return null;
 const r=await fetch(cfg.url+"/rest/v1/factory_project_control_wakes?select=status,attempts,updated_at&project_id=eq."+encodeURIComponent(projectId)+"&order=created_at.desc&limit=1",{
   headers:cfg.headers,cache:"no-store"
 });
 if(!r.ok)return null;
 const rows=await r.json();
 if(!Array.isArray(rows)||rows.length===0||!rows[0]||
    typeof rows[0].status!=="string"||!Number.isSafeInteger(rows[0].attempts))return null;
 return {status:rows[0].status,attempts:rows[0].attempts,updatedAt:rows[0].updated_at||null};
}
