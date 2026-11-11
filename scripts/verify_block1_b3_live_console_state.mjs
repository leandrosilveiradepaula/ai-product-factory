/** B3: retain a bounded observation of a real, authenticated backend state. */
const SHA=/^[0-9a-f]{40}$/;

function requireIdentity({runId,sourceCommit,targetCommit}){
 if(!Number.isSafeInteger(Number(runId))||Number(runId)<1||
    !SHA.test(String(sourceCommit))||!SHA.test(String(targetCommit)))
   throw Error("b3_live_state_identity_invalid");
}

function safeClass(body){
 if(!body||typeof body!=="object")throw Error("b3_live_state_body_invalid");
 if(body.status==="unavailable")return {state:"unavailable",countClass:"unknown"};
 if(body.status!=="ok"||!Number.isSafeInteger(body.count)||body.count<0||
    !Array.isArray(body.projects)||!body.projects.every(key=>typeof key==="string"&&key.length>0))
   throw Error("b3_live_state_body_invalid");
 return {state:"available",countClass:body.count===0?"zero":"positive"};
}

export function safeLiveStateWitness({runId,sourceCommit,targetCommit,httpStatus,body}){
 requireIdentity({runId,sourceCommit,targetCommit});
 if(httpStatus!==200&&httpStatus!==503)throw Error("b3_live_state_status_invalid");
 const observed=safeClass(body);
 if((httpStatus===200)!==(observed.state==="available"))
   throw Error("b3_live_state_status_body_mismatch");
 return {
   schema:"factory-b3-live-console-state-observation-v1",
   runId:Number(runId),sourceCommit,targetCommit,endpoint:"/api/human-attention",
   httpStatus,state:observed.state,countClass:observed.countClass,
   actualBackendStateObserved:true,fullUserExperienceCertified:false,
   independentCriterionCertified:false,visualAuditPassed:false,
   responseBodyRetained:false,projectsRetained:false,
   productionWrites:0,paidCalls:0,credentialOrUserDataRetained:false,
 };
}

export async function verifyLiveConsoleStateReadOnly({context,baseUrl,runId,sourceCommit,targetCommit}){
 let origin;
 try{
  const url=new URL(baseUrl);
  if(url.protocol!=="https:"||url.username||url.password||url.search||url.hash||url.pathname!=="/")throw Error();
  origin=url.origin;
 }catch{throw Error("b3_live_state_origin_invalid");}
 const response=await context.request.get(origin+"/api/human-attention",{maxRedirects:0,timeout:60000});
 const httpStatus=response.status();
 if(httpStatus!==200&&httpStatus!==503)throw Error("b3_live_state_response_invalid");
 let body;
 try{body=await response.json();}catch{throw Error("b3_live_state_json_invalid");}
 return safeLiveStateWitness({runId,sourceCommit,targetCommit,httpStatus,body});
}
