import {cookies} from "next/headers";
import {NextResponse} from "next/server";
import {requireConsoleAdmin} from "../../../../../lib/auth-server";
import {createGitHubAppManifestFlow} from "../../../../../lib/github-app";

function escapeHtml(value:string){
  return value.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

export async function GET(request:Request){
  await requireConsoleAdmin();
  const url=new URL(request.url);
  const organization=url.searchParams.get("organization");
  const gateId=url.searchParams.get("gate");
  const flow=createGitHubAppManifestFlow(url.origin,organization);
  const jar=await cookies();
  jar.set("factory_github_app_manifest_state",flow.state,{
    httpOnly:true,
    secure:process.env.NODE_ENV==="production",
    sameSite:"lax",
    path:"/api/integrations/github-app",
    maxAge:600,
  });
  if(gateId&&/^[0-9a-f-]{36}$/i.test(gateId)){
    jar.set("factory_github_app_gate",gateId,{
      httpOnly:true,
      secure:process.env.NODE_ENV==="production",
      sameSite:"lax",
      path:"/api/integrations/github-app",
      maxAge:600,
    });
  }
  const action=flow.target+"?state="+encodeURIComponent(flow.state);
  const manifest=JSON.stringify(flow.manifest);
  const html="<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><title>Registrar GitHub App</title></head><body>"+
    "<form id=\"github-app-manifest\" method=\"post\" action=\""+escapeHtml(action)+"\">"+
    "<input type=\"hidden\" name=\"manifest\" value=\""+escapeHtml(manifest)+"\">"+
    "<noscript><button type=\"submit\">Continuar para o GitHub</button></noscript></form>"+
    "<script>document.getElementById(\"github-app-manifest\").submit();</script></body></html>";
  return new NextResponse(html,{status:200,headers:{"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store"}});
}
