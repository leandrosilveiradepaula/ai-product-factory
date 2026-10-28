import {cookies} from "next/headers";
import {NextResponse} from "next/server";
import {requireConsoleAdmin} from "../../../../../lib/auth-server";
import {verifyProjectGitHubApp} from "../../../../../lib/github-app";

// A capability verification persists a Control Plane access decision.
// It must never be triggered by a navigation, prefetch, or foreign-site GET.
export function GET(){
  return NextResponse.json({error:"method not allowed"},{
    status:405,headers:{"Allow":"POST","Cache-Control":"no-store"}
  });
}

export async function POST(request:Request){
  await requireConsoleAdmin();
  const url=new URL(request.url);
  const origin=request.headers.get("origin");
  if(!origin||origin!==url.origin){
    return NextResponse.json({error:"invalid origin"},{status:403});
  }
  const type=request.headers.get("content-type")||"";
  if(!type.startsWith("application/x-www-form-urlencoded")){
    return NextResponse.json({error:"invalid content type"},{status:415});
  }
  const form=await request.formData();
  const project=String(form.get("project")||"");
  const returnTo=String(form.get("return_to")||"project");
  if(!/^[a-z0-9][a-z0-9-]{0,63}$/.test(project)
     ||!["project","gates"].includes(returnTo)){
    return NextResponse.json({error:"invalid verification request"},{status:400});
  }
  let outcome="verification_failed";
  try{
    const result=await verifyProjectGitHubApp(project);
    outcome=result.status==="ready"?"verified":"blocked";
  }catch{
    // Failure is not evidence of GitHub App readiness.
  }
  const jar=await cookies();
  if(jar.get("factory_github_app_install_project")?.value===project){
    jar.delete("factory_github_app_install_project");
  }
  const target=returnTo==="gates"
    ?"/gates?github_app="+outcome
    :"/projects/"+encodeURIComponent(project)+"?github_app="+outcome;
  return NextResponse.redirect(new URL(target,url.origin),303);
}
