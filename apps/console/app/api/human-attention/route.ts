import {NextResponse} from "next/server";
import {getGitHubAppInstallActions,getHumanGates} from "../../../lib/control-plane";
import {requireConsoleOperator} from "../../../lib/auth-server";
import {getGitHubAppStatus} from "../../../lib/github-app";
import {ownerAttentionCounts} from "../../../lib/owner-attention-counts";

export const dynamic="force-dynamic";

export async function GET(){
 await requireConsoleOperator();
 try{
  const [gates,installActions,githubApp]=await Promise.all([getHumanGates(100,true),getGitHubAppInstallActions(),getGitHubAppStatus()]);
  const pending=gates.filter(g=>g.status==="pending"&&g.actionable);
  const projects=[...new Set(pending.map(g=>g.projectKey).filter((key):key is string=>Boolean(key)))];
  // Match the /gates inbox, including the registration action when no App is configured.
  const counts=ownerAttentionCounts({pendingHumanGateCount:pending.length,githubAppConfigured:githubApp.configured,pendingInstallCount:installActions.length});
  return NextResponse.json({status:"ok",...counts,projects},{headers:{"Cache-Control":"no-store"}});
 }catch{
  return NextResponse.json({status:"unavailable"},{status:503,headers:{"Cache-Control":"no-store"}});
 }
}
