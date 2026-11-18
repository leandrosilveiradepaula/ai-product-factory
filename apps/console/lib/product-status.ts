import {requireConsoleOperator} from "./auth-server";
import {getSupabaseServerConfig} from "./supabase-server";
import {getHumanGates} from "./control-plane";
import {assessProductProof,type ProductProof} from "./product-evidence";
import {explainRunBlocker,type ProductBlocker} from "./product-blocker";

/* Read-only interpretation of authoritative Control Plane records. It is NOT
 * a release certification, work scheduler, heartbeat or progress percentage. */
export type ProductState="decision"|"executing"|"verifying"|"queued"|"stopped"|"paused"|"investigate"|"idle"|"unknown";
export type ProductLastRun={id:string;status:string;at:string;taskTitle:string};
export type ProductDatabaseEvidence={state:"verified"|"pending"|"not_recorded";linked:number;lastVerifiedAt:string|null};
export type ProductSituation={
 key:string;name:string;stage:string;isActive:boolean;controlState:string;
 projectKind:string;repository:string|null;isInternalRecord:boolean;
 proof:ProductProof;specStatus:string|null;lastReleaseAt:string|null;
 databaseEvidence:ProductDatabaseEvidence;requirementCount:number;sourceIssueUrl:string|null;blocker:ProductBlocker|null;
 state:ProductState;headline:string;explanation:string;nextOwner:string;nextLabel:string;nextHref:string;
 lastRequest:string|null;lastRequestAt:string|null;lastRun:ProductLastRun|null;
 unclosedTasks:number;confirmedRunning:number;observedAt:string;updatedAt:string;
};
export type ProductSnapshot={products:ProductSituation[];observedAt:string};
export type ProductObservation={
 key:string;isActive:boolean;controlState:string;
 humanDecisions:number;confirmedRunning:number;validatingRuns:number;queuedRuns:number;
 unclosedTasks:number;latestRunStatus:string|null;latestRunId:string|null;latestTaskStatus:string|null;
};
export function summarizeProductStatus(p:ProductObservation):Pick<ProductSituation,"state"|"headline"|"explanation"|"nextOwner"|"nextLabel"|"nextHref">{
 const detail="/projects/"+encodeURIComponent(p.key);
 const last=p.latestRunId?"/runs/"+encodeURIComponent(p.latestRunId):detail;
 const answer=(state:ProductState,headline:string,explanation:string,nextOwner:string,nextLabel:string,nextHref:string)=>
  ({state,headline,explanation,nextOwner,nextLabel,nextHref});
 if(!p.isActive)return answer("stopped","Fora do portfólio ativo","Este produto não está marcado como ativo no cadastro. Isso não diz se houve uma publicação.","Você, se desejar","Abrir produto",detail);
 if(p.controlState==="stopped")return answer("stopped","Projeto parado","A execução está desabilitada pelo controle do projeto. Nenhum novo trabalho será iniciado sem comando autorizado.","Você, se desejar retomar","Ver controle do projeto",detail+"#project-control");
 if(p.controlState==="paused"||p.controlState==="pausing"||p.controlState==="stopping")return answer("paused","Projeto pausado ou parando","O controle restringe novas execuções. Acompanhe o processo de pausa ou decida quando retomar.","Você, se desejar retomar","Ver controle do projeto",detail+"#project-control");
 if(p.humanDecisions>0)return answer("decision","Precisa da sua decisão","Existe uma decisão humana acionável e vinculada a este produto. Revise motivo, impacto e evidências.","Você","Revisar decisão","/gates");
 if(p.confirmedRunning>0)return answer("executing","Factory executando","Há execução com início registrado e lease vigente. Isso não significa que o produto esteja pronto.","Factory","Acompanhar execução",last);
 if(p.validatingRuns>0)return answer("verifying","Validação registrada","O Control Plane indica trabalho em validação; CI, Preview e release ainda precisam das respectivas evidências.","Factory","Ver validação",last);
 if(p.queuedRuns>0)return answer("queued","Trabalho aguardando execução","Há uma execução criada ou enfileirada, mas não foi confirmada atividade de worker.","Factory","Ver tarefa na fila",last);
 if(p.controlState==="unavailable"||p.controlState==="draft")return answer("unknown","Controle não habilitado ou indisponível","Não foi possível comprovar que o projeto pode executar novas tarefas. O Console não deve inferir prontidão.","Você, para avaliar","Ver controle do projeto",detail+"#project-control");
 const failed=new Set(["failed","blocked","failed_gate","repair_pending","dead_letter"]);
 const open=new Set(["failed","blocked","repair_pending","created","queued","running","implementing","ci_pending","planning"]);
 if(p.latestRunStatus&&failed.has(p.latestRunStatus)&&p.latestTaskStatus&&open.has(p.latestTaskStatus))
  return answer("investigate","Última tentativa precisa de investigação","A execução mais recente foi interrompida e sua tarefa continua sem conclusão comprovada. Isso não é uma aprovação humana.","Investigação técnica","Ver última tentativa",last);
 if(p.unclosedTasks>0)return answer("idle","Sem execução ativa confirmada","Existem tarefas sem conclusão técnica registrada, mas nenhum worker ativo foi comprovado nesta consulta.","Factory ou operador técnico","Consultar trabalho pendente","/deliveries?project="+encodeURIComponent(p.key));
 return answer("idle","Nenhum trabalho em execução","O projeto está habilitado para receber trabalho. Não há execução ativa confirmada nem decisão humana pendente nesta consulta.","Você, se quiser novo trabalho","Solicitar melhoria",detail+"/request");
}

type ProjectRow={id:string;project_key:string;name:string;is_active:boolean;lifecycle_stage:string;updated_at:string;manifest:unknown;project_kind?:string;repository?:string|null};
type ControlRow={project_id:string;state:string};
type TaskRow={id:string;project_id:string;title:string;status:string;created_at:string;updated_at:string};
type RunRow={id:string;task_id:string;status:string;created_at:string;started_at:string|null;lease_expires_at:string|null;last_error:string|null};
type ReleaseRow={id:string;project_id:string;status:string;candidate_commit:string|null;created_at:string;report:unknown};
type DeploymentRow={id:string;run_id:string;environment:string;status:string;created_at:string};
type CertificationRow={id:string;project_id:string;assessed_commit:string;is_current:boolean;state:string;created_at:string};
type SpecRow={id:string;project_id:string;status:string;version:number;created_at:string};
type DbRow={id:string;project_id:string;status:string;last_verified_at:string|null};
type RequirementRow={id:string;project_id:string;status:string};
function sourceIssue(manifest:Record<string,unknown>):string|null{
 if(!Array.isArray(manifest.references))return null;
 for(const ref of manifest.references){
  if(!ref||typeof ref!=="object"||Array.isArray(ref))continue;
  const href=(ref as Record<string,unknown>).value;
  if(typeof href==="string"&&/^https:\/\/github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+\/issues\/[1-9][0-9]*$/.test(href))return href;
 }
 return null;
}
function asObject(value:unknown):Record<string,unknown>{
 return value&&typeof value==="object"&&!Array.isArray(value)?value as Record<string,unknown>:{};
}
const terminal=new Set(["completed","integrated","merged","work_unit_completed","cancelled","canceled"]);
async function loadComplete<T extends Record<string,unknown>>(cfg:{url:string;headers:Record<string,string>},table:string,select:string,order:string,key:string):Promise<T[]>{
 const all:T[]=[];const seen=new Set<string>();const pageSize=200;
 for(let page=0;page<20;page++){
  const endpoint=cfg.url+"/rest/v1/"+table+"?select="+encodeURIComponent(select)+"&order="+encodeURIComponent(order)+"&limit="+pageSize+"&offset="+page*pageSize;
  const response=await fetch(endpoint,{headers:cfg.headers,cache:"no-store"});
  if(!response.ok)throw new Error("Estado do produto indisponível: "+table+" HTTP "+response.status);
  const batch:unknown=await response.json();
  if(!Array.isArray(batch)||batch.length>pageSize||batch.some(v=>!v||typeof v!=="object"||Array.isArray(v)))
   throw new Error("Inventário de produto inválido: "+table);
  for(const item of batch as T[]){
   const identity=item[key];
   if(typeof identity!=="string"||!identity||seen.has(identity))throw new Error("Inventário de produto inconsistente: "+table);
   seen.add(identity);all.push(item);
  }
  if(batch.length<pageSize)return all;
 }
 throw new Error("Inventário de produto excedeu o limite seguro de consulta: "+table);
}
export async function getProductSituations():Promise<ProductSnapshot>{
 await requireConsoleOperator();
 const cfg=getSupabaseServerConfig();
 if(!cfg)throw new Error("Control Plane indisponível. Não é seguro exibir produtos sem status.");
 const [projects,controls,tasks,runs,releases,deployments,certifications,specs,databases,requirements,gates]=await Promise.all([
  loadComplete<ProjectRow>(cfg,"factory_projects","id,project_key,name,is_active,lifecycle_stage,updated_at,manifest,project_kind,repository","updated_at.desc,id.desc","id"),
  loadComplete<ControlRow>(cfg,"factory_project_execution_controls","project_id,state","project_id.asc","project_id"),
  loadComplete<TaskRow>(cfg,"factory_tasks","id,project_id,title,status,created_at,updated_at","created_at.desc,id.desc","id"),
  loadComplete<RunRow>(cfg,"factory_runs","id,task_id,status,created_at,started_at,lease_expires_at,last_error","created_at.desc,id.desc","id"),
  loadComplete<ReleaseRow>(cfg,"factory_release_reports","id,project_id,status,candidate_commit,created_at,report","created_at.desc,id.desc","id"),
  loadComplete<DeploymentRow>(cfg,"factory_deployments","id,run_id,environment,status,created_at","created_at.desc,id.desc","id"),
  loadComplete<CertificationRow>(cfg,"factory_product_readiness_certifications","id,project_id,assessed_commit,is_current,state,created_at","created_at.desc,id.desc","id"),
  loadComplete<SpecRow>(cfg,"factory_product_specs","id,project_id,status,version,created_at","created_at.desc,id.desc","id"),
  loadComplete<DbRow>(cfg,"factory_project_databases","id,project_id,status,last_verified_at","id.asc","id"),
  loadComplete<RequirementRow>(cfg,"factory_requirements","id,project_id,status","id.asc","id"),
  getHumanGates(100,true),
 ]);
 if(gates.length===100)throw new Error("Inventário de decisões pode estar truncado.");
 const observedAt=new Date().toISOString(),now=Date.parse(observedAt);
 const byTask=new Map(tasks.map(t=>[t.id,t]));
 const projectTasks=new Map<string,TaskRow[]>();
 for(const t of tasks){const l=projectTasks.get(t.project_id)||[];l.push(t);projectTasks.set(t.project_id,l);}
 const projectRuns=new Map<string,RunRow[]>();
 for(const r of runs){const t=byTask.get(r.task_id);if(!t)continue;const l=projectRuns.get(t.project_id)||[];l.push(r);projectRuns.set(t.project_id,l);}
 const controlById=new Map(controls.map(c=>[c.project_id,c.state]));
 const latestReleases=new Map<string,ReleaseRow>();
 for(const r of releases)if(!latestReleases.has(r.project_id))latestReleases.set(r.project_id,r);
 const latestSpecs=new Map<string,SpecRow>();
 for(const s of specs)if(!latestSpecs.has(s.project_id))latestSpecs.set(s.project_id,s);
 const currentCertifications=new Map<string,CertificationRow>();
 for(const cert of certifications)if(cert.is_current&&cert.state==="persisted"&&!currentCertifications.has(cert.project_id))
  currentCertifications.set(cert.project_id,cert);
 const projectDeployments=new Map<string,DeploymentRow[]>();
 for(const d of deployments){
  const run=runs.find(r=>r.id===d.run_id);
  const task=run?byTask.get(run.task_id):null;
  if(!task)continue;
  const list=projectDeployments.get(task.project_id)||[];
  list.push(d);projectDeployments.set(task.project_id,list);
 }
 const databasesForProject=new Map<string,DbRow[]>();
 for(const db of databases){const list=databasesForProject.get(db.project_id)||[];list.push(db);databasesForProject.set(db.project_id,list);}
 const requirementCounts=new Map<string,number>();
 for(const req of requirements)if(req.status==="active")requirementCounts.set(req.project_id,(requirementCounts.get(req.project_id)||0)+1);
 const pendingGates=new Map<string,number>();
 for(const g of gates)if(g.status==="pending"&&g.actionable&&g.projectKey)pendingGates.set(g.projectKey,(pendingGates.get(g.projectKey)||0)+1);
 const products:ProductSituation[]=projects.map(p=>{
  const tasksFor=projectTasks.get(p.id)||[],runsFor=projectRuns.get(p.id)||[];
  const last=runsFor[0]||null;
  const lastTask=last?byTask.get(last.task_id):null;
  // An in-progress label requires an actual started run with a live lease.
  const verifiedRunning=runsFor.filter(r=>["running","implementing"].includes(r.status)&&
   typeof r.started_at==="string"&&Number.isFinite(Date.parse(r.started_at))&&
   typeof r.lease_expires_at==="string"&&Date.parse(r.lease_expires_at)>now);
  const latestRuns=new Map<string,RunRow>();
  for(const r of runsFor)if(!latestRuns.has(r.task_id))latestRuns.set(r.task_id,r);
  const relevant=[...latestRuns.values()].filter(r=>{
   const t=byTask.get(r.task_id);
   return t&&!terminal.has(t.status);
  });
  const validationCount=relevant.filter(r=>["ci_pending","preview_ready","review_ready"].includes(r.status)).length;
  const queuedCount=relevant.filter(r=>["created","queued"].includes(r.status)).length;
  const continuation=p.manifest&&typeof p.manifest==="object"&&!Array.isArray(p.manifest)
   ?(p.manifest as Record<string,unknown>).continuation_request:null;
  const request=continuation&&typeof continuation==="object"&&!Array.isArray(continuation)?continuation as Record<string,unknown>:null;
  const requestText=typeof request?.summary==="string"&&request.summary.trim()?request.summary.trim().slice(0,280):null;
  const requestDate=typeof request?.requested_at==="string"&&Number.isFinite(Date.parse(request.requested_at))?request.requested_at:null;
  const control=controlById.get(p.id)||"unavailable";
  const latestRelease=latestReleases.get(p.id)||null;
  const report=asObject(latestRelease?.report);
  const dFor=projectDeployments.get(p.id)||[];
  const readiness=asObject(report.product_readiness);
  const definition=asObject(report.definition_of_done);
  const certification=currentCertifications.get(p.id)||null;
  const proof=assessProductProof({
   releaseStatus:latestRelease?.status||null,
   productComplete:report.product_complete,
   productReadinessReady:readiness.ready,
   definitionReady:definition.ready,
   mergeSha:report.merge_sha,
   hasPreviewRecord:dFor.some(d=>d.environment==="preview"&&d.status==="success"),
   hasProductionDeployment:dFor.some(d=>d.environment==="production"&&d.status==="success"),
   certificationSha:certification?.assessed_commit||null,
   releaseCandidateSha:latestRelease?.candidate_commit||null,
  });
  const manifest=asObject(p.manifest);
  const databaseRecords=databasesForProject.get(p.id)||[];
  const verifiedDatabases=databaseRecords.filter(d=>["ready_read","ready_write"].includes(d.status)&&Boolean(d.last_verified_at));
  const dbEvidence:ProductDatabaseEvidence={
   state:verifiedDatabases.length>0?"verified":databaseRecords.length>0?"pending":"not_recorded",
   linked:databaseRecords.length,lastVerifiedAt:verifiedDatabases[0]?.last_verified_at||null,
  };
  const blocker=last&&lastTask&&!terminal.has(lastTask.status)?explainRunBlocker(last.status,last.last_error):null;
  const isInternalRecord=manifest.qa_canary===true&&(!p.repository||p.repository.length===0);
  const status=summarizeProductStatus({
   key:p.project_key,isActive:p.is_active,controlState:control,
   humanDecisions:pendingGates.get(p.project_key)||0,confirmedRunning:verifiedRunning.length,
   validatingRuns:validationCount,queuedRuns:queuedCount,
   unclosedTasks:tasksFor.filter(t=>!terminal.has(t.status)).length,
   latestRunStatus:last?.status||null,latestRunId:verifiedRunning[0]?.id||relevant.find(r=>["ci_pending","preview_ready","review_ready","created","queued"].includes(r.status))?.id||last?.id||null,latestTaskStatus:lastTask?.status||null,
  });
  return {...status,key:p.project_key,name:p.name,stage:p.lifecycle_stage,
   isActive:p.is_active,controlState:control,
   projectKind:p.project_kind||"unknown",repository:p.repository||null,isInternalRecord,
   proof,specStatus:latestSpecs.get(p.id)?.status||null,
   lastReleaseAt:latestRelease?.created_at||null,
   databaseEvidence:dbEvidence,requirementCount:requirementCounts.get(p.id)||0,
   sourceIssueUrl:sourceIssue(manifest),blocker,
   lastRequest:requestText,lastRequestAt:requestDate,
   lastRun:last?{id:last.id,status:last.status,at:last.created_at,taskTitle:lastTask?.title||"Execução registrada"}:null,
   unclosedTasks:tasksFor.filter(t=>!terminal.has(t.status)).length,
   confirmedRunning:verifiedRunning.length,observedAt,updatedAt:p.updated_at};
 });
 const order:Record<ProductState,number>={decision:0,executing:1,verifying:2,queued:3,investigate:4,idle:5,paused:6,stopped:7,unknown:8};
 products.sort((a,b)=>order[a.state]-order[b.state]||Date.parse(b.lastRun?.at||b.updatedAt)-Date.parse(a.lastRun?.at||a.updatedAt));
 return{products,observedAt};
}
