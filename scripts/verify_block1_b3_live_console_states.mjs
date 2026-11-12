/** B3: real authenticated React shell; intercepted GET responses are not backend certification. */
const SHA=/^[0-9a-f]{40}$/;
const names=["pending","unavailable","cleared","malformed"];
const fixtures={
 pending:{status:200,body:{status:"ok",count:2,projects:[]}},
 unavailable:{status:503,body:{status:"unavailable"}},
 cleared:{status:200,body:{status:"ok",count:0,projects:[]}},
 malformed:{status:200,body:{status:"ok",count:-1,projects:[]}},
};
// Chromium emits a native failed-resource console error for OUR deliberate
// GET /api/human-attention -> 503 fixture, even when React handles it correctly.
// The scope is strictly one 503 message with an exact resource URL per
// intercepted 503. Every other console/page error (including React #418) fails.
const EXPECTED_503_RESOURCE_ERROR=/^Failed to load resource: the server responded with a status of 503(?: \(Service Unavailable\))?$/;
export function isExpectedFixture503ResourceError(message,origin){
 if(typeof origin!=="string"||!origin.startsWith("https://"))return false;
 try{
  if(message?.type()!=="error"||
     !EXPECTED_503_RESOURCE_ERROR.test(message.text()))return false;
  const url=new URL(message.location()?.url);
  return url.origin===origin&&url.pathname==="/api/human-attention"&&
    url.search===""&&url.hash==="";
 }catch{return false;}
}

export function safeB3StateWitness({observed,runId,sourceCommit,targetCommit}){
 const reason=(!Number.isSafeInteger(Number(runId))||Number(runId)<1||
    !SHA.test(String(sourceCommit))||!SHA.test(String(targetCommit)))
      ?"identity_unverified"
      :!observed||typeof observed!=="object"||observed.blocked!==false
      ?"interception_unverified"
      :observed.browserErrors!==0
      ?"unexpected_browser_error"
      :observed.mutatingRequests!==0
      ?"unexpected_mutation"
      :names.some(name=>observed[name]!==true||
        !Number.isSafeInteger(observed.hits?.[name])||observed.hits[name]<1)
      ?"missing_state_transition"
      :!Number.isSafeInteger(observed.expected503ResourceErrors)||
       observed.expected503ResourceErrors<0||
       observed.expected503ResourceErrors>observed.hits.unavailable
      ?"unaccounted_fixture_http_error":null;
 if(reason)throw Error("b3_state_witness_incomplete:"+reason);
 return {
   schema:"factory-b3-authenticated-ui-state-fixture-v1",
   runId:Number(runId),sourceCommit,targetCommit,
   checks:{pending:true,unavailable:true,cleared:true,malformed:true},
   scope:"authenticated_browser_with_intercepted_get_responses_only",
   actualBackendStateCertified:false,fullUserExperienceCertified:false,
   independentCriterionCertified:false,visualAuditPassed:false,
   // This number counts only the exact synthetic 503 resource diagnostic.
   expected503ResourceConsoleErrors:observed.expected503ResourceErrors,
   productionWrites:0,paidCalls:0,credentialOrUserDataRetained:false,
 };
}
// Synthetic GET transitions cannot be mistaken for a real WCAG audit.
// Only the waitForFunction DOM timeout is classified as an absent bounded
// state witness. Authentication, navigation, browser and mutation failures
// keep their original fail-closed behavior.
export class B3SyntheticTransitionTimeout extends Error {
  constructor(transition){
    if(!names.includes(transition))throw Error("b3_unknown_transition");
    super("b3_synthetic_transition_not_observed:"+transition);
    this.name="B3SyntheticTransitionTimeout";
    this.transition=transition;
  }
}
async function requireSyntheticTransition(page,transition,predicate,arg,options){
  try{
    await page.waitForFunction(predicate,arg,options);
  }catch(error){
    if(error?.name!=="TimeoutError")throw error;
    throw new B3SyntheticTransitionTimeout(transition);
  }
}

export async function verifyConsoleStatesReadOnly({context,baseUrl,runId,sourceCommit,targetCommit}){
 let origin;
 try{
   const u=new URL(baseUrl);
   if(u.protocol!=="https:"||u.username||u.password||u.search||u.hash||u.pathname!=="/")
     throw Error("unsafe_origin");
   origin=u.origin;
 }catch{throw Error("b3_invalid_console_origin");}
 const page=await context.newPage();
 const observed={blocked:false,browserErrors:0,mutatingRequests:0,expected503ResourceErrors:0,
    hits:{pending:0,unavailable:0,cleared:0,malformed:0}};
 let scenario="pending";
 page.on("pageerror",()=>{observed.browserErrors++;});
 page.on("console",m=>{
   if(m.type()!=="error")return;
   if(observed.expected503ResourceErrors<observed.hits.unavailable&&
      isExpectedFixture503ResourceError(m,origin)){
     observed.expected503ResourceErrors++;
     return;
   }
   observed.browserErrors++;
 });
 page.on("request",r=>{
   if(new URL(r.url()).origin===origin&&!["GET","HEAD","OPTIONS"].includes(r.method()))
     observed.mutatingRequests++;
 });
 try{
   await page.route("**/api/human-attention",async route=>{
     const req=route.request(),url=new URL(req.url());
     if(req.method()!=="GET"||url.origin!==origin||
        url.pathname!=="/api/human-attention"||!Object.hasOwn(fixtures,scenario)){
       observed.blocked=true;await route.abort("blockedbyclient");return;
     }
     observed.hits[scenario]++;
     const response=fixtures[scenario];
     await route.fulfill({status:response.status,contentType:"application/json",
       headers:{"Cache-Control":"no-store"},body:JSON.stringify(response.body)});
   });
   const landing=await page.goto(origin+"/",{waitUntil:"networkidle",timeout:60000});
   if(!landing||landing.status()!==200||new URL(page.url()).pathname!=="/")
     throw Error("b3_authenticated_landing_unavailable");
   await requireSyntheticTransition(page,"pending",()=>{
     // The accessible name is provided by visible text, not the removed
     // aria-label. Regression from real authenticated capture #43138746238.
     const top=document.querySelector('a.topbarAttention.active[href="/gates"]');
     const nav=document.querySelector('.desktopSidebarContent .humanAttentionCount');
     return top?.textContent?.trim()==="2 decisões pendentes"&&
       !top.hasAttribute("aria-label")&&nav?.textContent?.trim()==="2";
   },null,{timeout:20000});
   observed.pending=true;
   scenario="unavailable";
   await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
   await requireSyntheticTransition(page,"unavailable",()=>{
     const top=document.querySelector('.topbarAttention[role="status"]');
     return top?.textContent?.trim()==="Aprovações indisponíveis"&&
        !document.querySelector('.desktopSidebarContent .humanAttentionCount');
   },null,{timeout:20000});
   observed.unavailable=true;
   scenario="cleared";
   await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
   await requireSyntheticTransition(page,"cleared",()=>
     !document.querySelector(".topbarAttention")&&
     !document.querySelector(".desktopSidebarContent .humanAttentionCount"),
      null,{timeout:20000});
   observed.cleared=true;
   scenario="malformed";
   await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
   await requireSyntheticTransition(page,"malformed",()=>{
     const top=document.querySelector('.topbarAttention[role="status"]');
     return top?.textContent?.trim()==="Aprovações indisponíveis"&&
        !document.querySelector('.desktopSidebarContent .humanAttentionCount');
   },null,{timeout:20000});
   observed.malformed=true;
   return safeB3StateWitness({observed,runId,sourceCommit,targetCommit});
 }finally{await page.close();}
}
