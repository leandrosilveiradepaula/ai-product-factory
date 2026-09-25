import {requireConsoleOperator} from "./auth-server";
export type Project={key:string;name:string;stage:string;status:string;updatedAt:string};
export type Dashboard={projects:Project[];activeRuns:number;pendingGates:number;codexCalls:number;modelCalls:number;failedRuns:number};
const demo:Dashboard={projects:[{key:"agente-sql-financeiro",name:"Agente SQL Financeiro",stage:"planning",status:"active",updatedAt:"pilot onboarded"}],activeRuns:0,pendingGates:0,codexCalls:0,modelCalls:0,failedRuns:0};
function slugify(value:string){return value.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,64)}
export async function createProjectIntake(input:{mode:"greenfield"|"import";name:string;summary:string;repository?:string;users?:string;mustHave?:string;integrations?:string}){await requireConsoleOperator();const url=process.env.SUPABASE_URL;const key=process.env.SUPABASE_SERVICE_ROLE_KEY;if(!url||!key)throw new Error("Control plane credentials are not configured");const projectKey=slugify(input.name);if(!projectKey)throw new Error("Unable to derive project key");const response=await fetch(`${url}/rest/v1/rpc/factory_create_project_intake`,{method:"POST",headers:{apikey:key,Authorization:`Bearer ${key}`,"Content-Type":"application/json"},body:JSON.stringify({p_project_key:projectKey,p_name:input.name,p_repository:input.repository||"",p_project_kind:input.mode,p_manifest:{source:"factory-console",autonomy:"default"},p_spec:{summary:input.summary,users:input.users||null,must_have:input.mustHave||null,integrations:input.integrations||null}}),cache:"no-store"});if(!response.ok){const body=await response.text();if(response.status===409||body.includes("duplicate key"))throw new Error("Já existe um projeto com esse nome/chave.");throw new Error("Não foi possível persistir o intake no Control Plane.");}const id=await response.json();return{projectId:String(id),projectKey};}

export async function enqueueProjectBootstrap(projectKey:string){await requireConsoleOperator();const url=process.env.SUPABASE_URL;const key=process.env.SUPABASE_SERVICE_ROLE_KEY;if(!url||!key)throw new Error("Control plane credentials are not configured");const response=await fetch(`${url}/rest/v1/rpc/factory_enqueue_project_bootstrap`,{method:"POST",headers:{apikey:key,Authorization:`Bearer ${key}`,"Content-Type":"application/json"},body:JSON.stringify({p_project_key:projectKey}),cache:"no-store"});if(!response.ok)throw new Error("Não foi possível enfileirar o ciclo inicial da Factory.");return response.json() as Promise<{project_id:string;task_id:string;run_id:string;created:boolean}>;}

export async function getDashboard():Promise<Dashboard>{
 await requireConsoleOperator();
 const url=process.env.SUPABASE_URL; const key=process.env.SUPABASE_SERVICE_ROLE_KEY;
 if(!url||!key)return demo;
 const headers={apikey:key,Authorization:`Bearer ${key}`};
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

function serverHeaders(){
 const url=process.env.SUPABASE_URL;const key=process.env.SUPABASE_SERVICE_ROLE_KEY;
 if(!url||!key)return null;
 return {url,headers:{apikey:key,Authorization:`Bearer ${key}`}};
}

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
