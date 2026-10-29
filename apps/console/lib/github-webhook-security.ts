/**
 * Pure authentication + normalization for the disabled-by-default GitHub App
 * webhook. No Supabase, GitHub or model actions live here.
 */
import {createHmac,timingSafeEqual} from "node:crypto";

export const MAX_WEBHOOK_BYTES=192*1024;
export type GitHubExternalEvent={
 deliveryId:string;
 eventType:"workflow_run"|"check_run"|"deployment_status"|"pull_request";
 action:"completed"|"created"|"closed";
 repositoryId:number;
 repository:string;
 installationId:number;
 candidateCommit:string;
 prNumber:number|null;
};

export class WebhookRejection extends Error{
 readonly code:string;
 constructor(code:string){super(code);this.name="WebhookRejection";this.code=code;}
}

function object(value:unknown):Record<string,unknown>{
 if(value===null||typeof value!=="object"||Array.isArray(value))throw new WebhookRejection("malformed_payload");
 return value as Record<string,unknown>;
}
function optionalObject(value:unknown):Record<string,unknown>|null{
 return value===undefined||value===null?null:object(value);
}
function positiveSafeNumber(value:unknown):number{
 if(typeof value!=="number"||!Number.isSafeInteger(value)||value<1)throw new WebhookRejection("invalid_identity");
 return value;
}
function commit(value:unknown):string{
 if(typeof value!=="string"||!/^[0-9a-f]{40}$/.test(value))throw new WebhookRejection("invalid_commit");
 return value;
}
function validGuid(value:string|null):string{
 if(!value||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)){
  throw new WebhookRejection("invalid_delivery");
 }
 return value.toLowerCase();
}

export function authenticateGitHubWebhook(raw:Uint8Array,headers:Headers,secret:string):unknown{
 if(!secret||secret.length<16)throw new WebhookRejection("webhook_unconfigured");
 if(raw.byteLength===0||raw.byteLength>MAX_WEBHOOK_BYTES)throw new WebhookRejection("body_size_invalid");
 if((headers.get("content-type")||"").split(";")[0].trim().toLowerCase()!=="application/json"){
  throw new WebhookRejection("invalid_content_type");
 }
 const signature=headers.get("x-hub-signature-256")||"";
 if(!/^sha256=[a-f0-9]{64}$/.test(signature))throw new WebhookRejection("invalid_signature");
 const expected=createHmac("sha256",secret).update(raw).digest();
 const supplied=Buffer.from(signature.slice(7),"hex");
 if(supplied.length!==expected.length||!timingSafeEqual(expected,supplied)){
  throw new WebhookRejection("invalid_signature");
 }
 let payload:unknown;
 try{payload=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(raw));}
 catch{throw new WebhookRejection("malformed_payload");}
 return object(payload);
}

/** Return null for authenticated but non-actionable events; never use the
 *  payload as an authority to start a project or approve a release. */
export function normalizeGitHubWebhook(payload:unknown,headers:Headers,appId:number):GitHubExternalEvent|null{
 const data=object(payload);
 const event=headers.get("x-github-event")||"";
 const deliveryId=validGuid(headers.get("x-github-delivery"));
 if(!Number.isSafeInteger(appId)||appId<1)throw new WebhookRejection("webhook_unconfigured");
 const repository=object(data.repository),installation=object(data.installation);
 const repositoryId=positiveSafeNumber(repository.id);
 const installationId=positiveSafeNumber(installation.id);
 const name=repository.full_name;
 if(typeof name!=="string"||!/^[-A-Za-z0-9_.]+\/[-A-Za-z0-9_.]+$/.test(name)||name.length>180){
  throw new WebhookRejection("invalid_repository");
 }
 if(installation.app_id!==undefined&&positiveSafeNumber(installation.app_id)!==appId){
  throw new WebhookRejection("foreign_app");
 }
 const action=data.action;
 if(typeof action!=="string")return null;
 let candidateCommit:string;
 let prNumber:number|null=null;
 if(event==="workflow_run"&&action==="completed"){
  const run=object(data.workflow_run);
  if(run.status!=="completed")throw new WebhookRejection("invalid_completion");
  candidateCommit=commit(run.head_sha);
 }else if(event==="check_run"&&action==="completed"){
  const check=object(data.check_run);
  if(check.status!=="completed")throw new WebhookRejection("invalid_completion");
  candidateCommit=commit(check.head_sha);
 }else if(event==="deployment_status"&&action==="created"){
  const status=object(data.deployment_status),deployment=object(data.deployment);
  if(!["success","failure","error"].includes(String(status.state)))return null;
  candidateCommit=commit(deployment.sha);
 }else if(event==="pull_request"&&action==="closed"){
  const pr=object(data.pull_request);
  if(pr.merged!==true)return null;
  candidateCommit=commit(object(pr.head).sha);
  commit(pr.merge_commit_sha); // Release observer separately checks human merger and actual target.
  prNumber=positiveSafeNumber(pr.number);
 }else{return null;}
 return{
  deliveryId,eventType:event,action:action as GitHubExternalEvent["action"],
  repositoryId,repository:name,installationId,candidateCommit,prNumber,
 } as GitHubExternalEvent;
}