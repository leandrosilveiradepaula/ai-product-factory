import {cookies} from "next/headers";
import {NextResponse} from "next/server";
import {requireConsoleAdmin} from "../../../../../lib/auth-server";
import {verifyProjectGitHubApp} from "../../../../../lib/github-app";

export async function GET(request:Request){
  await requireConsoleAdmin();
  const url=new URL(request.url);
  const project=url.searchParams.get("project");
  const returnTo=url.searchParams.get("return_to");
  if(!project)return NextResponse.json({error:"missing project"},{status:400});
  try{
    const result=await verifyProjectGitHubApp(project);
    const outcome=result.status==="ready"?"verified":"blocked";
    const jar=await cookies();
    jar.delete("factory_github_app_install_project");
    const target=returnTo==="gates"
      ?"/gates?github_app="+outcome
      :"/projects/"+encodeURIComponent(project)+"?github_app="+outcome;
    return NextResponse.redirect(new URL(target,url.origin));
  }catch{
    const jar=await cookies();
    jar.delete("factory_github_app_install_project");
    const target=returnTo==="gates"
      ?"/gates?github_app=verification_failed"
      :"/projects/"+encodeURIComponent(project)+"?github_app=verification_failed";
    return NextResponse.redirect(new URL(target,url.origin));
  }
}
