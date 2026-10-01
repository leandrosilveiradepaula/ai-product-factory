import {requireConsoleAdmin,requireConsoleOperator} from "./auth-server";import {getSupabaseServerConfig} from "./supabase-server";
export type Project={key:string;name:string;stage:string;status:string;updatedAt:string};
export type Dashboard={projects:Project[];activeRuns:number;pendingGates:number;codexCalls:number;modelCalls:number;failedRuns:number};
function slugify(value:string){return value.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,64)}
export async function createProjectIntake(input:{mode:"greenfield"|"existing";name:string;summary:string;repository?:string;users?:string;mustHave?:string;integrations?:string;references?:{kind:"url"|"figma";value:string}[];reportedStage?:string;knownPending?:string;constraints?:string}){await requireConsoleOperator();const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control plane credentials are not configured");const projectKey=slugify(input.name);if(!projectKey)throw new Error("Unable to derive project key");const response=await fetch(`${cfg.url}/rest/v1/rpc/factory_create_project_intake`,{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},body:JSON.stringify({p_project_key:projectKey,p_name:input.name,p_repository:input.repository||"",p_project_kind:input.mode,p_manifest:{source:"factory-console",autonomy:"default",onboarding_mode:input.mode,references:input.references||[],reported_stage:input.reportedStage||null,reconcile_first:input.mode==="existing"},p_spec:{summary:input.summary,continuation_brief:input.mode==="existing"?input.summary:null,users:input.users||null,must_have:input.mustHave||null,integrations:input.integrations||null,references:input.references||[],reported_stage:input.reportedStage||null,known_pending:input.knownPending||null,constraints:input.constraints||null}}),cache:"no-store"});if(!response.ok){const body=await response.text();if(response.status===409||body.includes("duplicate key"))throw new Error("Já existe um projeto com esse nome/chave.");throw new Error("Não foi possível persistir o intake no Control Plane.");}const id=await response.json();return{projectId:String(id),projectKey};}

export async function enqueueProjectBootstrap(projectKey:string){await requireConsoleOperator();const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control plane credentials are not configured");const response=await fetch(`${cfg.url}/rest/v1/rpc/factory_enqueue_project_bootstrap`,{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},body:JSON.stringify({p_project_key:projectKey}),cache:"no-store"});if(!response.ok)throw new Error("Não foi possível enfileirar o ciclo inicial da Factory.");return response.json() as Promise<{project_id:string;task_id:string;run_id:string;created:boolean}>;}

export async function getDashboard():Promise<Dashboard>{
 await requireConsoleOperator();
 const cfg=getSupabaseServerConfig();
 if(!cfg)throw new Error("Control Plane não configurado.");
 const {url,headers}=cfg;
 const [projects,runs,gates,codex,tools,failed]=await Promise.all([
  fetch(`${url}/rest/v1/factory_projects?select=project_key,name,lifecycle_stage,is_active,updated_at&order=updated_at.desc`,{headers,cache:"no-store"}),
  fetch(`${url}/rest/v1/factory_runs?select=status&status=in.(running,implementing,ci_pending,queued)`,{headers,cache:"no-store"}),
  fetch(`${url}/rest/v1/factory_human_gates?select=status&status=eq.pending`,{headers,cache:"no-store"}),
  fetch(`${url}/rest/v1/factory_codex_usage?select=invocation_count`,{headers,cache:"no-store"}),
  fetch(`${url}/rest/v1/factory_tool_usage?select=tool_family`,{headers,cache:"no-store"}),
  fetch(`${url}/rest/v1/factory_runs?select=status&status=eq.failed`,{headers,cache:"no-store"})]);
 if(!projects.ok)throw new Error("Control plane unavailable");
 const p=await projects.json(); const r=runs.ok?await runs.json():[]; const g=gates.ok?await gates.json():[]; const cx=codex.ok?await codex.json():[]; const t=tools.ok?await tools.json():[]; const f=failed.ok?await failed.json():[];
 return {
  projects:p.map((x:any)=>({key:x.project_key,name:x.name,stage:x.lifecycle_stage,status:x.is_active?"active":"inactive",updatedAt:x.updated_at})),
  activeRuns:r.length,
  pendingGates:g.length,
  codexCalls:cx.reduce((sum:number,x:any)=>sum+Number(x.invocation_count||0),0),
  modelCalls:t.filter((x:any)=>["model","openai"].includes(String(x.tool_family).toLowerCase())).length,
  failedRuns:f.length
 };
}
export type RunSummary={id:string;taskId:string;status:string;route:string|null;candidateCommit:string|null;createdAt:string;taskTitle:string;attemptCount:number;leaseOwner:string|null;leaseExpiresAt:string|null;lastError:string|null};
export type GateSummary={id:string;runId:string;type:string;status:string;reasons:unknown;requestedAt:string};

function serverHeaders(){return getSupabaseServerConfig();}

export async function getRuns(limit=50):Promise<RunSummary[]>{
 await requireConsoleOperator();
 const cfg=serverHeaders();if(!cfg)return [];
 const runsResponse=await fetch(`${cfg.url}/rest/v1/factory_runs?select=id,task_id,status,execution_route,candidate_commit,created_at,attempt_count,lease_owner,lease_expires_at,last_error&order=created_at.desc&limit=${limit}`,{headers:cfg.headers,cache:"no-store"});
 if(!runsResponse.ok)throw new Error("Unable to load Factory runs");
 const runs=await runsResponse.json();
 const taskIds=[...new Set(runs.map((x:any)=>x.task_id).filter(Boolean))];
 let taskMap=new Map<string,string>();
 if(taskIds.length){
  const tasksResponse=await fetch(`${cfg.url}/rest/v1/factory_tasks?select=id,title&id=in.(${taskIds.join(",")})`,{headers:cfg.headers,cache:"no-store"});
  if(tasksResponse.ok){const tasks=await tasksResponse.json();taskMap=new Map(tasks.map((x:any)=>[String(x.id),String(x.title)]));}
 }
 return runs.map((x:any)=>({id:x.id,taskId:x.task_id,status:x.status,route:x.execution_route,candidateCommit:x.candidate_commit,createdAt:x.created_at,taskTitle:taskMap.get(String(x.task_id))||"Task",attemptCount:Number(x.attempt_count||0),leaseOwner:x.lease_owner||null,leaseExpiresAt:x.lease_expires_at||null,lastError:x.last_error||null}));
}

export async function getHumanGates(limit=50):Promise<GateSummary[]>{
 await requireConsoleOperator();
 const cfg=serverHeaders();if(!cfg)return [];
 const response=await fetch(`${cfg.url}/rest/v1/factory_human_gates?select=id,run_id,gate_type,status,reasons,requested_at&order=requested_at.desc&limit=${limit}`,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load human gates");
 const rows=await response.json();
 return rows.map((x:any)=>({id:x.id,runId:x.run_id,type:x.gate_type,status:x.status,reasons:x.reasons,requestedAt:x.requested_at}));
}

export type ProjectTaskSummary={id:string;title:string;status:string;complexity:string;externalKey:string|null;updatedAt:string};
export type ProjectDetail={id:string;key:string;name:string;repository:string|null;kind:string;stage:string;active:boolean;updatedAt:string;tasks:ProjectTaskSummary[]};

export async function getProjectDetail(projectKey:string):Promise<ProjectDetail|null>{
 await requireConsoleOperator();
 const cfg=serverHeaders();if(!cfg)return null;
 const projectResponse=await fetch(`${cfg.url}/rest/v1/factory_projects?select=id,project_key,name,repository,project_kind,lifecycle_stage,is_active,updated_at&project_key=eq.${encodeURIComponent(projectKey)}&limit=1`,{headers:cfg.headers,cache:"no-store"});
 if(!projectResponse.ok)throw new Error("Unable to load project");
 const projects=await projectResponse.json();if(!projects.length)return null;
 const p=projects[0];
 const tasksResponse=await fetch(`${cfg.url}/rest/v1/factory_tasks?select=id,title,status,complexity,external_key,updated_at&project_id=eq.${p.id}&order=created_at.asc`,{headers:cfg.headers,cache:"no-store"});
 const tasks=tasksResponse.ok?await tasksResponse.json():[];
 return {id:p.id,key:p.project_key,name:p.name,repository:p.repository,kind:p.project_kind,stage:p.lifecycle_stage,active:Boolean(p.is_active),updatedAt:p.updated_at,tasks:tasks.map((x:any)=>({id:x.id,title:x.title,status:x.status,complexity:x.complexity,externalKey:x.external_key,updatedAt:x.updated_at}))};
}

export type ProjectDatabaseBinding={id:string;provider:string;environment:string;projectRef:string|null;organizationRef:string|null;region:string|null;accessMode:string;permissionMode:string;status:string;isExisting:boolean;lastVerifiedAt:string|null};

export async function getProjectDatabases(projectId:string):Promise<ProjectDatabaseBinding[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(cfg.url+"/rest/v1/factory_project_databases?select=id,provider,environment,project_ref,organization_ref,region,access_mode,permission_mode,status,is_existing,last_verified_at&project_id=eq."+encodeURIComponent(projectId)+"&order=environment.asc",{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load project databases");
 const rows=await response.json();
 return rows.map((x:any)=>({id:String(x.id),provider:String(x.provider),environment:String(x.environment),projectRef:x.project_ref?String(x.project_ref):null,organizationRef:x.organization_ref?String(x.organization_ref):null,region:x.region?String(x.region):null,accessMode:String(x.access_mode),permissionMode:String(x.permission_mode),status:String(x.status),isExisting:Boolean(x.is_existing),lastVerifiedAt:x.last_verified_at?String(x.last_verified_at):null}));
}

export type ProjectStateSnapshot={id:string;runId:string|null;observedStage:string|null;summary:string;evidence:unknown[];gaps:unknown[];constraints:unknown[];sourceStatus:Record<string,unknown>;createdAt:string};
export type ProjectStateContext={objective:string|null;snapshot:ProjectStateSnapshot|null};

export async function getProjectStateContext(projectId:string):Promise<ProjectStateContext>{
 await requireConsoleOperator();
 const cfg=serverHeaders();if(!cfg)return{objective:null,snapshot:null};
 const id=encodeURIComponent(projectId);
 const [specResponse,snapshotResponse]=await Promise.all([
  fetch(cfg.url+"/rest/v1/factory_product_specs?select=spec,version&project_id=eq."+id+"&order=version.desc&limit=1",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_project_state_snapshots?select=id,run_id,observed_stage,summary,evidence,gaps,constraints,source_status,created_at&project_id=eq."+id+"&order=created_at.desc&limit=1",{headers:cfg.headers,cache:"no-store"})
 ]);
 const specs=specResponse.ok?await specResponse.json():[];const spec=specs[0]?.spec||{};
 const snapshots=snapshotResponse.ok?await snapshotResponse.json():[];const x=snapshots[0];
 return{
  objective:typeof spec.summary==="string"?spec.summary:null,
  snapshot:x?{id:String(x.id),runId:x.run_id?String(x.run_id):null,observedStage:x.observed_stage?String(x.observed_stage):null,summary:String(x.summary),evidence:Array.isArray(x.evidence)?x.evidence:[],gaps:Array.isArray(x.gaps)?x.gaps:[],constraints:Array.isArray(x.constraints)?x.constraints:[],sourceStatus:x.source_status&&typeof x.source_status==="object"?x.source_status:{},createdAt:String(x.created_at)}:null
 };
}

export async function resolveHumanGate(gateId:string,resolution:"approved"|"rejected",note?:string){const operator=await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)throw new Error("Control plane unavailable");const response=await fetch(`${cfg.url}/rest/v1/rpc/factory_resolve_human_gate`,{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},body:JSON.stringify({p_gate_id:gateId,p_resolution:resolution,p_resolved_by:operator.email||operator.userId,p_note:note||null}),cache:"no-store"});if(!response.ok)throw new Error("Unable to resolve human gate");return response.json();}


export type OperatorAdminRow={userId:string;email:string|null;role:"operator"|"admin"|null;active:boolean};
export async function getOperatorAdminRows():Promise<OperatorAdminRow[]>{await requireConsoleAdmin();const cfg=serverHeaders();if(!cfg)return[];const usersResponse=await fetch(`${cfg.url}/auth/v1/admin/users?page=1&per_page=100`,{headers:cfg.headers,cache:"no-store"});if(!usersResponse.ok)throw new Error("Unable to list Supabase Auth users");const payload=await usersResponse.json();const users=Array.isArray(payload)?payload:(payload.users||[]);const operatorsResponse=await fetch(`${cfg.url}/rest/v1/factory_console_operators?select=user_id,role,is_active`,{headers:cfg.headers,cache:"no-store"});if(!operatorsResponse.ok)throw new Error("Unable to list console operators");const operators=await operatorsResponse.json();const byId=new Map(operators.map((x:any)=>[String(x.user_id),x]));return users.map((u:any)=>{const op:any=byId.get(String(u.id));return{userId:String(u.id),email:u.email?String(u.email):null,role:op?.role||null,active:Boolean(op?.is_active)}});}
export async function upsertConsoleOperator(targetUserId:string,role:"operator"|"admin",active:boolean){const actor=await requireConsoleAdmin();const cfg=serverHeaders();if(!cfg)throw new Error("Control plane unavailable");if(targetUserId===actor.userId&&!active)throw new Error("Você não pode desativar o próprio acesso administrativo.");const response=await fetch(`${cfg.url}/rest/v1/rpc/factory_upsert_console_operator`,{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},body:JSON.stringify({p_actor_user_id:actor.userId,p_target_user_id:targetUserId,p_role:role,p_active:active}),cache:"no-store"});if(!response.ok)throw new Error("Não foi possível atualizar o operador.");}


export type ProjectTimelineItem={id:string;kind:string;title:string;status:string|null;at:string;detail:string|null;cost:number|null;units:number|null;ref:string|null};
export type ProjectOperations={timeline:ProjectTimelineItem[];estimatedCost:number;usageUnits:number;codexInvocations:number;evaluations:number;deployments:number};
export async function getProjectOperations(projectId:string):Promise<ProjectOperations>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return{timeline:[],estimatedCost:0,usageUnits:0,codexInvocations:0,evaluations:0,deployments:0};
 const tasksResponse=await fetch(`${cfg.url}/rest/v1/factory_tasks?select=id&project_id=eq.${encodeURIComponent(projectId)}`,{headers:cfg.headers,cache:"no-store"});
 const tasks=tasksResponse.ok?await tasksResponse.json():[];const taskIds=tasks.map((x:any)=>String(x.id));
 if(!taskIds.length)return{timeline:[],estimatedCost:0,usageUnits:0,codexInvocations:0,evaluations:0,deployments:0};
 const taskFilter=taskIds.join(",");
 const runsResponse=await fetch(`${cfg.url}/rest/v1/factory_runs?select=id,task_id,status,execution_route,candidate_commit,branch_name,created_at,finished_at&task_id=in.(${taskFilter})&order=created_at.desc`,{headers:cfg.headers,cache:"no-store"});
 const runs=runsResponse.ok?await runsResponse.json():[];const runIds=runs.map((x:any)=>String(x.id));const runFilter=runIds.join(",");
 const empty=Promise.resolve({ok:false,json:async()=>[]}) as any;
 const req=(path:string)=>runIds.length?fetch(`${cfg.url}/rest/v1/${path}`,{headers:cfg.headers,cache:"no-store"}):empty;
 const [tools,codex,evals,deploys,gates,audit,decisions]=await Promise.all([
  req(`factory_tool_usage?select=id,run_id,tool_family,operation,usage_units,estimated_cost,metadata,created_at&run_id=in.(${runFilter})`),
  req(`factory_codex_usage?select=id,run_id,policy_level,reason,invocation_count,reported_usage,created_at&run_id=in.(${runFilter})`),
  req(`factory_evaluations?select=id,run_id,eval_type,status,score,baseline_ref,result,created_at&run_id=in.(${runFilter})`),
  req(`factory_deployments?select=id,run_id,environment,status,deployment_ref,rollback_ref,deployed_at,metadata,created_at&run_id=in.(${runFilter})`),
  req(`factory_human_gates?select=id,run_id,gate_type,status,reasons,requested_at,resolved_at,resolved_by,resolution&run_id=in.(${runFilter})`),
  fetch(`${cfg.url}/rest/v1/factory_audit_events?select=id,run_id,actor_type,actor_ref,event_type,payload,created_at&project_id=eq.${encodeURIComponent(projectId)}`,{headers:cfg.headers,cache:"no-store"}),
  fetch(`${cfg.url}/rest/v1/factory_decisions?select=id,task_id,decision_type,question,decision,decided_by,created_at&project_id=eq.${encodeURIComponent(projectId)}`,{headers:cfg.headers,cache:"no-store"})
 ]);
 const read=async(r:any)=>r.ok?await r.json():[];const [tu,cu,ev,dp,gt,au,de]=await Promise.all([read(tools),read(codex),read(evals),read(deploys),read(gates),read(audit),read(decisions)]);
 const timeline:ProjectTimelineItem[]=[];
 runs.forEach((x:any)=>timeline.push({id:`run-${x.id}`,kind:"run",title:`Execução · ${x.execution_route||"unrouted"}`,status:x.status,at:x.finished_at||x.created_at,detail:x.branch_name||null,cost:null,units:null,ref:x.candidate_commit||null}));
 tu.forEach((x:any)=>timeline.push({id:`tool-${x.id}`,kind:"tool",title:`${x.tool_family} · ${x.operation}`,status:null,at:x.created_at,detail:null,cost:x.estimated_cost==null?null:Number(x.estimated_cost),units:x.usage_units==null?null:Number(x.usage_units),ref:null}));
 cu.forEach((x:any)=>timeline.push({id:`codex-${x.id}`,kind:"codex",title:`Política Codex N${x.policy_level}`,status:Number(x.invocation_count)>0?"invoked":"not invoked",at:x.created_at,detail:JSON.stringify(x.reason||{}),cost:null,units:Number(x.invocation_count||0),ref:null}));
 ev.forEach((x:any)=>timeline.push({id:`eval-${x.id}`,kind:"evaluation",title:x.eval_type,status:x.status,at:x.created_at,detail:x.score==null?null:`score ${x.score}`,cost:null,units:null,ref:x.baseline_ref||null}));
 dp.forEach((x:any)=>timeline.push({id:`deploy-${x.id}`,kind:"deployment",title:`Implantação · ${x.environment}`,status:x.status,at:x.deployed_at||x.created_at,detail:null,cost:null,units:null,ref:x.deployment_ref||null}));
 gt.forEach((x:any)=>timeline.push({id:`gate-${x.id}`,kind:"gate",title:`Aprovação · ${x.gate_type}`,status:x.status,at:x.resolved_at||x.requested_at,detail:x.resolved_by||null,cost:null,units:null,ref:null}));
 au.forEach((x:any)=>timeline.push({id:`audit-${x.id}`,kind:"audit",title:x.event_type,status:null,at:x.created_at,detail:[x.actor_type,x.actor_ref].filter(Boolean).join(" · ")||null,cost:null,units:null,ref:null}));
 de.forEach((x:any)=>timeline.push({id:`decision-${x.id}`,kind:"decision",title:x.decision_type,status:null,at:x.created_at,detail:x.question||x.decided_by||null,cost:null,units:null,ref:null}));
 timeline.sort((a,b)=>Date.parse(b.at)-Date.parse(a.at));
 return{timeline,estimatedCost:tu.reduce((s:number,x:any)=>s+Number(x.estimated_cost||0),0),usageUnits:tu.reduce((s:number,x:any)=>s+Number(x.usage_units||0),0),codexInvocations:cu.reduce((s:number,x:any)=>s+Number(x.invocation_count||0),0),evaluations:ev.length,deployments:dp.length};
}


export type OperationsHealth={expiredLeases:number;deadLetterRuns:number;failedRuns:number;queuedRuns:number;knownCost:number;unknownCostEvents:number;incidents:{id:string;status:string;route:string|null;attempts:number;error:string|null;leaseExpiresAt:string|null;createdAt:string}[]};
export async function getOperationsHealth():Promise<OperationsHealth>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return{expiredLeases:0,deadLetterRuns:0,failedRuns:0,queuedRuns:0,knownCost:0,unknownCostEvents:0,incidents:[]};
 const [runsResponse,usageResponse]=await Promise.all([
  fetch(`${cfg.url}/rest/v1/factory_runs?select=id,task_id,status,execution_route,attempt_count,last_error,lease_expires_at,created_at&order=created_at.desc&limit=200`,{headers:cfg.headers,cache:"no-store"}),
  fetch(`${cfg.url}/rest/v1/factory_tool_usage?select=tool_family,estimated_cost,created_at&order=created_at.desc&limit=1000`,{headers:cfg.headers,cache:"no-store"})
 ]);
 if(!runsResponse.ok)throw new Error("Unable to load operational health");
 const runs=await runsResponse.json();const usage=usageResponse.ok?await usageResponse.json():[];const now=Date.now();
 const failedTaskIds=[...new Set(runs.filter((x:any)=>x.status==="failed"&&x.task_id).map((x:any)=>String(x.task_id)))];
 const failedTaskStatus=new Map<string,string>();
 if(failedTaskIds.length){
  const tasksResponse=await fetch(`${cfg.url}/rest/v1/factory_tasks?select=id,status&id=in.(${failedTaskIds.join(",")})`,{headers:cfg.headers,cache:"no-store"});
  if(tasksResponse.ok){const tasks=await tasksResponse.json();tasks.forEach((x:any)=>failedTaskStatus.set(String(x.id),String(x.status||"")));}
 }
 const expired=(x:any)=>x.lease_expires_at&&Date.parse(x.lease_expires_at)<now&&["running","implementing"].includes(x.status);
 const dead=(x:any)=>x.status==="failed"&&String(x.last_error||"").toLowerCase().includes("maximum attempts");
 const actionableFailed=(x:any)=>x.status==="failed"&&failedTaskStatus.get(String(x.task_id||""))==="failed";
 const incidents=runs.filter((x:any)=>expired(x)||dead(x)||actionableFailed(x)).map((x:any)=>({id:x.id,status:x.status,route:x.execution_route||null,attempts:Number(x.attempt_count||0),error:x.last_error||null,leaseExpiresAt:x.lease_expires_at||null,createdAt:x.created_at}));
 const paidFamilies=new Set(["model","openai","llm","paid_provider"]);return{expiredLeases:runs.filter(expired).length,deadLetterRuns:runs.filter(dead).length,failedRuns:runs.filter(actionableFailed).length,queuedRuns:runs.filter((x:any)=>["created","queued"].includes(x.status)).length,knownCost:usage.reduce((s:number,x:any)=>s+Number(x.estimated_cost||0),0),unknownCostEvents:usage.filter((x:any)=>x.estimated_cost==null&&paidFamilies.has(String(x.tool_family||"").toLowerCase())).length,incidents};
}


export type WorkQueueItem={id:string;title:string;status:string;complexity:string;externalKey:string|null;updatedAt:string;projectKey:string;projectName:string};
export async function getWorkQueue(limit=100):Promise<WorkQueueItem[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(`${cfg.url}/rest/v1/factory_tasks?select=id,project_id,title,status,complexity,external_key,updated_at&status=in.(queued,dispatching,queued_execution,awaiting_human,running,implementing)&order=updated_at.desc&limit=${limit}`,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load work queue");
 const rows=await response.json();const projectIds=[...new Set(rows.map((x:any)=>String(x.project_id)).filter(Boolean))];
 let projects=new Map<string,{key:string;name:string}>();
 if(projectIds.length){
  const p=await fetch(`${cfg.url}/rest/v1/factory_projects?select=id,project_key,name&id=in.(${projectIds.join(",")})`,{headers:cfg.headers,cache:"no-store"});
  if(p.ok){const values=await p.json();projects=new Map(values.map((x:any)=>[String(x.id),{key:String(x.project_key),name:String(x.name)}]));}
 }
 return rows.map((x:any)=>{const p=projects.get(String(x.project_id));return{id:String(x.id),title:String(x.title),status:String(x.status),complexity:String(x.complexity),externalKey:x.external_key?String(x.external_key):null,updatedAt:String(x.updated_at),projectKey:p?.key||"unknown",projectName:p?.name||"Unknown project"};});
}

export type EvaluationRow={id:string;runId:string;type:string;status:string;score:number|null;baselineRef:string|null;createdAt:string;taskTitle:string;projectKey:string;projectName:string};
async function getRunContextMap(runIds:string[]){
 const cfg=serverHeaders();if(!cfg||!runIds.length)return new Map<string,{taskTitle:string;projectKey:string;projectName:string}>();
 const runsResponse=await fetch(`${cfg.url}/rest/v1/factory_runs?select=id,task_id&id=in.(${runIds.join(",")})`,{headers:cfg.headers,cache:"no-store"});
 if(!runsResponse.ok)return new Map();
 const runs=await runsResponse.json();const taskIds=[...new Set(runs.map((x:any)=>String(x.task_id)).filter(Boolean))];
 const taskMap=new Map<string,{title:string;projectId:string}>();
 if(taskIds.length){
  const tasksResponse=await fetch(`${cfg.url}/rest/v1/factory_tasks?select=id,title,project_id&id=in.(${taskIds.join(",")})`,{headers:cfg.headers,cache:"no-store"});
  if(tasksResponse.ok){const tasks=await tasksResponse.json();tasks.forEach((x:any)=>taskMap.set(String(x.id),{title:String(x.title),projectId:String(x.project_id)}));}
 }
 const projectIds=[...new Set([...taskMap.values()].map(x=>x.projectId))];
 const projectMap=new Map<string,{key:string;name:string}>();
 if(projectIds.length){
  const p=await fetch(`${cfg.url}/rest/v1/factory_projects?select=id,project_key,name&id=in.(${projectIds.join(",")})`,{headers:cfg.headers,cache:"no-store"});
  if(p.ok){const values=await p.json();values.forEach((x:any)=>projectMap.set(String(x.id),{key:String(x.project_key),name:String(x.name)}));}
 }
 const out=new Map<string,{taskTitle:string;projectKey:string;projectName:string}>();
 runs.forEach((x:any)=>{const task=taskMap.get(String(x.task_id));const project=task?projectMap.get(task.projectId):undefined;out.set(String(x.id),{taskTitle:task?.title||"Task",projectKey:project?.key||"unknown",projectName:project?.name||"Unknown project"});});
 return out;
}

export async function getEvaluations(limit=100):Promise<EvaluationRow[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(`${cfg.url}/rest/v1/factory_evaluations?select=id,run_id,eval_type,status,score,baseline_ref,created_at&order=created_at.desc&limit=${limit}`,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load evaluations");
 const rows=await response.json();const ctx=await getRunContextMap(rows.map((x:any)=>String(x.run_id)));
 return rows.map((x:any)=>{const c=ctx.get(String(x.run_id));return{id:String(x.id),runId:String(x.run_id),type:String(x.eval_type),status:String(x.status),score:x.score==null?null:Number(x.score),baselineRef:x.baseline_ref?String(x.baseline_ref):null,createdAt:String(x.created_at),taskTitle:c?.taskTitle||"Task",projectKey:c?.projectKey||"unknown",projectName:c?.projectName||"Unknown project"};});
}

export type DeploymentRow={id:string;runId:string;environment:string;status:string;deploymentRef:string|null;rollbackRef:string|null;deployedAt:string|null;createdAt:string;taskTitle:string;projectKey:string;projectName:string};
export async function getDeployments(limit=100):Promise<DeploymentRow[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(`${cfg.url}/rest/v1/factory_deployments?select=id,run_id,environment,status,deployment_ref,rollback_ref,deployed_at,created_at&order=created_at.desc&limit=${limit}`,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load deployments");
 const rows=await response.json();const ctx=await getRunContextMap(rows.map((x:any)=>String(x.run_id)));
 return rows.map((x:any)=>{const c=ctx.get(String(x.run_id));return{id:String(x.id),runId:String(x.run_id),environment:String(x.environment),status:String(x.status),deploymentRef:x.deployment_ref?String(x.deployment_ref):null,rollbackRef:x.rollback_ref?String(x.rollback_ref):null,deployedAt:x.deployed_at?String(x.deployed_at):null,createdAt:String(x.created_at),taskTitle:c?.taskTitle||"Task",projectKey:c?.projectKey||"unknown",projectName:c?.projectName||"Unknown project"};});
}

export type UsageOverview={knownCost:number;unknownPaidCostEvents:number;toolEvents:number;codexInvocations:number;codexPolicyRows:number;byFamily:{family:string;events:number;knownCost:number}[]};
export async function getUsageOverview():Promise<UsageOverview>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return{knownCost:0,unknownPaidCostEvents:0,toolEvents:0,codexInvocations:0,codexPolicyRows:0,byFamily:[]};
 const [toolResponse,codexResponse]=await Promise.all([
  fetch(`${cfg.url}/rest/v1/factory_tool_usage?select=tool_family,estimated_cost,created_at&order=created_at.desc&limit=2000`,{headers:cfg.headers,cache:"no-store"}),
  fetch(`${cfg.url}/rest/v1/factory_codex_usage?select=policy_level,invocation_count,created_at&order=created_at.desc&limit=2000`,{headers:cfg.headers,cache:"no-store"})
 ]);
 const tools=toolResponse.ok?await toolResponse.json():[];const codex=codexResponse.ok?await codexResponse.json():[];
 const paidFamilies=new Set(["model","openai","llm","paid_provider"]);const grouped=new Map<string,{events:number;knownCost:number}>();
 tools.forEach((x:any)=>{const family=String(x.tool_family||"unknown");const current=grouped.get(family)||{events:0,knownCost:0};current.events+=1;current.knownCost+=Number(x.estimated_cost||0);grouped.set(family,current);});
 return{knownCost:tools.reduce((s:number,x:any)=>s+Number(x.estimated_cost||0),0),unknownPaidCostEvents:tools.filter((x:any)=>x.estimated_cost==null&&paidFamilies.has(String(x.tool_family||"").toLowerCase())).length,toolEvents:tools.length,codexInvocations:codex.reduce((s:number,x:any)=>s+Number(x.invocation_count||0),0),codexPolicyRows:codex.length,byFamily:[...grouped.entries()].map(([family,v])=>({family,...v})).sort((a,b)=>b.events-a.events)};
}

export type AuditRow={id:string;eventType:string;actorType:string;actorRef:string|null;createdAt:string;runId:string|null;taskId:string|null;projectKey:string|null;projectName:string|null;payload:unknown};
export async function getAuditEvents(limit=150):Promise<AuditRow[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(`${cfg.url}/rest/v1/factory_audit_events?select=id,project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at&order=created_at.desc&limit=${limit}`,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load audit log");
 const rows=await response.json();const projectIds=[...new Set(rows.map((x:any)=>x.project_id?String(x.project_id):"").filter(Boolean))];const projects=new Map<string,{key:string;name:string}>();
 if(projectIds.length){const p=await fetch(`${cfg.url}/rest/v1/factory_projects?select=id,project_key,name&id=in.(${projectIds.join(",")})`,{headers:cfg.headers,cache:"no-store"});if(p.ok){const values=await p.json();values.forEach((x:any)=>projects.set(String(x.id),{key:String(x.project_key),name:String(x.name)}));}}
 return rows.map((x:any)=>{const p=x.project_id?projects.get(String(x.project_id)):undefined;return{id:String(x.id),eventType:String(x.event_type),actorType:String(x.actor_type),actorRef:x.actor_ref?String(x.actor_ref):null,createdAt:String(x.created_at),runId:x.run_id?String(x.run_id):null,taskId:x.task_id?String(x.task_id):null,projectKey:p?.key||null,projectName:p?.name||null,payload:x.payload};});
}

export type RunDetail=RunSummary&{projectKey:string;projectName:string;projectStage:string;taskStatus:string;taskComplexity:string;branchName:string|null;metadata:unknown;evaluations:EvaluationRow[];deployments:DeploymentRow[];gates:GateSummary[];audit:AuditRow[];toolUsage:{id:string;family:string;operation:string|null;units:number|null;cost:number|null;createdAt:string}[];codex:{id:string;level:number;invocations:number;createdAt:string}[]};
export async function getRunDetail(runId:string):Promise<RunDetail|null>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return null;
 const runResponse=await fetch(`${cfg.url}/rest/v1/factory_runs?select=id,task_id,status,execution_route,candidate_commit,branch_name,metadata,created_at,attempt_count,lease_owner,lease_expires_at,last_error&id=eq.${encodeURIComponent(runId)}&limit=1`,{headers:cfg.headers,cache:"no-store"});
 if(!runResponse.ok)throw new Error("Unable to load run");const runs=await runResponse.json();if(!runs.length)return null;const r=runs[0];
 const taskResponse=await fetch(`${cfg.url}/rest/v1/factory_tasks?select=id,project_id,title,status,complexity&id=eq.${r.task_id}&limit=1`,{headers:cfg.headers,cache:"no-store"});const tasks=taskResponse.ok?await taskResponse.json():[];const t=tasks[0];if(!t)return null;
 const projectResponse=await fetch(`${cfg.url}/rest/v1/factory_projects?select=id,project_key,name,lifecycle_stage&id=eq.${t.project_id}&limit=1`,{headers:cfg.headers,cache:"no-store"});const projects=projectResponse.ok?await projectResponse.json():[];const p=projects[0];if(!p)return null;
 const [evals,deployments,gates,audit,tools,codex]=await Promise.all([
  fetch(`${cfg.url}/rest/v1/factory_evaluations?select=id,run_id,eval_type,status,score,baseline_ref,created_at&run_id=eq.${r.id}&order=created_at.desc`,{headers:cfg.headers,cache:"no-store"}),
  fetch(`${cfg.url}/rest/v1/factory_deployments?select=id,run_id,environment,status,deployment_ref,rollback_ref,deployed_at,created_at&run_id=eq.${r.id}&order=created_at.desc`,{headers:cfg.headers,cache:"no-store"}),
  fetch(`${cfg.url}/rest/v1/factory_human_gates?select=id,run_id,gate_type,status,reasons,requested_at&run_id=eq.${r.id}&order=requested_at.desc`,{headers:cfg.headers,cache:"no-store"}),
  fetch(`${cfg.url}/rest/v1/factory_audit_events?select=id,project_id,task_id,run_id,actor_type,actor_ref,event_type,payload,created_at&run_id=eq.${r.id}&order=created_at.desc`,{headers:cfg.headers,cache:"no-store"}),
  fetch(`${cfg.url}/rest/v1/factory_tool_usage?select=id,tool_family,operation,usage_units,estimated_cost,created_at&run_id=eq.${r.id}&order=created_at.desc`,{headers:cfg.headers,cache:"no-store"}),
  fetch(`${cfg.url}/rest/v1/factory_codex_usage?select=id,policy_level,invocation_count,created_at&run_id=eq.${r.id}&order=created_at.desc`,{headers:cfg.headers,cache:"no-store"})
 ]);
 const read=async(x:any)=>x.ok?await x.json():[];const [ev,dp,gt,au,tu,cu]=await Promise.all([read(evals),read(deployments),read(gates),read(audit),read(tools),read(codex)]);
 const context={taskTitle:String(t.title),projectKey:String(p.project_key),projectName:String(p.name)};
 return{id:String(r.id),taskId:String(r.task_id),status:String(r.status),route:r.execution_route?String(r.execution_route):null,candidateCommit:r.candidate_commit?String(r.candidate_commit):null,createdAt:String(r.created_at),taskTitle:String(t.title),attemptCount:Number(r.attempt_count||0),leaseOwner:r.lease_owner?String(r.lease_owner):null,leaseExpiresAt:r.lease_expires_at?String(r.lease_expires_at):null,lastError:r.last_error?String(r.last_error):null,projectKey:String(p.project_key),projectName:String(p.name),projectStage:String(p.lifecycle_stage),taskStatus:String(t.status),taskComplexity:String(t.complexity),branchName:r.branch_name?String(r.branch_name):null,metadata:r.metadata,evaluations:ev.map((x:any)=>({id:String(x.id),runId:String(x.run_id),type:String(x.eval_type),status:String(x.status),score:x.score==null?null:Number(x.score),baselineRef:x.baseline_ref?String(x.baseline_ref):null,createdAt:String(x.created_at),...context})),deployments:dp.map((x:any)=>({id:String(x.id),runId:String(x.run_id),environment:String(x.environment),status:String(x.status),deploymentRef:x.deployment_ref?String(x.deployment_ref):null,rollbackRef:x.rollback_ref?String(x.rollback_ref):null,deployedAt:x.deployed_at?String(x.deployed_at):null,createdAt:String(x.created_at),...context})),gates:gt.map((x:any)=>({id:String(x.id),runId:String(x.run_id),type:String(x.gate_type),status:String(x.status),reasons:x.reasons,requestedAt:String(x.requested_at)})),audit:au.map((x:any)=>({id:String(x.id),eventType:String(x.event_type),actorType:String(x.actor_type),actorRef:x.actor_ref?String(x.actor_ref):null,createdAt:String(x.created_at),runId:x.run_id?String(x.run_id):null,taskId:x.task_id?String(x.task_id):null,projectKey:String(p.project_key),projectName:String(p.name),payload:x.payload})),toolUsage:tu.map((x:any)=>({id:String(x.id),family:String(x.tool_family),operation:x.operation?String(x.operation):null,units:x.usage_units==null?null:Number(x.usage_units),cost:x.estimated_cost==null?null:Number(x.estimated_cost),createdAt:String(x.created_at)})),codex:cu.map((x:any)=>({id:String(x.id),level:Number(x.policy_level||0),invocations:Number(x.invocation_count||0),createdAt:String(x.created_at)}))};
}

export type ConsoleConfiguration={controlPlaneConfigured:boolean;projects:{key:string;name:string;repository:string|null;kind:string;stage:string;active:boolean;manifest:unknown}[]};
export async function getConsoleConfiguration():Promise<ConsoleConfiguration>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return{controlPlaneConfigured:false,projects:[]};
 const response=await fetch(`${cfg.url}/rest/v1/factory_projects?select=project_key,name,repository,project_kind,lifecycle_stage,is_active,manifest&order=project_key.asc`,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load configuration");
 const rows=await response.json();return{controlPlaneConfigured:true,projects:rows.map((x:any)=>({key:String(x.project_key),name:String(x.name),repository:x.repository?String(x.repository):null,kind:String(x.project_kind),stage:String(x.lifecycle_stage),active:Boolean(x.is_active),manifest:x.manifest}))};
}


export type ExecutionTeamPlan={
 id:string;version:number;status:string;createdAt:string;
 profilesSelected:number;plannedWorkerPeak:number;
 selectedAgents:{agent_key:string;role:string;workers_planned:number;max_concurrency:number;execution_ready:boolean;task_keys:string[];reasons:string[]}[];
 excludedAgents:{agent_key:string;role:string;reason:string}[];
 waves:{wave:number;task_keys:string[];agent_load:Record<string,number>;parallel_workers:number}[];
 blockers:{code:string;task_key?:string;title?:string;dependency?:string}[];
 advisorySpecialistLanes:{role:string;code:string;reasons:string[];execution_ready:boolean;note:string}[];
};

export async function getProjectExecutionTeamPlan(projectId:string):Promise<ExecutionTeamPlan|null>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return null;
 const response=await fetch(cfg.url+"/rest/v1/factory_execution_team_plans?select=id,version,status,plan,created_at&project_id=eq."+encodeURIComponent(projectId)+"&status=neq.superseded&order=version.desc&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Não foi possível carregar o plano de equipe do projeto.");
 const rows=await response.json();if(!rows.length)return null;
 const row=rows[0];const plan=row.plan&&typeof row.plan==="object"?row.plan:{};
 return{
  id:String(row.id),version:Number(row.version||1),status:String(row.status),createdAt:String(row.created_at),
  profilesSelected:Number(plan.profiles_selected||0),plannedWorkerPeak:Number(plan.planned_worker_peak||0),
  selectedAgents:Array.isArray(plan.selected_agents)?plan.selected_agents:[],
  excludedAgents:Array.isArray(plan.excluded_agents)?plan.excluded_agents:[],
  waves:Array.isArray(plan.waves)?plan.waves:[],
  blockers:Array.isArray(plan.blockers)?plan.blockers:[],
  advisorySpecialistLanes:Array.isArray(plan.advisory_specialist_lanes)?plan.advisory_specialist_lanes:[],
 };
}


export type OrchestrationProject={
 projectId:string;projectKey:string;projectName:string;priority:string;deadline:string|null;
 customerImpact:number;maxActiveWorkers:number;paused:boolean;
};
export type OrchestrationIncident={id:string;projectKey:string;projectName:string;severity:string;status:string;title:string;summary:string;openedAt:string;updatedAt:string};
export type OrchestrationRepair={id:string;projectKey:string;projectName:string;sourceRole:string;cycle:number;maxCycles:number;ownerAgentKey:string;candidateCommit:string;status:string;createdAt:string};
export type OrchestrationReplay={id:string;sourceRunId:string;mode:string;status:string;effect:string;modelCallsAllowed:boolean;createdAt:string};
export type OrchestrationProposal={id:string;proposalKey:string;status:string;requiresSourceControl:boolean;autoApply:boolean;createdAt:string};
export type OrchestrationRelease={id:string;projectKey:string;projectName:string;runId:string;candidateCommit:string;status:string;report:Record<string,unknown>;rollback:Record<string,unknown>;updatedAt:string};
export type OrchestrationOverview={
 projects:OrchestrationProject[];incidents:OrchestrationIncident[];repairs:OrchestrationRepair[];
 replays:OrchestrationReplay[];proposals:OrchestrationProposal[];releases:OrchestrationRelease[];
};

export async function getOrchestrationOverview():Promise<OrchestrationOverview>{
 await requireConsoleOperator();const cfg=serverHeaders();
 if(!cfg)return{projects:[],incidents:[],repairs:[],replays:[],proposals:[],releases:[]};
 const [projectsResponse,schedulingResponse,incidentsResponse,repairsResponse,replaysResponse,proposalsResponse,releasesResponse]=await Promise.all([
  fetch(cfg.url+"/rest/v1/factory_projects?select=id,project_key,name,is_active&is_active=eq.true&order=name.asc",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_project_scheduling?select=project_id,priority,deadline,customer_impact,max_active_workers,paused,updated_at",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_incidents?select=id,project_id,severity,status,title,summary,opened_at,updated_at&status=not.eq.resolved&order=opened_at.desc&limit=50",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_repair_jobs?select=id,project_id,source_role,cycle,max_cycles,owner_agent_key,candidate_commit,status,created_at&status=in.(queued,running,integrated,blocked,exhausted)&order=created_at.desc&limit=50",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_replay_requests?select=id,source_run_id,mode,status,effect,model_calls_allowed,created_at&order=created_at.desc&limit=30",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_improvement_proposals?select=id,proposal_key,status,requires_source_control,auto_apply,created_at&status=eq.proposed&order=created_at.desc&limit=30",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_release_reports?select=id,project_id,run_id,candidate_commit,status,report,rollback,updated_at&status=in.(blocked,ready_for_human_release)&order=updated_at.desc&limit=50",{headers:cfg.headers,cache:"no-store"}),
 ]);
 if(!projectsResponse.ok)throw new Error("Não foi possível carregar o portfólio da Factory.");
 const rawProjects=await projectsResponse.json();
 const projectMap=new Map<string,{key:string;name:string}>(rawProjects.map((x:any)=>[String(x.id),{key:String(x.project_key),name:String(x.name)}]));
 const schedule=schedulingResponse.ok?await schedulingResponse.json():[];
 const scheduleMap=new Map<string,any>(schedule.map((x:any)=>[String(x.project_id),x]));
 const projectRows:OrchestrationProject[]=rawProjects.map((x:any)=>{
  const s= scheduleMap.get(String(x.id))||{};
  return{projectId:String(x.id),projectKey:String(x.project_key),projectName:String(x.name),priority:String(s.priority||"P2"),
   deadline:s.deadline?String(s.deadline):null,customerImpact:Number(s.customer_impact??1),
   maxActiveWorkers:Number(s.max_active_workers??4),paused:Boolean(s.paused)};
 });
 const nameFor=(projectId:unknown)=>projectMap.get(String(projectId))||{key:"unknown",name:"Projeto desconhecido"};
 const incidents=incidentsResponse.ok?await incidentsResponse.json():[];
 const repairs=repairsResponse.ok?await repairsResponse.json():[];
 const replays=replaysResponse.ok?await replaysResponse.json():[];
 const proposals=proposalsResponse.ok?await proposalsResponse.json():[];
 const releases=releasesResponse.ok?await releasesResponse.json():[];
 return{
  projects:projectRows,
  incidents:incidents.map((x:any)=>{const p=nameFor(x.project_id);return{id:String(x.id),projectKey:p.key,projectName:p.name,severity:String(x.severity),status:String(x.status),title:String(x.title),summary:String(x.summary),openedAt:String(x.opened_at),updatedAt:String(x.updated_at)}}),
  repairs:repairs.map((x:any)=>{const p=nameFor(x.project_id);return{id:String(x.id),projectKey:p.key,projectName:p.name,sourceRole:String(x.source_role),cycle:Number(x.cycle),maxCycles:Number(x.max_cycles),ownerAgentKey:String(x.owner_agent_key),candidateCommit:String(x.candidate_commit),status:String(x.status),createdAt:String(x.created_at)}}),
  replays:replays.map((x:any)=>({id:String(x.id),sourceRunId:String(x.source_run_id),mode:String(x.mode),status:String(x.status),effect:String(x.effect),modelCallsAllowed:Boolean(x.model_calls_allowed),createdAt:String(x.created_at)})),
  proposals:proposals.map((x:any)=>({id:String(x.id),proposalKey:String(x.proposal_key),status:String(x.status),requiresSourceControl:Boolean(x.requires_source_control),autoApply:Boolean(x.auto_apply),createdAt:String(x.created_at)})),
  releases:releases.map((x:any)=>{const p=nameFor(x.project_id);return{id:String(x.id),projectKey:p.key,projectName:p.name,runId:String(x.run_id),candidateCommit:String(x.candidate_commit),status:String(x.status),report:x.report&&typeof x.report==="object"?x.report:{},rollback:x.rollback&&typeof x.rollback==="object"?x.rollback:{},updatedAt:String(x.updated_at)}}),
 };
}

export type ResourceLimitRow={provider:string;resourceKey:string;metricKey:string;used:number|null;limit:number|null;percent:number|null;unit:string;windowKey:string|null;resetsAt:string|null;quality:string;source:string;status:string;observedAt:string};
export async function getResourceLimits():Promise<ResourceLimitRow[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(cfg.url+"/rest/v1/factory_resource_limit_snapshots?select=provider,resource_key,metric_key,used_value,limit_value,unit,window_key,resets_at,quality,source,status,observed_at&order=observed_at.desc&limit=200",{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)return[];
 const rows=await response.json();const seen=new Set<string>();const out:ResourceLimitRow[]=[];
 for(const x of rows){const key=[x.provider,x.resource_key,x.metric_key].join("|");if(seen.has(key))continue;seen.add(key);
  const used=x.used_value==null?null:Number(x.used_value),limit=x.limit_value==null?null:Number(x.limit_value);
  out.push({provider:String(x.provider),resourceKey:String(x.resource_key),metricKey:String(x.metric_key),used,limit,percent:used==null||limit==null||limit<=0?null:(used/limit)*100,unit:String(x.unit),windowKey:x.window_key?String(x.window_key):null,resetsAt:x.resets_at?String(x.resets_at):null,quality:String(x.quality),source:String(x.source),status:String(x.status),observedAt:String(x.observed_at)});
 }
 return out;
}

export type AgentRunSummary={runId:string;taskTitle:string;status:string;route:string|null};
export type FactoryAgentSummary={
 id:string;key:string;name:string;role:string;description:string;healthStatus:string;active:boolean;
 capabilities:string[];allowedTools:string[];modelPolicy:Record<string,unknown>;
 maxConcurrency:number;activeSlots:number;budgetUsd:number|null;knownCostUsd:number;
 activeRuns:AgentRunSummary[];activeScopes:string[];
};

export async function getFactoryAgents():Promise<FactoryAgentSummary[]>{
 await requireConsoleOperator();
 const cfg=serverHeaders();if(!cfg)return[];
 const agentsResponse=await fetch(cfg.url+"/rest/v1/factory_agents?select=id,agent_key,name,role,description,capabilities,allowed_tools,model_policy,max_concurrency,cost_budget_usd,is_active,health_status&order=agent_key.asc",{headers:cfg.headers,cache:"no-store"});
 if(!agentsResponse.ok)throw new Error("Não foi possível carregar os agentes da Factory.");
 const agents=await agentsResponse.json();
 if(!agents.length)return[];

 const agentIds=agents.map((x:any)=>String(x.id));
 const assignmentsResponse=await fetch(cfg.url+"/rest/v1/factory_run_agent_assignments?select=agent_id,run_id,status,assigned_at&agent_id=in.("+agentIds.join(",")+")&order=assigned_at.desc",{headers:cfg.headers,cache:"no-store"});
 const assignments=assignmentsResponse.ok?await assignmentsResponse.json():[];
 const runIds=[...new Set(assignments.map((x:any)=>String(x.run_id)).filter(Boolean))];

 let runs:any[]=[];let tasks:any[]=[];let usage:any[]=[];
 if(runIds.length){
  const runsResponse=await fetch(cfg.url+"/rest/v1/factory_runs?select=id,task_id,status,execution_route&id=in.("+runIds.join(",")+")",{headers:cfg.headers,cache:"no-store"});
  runs=runsResponse.ok?await runsResponse.json():[];
  const taskIds=[...new Set(runs.map((x:any)=>String(x.task_id)).filter(Boolean))];
  if(taskIds.length){
   const tasksResponse=await fetch(cfg.url+"/rest/v1/factory_tasks?select=id,title&id=in.("+taskIds.join(",")+")",{headers:cfg.headers,cache:"no-store"});
   tasks=tasksResponse.ok?await tasksResponse.json():[];
  }
  const usageResponse=await fetch(cfg.url+"/rest/v1/factory_tool_usage?select=run_id,estimated_cost&run_id=in.("+runIds.join(",")+")",{headers:cfg.headers,cache:"no-store"});
  usage=usageResponse.ok?await usageResponse.json():[];
 }

 const now=new Date().toISOString();
 const locksResponse=await fetch(cfg.url+"/rest/v1/factory_agent_scope_locks?select=agent_id,scope_key,run_id,lease_expires_at&agent_id=in.("+agentIds.join(",")+")&released_at=is.null&lease_expires_at=gt."+encodeURIComponent(now),{headers:cfg.headers,cache:"no-store"});
 const locks=locksResponse.ok?await locksResponse.json():[];
 const runById=new Map(runs.map((x:any)=>[String(x.id),x]));
 const taskById=new Map(tasks.map((x:any)=>[String(x.id),String(x.title)]));
 const usageByRun=new Map<string,number>();
 usage.forEach((x:any)=>usageByRun.set(String(x.run_id),(usageByRun.get(String(x.run_id))||0)+(x.estimated_cost==null?0:Number(x.estimated_cost))));

 return agents.map((a:any)=>{
  const agentAssignments=assignments.filter((x:any)=>String(x.agent_id)===String(a.id));
  const activeAssignments=agentAssignments.filter((x:any)=>["assigned","claimed"].includes(String(x.status)));
  const uniqueRunIds:string[]=[...new Set<string>(agentAssignments.map((x:any)=>String(x.run_id)))];
  const activeRuns=activeAssignments.map((x:any)=>{
   const run:any=runById.get(String(x.run_id))||{};
   return {runId:String(x.run_id),taskTitle:taskById.get(String(run.task_id))||"Tarefa sem título",status:String(run.status||x.status),route:run.execution_route?String(run.execution_route):null};
  });
  const knownCostUsd=uniqueRunIds.reduce((sum:number,runId:string)=>sum+(usageByRun.get(runId)||0),0);
  return {
   id:String(a.id),key:String(a.agent_key),name:String(a.name),role:String(a.role),description:String(a.description||""),
   healthStatus:String(a.health_status),active:Boolean(a.is_active),
   capabilities:Array.isArray(a.capabilities)?a.capabilities.map(String):[],
   allowedTools:Array.isArray(a.allowed_tools)?a.allowed_tools.map(String):[],
   modelPolicy:a.model_policy&&typeof a.model_policy==="object"?a.model_policy:{},
   maxConcurrency:Number(a.max_concurrency||1),activeSlots:activeAssignments.length,
   budgetUsd:a.cost_budget_usd==null?null:Number(a.cost_budget_usd),knownCostUsd,
   activeRuns,
   activeScopes:locks.filter((x:any)=>String(x.agent_id)===String(a.id)).map((x:any)=>String(x.scope_key)),
  } satisfies FactoryAgentSummary;
 });
}

