// Trusted Vercel tenant/project boundary for an authenticated Console capture.
// A generic *.vercel.app hostname is NOT a credential-safe identity: a third
// party can serve a forged /api/health response and receive the OIDC header,
// temporary operator email and password. Pin the official project namespace.
export const CONSOLE_PRODUCTION_HOST="ai-product-factory-console.vercel.app";
export const CONSOLE_PROJECT="ai-product-factory-console";
export const CONSOLE_TEAM="leandros-projects-102e32ab";
const PREVIEW_HOST=/^ai-product-factory-console-[a-z0-9]{8,20}-leandros-projects-102e32ab\.vercel\.app$/;
const DEPLOYMENT_ID=/^[A-Za-z0-9]{20,40}$/;

export function consoleVisualOrigin(input){
 if(typeof input!=="string"||input.length<12||input.length>255)
  throw new Error("invalid visual target origin");
 let url;
 try{url=new URL(input);}catch{throw new Error("invalid visual target URL");}
 const host=url.hostname;
 if(url.protocol!=="https:"||
    (host!==CONSOLE_PRODUCTION_HOST&&!PREVIEW_HOST.test(host))||
    url.username||url.password||url.port||url.search||url.hash||
    (url.pathname!=="/"&&url.pathname!=="")){
  throw new Error("visual target is not a trusted Infodive Console Vercel origin");
 }
 return url.origin;
}

export function consoleVercelDeploymentStatus(status){
 if(!status||typeof status!=="object"||Array.isArray(status)||
    status.context!=="Vercel"||status.state!=="success"||
    typeof status.target_url!=="string"||
    status.target_url.length>250){
  throw new Error("Vercel exact-SHA deployment status missing or unsuccessful");
 }
 let url;
 try{url=new URL(status.target_url);}catch{throw new Error("invalid Vercel deployment status URL");}
 const parts=url.pathname.split("/").filter(Boolean);
 if(url.protocol!=="https:"||url.hostname!=="vercel.com"||
    url.username||url.password||url.port||url.search||url.hash||
    parts.length!==3||parts[0]!==CONSOLE_TEAM||
    parts[1]!==CONSOLE_PROJECT||!DEPLOYMENT_ID.test(parts[2])){
  throw new Error("Vercel status is not the Infodive Console project");
 }
 return {deploymentId:parts[2],project:CONSOLE_PROJECT,team:CONSOLE_TEAM};
}
