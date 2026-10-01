import releasePolicy from "../../../config/factory.release-policy.v1.json";
import {requireConsoleAdmin} from "./auth-server";
import {getSupabaseServerConfig} from "./supabase-server";

type ReleaseMergeReadiness={enabled:boolean;reason:string|null};
type ReleaseMergeResult={merged:true;mergeSha:string;repository:string;prNumber:number;controlPlaneRecorded:boolean};

const SHA_RE=/^[0-9a-f]{40}$/;
const REPO_RE=/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

function allowedRepositories(){
 return new Set((process.env.FACTORY_RELEASE_GITHUB_REPOSITORIES||"")
  .split(",").map(x=>x.trim()).filter(Boolean));
}

function configuredMergeMethod(){
 const method=String((releasePolicy as any).production?.operator_merge_method||"squash");
 if(!["merge","squash","rebase"].includes(method))throw new Error("Método de merge de produção inválido na política.");
 return method as "merge"|"squash"|"rebase";
}

export function getReleaseMergeReadiness(repository:string|null):ReleaseMergeReadiness{
 if(process.env.VERCEL_ENV!=="production")return{enabled:false,reason:"O merge pelo Console só é habilitado em produção."};
 if(!(releasePolicy as any).production?.human_console_merge_allowed)return{enabled:false,reason:"A política de release não habilita merge humano pelo Console."};
 if(!process.env.FACTORY_RELEASE_GITHUB_TOKEN)return{enabled:false,reason:"Credencial dedicada de release ainda não configurada."};
 if(!repository||!REPO_RE.test(repository))return{enabled:false,reason:"Repositório de release inválido ou ausente."};
 if(!allowedRepositories().has(repository))return{enabled:false,reason:"Repositório fora da allowlist de release."};
 return{enabled:true,reason:null};
}

function githubHeaders(token:string){
 return{
  Accept:"application/vnd.github+json",
  Authorization:`Bearer ${token}`,
  "X-GitHub-Api-Version":"2022-11-28",
  "User-Agent":"ai-product-factory-console-release",
 };
}

async function controlPlaneJson(path:string,init?:RequestInit){
 const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control Plane não configurado.");
 const response=await fetch(cfg.url+"/rest/v1/"+path,{...init,headers:{...cfg.headers,...(init?.headers||{})},cache:"no-store"});
 if(!response.ok)throw new Error("Falha ao consultar o Control Plane para release.");
 return response.json();
}

async function recordAudit(input:{projectId:string;taskId:string;runId:string;actorRef:string;eventType:string;payload:Record<string,unknown>}){
 const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control Plane não configurado.");
 const response=await fetch(cfg.url+"/rest/v1/factory_audit_events",{
  method:"POST",
  headers:{...cfg.headers,"Content-Type":"application/json","Prefer":"return=minimal"},
  body:JSON.stringify({
   project_id:input.projectId,task_id:input.taskId,run_id:input.runId,
   actor_type:"human",actor_ref:input.actorRef,event_type:input.eventType,payload:input.payload,
  }),
  cache:"no-store",
 });
 if(!response.ok)throw new Error("Não foi possível registrar a auditoria pré-merge.");
}

export async function mergeReadyReleaseFromConsole(runId:string,expectedCandidate:string):Promise<ReleaseMergeResult>{
 const operator=await requireConsoleAdmin();
 if(!runId.trim()||!SHA_RE.test(expectedCandidate))throw new Error("Release ou SHA candidato inválido.");

 const reports=await controlPlaneJson(
  "factory_release_reports?select=id,project_id,run_id,candidate_commit,status,report&run_id=eq."+
  encodeURIComponent(runId)+"&limit=1"
 ) as any[];
 const report=reports[0];
 if(!report||String(report.status)!=="ready_for_human_release")throw new Error("Release não está pronto para merge humano.");
 const candidate=String(report.candidate_commit||"");
 if(candidate!==expectedCandidate)throw new Error("O candidato mudou desde a abertura da tela. Atualize antes de continuar.");

 const [runs,projects]=await Promise.all([
  controlPlaneJson("factory_runs?select=id,task_id,status&run_id=eq."+encodeURIComponent(runId)+"&limit=1").catch(async()=>{
   return controlPlaneJson("factory_runs?select=id,task_id,status&id=eq."+encodeURIComponent(runId)+"&limit=1");
  }),
  controlPlaneJson("factory_projects?select=id,repository&" + "id=eq."+encodeURIComponent(String(report.project_id))+"&limit=1"),
 ]) as [any[],any[]];
 const run=runs[0];const project=projects[0];
 if(!run||String(run.status)!=="awaiting_release")throw new Error("A execução não está em awaiting_release.");
 const repository=String(project?.repository||"");
 const readiness=getReleaseMergeReadiness(repository);
 if(!readiness.enabled)throw new Error(readiness.reason||"Merge pelo Console indisponível.");

 const prNumber=Number(report.report?.pr_number);
 if(!Number.isInteger(prNumber)||prNumber<=0)throw new Error("Release report sem PR válido.");
 const token=process.env.FACTORY_RELEASE_GITHUB_TOKEN as string;
 const method=configuredMergeMethod();
 const prResponse=await fetch(`https://api.github.com/repos/${repository}/pulls/${prNumber}`,{
  headers:githubHeaders(token),cache:"no-store"
 });
 if(!prResponse.ok)throw new Error("Não foi possível revalidar o PR no GitHub.");
 const pr=await prResponse.json();
 if(String(pr.state)!=="open")throw new Error("O PR não está aberto.");
 if(Boolean(pr.draft))throw new Error("PR draft não pode ser liberado.");
 if(String(pr.base?.ref)!=="main")throw new Error("O PR não aponta para main.");
 if(String(pr.base?.repo?.full_name)!==repository)throw new Error("Repositório base divergente.");
 if(String(pr.head?.repo?.full_name)!==repository)throw new Error("PR de fork não é permitido para release pela Factory.");
 if(String(pr.head?.sha)!==candidate)throw new Error("SHA do PR diverge do candidato validado.");
 if(pr.mergeable!==true)throw new Error("GitHub ainda não considera o PR mergeável. Atualize e tente novamente.");

 const actorRef=operator.email||operator.userId;
 const auditBase={repository,pr_number:prNumber,candidate_commit:candidate,merge_method:method};
 await recordAudit({
  projectId:String(report.project_id),taskId:String(run.task_id),runId,actorRef,
  eventType:"human_release.console_merge_requested",payload:auditBase,
 });

 const mergeResponse=await fetch(`https://api.github.com/repos/${repository}/pulls/${prNumber}/merge`,{
  method:"PUT",headers:{...githubHeaders(token),"Content-Type":"application/json"},
  body:JSON.stringify({sha:candidate,merge_method:method}),cache:"no-store",
 });
 const merge=await mergeResponse.json().catch(()=>({}));
 if(!mergeResponse.ok||merge?.merged!==true){
  await recordAudit({
   projectId:String(report.project_id),taskId:String(run.task_id),runId,actorRef,
   eventType:"human_release.console_merge_failed",
   payload:{...auditBase,http_status:mergeResponse.status},
  }).catch(()=>undefined);
  throw new Error("O GitHub recusou o merge. Nenhuma liberação foi registrada pela Factory.");
 }
 const mergeSha=String(merge.sha||"");
 if(!SHA_RE.test(mergeSha))throw new Error("GitHub confirmou o merge sem retornar um SHA válido.");

 await recordAudit({
  projectId:String(report.project_id),taskId:String(run.task_id),runId,actorRef,
  eventType:"human_release.console_merge_succeeded",
  payload:{...auditBase,merge_sha:mergeSha},
 }).catch(()=>undefined);

 let controlPlaneRecorded=false;
 const cfg=getSupabaseServerConfig();
 if(cfg){
  const marked=await fetch(cfg.url+"/rest/v1/rpc/factory_mark_release_report_released",{
   method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},
   body:JSON.stringify({p_run_id:runId,p_merge_sha:mergeSha}),cache:"no-store",
  });
  controlPlaneRecorded=marked.ok;
 }
 return{merged:true,mergeSha,repository,prNumber,controlPlaneRecorded};
}
