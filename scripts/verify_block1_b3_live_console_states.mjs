/** B3: real authenticated React shell; intercepted GET responses are not backend certification. */
const SHA=/^[0-9a-f]{40}$/;
const names=["pending","unavailable","cleared","malformed"];
const fixtures={
 pending:{status:200,body:{status:"ok",count:2,projects:[]}},
 unavailable:{status:503,body:{status:"unavailable"}},
 cleared:{status:200,body:{status:"ok",count:0,projects:[]}},
 malformed:{status:200,body:{status:"ok",count:-1,projects:[]}},
};
export function safeB3StateWitness({observed,runId,sourceCommit,targetCommit}){
 if(!Number.isSafeInteger(Number(runId))||Number(runId)<1||
    !SHA.test(String(sourceCommit))||!SHA.test(String(targetCommit))||
    !observed||observed.blocked!==false||observed.browserErrors!==0||
    observed.mutatingRequests!==0||names.some(name=>observed[name]!==true||
       !Number.isSafeInteger(observed.hits?.[name])||observed.hits[name]<1))
    throw Error("b3_state_witness_incomplete");
 return {
   schema:"factory-b3-authenticated-ui-state-fixture-v1",
   runId:Number(runId),sourceCommit,targetCommit,
   checks:{pending:true,unavailable:true,cleared:true,malformed:true},
   scope:"authenticated_browser_with_intercepted_get_responses_only",
   actualBackendStateCertified:false,fullUserExperienceCertified:false,
   independentCriterionCertified:false,visualAuditPassed:false,
   productionWrites:0,paidCalls:0,credentialOrUserDataRetained:false,
 };
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
 const observed={blocked:false,browserErrors:0,mutatingRequests:0,
    hits:{pending:0,unavailable:0,cleared:0,malformed:0}};
 let scenario="pending";
 page.on("pageerror",()=>{observed.browserErrors++;});
 page.on("console",m=>{if(m.type()==="error")observed.browserErrors++;});
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
   await page.waitForFunction(()=>{
     const top=document.querySelector('a.topbarAttention[aria-label="2 aprovações humanas pendentes"]');
     const nav=document.querySelector('.desktopSidebarContent .humanAttentionCount');
     return top?.getAttribute("href")==="/gates"&&nav?.textContent?.trim()==="2";
   },null,{timeout:20000});
   observed.pending=true;
   scenario="unavailable";
   await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
   await page.waitForFunction(()=>{
     const top=document.querySelector('.topbarAttention[role="status"]');
     return top?.textContent?.trim()==="Aprovações indisponíveis"&&
        !document.querySelector('.desktopSidebarContent .humanAttentionCount');
   },null,{timeout:20000});
   observed.unavailable=true;
   scenario="cleared";
   await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
   await page.waitForFunction(()=>
     !document.querySelector(".topbarAttention")&&
     !document.querySelector(".desktopSidebarContent .humanAttentionCount"),
      null,{timeout:20000});
   observed.cleared=true;
   scenario="malformed";
   await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
   await page.waitForFunction(()=>{
     const top=document.querySelector('.topbarAttention[role="status"]');
     return top?.textContent?.trim()==="Aprovações indisponíveis"&&
        !document.querySelector('.desktopSidebarContent .humanAttentionCount');
   },null,{timeout:20000});
   observed.malformed=true;
   return safeB3StateWitness({observed,runId,sourceCommit,targetCommit});
 }finally{await page.close();}
}
