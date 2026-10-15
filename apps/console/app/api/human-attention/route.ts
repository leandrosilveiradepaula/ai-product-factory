import {NextResponse} from "next/server";
import {getGitHubAppInstallActions,getHumanGates} from "../../../lib/control-plane";
import {requireConsoleOperator} from "../../../lib/auth-server";

export const dynamic="force-dynamic";

export async function GET(){
 await requireConsoleOperator();
 try{
  const [gates,installActions]=await Promise.all([getHumanGates(100),getGitHubAppInstallActions()]);
  const pending=gates.filter(g=>g.status==="pending"&&g.actionable);
  const projects=[...new Set(pending.map(g=>g.projectKey).filter((key):key is string=>Boolean(key)))];
  const count=pending.length+installActions.length;
  return NextResponse.json({status:"ok",count,projects},{headers:{"Cache-Control":"no-store"}});
 }catch{
  return NextResponse.json({status:"unavailable"},{status:503,headers:{"Cache-Control":"no-store"}});
 }
}
