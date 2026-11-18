import {requireConsoleOperator} from "./auth-server";
import {getSupabaseServerConfig} from "./supabase-server";
import {getHumanGates} from "./control-plane";

/** Read-only delivery board sourced from the Control Plane.
 * Cards are root task packages (not synthetic stories or product-ready claims).
 * The Factory changes statuses; dragging a card does not dispatch work.
 */
export type DeliveryLane="received"|"working"|"validating"|"waiting_human"|"blocked"|"closed";
export type DeliveryCard={
 id:string;projectKey:string;projectName:string;title:string;
 latestActivity:string|null;lane:DeliveryLane;statusLabel:string;
 updatedAt:string;taskCount:number;latestRunId:string|null;internalRoutine:boolean;
 needsHuman:boolean;
};
export type DeliveryBoard={cards:DeliveryCard[];projects:{key:string;name:string}[];readAt:string};
type ProjectRow={id:string;project_key:string;name:string;is_active:boolean};
type TaskRow={id:string;project_id:string;parent_task_id:string|null;title:string;status:string;updated_at:string;external_key:string|null};
type RunRow={id:string;task_id:string;status:string;created_at:string};

const completeStatuses=new Set(["completed","integrated","merged","work_unit_completed"]);
const abandonedStatuses=new Set(["cancelled","canceled"]);
const blockedStatuses=new Set(["blocked","failed","failed_gate","repair_pending","dead_letter"]);
const workStatuses=new Set(["running","implementing","in_progress","processing","dispatching","planning"]);
const validationStatuses=new Set(["preview_ready","ci_pending","review_ready","validating","review","testing"]);
export const deliveryLanes:{key:DeliveryLane;label:string;hint:string}[]=[
 {key:"received",label:"A fazer",hint:"Registrado, sem execução comprovada"},
 {key:"working",label:"Em execução",hint:"Há atividade de execução registrada"},
 {key:"validating",label:"Validando",hint:"Testes ou prévia em andamento"},
 {key:"waiting_human",label:"Aguardando você",hint:"Existe uma decisão humana acionável"},
 {key:"blocked",label:"Bloqueado",hint:"Problema técnico; não autoriza ação sua"},
 {key:"closed",label:"Encerrado",hint:"Trabalho concluído ou cancelado; não comprova publicação"},
];

/** The latest run of each task beats historical failures on earlier attempts. */
export function chooseDeliveryLane(taskStatuses:readonly string[],recentRunStatuses:readonly string[],humanGate:boolean):DeliveryLane{
 if(humanGate)return "waiting_human";
 if(taskStatuses.some(s=>blockedStatuses.has(s))||recentRunStatuses.some(s=>blockedStatuses.has(s)))return "blocked";
 if(recentRunStatuses.some(s=>validationStatuses.has(s)))return "validating";
 if(recentRunStatuses.some(s=>workStatuses.has(s))||taskStatuses.some(s=>workStatuses.has(s)))return "working";
 if(taskStatuses.length>0&&taskStatuses.every(s=>completeStatuses.has(s)||abandonedStatuses.has(s)))return "closed";
 return "received";
}
export function deliveryStatusLabel(lane:DeliveryLane,taskStatuses:readonly string[]):string{
 if(lane==="closed"){
  if(taskStatuses.length>0&&taskStatuses.every(s=>abandonedStatuses.has(s)))return "Cancelado";
  if(taskStatuses.some(s=>abandonedStatuses.has(s)))return "Parcialmente cancelado";
  return "Trabalho técnico concluído";
 }
 switch(lane){
  case "received":return "Aguardando trabalho";
  case "working":return "Atividade registrada";
  case "validating":return "Em validação";
  case "waiting_human":return "Decisão humana necessária";
  case "blocked":return "Execução bloqueada";
 }
}

async function allRows<T>(cfg:{url:string;headers:Record<string,string>},table:string,select:string,order:string):Promise<T[]>{
 const rows:T[]=[];
 const pageSize=200,maxPages=20;
 for(let page=0;page<maxPages;page++){
  const endpoint=cfg.url+"/rest/v1/"+table+"?select="+encodeURIComponent(select)+"&order="+encodeURIComponent(order)+
   "&limit="+pageSize+"&offset="+page*pageSize;
  const response=await fetch(endpoint,{headers:cfg.headers,cache:"no-store"});
  if(!response.ok)throw new Error("Consulta do quadro indisponível: "+table+" (HTTP "+response.status+").");
  const current:unknown=await response.json();
  if(!Array.isArray(current)||current.length>pageSize||current.some(x=>!x||typeof x!=="object"||Array.isArray(x)))
   throw new Error("Resposta incompleta do Control Plane: "+table+".");
  rows.push(...current as T[]);
  if(current.length<pageSize)return rows;
 }
 throw new Error("Inventário de entregas excede limite verificado. Quadro não pode omitir registros silenciosamente.");
}

function rootOf(task:TaskRow,taskById:Map<string,TaskRow>):string{
 let current=task;
 const seen=new Set<string>([task.id]);
 while(current.parent_task_id){
  if(seen.has(current.parent_task_id))throw new Error("Árvore de tarefas com ciclo detectado.");
  seen.add(current.parent_task_id);
  const parent=taskById.get(current.parent_task_id);
  if(!parent)throw new Error("Árvore de tarefas incompleta; quadro bloqueado por integridade.");
  if(parent.project_id!==task.project_id)throw new Error("Tarefa com projeto de origem divergente.");
  current=parent;
 }
 return current.id;
}
const latestFirst=(a:{created_at:string},b:{created_at:string})=>Date.parse(b.created_at)-Date.parse(a.created_at);

export async function getDeliveryBoard():Promise<DeliveryBoard>{
 await requireConsoleOperator();
 const cfg=getSupabaseServerConfig();
 if(!cfg)throw new Error("Control Plane indisponível. Não é seguro exibir um quadro vazio.");
 const [projects,tasks,runs,gates]=await Promise.all([
  allRows<ProjectRow>(cfg,"factory_projects","id,project_key,name,is_active","updated_at.desc,id.desc"),
  allRows<TaskRow>(cfg,"factory_tasks","id,project_id,parent_task_id,title,status,updated_at,external_key","updated_at.desc,id.desc"),
  allRows<RunRow>(cfg,"factory_runs","id,task_id,status,created_at","created_at.desc,id.desc"),
  getHumanGates(100,true),
 ]);
 const projectMap=new Map(projects.filter(p=>p.is_active).map(p=>[p.id,p]));
 const byId=new Map(tasks.map(t=>[t.id,t]));
 if(byId.size!==tasks.length)throw new Error("Tarefa duplicada no inventário.");
 const groups=new Map<string,TaskRow[]>();
 for(const task of tasks){
  if(!projectMap.has(task.project_id))continue;
  const id=rootOf(task,byId);
  const group=groups.get(id)||[];
  group.push(task);groups.set(id,group);
 }
 const runsByTask=new Map<string,RunRow[]>();
 for(const run of runs){
  const group=runsByTask.get(run.task_id)||[];
  group.push(run);runsByTask.set(run.task_id,group);
 }
 const actionableIds=new Set(gates.filter(g=>g.status==="pending"&&g.actionable).map(g=>g.runId));
 const cards:DeliveryCard[]=[];
 for(const [rootId,children] of groups){
  const root=byId.get(rootId);
  if(!root)throw new Error("Raiz não encontrada.");
  const project=projectMap.get(root.project_id);
  if(!project)continue;
  const byRecent=[...children].sort((a,b)=>Date.parse(b.updated_at)-Date.parse(a.updated_at));
  const latestRuns=children.flatMap(t=>runsByTask.get(t.id)?.slice(0,1)||[]);
  const humanGate=children.some(t=>(runsByTask.get(t.id)||[]).some(r=>actionableIds.has(r.id)));
  const statuses=children.map(t=>t.status);
  const lane=chooseDeliveryLane(statuses,latestRuns.map(r=>r.status),humanGate);
  const mostRecentRun=[...latestRuns].sort(latestFirst)[0];
  const newest=byRecent[0];
  cards.push({
   id:root.id,projectKey:project.project_key,projectName:project.name,
   title:root.title,latestActivity:newest.id!==root.id?newest.title:null,
   lane,statusLabel:deliveryStatusLabel(lane,statuses),
   updatedAt:newest.updated_at,taskCount:children.length,
   latestRunId:mostRecentRun?.id||null,needsHuman:humanGate,
   // This versioned system event is a certification run, not a user delivery.
   // It remains accessible via the board Technical routines toggle and /runs.
   internalRoutine:typeof root.external_key==="string"&&root.external_key.startsWith("product-readiness:"),
  });
 }
 cards.sort((a,b)=>Date.parse(b.updatedAt)-Date.parse(a.updatedAt));
 return{cards,projects:projects.filter(p=>p.is_active).map(p=>({key:p.project_key,name:p.name})).sort((a,b)=>a.name.localeCompare(b.name)),readAt:new Date().toISOString()};
}
