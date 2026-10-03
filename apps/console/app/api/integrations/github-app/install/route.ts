import {cookies} from "next/headers";
import {NextResponse} from "next/server";
import {requireConsoleAdmin} from "../../../../../lib/auth-server";
import {getProjectDetail} from "../../../../../lib/control-plane";
import {getGitHubAppStatus} from "../../../../../lib/github-app";

export async function GET(request:Request){
  await requireConsoleAdmin();
  const url=new URL(request.url);
  const projectKey=String(url.searchParams.get("project")||"").trim();
  if(!/^[a-z0-9][a-z0-9-]{0,63}$/.test(projectKey)){
    return NextResponse.redirect(new URL("/gates?github_app=install_project_invalid",url.origin));
  }

  const [project,app]=await Promise.all([getProjectDetail(projectKey),getGitHubAppStatus()]);
  if(!project||!project.active||!project.repository||project.key==="ai-product-factory"){
    return NextResponse.redirect(new URL("/gates?github_app=install_project_invalid",url.origin));
  }
  if(!app.configured||!app.app_slug){
    return NextResponse.redirect(new URL("/gates?github_app=not_registered",url.origin));
  }

  const jar=await cookies();
  jar.set("factory_github_app_install_project",project.key,{
    httpOnly:true,
    secure:process.env.NODE_ENV==="production",
    sameSite:"lax",
    path:"/",
    maxAge:900,
  });

  return NextResponse.redirect("https://github.com/apps/"+encodeURIComponent(app.app_slug)+"/installations/new");
}
