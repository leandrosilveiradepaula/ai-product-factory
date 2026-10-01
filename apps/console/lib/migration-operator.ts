import {createHash} from "node:crypto";
import migrationPolicy from "../../../config/factory.supabase-migration-policy.v1.json";
import {requireConsoleAdmin} from "./auth-server";
import {getSupabaseServerConfig} from "./supabase-server";

type MigrationReadiness={enabled:boolean;reason:string|null};
type MigrationApplyResult={
 applied:boolean;
 alreadyApplied:boolean;
 migrationName:string;
 projectRef:string;
 candidateCommit:string;
};

const SHA_RE=/^[0-9a-f]{40}$/;
const MIGRATION_PATH_RE=/^supabase\/migrations\/(\d{14})_([a-z0-9_]+)\.sql$/;
const REPO_RE=/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

type ProjectPolicy={
 repository:string;
 supabase_project_ref:string;
 migration_path_prefix:string;
};

function policyProject(projectKey:string|null):ProjectPolicy|null{
 if(!projectKey)return null;
 const projects=(migrationPolicy as any).projects||{};
 const item=projects[projectKey];
 if(!item)return null;
 return{
  repository:String(item.repository||""),
  supabase_project_ref:String(item.supabase_project_ref||""),
  migration_path_prefix:String(item.migration_path_prefix||""),
 };
}

export function getMigrationApplyReadiness(projectKey:string|null,repository:string|null):MigrationReadiness{
 if(process.env.VERCEL_ENV!=="production")return{enabled:false,reason:"A aplicação de migration pelo Console só é habilitada em produção."};
 if(!(migrationPolicy as any).enabled)return{enabled:false,reason:"A política de migrations não habilita aplicação pelo Console."};
 if(!process.env.FACTORY_SUPABASE_MANAGEMENT_TOKEN)return{enabled:false,reason:"Credencial Supabase Management API ainda não configurada."};
 if(!process.env.FACTORY_RELEASE_GITHUB_TOKEN)return{enabled:false,reason:"Credencial GitHub de release ainda não configurada."};
 const project=policyProject(projectKey);
 if(!project)return{enabled:false,reason:"Projeto fora da allowlist de migrations."};
 if(!repository||!REPO_RE.test(repository)||repository!==project.repository)return{enabled:false,reason:"Repositório divergente da política de migrations."};
 if(!/^[a-z0-9]{20}$/.test(project.supabase_project_ref))return{enabled:false,reason:"Project ref Supabase inválido na política."};
 if(project.migration_path_prefix!=="supabase/migrations/")return{enabled:false,reason:"Prefixo de migrations inválido na política."};
 return{enabled:true,reason:null};
}

function githubHeaders(token:string){
 return{
  Accept:"application/vnd.github+json",
  Authorization:`Bearer ${token}`,
  "X-GitHub-Api-Version":"2022-11-28",
  "User-Agent":"ai-product-factory-console-migration",
 };
}

async function controlPlaneJson(path:string,init?:RequestInit){
 const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control Plane não configurado.");
 const response=await fetch(cfg.url+"/rest/v1/"+path,{...init,headers:{...cfg.headers,...(init?.headers||{})},cache:"no-store"});
 if(!response.ok)throw new Error("Falha ao consultar o Control Plane para migration.");
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
 if(!response.ok)throw new Error("Não foi possível registrar a auditoria da migration.");
}

async function resolveAppliedGate(gateId:string,operatorRef:string,migrationName:string){
 const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control Plane não configurado.");
 const response=await fetch(cfg.url+"/rest/v1/rpc/factory_resolve_human_gate",{
  method:"POST",
  headers:{...cfg.headers,"Content-Type":"application/json"},
  body:JSON.stringify({
   p_gate_id:gateId,
   p_resolution:"approved",
   p_resolved_by:operatorRef,
   p_note:`Migration ${migrationName} aplicada por ação humana explícita no Console.`,
  }),
  cache:"no-store",
 });
 if(!response.ok)throw new Error("Migration aplicada, mas o gate não pôde ser reconciliado. Tente novamente; a operação é idempotente.");
}

function migrationNameSet(payload:any):Set<string>{
 const rows=Array.isArray(payload)?payload:Array.isArray(payload?.data)?payload.data:Array.isArray(payload?.migrations)?payload.migrations:[];
 return new Set(rows.map((x:any)=>String(x?.name||"")).filter(Boolean));
}

async function listMigrations(projectRef:string,token:string):Promise<Set<string>>{
 const response=await fetch(`https://api.supabase.com/v1/projects/${encodeURIComponent(projectRef)}/database/migrations`,{
  headers:{Authorization:`Bearer ${token}`,Accept:"application/json"},
  cache:"no-store",
 });
 if(!response.ok){
  if(response.status===403||response.status===404)throw new Error("A conta/projeto Supabase não disponibiliza o endpoint de migrations para esta credencial.");
  throw new Error(`Não foi possível consultar migrations no Supabase (HTTP ${response.status}).`);
 }
 const payload=await response.json().catch(()=>[]);
 return migrationNameSet(payload);
}

function migrationIdempotencyKey(projectRef:string,candidateCommit:string,migrationName:string){
 return createHash("sha256").update(`${projectRef}:${candidateCommit}:${migrationName}`,"utf8").digest("hex");
}

async function applyMigration(projectRef:string,token:string,migrationName:string,sql:string,idempotencyKey:string){
 const response=await fetch(`https://api.supabase.com/v1/projects/${encodeURIComponent(projectRef)}/database/migrations`,{
  method:"POST",
  headers:{Authorization:`Bearer ${token}`,Accept:"application/json","Content-Type":"application/json","Idempotency-Key":idempotencyKey},
  body:JSON.stringify({name:migrationName,query:sql}),
  cache:"no-store",
 });
 if(!response.ok){
  const detail=await response.text().catch(()=>"");
  if(response.status===403||response.status===404)throw new Error("O endpoint oficial de migrations do Supabase não está habilitado para esta conta/projeto.");
  throw new Error(`Supabase recusou a migration (HTTP ${response.status})${detail?" — "+detail.slice(0,300):""}`);
 }
 return response.json().catch(()=>({}));
}

export async function applyPendingMigrationFromConsole(gateId:string,expectedCandidate:string):Promise<MigrationApplyResult>{
 const operator=await requireConsoleAdmin();
 if(!gateId.trim()||!SHA_RE.test(expectedCandidate))throw new Error("Gate ou SHA candidato inválido.");

 const gates=await controlPlaneJson(
  "factory_human_gates?select=id,run_id,status,gate_type&id=eq."+encodeURIComponent(gateId)+"&limit=1"
 ) as any[];
 const gate=gates[0];
 if(!gate||String(gate.status)!=="pending")throw new Error("Gate de migration não está pendente.");

 const runs=await controlPlaneJson(
  "factory_runs?select=id,task_id,status,candidate_commit,metadata&id=eq."+encodeURIComponent(String(gate.run_id))+"&limit=1"
 ) as any[];
 const run=runs[0];
 if(!run||String(run.status)!=="awaiting_human")throw new Error("Execução de migration não está aguardando decisão humana.");
 const metadata=run.metadata&&typeof run.metadata==="object"?run.metadata:{};
 if(metadata.requested_action!=="apply_control_plane_migration")throw new Error("Gate não representa aplicação de migration.");
 if(metadata.decision_only!==true||metadata.automatic_apply!==false)throw new Error("Contrato de migration do gate é inválido.");

 const candidate=String(run.candidate_commit||"");
 if(candidate!==expectedCandidate)throw new Error("O candidato mudou desde a abertura da tela. Atualize antes de continuar.");

 const taskRows=await controlPlaneJson(
  "factory_tasks?select=id,project_id,status&id=eq."+encodeURIComponent(String(run.task_id))+"&limit=1"
 ) as any[];
 const task=taskRows[0];
 if(!task||String(task.status)!=="awaiting_human")throw new Error("Tarefa de migration não está aguardando decisão humana.");

 const projectRows=await controlPlaneJson(
  "factory_projects?select=id,project_key,repository&id=eq."+encodeURIComponent(String(task.project_id))+"&limit=1"
 ) as any[];
 const project=projectRows[0];
 const projectKey=String(project?.project_key||"");
 const repository=String(project?.repository||"");
 const readiness=getMigrationApplyReadiness(projectKey,repository);
 if(!readiness.enabled)throw new Error(readiness.reason||"Migration pelo Console indisponível.");
 const configured=policyProject(projectKey) as ProjectPolicy;

 const migrationFile=String(metadata.migration_file||"");
 const match=MIGRATION_PATH_RE.exec(migrationFile);
 if(!match||!migrationFile.startsWith(configured.migration_path_prefix))throw new Error("Arquivo de migration inválido ou fora do caminho permitido.");
 const migrationName=String(metadata.migration_name||"");
 if(!migrationName||migrationName!==match[2])throw new Error("Nome da migration diverge do arquivo versionado.");
 const prNumber=Number(metadata.pr_number);
 if(!Number.isInteger(prNumber)||prNumber<=0)throw new Error("Gate sem PR válido.");

 const githubToken=process.env.FACTORY_RELEASE_GITHUB_TOKEN as string;
 const prResponse=await fetch(`https://api.github.com/repos/${repository}/pulls/${prNumber}`,{
  headers:githubHeaders(githubToken),cache:"no-store"
 });
 if(!prResponse.ok)throw new Error("Não foi possível revalidar o PR da migration.");
 const pr=await prResponse.json();
 const prState=String(pr.state||"");
 const prMerged=Boolean(pr.merged_at)||Boolean(pr.merged);
 if(prState==="open"){
  if(Boolean(pr.draft))throw new Error("PR da migration ainda está em draft.");
 }else if(prState==="closed"){
  if(!prMerged||!String(pr.merge_commit_sha||"").match(SHA_RE))throw new Error("PR da migration foi fechado sem merge.");
 }else{
  throw new Error("Estado do PR da migration não é elegível.");
 }
 if(String(pr.base?.ref)!=="main"||String(pr.base?.repo?.full_name)!==repository)throw new Error("Base do PR da migration é divergente.");
 if(String(pr.head?.repo?.full_name)!==repository)throw new Error("Migration de fork não é permitida.");
 if(String(pr.head?.sha)!==candidate)throw new Error("SHA do PR diverge do candidato validado.");

 const checksResponse=await fetch(`https://api.github.com/repos/${repository}/commits/${candidate}/check-runs?per_page=100`,{
  headers:githubHeaders(githubToken),cache:"no-store"
 });
 if(!checksResponse.ok)throw new Error("Não foi possível revalidar os checks da migration.");
 const checks=await checksResponse.json();
 const successful=new Set((checks.check_runs||[]).filter((x:any)=>x.status==="completed"&&["success","neutral"].includes(String(x.conclusion))).map((x:any)=>String(x.name)));
 const required=(migrationPolicy as any).required_checks||[];
 const missing=required.filter((name:string)=>!successful.has(name));
 if(missing.length)throw new Error("Checks obrigatórios não estão verdes: "+missing.join(", "));

 const encodedPath=migrationFile.split("/").map(encodeURIComponent).join("/");
 const fileResponse=await fetch(`https://api.github.com/repos/${repository}/contents/${encodedPath}?ref=${encodeURIComponent(candidate)}`,{
  headers:githubHeaders(githubToken),cache:"no-store"
 });
 if(!fileResponse.ok)throw new Error("Não foi possível obter o arquivo de migration no SHA candidato.");
 const file=await fileResponse.json();
 if(file.type!=="file"||file.encoding!=="base64"||typeof file.content!=="string")throw new Error("Conteúdo da migration no GitHub é inválido.");
 const sql=Buffer.from(file.content.replace(/\n/g,""),"base64").toString("utf8");
 const maxBytes=Number((migrationPolicy as any).max_migration_bytes||1048576);
 if(!sql.trim()||Buffer.byteLength(sql,"utf8")>maxBytes)throw new Error("Migration vazia ou acima do limite permitido.");

 const actorRef=operator.email||operator.userId;
 const auditBase={
  repository,pr_number:prNumber,candidate_commit:candidate,
  pr_state:prState,pr_merged:prMerged,merge_commit_sha:prMerged?String(pr.merge_commit_sha||""):null,
  migration_name:migrationName,migration_file:migrationFile,
  supabase_project_ref:configured.supabase_project_ref,
 };
 await recordAudit({
  projectId:String(task.project_id),taskId:String(task.id),runId:String(run.id),actorRef,
  eventType:"human_migration.console_apply_requested",payload:auditBase,
 });

 const managementToken=process.env.FACTORY_SUPABASE_MANAGEMENT_TOKEN as string;
 let appliedNames:Set<string>;
 try{
  appliedNames=await listMigrations(configured.supabase_project_ref,managementToken);
 }catch(error){
  await recordAudit({
   projectId:String(task.project_id),taskId:String(task.id),runId:String(run.id),actorRef,
   eventType:"human_migration.console_apply_failed",
   payload:{...auditBase,phase:"list_before",error:String(error instanceof Error?error.message:error).slice(0,300)},
  }).catch(()=>undefined);
  throw error;
 }

 await recordAudit({
  projectId:String(task.project_id),taskId:String(task.id),runId:String(run.id),actorRef,
  eventType:"human_migration.console_preflight_succeeded",
  payload:{...auditBase,migration_history_checked:true,already_applied:appliedNames.has(migrationName)},
 });

 if(appliedNames.has(migrationName)){
  await recordAudit({
   projectId:String(task.project_id),taskId:String(task.id),runId:String(run.id),actorRef,
   eventType:"human_migration.console_already_applied",payload:auditBase,
  });
  await resolveAppliedGate(gateId,actorRef,migrationName);
  return{applied:false,alreadyApplied:true,migrationName,projectRef:configured.supabase_project_ref,candidateCommit:candidate};
 }

 try{
  const idempotencyKey=migrationIdempotencyKey(configured.supabase_project_ref,candidate,migrationName);
  await applyMigration(configured.supabase_project_ref,managementToken,migrationName,sql,idempotencyKey);
  const after=await listMigrations(configured.supabase_project_ref,managementToken);
  if(!after.has(migrationName))throw new Error("Supabase aceitou a requisição, mas a migration não apareceu no histórico.");
 }catch(error){
  await recordAudit({
   projectId:String(task.project_id),taskId:String(task.id),runId:String(run.id),actorRef,
   eventType:"human_migration.console_apply_failed",
   payload:{...auditBase,phase:"apply_or_verify",error:String(error instanceof Error?error.message:error).slice(0,300)},
  }).catch(()=>undefined);
  throw error;
 }

 await recordAudit({
  projectId:String(task.project_id),taskId:String(task.id),runId:String(run.id),actorRef,
  eventType:"human_migration.console_apply_succeeded",payload:auditBase,
 });
 await resolveAppliedGate(gateId,actorRef,migrationName);
 return{applied:true,alreadyApplied:false,migrationName,projectRef:configured.supabase_project_ref,candidateCommit:candidate};
}
