import {createHash,randomBytes} from "node:crypto";
import {getSupabaseServerConfig} from "./supabase-server";

export const SUPABASE_OAUTH_CALLBACK="https://ai-product-factory-console.vercel.app/api/integrations/supabase/callback";

function oauthConfig(){
 const clientId=process.env.SUPABASE_OAUTH_CLIENT_ID?.trim();
 const clientSecret=process.env.SUPABASE_OAUTH_CLIENT_SECRET?.trim();
 if(!clientId||!clientSecret)throw new Error("Supabase OAuth is not configured");
 return{clientId,clientSecret};
}
function b64url(value:Buffer){return value.toString("base64url");}
export function createSupabaseOAuthRequest(projectKey:string,databaseId:string){
 const {clientId}=oauthConfig();const verifier=b64url(randomBytes(48));const state=b64url(randomBytes(32));
 const challenge=b64url(createHash("sha256").update(verifier).digest());
 const url=new URL("https://api.supabase.com/v1/oauth/authorize");
 url.searchParams.set("client_id",clientId);url.searchParams.set("redirect_uri",SUPABASE_OAUTH_CALLBACK);
 url.searchParams.set("response_type","code");url.searchParams.set("state",state);
 url.searchParams.set("code_challenge",challenge);url.searchParams.set("code_challenge_method","S256");
 return{url:url.toString(),verifier,state,projectKey,databaseId};
}
export async function exchangeSupabaseOAuthCode(code:string,verifier:string){
 const {clientId,clientSecret}=oauthConfig();
 const response=await fetch("https://api.supabase.com/v1/oauth/token",{method:"POST",headers:{
  "Content-Type":"application/x-www-form-urlencoded",Accept:"application/json",
  Authorization:"Basic "+Buffer.from(clientId+":"+clientSecret).toString("base64")
 },body:new URLSearchParams({grant_type:"authorization_code",code,redirect_uri:SUPABASE_OAUTH_CALLBACK,code_verifier:verifier}),cache:"no-store"});
 if(!response.ok)throw new Error("Supabase OAuth token exchange failed");
 return response.json() as Promise<{access_token:string;refresh_token?:string;token_type?:string;expires_in?:number}>;
}
export async function verifySupabaseProjectReadAccess(accessToken:string,projectRef:string){
 const project=await fetch("https://api.supabase.com/v1/projects/"+encodeURIComponent(projectRef),{headers:{Authorization:"Bearer "+accessToken,Accept:"application/json"},cache:"no-store"});
 if(!project.ok)throw new Error("Authorized Supabase account cannot access the expected project");
 const metadata=await project.json();const observed=String(metadata.ref||metadata.id||"");
 if(observed!==projectRef)throw new Error("Supabase project identity mismatch");
 const query=await fetch("https://api.supabase.com/v1/projects/"+encodeURIComponent(projectRef)+"/database/query/read-only",{method:"POST",headers:{Authorization:"Bearer "+accessToken,"Content-Type":"application/json",Accept:"application/json"},body:JSON.stringify({query:"select current_database() as database_name, current_user as database_user"}),cache:"no-store"});
 if(!query.ok)throw new Error("Supabase read-only database verification failed");
 await query.json();return{projectRef,readVerified:true};
}
async function rpc(name:string,body:unknown){
 const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control Plane is unavailable");
 const r=await fetch(cfg.url+"/rest/v1/rpc/"+name,{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},body:JSON.stringify(body),cache:"no-store"});
 if(!r.ok)throw new Error("Control Plane OAuth persistence failed");return r.json();
}
export async function storeSupabaseOAuth(databaseId:string,tokens:{access_token:string;refresh_token?:string;token_type?:string;expires_in?:number}){
 const expires=tokens.expires_in?new Date(Date.now()+tokens.expires_in*1000).toISOString():null;
 await rpc("factory_store_project_database_oauth",{p_database_id:databaseId,p_access_token:tokens.access_token,p_refresh_token:tokens.refresh_token||null,p_token_type:tokens.token_type||"bearer",p_expires_at:expires});
}
export async function recordSupabaseReadVerification(databaseId:string,projectRef:string){
 await rpc("factory_record_project_database_verification",{p_database_id:databaseId,p_verified_project_ref:projectRef,p_read_verified:true,p_write_verified:false,p_evidence:{method:"oauth_management_api",read_only_query:true}});
}
