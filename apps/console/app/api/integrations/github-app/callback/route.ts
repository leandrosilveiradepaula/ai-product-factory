import {cookies} from "next/headers";
import {NextResponse} from "next/server";
import {requireConsoleAdmin} from "../../../../../lib/auth-server";
import {convertGitHubAppManifest,storeGitHubAppConversion} from "../../../../../lib/github-app";

export async function GET(request:Request){
  await requireConsoleAdmin();
  const url=new URL(request.url);
  const code=url.searchParams.get("code");
  const state=url.searchParams.get("state");
  const jar=await cookies();
  const expected=jar.get("factory_github_app_manifest_state")?.value;
  jar.delete("factory_github_app_manifest_state");
  if(!code||!state||!expected||state!==expected){
    return NextResponse.redirect(new URL("/projects?github_app=manifest_invalid",url.origin));
  }
  try{
    const app=await convertGitHubAppManifest(code);
    await storeGitHubAppConversion(app);
    return NextResponse.redirect(new URL("/projects?github_app=registered",url.origin));
  }catch{
    return NextResponse.redirect(new URL("/projects?github_app=registration_failed",url.origin));
  }
}
