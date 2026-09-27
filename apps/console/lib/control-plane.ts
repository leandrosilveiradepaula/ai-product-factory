import {requireConsoleAdmin,requireConsoleOperator} from "./auth-server";import {getSupabaseServerConfig} from "./supabase-server";
export type Project={key:string;name:string;stage:string;status:string;updatedAt:string};
export type Dashboard={projects:Project[];activeRuns:number;pendingGates:number;codexCalls:number;modelCalls:number;failedRuns:number};
const demo:Dashboard={projects:[{key:"agente-sql-financeiro",name:"Agente SQL Financeiro",stage:"planning",status:"active",updatedAt:"pilot onboarded"}],activeRuns:0,pendingGates:0,codexCalls:0,modelCalls:0,failedRuns:0};
function slugify(value:string){return value.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,64)}
export async function createProjectIntake(input:{mode:"greenfield"|"import";name:string;summary:string;repository?:string;users?:string;mustHave?:string;integrations?:string}){await requireConsoleOperator();const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control plane credentials are not configured");const projectKey=slugify(input.name);if(!projectKey)throw new Error("Unable to derive project key");const response=await fetch(`${cfg.url}/rest/v1/rpc/factory_create_project_intake`,{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},body:JSON.stringify({p_project_key:projectKey,p_name:input.name,p_repository:input.repository||"",p_project_kind:input.mode,p_manifest:{source:"factory-console",autonomy:"default"},p_spec:{summary:input.summary,users:input.users||null,must_have:input.mustHave||null,integrations:input.integrations||null}}),cache:"no-store"});if(!response.ok){const body=await response.text();if(response.status===409||body.includes("duplicate key"))throw new Error("Já existe um projeto com esse nome/chave.");throw new Error("Não foi possível persistir o intake no Control Plane.");}const id=await response.json();return{projectId:String(id),projectKey};}

export async function enqueueProjectBootstrap(projectKey:string){await requireConsoleOperator();const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control plane credentials are not configured");const response=await fetch(`${cfg.url}/rest/v1/rpc/factory_enqueue_project_bootstrap`,{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},body:JSON.stringify({p_project_key:projectKey}),cache:"no-store"});if(!response.ok)throw new Error("Não foi possível enfileirar o ciclo inicial da Factory.");return response.json() as Promise<{project_id:string;task_id:string;run_id:string;created:boolean}>;}

export async function getDashboard():Promise<Dashboard>{
 await requireConsoleOperator();
 const cfg=getSupabaseServerConfig();
 if(!cfg)return demo;
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
 runs.forEach((x:any)=>timeline.push({id:`run-${x.id}`,kind:"run",title:`Run · ${x.execution_route||"unrouted"}`,status:x.status,at:x.finished_at||x.created_at,detail:x.branch_name||null,cost:null,units:null,ref:x.candidate_commit||null}));
 tu.forEach((x:any)=>timeline.push({id:`tool-${x.id}`,kind:"tool",title:`${x.tool_family} · ${x.operation}`,status:null,at:x.created_at,detail:null,cost:x.estimated_cost==null?null:Number(x.estimated_cost),units:x.usage_units==null?null:Number(x.usage_units),ref:null}));
 cu.forEach((x:any)=>timeline.push({id:`codex-${x.id}`,kind:"codex",title:`Codex policy L${x.policy_level}`,status:Number(x.invocation_count)>0?"invoked":"not invoked",at:x.created_at,detail:JSON.stringify(x.reason||{}),cost:null,units:Number(x.invocation_count||0),ref:null}));
 ev.forEach((x:any)=>timeline.push({id:`eval-${x.id}`,kind:"evaluation",title:x.eval_type,status:x.status,at:x.created_at,detail:x.score==null?null:`score ${x.score}`,cost:null,units:null,ref:x.baseline_ref||null}));
 dp.forEach((x:any)=>timeline.push({id:`deploy-${x.id}`,kind:"deployment",title:`Deployment · ${x.environment}`,status:x.status,at:x.deployed_at||x.created_at,detail:null,cost:null,units:null,ref:x.deployment_ref||null}));
 gt.forEach((x:any)=>timeline.push({id:`gate-${x.id}`,kind:"gate",title:`Gate · ${x.gate_type}`,status:x.status,at:x.resolved_at||x.requested_at,detail:x.resolved_by||null,cost:null,units:null,ref:null}));
 au.forEach((x:any)=>timeline.push({id:`audit-${x.id}`,kind:"audit",title:x.event_type,status:null,at:x.created_at,detail:[x.actor_type,x.actor_ref].filter(Boolean).join(" · ")||null,cost:null,units:null,ref:null}));
 de.forEach((x:any)=>timeline.push({id:`decision-${x.id}`,kind:"decision",title:x.decision_type,status:null,at:x.created_at,detail:x.question||x.decided_by||null,cost:null,units:null,ref:null}));
 timeline.sort((a,b)=>Date.parse(b.at)-Date.parse(a.at));
 return{timeline,estimatedCost:tu.reduce((s:number,x:any)=>s+Number(x.estimated_cost||0),0),usageUnits:tu.reduce((s:number,x:any)=>s+Number(x.usage_units||0),0),codexInvocations:cu.reduce((s:number,x:any)=>s+Number(x.invocation_count||0),0),evaluations:ev.length,deployments:dp.length};
}


export type OperationsHealth={expiredLeases:number;deadLetterRuns:number;failedRuns:number;queuedRuns:number;knownCost:number;unknownCostEvents:number;incidents:{id:string;status:string;route:string|null;attempts:number;error:string|null;leaseExpiresAt:string|null;createdAt:string}[]};
export async function getOperationsHealth():Promise<OperationsHealth>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return{expiredLeases:0,deadLetterRuns:0,failedRuns:0,queuedRuns:0,knownCost:0,unknownCostEvents:0,incidents:[]};
 const [runsResponse,usageResponse]=await Promise.all([
  fetch(`${cfg.url}/rest/v1/factory_runs?select=id,status,execution_route,attempt_count,last_error,lease_expires_at,created_at&order=created_at.desc&limit=200`,{headers:cfg.headers,cache:"no-store"}),
  fetch(`${cfg.url}/rest/v1/factory_tool_usage?select=tool_family,estimated_cost,created_at&order=created_at.desc&limit=1000`,{headers:cfg.headers,cache:"no-store"})
 ]);
 if(!runsResponse.ok)throw new Error("Unable to load operational health");
 const runs=await runsResponse.json();const usage=usageResponse.ok?await usageResponse.json():[];const now=Date.now();
 const expired=(x:any)=>x.lease_expires_at&&Date.parse(x.lease_expires_at)<now&&["running","implementing"].includes(x.status);
 const dead=(x:any)=>x.status==="failed"&&String(x.last_error||"").includes("maximum attempts");
 const incidents=runs.filter((x:any)=>expired(x)||dead(x)||x.status==="failed").map((x:any)=>({id:x.id,status:x.status,route:x.execution_route||null,attempts:Number(x.attempt_count||0),error:x.last_error||null,leaseExpiresAt:x.lease_expires_at||null,createdAt:x.created_at}));
 const paidFamilies=new Set(["model","openai","llm","paid_provider"]);return{expiredLeases:runs.filter(expired).length,deadLetterRuns:runs.filter(dead).length,failedRuns:runs.filter((x:any)=>x.status==="failed").length,queuedRuns:runs.filter((x:any)=>["created","queued"].includes(x.status)).length,knownCost:usage.reduce((s:number,x:any)=>s+Number(x.estimated_cost||0),0),unknownCostEvents:usage.filter((x:any)=>x.estimated_cost==null&&paidFamilies.has(String(x.tool_family||"").toLowerCase())).length,incidents};
}


export type WorkQueueItem={id:string;projectId:string;projectName:string;title:string;status:string;complexity:string;externalKey:string|null;createdAt:string;updatedAt:string};
export type EvaluationRow={id:string;runId:string;type:string;status:string;score:number|null;baselineRef:string|null;createdAt:string};
export type DeploymentRow={id:string;runId:string;environment:string;status:string;deploymentRef:string|null;deployedAt:string|null;createdAt:string};
export type UsageRow={id:string;runId:string|null;family:string;operation:string;units:number|null;cost:number|null;createdAt:string};
export type AuditRow={id:string;projectId:string|null;runId:string|null;actorType:string;actorRef:string|null;eventType:string;createdAt:string;payload:unknown};
export type ProjectConfigRow={id:string;key:string;name:string;repository:string|null;stage:string;active:boolean;manifest:Record<string,unknown>};
export type RunDetail={id:string;taskId:string;taskTitle:string;projectId:string|null;projectName:string|null;status:string;route:string|null;candidateCommit:string|null;branchName:string|null;attemptCount:number;leaseOwner:string|null;leaseExpiresAt:string|null;lastError:string|null;createdAt:string;finishedAt:string|null;evaluations:EvaluationRow[];deployments:DeploymentRow[];gates:GateSummary[];usage:UsageRow[];audit:AuditRow[]};

async function projectNameMap(projectIds:string[],cfg:NonNullable<ReturnType<typeof getSupabaseServerConfig>>){
 if(!projectIds.length)return new Map<string,string>();
 const response=await fetch(cfg.url+"/rest/v1/factory_projects?select=id,name&id=in.("+projectIds.join(",")+")",{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)return new Map<string,string>();
 const rows=await response.json();return new Map(rows.map((x:any)=>[String(x.id),String(x.name)]));
}

export async function getWorkQueue(limit=100):Promise<WorkQueueItem[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(cfg.url+"/rest/v1/factory_tasks?select=id,project_id,title,status,complexity,external_key,created_at,updated_at&status=not.in.(completed,cancelled)&order=updated_at.desc&limit="+limit,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load work queue");
 const rows=await response.json();const ids=[...new Set(rows.map((x:any)=>String(x.project_id)).filter(Boolean))] as string[];const names=await projectNameMap(ids,cfg);
 return rows.map((x:any)=>({id:String(x.id),projectId:String(x.project_id),projectName:names.get(String(x.project_id))||"Project",title:String(x.title),status:String(x.status),complexity:String(x.complexity||"—"),externalKey:x.external_key||null,createdAt:String(x.created_at),updatedAt:String(x.updated_at)}));
}

export async function getEvaluations(limit=100):Promise<EvaluationRow[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(cfg.url+"/rest/v1/factory_evaluations?select=id,run_id,eval_type,status,score,baseline_ref,created_at&order=created_at.desc&limit="+limit,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load evaluations");
 const rows=await response.json();return rows.map((x:any)=>({id:String(x.id),runId:String(x.run_id),type:String(x.eval_type),status:String(x.status),score:x.score==null?null:Number(x.score),baselineRef:x.baseline_ref||null,createdAt:String(x.created_at)}));
}

export async function getDeployments(limit=100):Promise<DeploymentRow[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(cfg.url+"/rest/v1/factory_deployments?select=id,run_id,environment,status,deployment_ref,deployed_at,created_at&order=created_at.desc&limit="+limit,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load deployments");
 const rows=await response.json();return rows.map((x:any)=>({id:String(x.id),runId:String(x.run_id),environment:String(x.environment),status:String(x.status),deploymentRef:x.deployment_ref||null,deployedAt:x.deployed_at||null,createdAt:String(x.created_at)}));
}

export async function getUsage(limit=250):Promise<UsageRow[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(cfg.url+"/rest/v1/factory_tool_usage?select=id,run_id,tool_family,operation,usage_units,estimated_cost,created_at&order=created_at.desc&limit="+limit,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load usage");
 const rows=await response.json();return rows.map((x:any)=>({id:String(x.id),runId:x.run_id?String(x.run_id):null,family:String(x.tool_family),operation:String(x.operation),units:x.usage_units==null?null:Number(x.usage_units),cost:x.estimated_cost==null?null:Number(x.estimated_cost),createdAt:String(x.created_at)}));
}

export async function getAuditLog(limit=200):Promise<AuditRow[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(cfg.url+"/rest/v1/factory_audit_events?select=id,project_id,run_id,actor_type,actor_ref,event_type,payload,created_at&order=created_at.desc&limit="+limit,{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load audit log");
 const rows=await response.json();return rows.map((x:any)=>({id:String(x.id),projectId:x.project_id?String(x.project_id):null,runId:x.run_id?String(x.run_id):null,actorType:String(x.actor_type),actorRef:x.actor_ref||null,eventType:String(x.event_type),createdAt:String(x.created_at),payload:x.payload}));
}

export async function getProjectConfigs():Promise<ProjectConfigRow[]>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return[];
 const response=await fetch(cfg.url+"/rest/v1/factory_projects?select=id,project_key,name,repository,lifecycle_stage,is_active,manifest&order=name.asc",{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Unable to load project configuration");
 const rows=await response.json();return rows.map((x:any)=>({id:String(x.id),key:String(x.project_key),name:String(x.name),repository:x.repository||null,stage:String(x.lifecycle_stage),active:Boolean(x.is_active),manifest:(x.manifest||{}) as Record<string,unknown>}));
}

export async function getRunDetail(runId:string):Promise<RunDetail|null>{
 await requireConsoleOperator();const cfg=serverHeaders();if(!cfg)return null;
 const runResponse=await fetch(cfg.url+"/rest/v1/factory_runs?select=id,task_id,status,execution_route,candidate_commit,branch_name,attempt_count,lease_owner,lease_expires_at,last_error,created_at,finished_at&id=eq."+encodeURIComponent(runId)+"&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!runResponse.ok)throw new Error("Unable to load run");const runs=await runResponse.json();if(!runs.length)return null;const r=runs[0];
 let taskTitle="Task",projectId:string|null=null,projectName:string|null=null;
 const taskResponse=await fetch(cfg.url+"/rest/v1/factory_tasks?select=id,title,project_id&id=eq."+encodeURIComponent(String(r.task_id))+"&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(taskResponse.ok){const tasks=await taskResponse.json();if(tasks.length){taskTitle=String(tasks[0].title);projectId=String(tasks[0].project_id);const names=await projectNameMap([projectId],cfg);projectName=names.get(projectId)||null;}}
 const runFilter=encodeURIComponent(runId);
 const [ev,dp,gt,us,au]=await Promise.all([
  fetch(cfg.url+"/rest/v1/factory_evaluations?select=id,run_id,eval_type,status,score,baseline_ref,created_at&run_id=eq."+runFilter+"&order=created_at.asc",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_deployments?select=id,run_id,environment,status,deployment_ref,deployed_at,created_at&run_id=eq."+runFilter+"&order=created_at.asc",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_human_gates?select=id,run_id,gate_type,status,reasons,requested_at&run_id=eq."+runFilter+"&order=requested_at.asc",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_tool_usage?select=id,run_id,tool_family,operation,usage_units,estimated_cost,created_at&run_id=eq."+runFilter+"&order=created_at.asc",{headers:cfg.headers,cache:"no-store"}),
  fetch(cfg.url+"/rest/v1/factory_audit_events?select=id,project_id,run_id,actor_type,actor_ref,event_type,payload,created_at&run_id=eq."+runFilter+"&order=created_at.asc",{headers:cfg.headers,cache:"no-store"})
 ]);
 const read=async(x:any)=>x.ok?await x.json():[];
 const [evals,deployments,gates,usage,audit]=await Promise.all([read(ev),read(dp),read(gt),read(us),read(au)]);
 return{id:String(r.id),taskId:String(r.task_id),taskTitle,projectId,projectName,status:String(r.status),route:r.execution_route||null,candidateCommit:r.candidate_commit||null,branchName:r.branch_name||null,attemptCount:Number(r.attempt_count||0),leaseOwner:r.lease_owner||null,leaseExpiresAt:r.lease_expires_at||null,lastError:r.last_error||null,createdAt:String(r.created_at),finishedAt:r.finished_at||null,
  evaluations:evals.map((x:any)=>({id:String(x.id),runId:String(x.run_id),type:String(x.eval_type),status:String(x.status),score:x.score==null?null:Number(x.score),baselineRef:x.baseline_ref||null,createdAt:String(x.created_at)})),
  deployments:deployments.map((x:any)=>({id:String(x.id),runId:String(x.run_id),environment:String(x.environment),status:String(x.status),deploymentRef:x.deployment_ref||null,deployedAt:x.deployed_at||null,createdAt:String(x.created_at)})),
  gates:gates.map((x:any)=>({id:String(x.id),runId:String(x.run_id),type:String(x.gate_type),status:String(x.status),reasons:x.reasons,requestedAt:String(x.requested_at)})),
  usage:usage.map((x:any)=>({id:String(x.id),runId:x.run_id?String(x.run_id):null,family:String(x.tool_family),operation:String(x.operation),units:x.usage_units==null?null:Number(x.usage_units),cost:x.estimated_cost==null?null:Number(x.estimated_cost),createdAt:String(x.created_at)})),
  audit:audit.map((x:any)=>({id:String(x.id),projectId:x.project_id?String(x.project_id):null,runId:x.run_id?String(x.run_id):null,actorType:String(x.actor_type),actorRef:x.actor_ref||null,eventType:String(x.event_type),createdAt:String(x.created_at),payload:x.payload}))
 };
}
