/** Fail-closed REST reader for the Console. Read-only; never dispatches work. */
export type OperationalRow=Record<string,unknown>&{id:unknown;created_at:unknown};
export type OperationalIdKind="uuid"|"bigint";
const PAGE_SIZE=200;
const MAX_PAGES=20;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const BIGINT=/^[1-9][0-9]*$/;
const TZ=/(?:Z|[+-][0-9]{2}:[0-9]{2})$/i;

function verifiedId(value:unknown,kind:OperationalIdKind):string{
 if(kind==="uuid"){
  if(typeof value!=="string"||!UUID.test(value))throw new Error("Inventário operacional contém UUID inválido.");
  return value.toLowerCase();
 }
 if(typeof value==="number"){
  if(!Number.isSafeInteger(value)||value<=0)throw new Error("ID BIGINT de custo não representável.");
  return String(value);
 }
 if(typeof value!=="string"||!BIGINT.test(value))throw new Error("ID BIGINT de custo inválido.");
 return value;
}
function verifiedTime(value:unknown):number{
 if(typeof value!=="string"||!TZ.test(value))throw new Error("Inventário operacional sem timezone verificável.");
 const time=Date.parse(value);
 if(!Number.isFinite(time))throw new Error("Inventário operacional com horário inválido.");
 return time;
}
function greater(a:string,b:string,kind:OperationalIdKind):boolean{
 return kind==="bigint"?BigInt(a)>BigInt(b):a>b;
}
export async function readCompleteOperationalRows(args:{
 url:string;headers:Record<string,string>;table:"factory_runs"|"factory_tool_usage"|"factory_tasks"|"factory_projects"|"factory_journeys";
 select:string;idKind:OperationalIdKind;transport?:typeof fetch;
}):Promise<OperationalRow[]>{
 const fetcher=args.transport||fetch;
 const result:OperationalRow[]=[];
 const seen=new Set<string>();
 let prevTime:number|null=null,prevId:string|null=null;
 for(let page=0;page<MAX_PAGES;page++){
  const endpoint=args.url.replace(/\/$/,"")+"/rest/v1/"+args.table+
   "?select="+args.select+"&order=created_at.desc,id.desc&limit="+PAGE_SIZE+"&offset="+page*PAGE_SIZE;
  const response=await fetcher(endpoint,{headers:args.headers,cache:"no-store"});
  if(!response.ok)throw new Error("Inventário operacional indisponível ("+args.table+" HTTP "+response.status+").");
  const parsed:unknown=await response.json();
  if(!Array.isArray(parsed)||parsed.length>PAGE_SIZE||!parsed.every(x=>x!==null&&typeof x==="object"&&!Array.isArray(x)))
   throw new Error("Inventário operacional retornou página inválida ("+args.table+").");
  const rows=parsed as OperationalRow[];
  for(const row of rows){
   const id=verifiedId(row.id,args.idKind),at=verifiedTime(row.created_at);
   if(seen.has(id))throw new Error("Inventário operacional repetiu ID ("+args.table+").");
   if(prevTime!==null&&(at>prevTime||(at===prevTime&&prevId!==null&&greater(id,prevId,args.idKind))))
    throw new Error("Inventário operacional perdeu ordenação ("+args.table+").");
   seen.add(id);prevTime=at;prevId=id;result.push(row);
  }
  if(rows.length<PAGE_SIZE)return result;
 }
 // A full last page cannot prove exhaustion. Never show truncated healthy counts.
 throw new Error("Inventário operacional excede limite verificado de 4.000 ("+args.table+").");
}
export function parseRecordedCost(value:unknown):number|null{
 if(value===null)return null;
 if(typeof value!=="number"&&typeof value!=="string")throw new Error("Custo operacional inválido.");
 if(typeof value==="string"&&!/^(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$/.test(value))
  throw new Error("Custo operacional não numérico.");
 const amount=Number(value);
 if(!Number.isFinite(amount)||amount<0)throw new Error("Custo operacional fora do limite.");
 return amount;
}
/** Provider credit exhaustion is independent of the Factory's configured budget. */
export function isProviderCreditExhausted(error:string|null|undefined):boolean{
 if(!error)return false;
 return error.includes("credit_balance_exhausted")||
   (error.includes("insufficient_quota")&&/no credits remaining/i.test(error));
}
export function summarizeOperationalHealth(
 runs:OperationalRow[],usage:OperationalRow[],failedTasks:Map<string,string>,now:number
){
 if(!Number.isFinite(now))throw new Error("Relógio operacional inválido.");
 const incidents:{id:string;status:string;route:string|null;attempts:number;error:string|null;leaseExpiresAt:string|null;createdAt:string}[]=[];
 let expiredLeases=0,deadLetterRuns=0,failedRuns=0,blockedRuns=0,queuedRuns=0,knownCost=0,unknownCostEvents=0;
 for(const row of runs){
  const id=verifiedId(row.id,"uuid"),status=row.status,taskId=row.task_id;
  if(typeof status!=="string"||!status||typeof taskId!=="string"||!UUID.test(taskId))
   throw new Error("Run sem status ou tarefa confiável.");
  const error=row.last_error==null?null:String(row.last_error);
  const expires=row.lease_expires_at==null?null:verifiedTime(row.lease_expires_at);
  const expired=(status==="running"||status==="implementing")&&expires!==null&&expires<now;
  const failed=status==="failed"&&failedTasks.get(taskId)==="failed";
  const blocked=status==="blocked";
  const dead=failed&&!!error&&error.toLowerCase().includes("maximum attempts");
  if(expired)expiredLeases++;
  if(failed)failedRuns++;
  if(blocked)blockedRuns++;
  if(dead)deadLetterRuns++;
  if(status==="created"||status==="queued")queuedRuns++;
  if(expired||failed||blocked){
   const attempts=Number(row.attempt_count??0);
   if(!Number.isSafeInteger(attempts)||attempts<0)throw new Error("Run com tentativas inválidas.");
   incidents.push({id,status,route:row.execution_route==null?null:String(row.execution_route),
    attempts,error,leaseExpiresAt:row.lease_expires_at==null?null:String(row.lease_expires_at),
    createdAt:String(row.created_at)});
  }
 }
 const paid=new Set(["model","openai","llm","paid_provider"]);
 for(const row of usage){
  const amount=parseRecordedCost(row.estimated_cost);
  const family=String(row.tool_family||"").toLowerCase();
  if(!family)throw new Error("Uso operacional sem família.");
  if(amount===null){if(paid.has(family))unknownCostEvents++;}
  else{
   knownCost+=amount;
   if(!Number.isFinite(knownCost))throw new Error("Total de custos sem limite confiável.");
  }
 }
 return {expiredLeases,deadLetterRuns,failedRuns,blockedRuns,queuedRuns,knownCost,unknownCostEvents,incidents};
}

// Portfolio attention is deliberately separate from the historical run/cost inventory.
// A failed attempt is not an active incident, and a registered phase is not readiness.
export type PortfolioProject = {
 id:string; key:string; name:string; stage:string; active:boolean; updatedAt:string;
 controlState:string; activeLeases:number; totalTasks:number; pendingTasks:PortfolioPendingTask[];
};
export type PortfolioPendingTask = {
 taskId:string; runId:string|null; title:string; status:"failed"|"blocked";
 legacy:boolean; updatedAt:string; error:string|null;
};
export type PortfolioOverview = {
 projects:PortfolioProject[]; activeLeases:number; historicalFailureRecords:number;
 trackedPendingTasks:number; stoppedPendingTasks:number;
};
const closedJourneyStates=new Set(["closed","superseded","cancelled","canceled"]);
const controlStates=new Set(["draft","running","pausing","paused","stopping","stopped","unavailable"]);
function requiredText(value:unknown,description:string):string {
 if(typeof value!=="string"||!value.trim())throw new Error("Inventário do portfólio sem "+description+".");
 return value;
}
function uniqueRows(rows:OperationalRow[],description:string):Map<string,OperationalRow>{
 const result=new Map<string,OperationalRow>();
 for(const row of rows){
  const id=verifiedId(row.id,"uuid");
  if(result.has(id))throw new Error("Inventário do portfólio duplicou "+description+".");
  result.set(id,row);
 }
 return result;
}
export function summarizePortfolioOverview(
 runs:OperationalRow[],tasks:OperationalRow[],projects:OperationalRow[],
 journeys:OperationalRow[],controls:Map<string,string>,now:number
):PortfolioOverview{
 if(!Number.isFinite(now))throw new Error("Relógio do portfólio inválido.");
 const taskMap=uniqueRows(tasks,"tarefa"),journeyMap=uniqueRows(journeys,"jornada");
 const projectMap=new Map<string,PortfolioProject>();
 const keys=new Set<string>();
 for(const [id,row] of uniqueRows(projects,"projeto")){
  const key=requiredText(row.project_key,"chave de projeto");
  if(keys.has(key)||typeof row.is_active!=="boolean")throw new Error("Cadastro do portfólio inconsistente.");
  keys.add(key);
  verifiedTime(row.updated_at);
  const controlState=controls.get(id)||"unavailable";
  if(!controlStates.has(controlState))throw new Error("Controle de execução inválido.");
  projectMap.set(id,{id,key,name:requiredText(row.name,"nome de projeto"),
   stage:requiredText(row.lifecycle_stage,"etapa registrada"),active:row.is_active,
   updatedAt:String(row.updated_at),controlState,activeLeases:0,totalTasks:0,pendingTasks:[]});
 }
 for(const id of controls.keys())if(!projectMap.has(id))throw new Error("Controle sem projeto no portfólio.");
 for(const row of journeyMap.values()){
  if(!projectMap.has(verifiedId(row.project_id,"uuid")))throw new Error("Jornada sem projeto no portfólio.");
  requiredText(row.state,"estado de jornada");
 }
 const latest=new Map<string,OperationalRow>();
 let historicalFailureRecords=0,activeLeases=0;
 for(const row of uniqueRows(runs,"execução").values()){
  const taskId=verifiedId(row.task_id,"uuid"),task=taskMap.get(taskId);
  if(!task)throw new Error("Execução sem tarefa no portfólio.");
  const project=projectMap.get(verifiedId(task.project_id,"uuid"));
  if(!project)throw new Error("Execução sem projeto no portfólio.");
  const status=requiredText(row.status,"estado da execução");
  const at=verifiedTime(row.created_at);
  const old=latest.get(taskId);
  if(!old||at>verifiedTime(old.created_at)||(at===verifiedTime(old.created_at)&&String(row.id)>String(old.id)))latest.set(taskId,row);
  if(status==="failed"||status==="blocked")historicalFailureRecords++;
  const expires=row.lease_expires_at==null?null:verifiedTime(row.lease_expires_at);
  if(expires!==null&&expires>now&&typeof row.lease_owner==="string"&&row.lease_owner.trim()){
   activeLeases++;project.activeLeases++;
  }
 }
 for(const [taskId,task] of taskMap){
  const project=projectMap.get(verifiedId(task.project_id,"uuid"));
  if(!project)throw new Error("Tarefa sem projeto no portfólio.");
  project.totalTasks++;
  const status=requiredText(task.status,"estado da tarefa");
  if(status!=="failed"&&status!=="blocked")continue;
  const run=latest.get(taskId);
  const taskJourney=task.journey_id==null?null:verifiedId(task.journey_id,"uuid");
  const runJourney=run?.journey_id==null?null:verifiedId(run.journey_id,"uuid");
  if(taskJourney&&runJourney&&taskJourney!==runJourney)throw new Error("Linhagem de execução inconsistente.");
  const journeyId=taskJourney||runJourney;
  if(journeyId){
   const journey=journeyMap.get(journeyId);
   if(!journey||verifiedId(journey.project_id,"uuid")!==project.id)throw new Error("Linhagem de jornada não verificável.");
   if(closedJourneyStates.has(String(journey.state)))continue;
  }
  verifiedTime(task.updated_at);
  project.pendingTasks.push({taskId,runId:run?String(run.id):null,
   title:requiredText(task.title,"título da tarefa"),status,legacy:journeyId===null,
   updatedAt:String(task.updated_at),error:run&&(run.status==="failed"||run.status==="blocked")&&run.last_error!=null?String(run.last_error):null});
 }
 const ordered=[...projectMap.values()].sort((a,b)=>Date.parse(b.updatedAt)-Date.parse(a.updatedAt)||a.key.localeCompare(b.key));
 for(const p of ordered)p.pendingTasks.sort((a,b)=>Date.parse(b.updatedAt)-Date.parse(a.updatedAt)||a.taskId.localeCompare(b.taskId));
 const tracked=ordered.filter(p=>p.active&&p.controlState!=="stopped");
 const stopped=ordered.filter(p=>!p.active||p.controlState==="stopped");
 return {projects:ordered,activeLeases,historicalFailureRecords,
  trackedPendingTasks:tracked.reduce((n,p)=>n+p.pendingTasks.length,0),
  stoppedPendingTasks:stopped.reduce((n,p)=>n+p.pendingTasks.length,0)};
}
export function portfolioProjectControlLabel(project:PortfolioProject):string{
 if(project.controlState==="unavailable")return "Controle não verificável";
 if(!project.active||project.controlState==="stopped")return "Parado";
 if(project.controlState==="paused")return "Pausado";
 if(project.controlState==="pausing")return "Pausa solicitada";
 if(project.controlState==="stopping")return "Parada solicitada";
 if(project.controlState==="draft")return "Não iniciado";
 if(project.activeLeases)return "Execução com reserva vigente";
 if(project.pendingTasks.length)return "Pendência técnica registrada";
 return "Sem execução ativa";
}
export function portfolioPendingReason(error:string|null):string{
 if(isProviderCreditExhausted(error))return "Uma tentativa anterior foi recusada por falta de crédito no provedor.";
 if(error?.includes("reserved provider cost exceeds remaining budget")||error?.includes("budget_exhausted"))return "Uma tentativa anterior atingiu o limite financeiro interno da Factory.";
 if(error?.includes("planning has no actionable tasks or decisions"))return "O planejamento anterior não encontrou tarefas ou decisões executáveis.";
 if(error?.includes("reconciliation_context_preflight_failed"))return "A validação do contexto da reconciliação anterior falhou.";
 if(error?.includes("reconciliation_source_candidate_sha_drift"))return "A versão do repositório mudou durante a reconciliação anterior.";
 if(error?.includes("AGENTS.md")||error?.includes("CURRENT_TASK.md"))return "A tentativa anterior foi bloqueada pela falta de contexto ou autorização de escopo no repositório.";
 return "Há uma tarefa sem encerramento confirmado no histórico do projeto.";
}


// The next-action panel consumes operational evidence, not the registered lifecycle phase.
export function projectWorkFocus(input:{
 observation:"running"|"recorded"|"idle"|"unavailable";
 pendingCount:number|null;
 gateCount:number|null;
 hasPendingDatabase:boolean;
 projectKey:string;
}):{title:string;body:string;href:string;label:string}|null{
 if(input.gateCount!==null&&input.gateCount>0)return {
  title:"Decisão humana pendente",body:"Existe uma aprovação acionável vinculada a este projeto. Revise o motivo antes de continuar.",
  href:"/gates",label:"Abrir aprovações"
 };
 if(input.hasPendingDatabase)return {
  title:"Conectar o banco de dados",body:"Há uma conexão de banco registrada como pendente. Revise o acesso necessário; isso não comprova que um worker esteja executando.",
  href:"#databases",label:"Ver banco de dados"
 };
 if(input.observation==="unavailable"||input.pendingCount===null||input.gateCount===null)return {
  title:"Estado operacional não verificável",body:"Não foi possível confirmar todos os dados da fila e das aprovações. Nenhuma execução ou conclusão é inferida.",
  href:"#project-control",label:"Ver estado do projeto"
 };
 if(input.observation==="running")return {
  title:"Trabalho assumido por um worker",body:"Uma execução possui reserva vigente e início observado. Acompanhe sua evolução; isso não comprova a conclusão da etapa.",
  href:"/runs",label:"Ver execuções"
 };
 if(input.observation==="recorded")return {
  title:"Pedido na fila",body:"Existe trabalho registrado, ainda sem execução ativa comprovada. O worker deve verificar a elegibilidade e os bloqueios.",
  href:"/queue",label:"Ver fila"
 };
 if(input.pendingCount>0)return {
  title:"Pendências técnicas sem execução ativa",body:input.pendingCount+" tarefa(s) sem encerramento confirmado. Consulte as causas registradas; o projeto não está sendo desenvolvido neste momento.",
  href:"#technical-pendencies",label:"Ver pendências"
 };
 return null;
}

export function projectCandidateTaskIds(tasks:readonly {id:string;status:string}[]):string[]{
 const historical=new Set(["completed","cancelled","canceled","failed","merged","integrated","work_unit_completed","blocked","superseded"]);
 return tasks.filter(t=>!historical.has(t.status)).map(t=>t.id);
}

export function projectWorkObservation(
 observed:"running"|"recorded"|"idle"|"unavailable",
 inventory:{totalTasks:number;activeLeases:number;controlState:string}|null,
 taskCount:number,controlState:string
):"running"|"recorded"|"idle"|"unavailable"{
 if(!inventory||inventory.totalTasks!==taskCount||inventory.controlState!==controlState||
    (observed==="running"&&inventory.activeLeases===0)||
    (observed!=="running"&&inventory.activeLeases>0))return "unavailable";
 return observed;
}
