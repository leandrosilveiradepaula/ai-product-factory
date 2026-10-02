import {NextResponse} from "next/server";
import {requireConsoleAdmin} from "../../../../../lib/auth-server";
import {verifyProjectGitHubApp} from "../../../../../lib/github-app";

export async function GET(request:Request){
  await requireConsoleAdmin();
  const url=new URL(request.url);
  const project=url.searchParams.get("project");
  if(!project)return NextResponse.json({error:"missing project"},{status:400});
  try{
    const result=await verifyProjectGitHubApp(project);
    const outcome=result.status==="ready"?"verified":"blocked";
    return NextResponse.redirect(new URL("/projects/"+encodeURIComponent(project)+"?github_app="+outcome,url.origin));
  }catch{
    return NextResponse.redirect(new URL("/projects/"+encodeURIComponent(project)+"?github_app=verification_failed",url.origin));
  }
}
