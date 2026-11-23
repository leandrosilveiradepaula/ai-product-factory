import {NextResponse} from "next/server";
import {getGitHubAppInstallActions,getHumanGates} from "../../../lib/control-plane";
import {requireConsoleOperator} from "../../../lib/auth-server";
import {getGitHubAppStatus} from "../../../lib/github-app";

export const dynamic="force-dynamic";

export async function GET(){
 await requireConsoleOperator();
 try{
  const [gates,installActions,githubApp]=await Promise.all([getHumanGates(100,true),getGitHubAppInstallActions(),getGitHubAppStatus()]);
  const pending=gates.filter(g=>g.status==="pending"&&g.actionable);
  const projects=[...new Set(pending.map(g=>g.projectKey).filter((key):key is string=>Boolean(key)))];
  // Only genuine actionable gates and required per-project access steps count.
  // Registering an optional global GitHub App is not a production decision.
  const count=pending.length+(githubApp.configured?installActions.length:0);
  return NextResponse.json({status:"ok",count,pendingHumanGateCount:pending.length,projects},{headers:{"Cache-Control":"no-store"}});
 }catch{
  return NextResponse.json({status:"unavailable"},{status:503,headers:{"Cache-Control":"no-store"}});
 }
}
