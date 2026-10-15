import {NextResponse} from "next/server";
import {requireConsoleAdmin} from "../../../../../lib/auth-server";
import {getSupabaseServerConfig} from "../../../../../lib/supabase-server";
import {getProjectDetail} from "../../../../../lib/control-plane";
import {inspectPrivateProjectRepositoryBeforeLink,verifyProjectGitHubApp} from "../../../../../lib/github-app";

export const dynamic="force-dynamic";

function back(origin:string,key:string,result:string){
 return NextResponse.redirect(
  new URL("/projects/"+encodeURIComponent(key)+"?repo_link="+encodeURIComponent(result),origin),303
 );
}

export async function POST(request:Request,{params}:{params:Promise<{key:string}>}){
 await requireConsoleAdmin();
 const url=new URL(request.url);
 if(!request.headers.get("origin")||request.headers.get("origin")!==url.origin){
  return NextResponse.json({error:"invalid origin"},{status:403});
 }
 if(!(request.headers.get("content-type")||"").startsWith("application/x-www-form-urlencoded")){
  return NextResponse.json({error:"invalid content type"},{status:415});
 }
 const {key}=await params;
 if(!/^[a-z0-9][a-z0-9-]{0,63}$/.test(key)){
  return NextResponse.json({error:"invalid project key"},{status:400});
 }
 const expected="leandrosilveiradepaula/"+key;
 const cfg=getSupabaseServerConfig();
 if(!cfg)return back(url.origin,key,"unavailable");
 const project=await getProjectDetail(key);
 if(!project||!project.active||project.kind!=="greenfield"){
  return back(url.origin,key,"not_eligible");
 }
 if(project.repository&&project.repository!==expected){
  return back(url.origin,key,"already_bound");
 }
 // Reject linking a repository already owned by another Factory project.
 const existing=await fetch(
  cfg.url+"/rest/v1/factory_projects?select=id&repository=eq."+
  encodeURIComponent(expected)+"&is_active=eq.true&limit=2",
  {headers:cfg.headers,cache:"no-store"}
 );
 if(!existing.ok)return back(url.origin,key,"unavailable");
 const conflicts=(await existing.json()) as {id:string}[];
 if(conflicts.some(x=>x.id!==project.id))return back(url.origin,key,"already_bound");

 // A GitHub App installed by the operator must already be authorized on the
 // exact new private repository. Probe first, before any Control Plane write.
 try{await inspectPrivateProjectRepositoryBeforeLink(expected);}
 catch{return back(url.origin,key,"not_ready");}

 if(!project.repository){
  const linked=await fetch(
   cfg.url+"/rest/v1/factory_projects?id=eq."+encodeURIComponent(project.id)+
   "&repository=is.null&project_kind=eq.greenfield&is_active=eq.true",
   {method:"PATCH",
    headers:{...cfg.headers,"Content-Type":"application/json","Prefer":"return=representation"},
    body:JSON.stringify({repository:expected}),cache:"no-store"}
  );
  if(!linked.ok)return back(url.origin,key,"unavailable");
  const rows=(await linked.json()) as {id:string;repository:string}[];
  if(rows.length!==1||rows[0].id!==project.id||rows[0].repository!==expected){
   return back(url.origin,key,"already_bound");
  }
 }
 // Authoritative project capability verification persists durable evidence via
 // the restricted factory_record_project_github_access RPC. Never claim ready
 // based merely on installing the App or observing a successful repository GET.
 try{
  const result=await verifyProjectGitHubApp(key);
  return back(url.origin,key,result.status==="ready"?"linked":"verify_pending");
 }catch{
  return back(url.origin,key,"verify_pending");
 }
}
