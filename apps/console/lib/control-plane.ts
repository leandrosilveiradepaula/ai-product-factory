export type Project={key:string;name:string;stage:string;status:string;updatedAt:string};
export type Dashboard={projects:Project[];activeRuns:number;pendingGates:number;codexCalls:number;modelCalls:number;failedRuns:number};
const demo:Dashboard={projects:[{key:"agente-sql-financeiro",name:"Agente SQL Financeiro",stage:"planning",status:"active",updatedAt:"pilot onboarded"}],activeRuns:0,pendingGates:0,codexCalls:0,modelCalls:0,failedRuns:0};
function slugify(value:string){return value.normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,64)}
export async function createProjectIntake(input:{mode:"greenfield"|"import";name:string;summary:string;repository?:string;users?:string;mustHave?:string;integrations?:string}){const url=process.env.SUPABASE_URL;const key=process.env.SUPABASE_SERVICE_ROLE_KEY;if(!url||!key)throw new Error("Control plane credentials are not configured");const projectKey=slugify(input.name);if(!projectKey)throw new Error("Unable to derive project key");const response=await fetch(`${url}/rest/v1/rpc/factory_create_project_intake`,{method:"POST",headers:{apikey:key,Authorization:`Bearer ${key}`,"Content-Type":"application/json"},body:JSON.stringify({p_project_key:projectKey,p_name:input.name,p_repository:input.repository||"",p_project_kind:input.mode,p_manifest:{source:"factory-console",autonomy:"default"},p_spec:{summary:input.summary,users:input.users||null,must_have:input.mustHave||null,integrations:input.integrations||null}}),cache:"no-store"});if(!response.ok){const body=await response.text();if(response.status===409||body.includes("duplicate key"))throw new Error("Já existe um projeto com esse nome/chave.");throw new Error("Não foi possível persistir o intake no Control Plane.");}const id=await response.json();return{projectId:String(id),projectKey};}

export async function enqueueProjectBootstrap(projectKey:string){const url=process.env.SUPABASE_URL;const key=process.env.SUPABASE_SERVICE_ROLE_KEY;if(!url||!key)throw new Error("Control plane credentials are not configured");const response=await fetch(`${url}/rest/v1/rpc/factory_enqueue_project_bootstrap`,{method:"POST",headers:{apikey:key,Authorization:`Bearer ${key}`,"Content-Type":"application/json"},body:JSON.stringify({p_project_key:projectKey}),cache:"no-store"});if(!response.ok)throw new Error("Não foi possível enfileirar o ciclo inicial da Factory.");return response.json() as Promise<{project_id:string;task_id:string;run_id:string;created:boolean}>;}

export async function getDashboard():Promise<Dashboard>{
 const url=process.env.SUPABASE_URL; const key=process.env.SUPABASE_SERVICE_ROLE_KEY;
 if(!url||!key)return demo;
 const headers={apikey:key,Authorization:`Bearer ${key}`};
 const [projects,runs,gates,tools]=await Promise.all([
  fetch(`${url}/rest/v1/factory_projects?select=project_key,name,current_stage,status,updated_at&order=updated_at.desc`,{headers,cache:"no-store"}),
  fetch(`${url}/rest/v1/factory_runs?select=status&status=eq.running`,{headers,cache:"no-store"}),
  fetch(`${url}/rest/v1/factory_human_gates?select=status&status=eq.pending`,{headers,cache:"no-store"}),
  fetch(`${url}/rest/v1/factory_tool_usage?select=tool_name`,{headers,cache:"no-store"})]);
 if(!projects.ok)throw new Error("Control plane unavailable");
 const p=await projects.json(); const r=runs.ok?await runs.json():[]; const g=gates.ok?await gates.json():[]; const t=tools.ok?await tools.json():[];
 return {projects:p.map((x:any)=>({key:x.project_key,name:x.name,stage:x.current_stage,status:x.status,updatedAt:x.updated_at})),activeRuns:r.length,pendingGates:g.length,codexCalls:t.filter((x:any)=>String(x.tool_name).toLowerCase().includes("codex")).length,modelCalls:t.filter((x:any)=>String(x.tool_name).toLowerCase().includes("model")).length,failedRuns:0};
}