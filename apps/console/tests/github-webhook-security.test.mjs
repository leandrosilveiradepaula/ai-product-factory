import test from "node:test";
import assert from "node:assert/strict";
import {createHmac} from "node:crypto";
import {
 authenticateGitHubWebhook,normalizeGitHubWebhook,WebhookRejection,MAX_WEBHOOK_BYTES,
} from "../lib/github-webhook-security.ts";

const SHA="a".repeat(40),MERGE="b".repeat(40),APP=5168709;
const GUID="1426ab7d-824b-4a2d-a5de-c18823baff26";
const SECRET="It's a Secret to Everybody";
const base={
 action:"completed",repository:{id:1189600617,full_name:"leandrosilveiradepaula/crm-infodive"},
 installation:{id:167522851,app_id:APP},
 workflow_run:{status:"completed",head_sha:SHA,conclusion:"success"},
};
function signed(data=base,event="workflow_run",secret=SECRET){
 const raw=Buffer.from(JSON.stringify(data));
 const headers=new Headers({
  "Content-Type":"application/json; charset=utf-8",
  "X-GitHub-Delivery":GUID,
  "X-GitHub-Event":event,
  "X-Hub-Signature-256":"sha256="+createHmac("sha256",secret).update(raw).digest("hex"),
 });
 return{raw,headers};
}
function verified(data=base,event="workflow_run"){
 const {raw,headers}=signed(data,event);
 return normalizeGitHubWebhook(authenticateGitHubWebhook(raw,headers,SECRET),headers,APP);
}
function rejected(cb){assert.throws(cb,err=>err instanceof WebhookRejection);}

test("GitHub published HMAC SHA-256 vector over original bytes",()=>{
 const raw=Buffer.from("Hello, World!");
 const headers=new Headers({"Content-Type":"application/json","X-Hub-Signature-256":"sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17"});
 rejected(()=>authenticateGitHubWebhook(raw,headers,SECRET)); // signed bytes valid, JSON intentionally not valid
 const s=signed();
 assert.deepEqual(authenticateGitHubWebhook(s.raw,s.headers,SECRET),base);
});
test("exactly normalized completed workflow run binds numerical repo and installation",()=>{
 const e=verified();
 assert.deepEqual(e,{deliveryId:GUID,eventType:"workflow_run",action:"completed",repositoryId:1189600617,
  repository:"leandrosilveiradepaula/crm-infodive",installationId:167522851,candidateCommit:SHA,prNumber:null});
});
test("reject tampered body, wrong key, missing signature and legacy sha1",()=>{
 const s=signed();const bad=new Headers(s.headers);bad.set("X-Hub-Signature-256","sha1="+"0".repeat(40));
 rejected(()=>authenticateGitHubWebhook(s.raw,bad,SECRET));
 rejected(()=>authenticateGitHubWebhook(Buffer.concat([s.raw,Buffer.from(" ")]),s.headers,SECRET));
 rejected(()=>authenticateGitHubWebhook(s.raw,s.headers,"not the same key at all"));
 bad.delete("X-Hub-Signature-256");rejected(()=>authenticateGitHubWebhook(s.raw,bad,SECRET));
});
test("reject malformed/short secret and malformed HMAC even on well-formed JSON",()=>{
 const s=signed();
 for(const secret of ["", "abc"]){rejected(()=>authenticateGitHubWebhook(s.raw,s.headers,secret));}
 const bad=new Headers(s.headers);bad.set("X-Hub-Signature-256","sha256="+"a".repeat(63));
 rejected(()=>authenticateGitHubWebhook(s.raw,bad,SECRET));
});
test("bound body and content-type",()=>{
 const s=signed();
 rejected(()=>authenticateGitHubWebhook(Buffer.alloc(MAX_WEBHOOK_BYTES+1),s.headers,SECRET));
 rejected(()=>authenticateGitHubWebhook(Buffer.alloc(0),s.headers,SECRET));
 const bad=new Headers(s.headers);bad.set("Content-Type","application/x-www-form-urlencoded");
 rejected(()=>authenticateGitHubWebhook(s.raw,bad,SECRET));
});
test("reject identity spoofing even with valid synthetic HMAC",()=>{
 for(const data of [
  {...base,repository:{...base.repository,id:"1189600617"}},
  {...base,repository:{...base.repository,full_name:"attacker/../crm"}},
  {...base,installation:{...base.installation,id:0}},
  {...base,installation:{...base.installation,app_id:APP+1}},
 ])rejected(()=>verified(data));
 const s=signed();s.headers.set("X-GitHub-Delivery","attacker");
 rejected(()=>normalizeGitHubWebhook(authenticateGitHubWebhook(s.raw,s.headers,SECRET),s.headers,APP));
});
test("reject invalid SHA and untrusted completion state",()=>{
 rejected(()=>verified({...base,workflow_run:{status:"queued",head_sha:SHA}},"workflow_run"));
 rejected(()=>verified({...base,workflow_run:{status:"completed",head_sha:SHA.slice(0,39)}},"workflow_run"));
});
test("check_run and failure outcomes still hint CI reconciliation",()=>{
 const e=verified({...base,check_run:{status:"completed",head_sha:SHA,conclusion:"failure"}},"check_run");
 assert.equal(e?.eventType,"check_run");
 assert.equal(e?.candidateCommit,SHA);
});
test("deployment status is advisory, not Preview PASS",()=>{
 assert.equal(verified({...base,action:"created",deployment:{sha:SHA},deployment_status:{state:"pending"}},"deployment_status"),null);
 assert.equal(verified({...base,action:"created",deployment:{sha:SHA},deployment_status:{state:"success"}},"deployment_status")?.eventType,"deployment_status");
});
test("only merged pull requests reach release observer, never auto merge",()=>{
 const pr={...base,action:"closed",pull_request:{merged:true,number:205,head:{sha:SHA},merge_commit_sha:MERGE}};
 assert.equal(verified(pr,"pull_request")?.prNumber,205);
 assert.equal(verified({...pr,pull_request:{...pr.pull_request,merged:false}},"pull_request"),null);
 rejected(()=>verified({...pr,pull_request:{...pr.pull_request,merge_commit_sha:null}},"pull_request"));
});
test("unsupported actions and event kinds do not wake any worker",()=>{
 assert.equal(verified({...base,action:"requested"},"workflow_run"),null);
 assert.equal(verified({...base,action:"completed"},"push"),null);
 assert.equal(verified({...base,action:"opened"},"pull_request"),null);
});
test("delivery ID is normalized to lowercase for durable uniqueness",()=>{
 const s=signed();s.headers.set("X-GitHub-Delivery",GUID.toUpperCase());
 assert.equal(normalizeGitHubWebhook(authenticateGitHubWebhook(s.raw,s.headers,SECRET),s.headers,APP)?.deliveryId,GUID);
});