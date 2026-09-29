import {NextResponse} from "next/server";import {cookies} from "next/headers";
import {requireConsoleAdmin} from "../../../../../lib/auth-server";
import {createSupabaseOAuthRequest,isSupabaseOAuthConfigured} from "../../../../../lib/supabase-oauth";
import {getSupabaseServerConfig} from "../../../../../lib/supabase-server";

export async function GET(request:Request){
 await requireConsoleAdmin();const u=new URL(request.url);const projectKey=u.searchParams.get("project");const databaseId=u.searchParams.get("database");
 if(!projectKey||!databaseId)return NextResponse.json({error:"missing project/database"},{status:400});
 if(!isSupabaseOAuthConfigured())return NextResponse.json({error:"supabase_oauth_not_configured"},{status:503});
 const cfg=getSupabaseServerConfig();if(!cfg)return NextResponse.json({error:"control plane unavailable"},{status:503});
 const projectLookup=await fetch(cfg.url+"/rest/v1/factory_projects?select=id,project_key&project_key=eq."+encodeURIComponent(projectKey)+"&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!projectLookup.ok)return NextResponse.json({error:"project lookup failed"},{status:502});const projects=await projectLookup.json();if(!projects.length)return NextResponse.json({error:"project unavailable"},{status:404});
 const lookup=await fetch(cfg.url+"/rest/v1/factory_project_databases?select=id,project_id,project_ref,status&id=eq."+encodeURIComponent(databaseId)+"&project_id=eq."+encodeURIComponent(String(projects[0].id))+"&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!lookup.ok)return NextResponse.json({error:"database lookup failed"},{status:502});const rows=await lookup.json();if(!rows.length||!rows[0].project_ref)return NextResponse.json({error:"database binding unavailable"},{status:404});
 if(rows[0].status!=="pending_access")return NextResponse.json({error:"database binding is not awaiting access"},{status:409});
 const flow=createSupabaseOAuthRequest(projectKey,databaseId);const jar=await cookies();
 const opts={httpOnly:true,secure:true,sameSite:"lax" as const,path:"/api/integrations/supabase",maxAge:600};
 jar.set("factory_supa_oauth_state",flow.state,opts);jar.set("factory_supa_oauth_verifier",flow.verifier,opts);
 jar.set("factory_supa_oauth_project",projectKey,opts);jar.set("factory_supa_oauth_database",databaseId,opts);
 return NextResponse.redirect(flow.url);
}