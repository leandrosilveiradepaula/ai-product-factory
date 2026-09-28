import {NextResponse} from "next/server";import {cookies} from "next/headers";
import {requireConsoleAdmin} from "../../../../../lib/auth-server";
import {exchangeSupabaseOAuthCode,recordSupabaseReadVerification,storeSupabaseOAuth,verifySupabaseProjectReadAccess} from "../../../../../lib/supabase-oauth";
import {getSupabaseServerConfig} from "../../../../../lib/supabase-server";

export async function GET(request:Request){
 await requireConsoleAdmin();const u=new URL(request.url);const code=u.searchParams.get("code");const state=u.searchParams.get("state");const jar=await cookies();
 const expected=jar.get("factory_supa_oauth_state")?.value;const verifier=jar.get("factory_supa_oauth_verifier")?.value;const projectKey=jar.get("factory_supa_oauth_project")?.value;const databaseId=jar.get("factory_supa_oauth_database")?.value;
 for(const n of ["factory_supa_oauth_state","factory_supa_oauth_verifier","factory_supa_oauth_project","factory_supa_oauth_database"])jar.delete(n);
 if(!code||!state||!expected||state!==expected||!verifier||!projectKey||!databaseId)return NextResponse.redirect(new URL("/projects?supabase=oauth_invalid",u.origin));
 const cfg=getSupabaseServerConfig();if(!cfg)return NextResponse.redirect(new URL("/projects/"+encodeURIComponent(projectKey)+"?supabase=control_plane_unavailable",u.origin));
 const lookup=await fetch(cfg.url+"/rest/v1/factory_project_databases?select=project_ref&id=eq."+encodeURIComponent(databaseId)+"&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!lookup.ok)return NextResponse.redirect(new URL("/projects/"+encodeURIComponent(projectKey)+"?supabase=lookup_failed",u.origin));const rows=await lookup.json();const projectRef=rows[0]?.project_ref;
 if(!projectRef)return NextResponse.redirect(new URL("/projects/"+encodeURIComponent(projectKey)+"?supabase=project_ref_missing",u.origin));
 try{
  const tokens=await exchangeSupabaseOAuthCode(code,verifier);
  await verifySupabaseProjectReadAccess(tokens.access_token,String(projectRef));
  await storeSupabaseOAuth(databaseId,tokens);await recordSupabaseReadVerification(databaseId,String(projectRef));
  return NextResponse.redirect(new URL("/projects/"+encodeURIComponent(projectKey)+"?supabase=connected",u.origin));
 }catch{return NextResponse.redirect(new URL("/projects/"+encodeURIComponent(projectKey)+"?supabase=verification_failed",u.origin));}
}