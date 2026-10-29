import {authenticateGitHubWebhook,normalizeGitHubWebhook,MAX_WEBHOOK_BYTES,WebhookRejection} from "../../../../../lib/github-webhook-security";
import {getGitHubWebhookVerificationConfig} from "../../../../../lib/github-webhook-verification-config";
import {claimExternalWebhookWake,acknowledgeExternalWebhookWake} from "../../../../../lib/github-webhook-outbox";
import {requestIntakeWorkerWake} from "../../../../../lib/intake-worker-wake";

export const runtime="nodejs";
const noStore={"Cache-Control":"no-store"};
function answer(status:number,detail:string){return Response.json({status:detail},{status,headers:noStore});}

/** Read at most MAX_WEBHOOK_BYTES. Never parse JSON or consume unbounded data
 * before validating the GitHub HMAC over the original raw bytes. */
async function boundedBody(request:Request):Promise<Uint8Array>{
 const declared=request.headers.get("content-length");
 if(declared!==null&&(!/^\d+$/.test(declared)||Number(declared)>MAX_WEBHOOK_BYTES)){
  throw new WebhookRejection("body_size_invalid");
 }
 const reader=request.body?.getReader();
 if(!reader)throw new WebhookRejection("body_size_invalid");
 const chunks:Uint8Array[]=[];let size=0;
 try{
  while(true){
   const next=await reader.read();if(next.done)break;
   size+=next.value.byteLength;
   if(size>MAX_WEBHOOK_BYTES)throw new WebhookRejection("body_size_invalid");
   chunks.push(next.value);
  }
 }catch(error){await reader.cancel().catch(()=>{});throw error;}
 finally{reader.releaseLock();}
 const buffer=new Uint8Array(size);let index=0;
 for(const chunk of chunks){buffer.set(chunk,index);index+=chunk.byteLength;}
 return buffer;
}

export async function POST(request:Request){
 // Deliberately OFF in all deployments until the sensitive GitHub App webhook
 // registration, Vault secret, reviewed SQL migration and Console release gate.
 if(process.env.FACTORY_GITHUB_WEBHOOK_ENABLED!=="true")return answer(503,"disabled");
 let verifier:{appId:number;webhookSecret:string};
 try{verifier=await getGitHubWebhookVerificationConfig();}
 catch{return answer(503,"unavailable");}
 let event;
 try{
  const bytes=await boundedBody(request);
  const payload=authenticateGitHubWebhook(bytes,request.headers,verifier.webhookSecret);
  event=normalizeGitHubWebhook(payload,request.headers,verifier.appId);
 }catch(error){
  return answer(error instanceof WebhookRejection?403:503,"rejected");
 }
 if(event===null)return answer(202,"ignored");
 let claim;
 try{claim=await claimExternalWebhookWake(event);}
 catch{return answer(503,"unavailable");}
 if(claim.status!=="claimed")return answer(202,claim.status);
 let result:"requested"|"failed"="failed";
 try{result=(await requestIntakeWorkerWake())==="requested"?"requested":"failed";}
 catch{result="failed";}
 try{
  const ack=await acknowledgeExternalWebhookWake(event.deliveryId,claim.attempt,result);
  if(result==="requested"&&ack==="requested")return answer(202,"wake_requested");
 }catch{return answer(503,"ack_unavailable");}
 // Durable receipt can be safely retried after lease/backoff; no claim/model
 // is executed by this route, and a GitHub HTTP 204 is only dispatch acceptance.
 return answer(503,"wake_pending");
}