import {notFound} from "next/navigation";
import {revalidatePath} from "next/cache";
import {getProjectDatabases,getProjectDetail,getProjectExecutionTeamPlan,getProjectGitHubAccess,getProjectOperations,getProjectStateContext,requestProjectGitHubRecheck} from "../../../lib/control-plane";
import {isSupabaseOAuthConfigured} from "../../../lib/supabase-oauth";
import {requireConsoleOperator} from "../../../lib/auth-server";
import {ActionLink,EmptyState,humanizeStatus,MetricCard,PageHeader,SectionHeader,StatusPill} from "../../ui";

const stages=["discovery","specification","planning","implementation","review","validation","preview","human_gate","release","operations"];
const stageLabels=["Descoberta","Especificação","Plano","Implementação","Revisão","Testes / Avaliações","Prévia","Aprovação","Liberação","Operação"];
const macroStages=[
 {label:"Entender",detail:"Descoberta e especificação",members:["discovery","specification"]},
 {label:"Planejar",detail:"Plano técnico e backlog",members:["planning"]},
 {label:"Construir",detail:"Implementação e revisão",members:["implementation","review"]},
 {label:"Validar",detail:"Testes, avaliações e prévia",members:["validation","preview"]},
 {label:"Liberar",detail:"Aprovação, release e operação",members:["human_gate","release","operations"]},
];
function progress(stage:string){const i=stages.indexOf(stage);return i<0?0:Math.round(((i+1)/stages.length)*100)}
function macroStageIndex(stage:string){const i=macroStages.findIndex(item=>item.members.includes(stage));return i<0?0:i}
function display(value:unknown){return typeof value==="string"?value:JSON.stringify(value)}
function nextAction(stage:string,hasPendingDatabase:boolean,activeTasks:number){
 if(hasPendingDatabase)return {title:"Conectar o banco de dados",body:"A Factory está aguardando a conexão mínima necessária para reconciliar e executar o trabalho com evidência real.",href:"#databases",label:"Ver banco de dados"};
 if(stage==="human_gate")return {title:"Tomar a decisão pendente",body:"A automação chegou a um gate humano. Revise o motivo e decida antes de a Factory continuar.",href:"/gates",label:"Abrir aprovações"};
 if(stage==="release")return {title:"Revisar e fazer o merge de produção",body:"Os gates automáticos terminaram. Produção continua dependendo de um merge humano explícito.",href:"/deployments",label:"Ver release"};
 if(stage==="operations")return {title:"Acompanhar a operação",body:"O projeto já está em operação. Use as evidências e implantações para acompanhar saúde e novos trabalhos.",href:"/deployments",label:"Ver implantações"};
 if(activeTasks===0)return {title:"Nenhuma ação necessária agora",body:"Não há tarefas abertas neste projeto. Acompanhe novas evidências ou inicie um novo trabalho quando necessário.",href:"/projects",label:"Voltar aos projetos"};
 if(["discovery","specification"].includes(stage))return {title:"Acompanhar entendimento do produto",body:"A Factory está transformando o objetivo em requisitos e especificação. Você só precisa agir se aparecer uma decisão em “Precisa de atenção”.",href:"/gates",label:"Ver decisões"};
 if(stage==="planning")return {title:"Aguardar o plano de execução",body:"A Factory está decompondo o trabalho, escolhendo agentes e organizando dependências. Nenhuma escolha técnica manual é necessária.",href:"/queue",label:"Ver fila"};
 if(["implementation","review"].includes(stage))return {title:"Acompanhar construção e revisão",body:"A execução está com os agentes e revisores. Use a fila para acompanhar o trabalho sem interferir no roteamento.",href:"/queue",label:"Ver fila"};
 return {title:"Acompanhar validação e prévia",body:"A Factory está validando qualidade e preparando evidências antes do gate humano de produção.",href:"/runs",label:"Ver execuções"};
}

const supabaseMessages:Record<string,{status:string;message:string}>={
 connected:{status:"success",message:"Supabase conectado e acesso somente leitura verificado."},
 oauth_invalid:{status:"failed",message:"A autorização do Supabase expirou ou não corresponde ao fluxo iniciado. Tente conectar novamente."},
 control_plane_unavailable:{status:"failed",message:"O Control Plane não estava disponível para concluir a conexão."},
 project_lookup_failed:{status:"failed",message:"Não foi possível localizar o projeto durante a conexão com o Supabase."},
 project_missing:{status:"failed",message:"O projeto não foi encontrado durante a conexão com o Supabase."},
 lookup_failed:{status:"failed",message:"Não foi possível localizar o vínculo de banco durante a conexão."},
 project_ref_missing:{status:"failed",message:"O vínculo do Supabase não possui project_ref válido."},
 verification_failed:{status:"failed",message:"A autorização retornou, mas a verificação do acesso não foi concluída. Nenhuma ampliação de permissão foi aplicada."},
};

const githubCapabilityLabels:Record<string,string>={
 metadata_read:"Repositório conectado",
 contents_read:"Leitura do código",
 contents_write:"Criar branch / commit",
 issues_read:"Issues · leitura",
 issues_write:"Issues · escrita",
 pull_requests_read:"Pull Requests · leitura",
 pull_requests_write:"Pull Requests · escrita",
 actions_read:"Actions / logs",
 commit_statuses_read:"Commit Statuses",
 ci_evidence_read:"Checks / evidência de CI",
};
function githubCapabilityLabel(status:string){return status==="verified"?"Verificado":status==="missing"?"Permissão faltando":status==="unverified"?"Ainda não verificado":humanizeStatus(status)}
async function requestGitHubRecheck(formData:FormData){
 "use server";
 const projectId=String(formData.get("project_id")||"");
 const projectKey=String(formData.get("project_key")||"");
 if(!projectId||!projectKey)throw new Error("Projeto inválido para revalidação GitHub.");
 await requestProjectGitHubRecheck(projectId);
 revalidatePath("/projects/"+projectKey);
}

export default async function Project({params,searchParams}:{params:Promise<{key:string}>;searchParams:Promise<{supabase?:string}>}){
 const [{key},query,operator]=await Promise.all([params,searchParams,requireConsoleOperator()]);
 const p=await getProjectDetail(key);if(!p)notFound();
 const [ops,state,databases,teamPlan,githubAccess]=await Promise.all([getProjectOperations(p.id),getProjectStateContext(p.id),getProjectDatabases(p.id),getProjectExecutionTeamPlan(p.id),getProjectGitHubAccess(p.id,p.repository)]);
 const activeTasks=p.tasks.filter(t=>!["completed","cancelled"].includes(t.status));const oauthReady=isSupabaseOAuthConfigured();
 const hasPendingDatabase=databases.some(db=>db.status==="pending_access");
 const action=nextAction(p.stage,hasPendingDatabase,activeTasks.length);
 const currentMacro=macroStageIndex(p.stage);
 const supabaseNotice=query.supabase?supabaseMessages[query.supabase]:undefined;
 return <>
  <PageHeader eyebrow="Detalhes do projeto" title={p.name} subtitle={p.repository||p.key} actions={<><StatusPill status={p.stage} tone="accent"/><ActionLink href="/queue">Fila de trabalho</ActionLink></>}/>
  {supabaseNotice?<div className={supabaseNotice.status==="success"?"card noticeCard success":"card noticeCard danger"} role="status"><StatusPill status={supabaseNotice.status}/><span>{supabaseNotice.message}</span></div>:null}
  <div className="projectOrientation">
   <div>
    <div className="macroLifecycle" aria-label="Ciclo do produto em cinco macroetapas">
     {macroStages.map((item,i)=><div className={"macroStage "+(i<currentMacro?"done":i===currentMacro?"current":"")} key={item.label}><span>Etapa {i+1}</span><strong>{item.label}</strong><small>{item.detail}</small></div>)}
    </div>
    <div className="microStageLine"><span>Etapa detalhada atual:</span><StatusPill status={p.stage} tone="accent"/><span className="muted">{stageLabels[stages.indexOf(p.stage)]||humanizeStatus(p.stage)}</span></div>
   </div>
   <aside className="nextActionCard" aria-label="Próxima ação">
    <span className="detailLabel">O que você precisa fazer agora</span>
    <h2>{action.title}</h2>
    <p>{action.body}</p>
    <div className="actions"><ActionLink href={action.href} variant="primary">{action.label}</ActionLink></div>
   </aside>
  </div>
  <div className="grid compact projectPrimaryMetrics">
   <MetricCard label="Ciclo de vida" value={progress(p.stage)+"%"} note={<div className="progressTrack"><div className="progressFill" style={{width:progress(p.stage)+"%"}}/></div>}/>
   <MetricCard label="Tarefas abertas" value={activeTasks.length} note={p.tasks.length+" no total"}/>
   <MetricCard label="Evidências" value={ops.evaluations+ops.deployments} note={ops.evaluations+" avaliações · "+ops.deployments+" implantações"}/>
  </div>
  {githubAccess?<section className="section" id="github-access"><SectionHeader title="GitHub · acesso do projeto" action={<div className="badgeLine"><StatusPill status={githubAccess.status} label={githubAccess.status==="ready"?"Pronto":githubAccess.status==="partial"?"Parcial":githubAccess.status==="blocked"?"Bloqueado":"Aguardando verificação"}/><span className="muted">{githubAccess.lastVerifiedAt?"verificado em "+new Date(githubAccess.lastVerifiedAt).toLocaleString("pt-BR"):"sem preflight registrado"}</span></div>}/>
   <div className="card denseStack">
    <div className="panelHeading"><div><strong>{githubAccess.repository}</strong><div className="muted">Autenticação operacional: {githubAccess.authMode==="github_app"?"GitHub App":githubAccess.authMode==="native_github_token"?"token nativo do workflow":"token fine-grained"}</div></div><StatusPill status={githubAccess.status}/></div>
    <div className="table">
     <div className="tableRow tableHeader"><span>Capacidade</span><span>Necessária</span><span>Estado</span><span>Ação</span></div>
     {githubAccess.capabilities.map(cap=><div className="tableRow" key={cap.key}><strong>{githubCapabilityLabels[cap.key]||cap.key}</strong><span>{cap.required?"Sim":"Não"}</span><StatusPill status={cap.status} label={githubCapabilityLabel(cap.status)}/><span className="muted">{cap.status==="verified"?"nenhuma":cap.status==="missing"?"corrigir permissão":"revalidar acesso"}</span></div>)}
     <div className="tableRow"><strong>Release humano</strong><span>Separado</span><StatusPill status={githubAccess.releaseHuman.enabled?"verified":"blocked"} label={githubAccess.releaseHuman.enabled?"Habilitado":"Bloqueado"}/><span className="muted">{githubAccess.releaseHuman.reason||"merge somente por ação humana explícita"}</span></div>
    </div>
    {githubAccess.lastError?<div className="errorText">{githubAccess.lastError}</div>:null}
    <div className="actions">
     <a className="linkButton" href="https://github.com/settings/personal-access-tokens" target="_blank" rel="noreferrer">Corrigir acesso no GitHub</a>
     {operator.role==="admin"?<form action={requestGitHubRecheck}><input type="hidden" name="project_id" value={p.id}/><input type="hidden" name="project_key" value={p.key}/><button type="submit" className="primary linkButton">Verificar novamente</button></form>:null}
    </div>
    <p className="muted" style={{margin:0}}>A Factory só executa uma etapa quando as capacidades exigidas por aquela etapa estão comprovadas. Permissões de escrita não são testadas por mutações artificiais; permanecem fail-closed até haver credencial apropriada, preferencialmente uma GitHub App.</p>
   </div>
  </section>:null}
  {state.objective?<section className="section"><SectionHeader title="Objetivo atual"/><div className="card"><p style={{margin:0}}>{state.objective}</p></div></section>:null}
  {p.kind==="existing"?<section className="section"><SectionHeader title="Estado reconciliado" action={state.snapshot?<span className="muted">atualizado em {new Date(state.snapshot.createdAt).toLocaleString("pt-BR")}</span>:undefined}/>
   {!state.snapshot?<EmptyState>A reconciliação ainda não foi concluída. A Factory vai registrar aqui o estado real confirmado, as evidências e o trabalho que ainda falta.</EmptyState>:<div className="card stack">
    <div className="cardTop"><div><span className="detailLabel">Etapa observada</span><div style={{marginTop:7}}><StatusPill status={state.snapshot.observedStage||"unknown"} label={state.snapshot.observedStage?humanizeStatus(state.snapshot.observedStage):"Não determinada"}/></div></div><div className="muted mono">{state.snapshot.runId?"execução "+state.snapshot.runId.slice(0,8):"registro independente"}</div></div>
    <div><span className="detailLabel">Resumo do estado atual</span><p>{state.snapshot.summary}</p></div>
    <div className="twoCol">
     <div><span className="detailLabel">Evidências confirmadas</span>{state.snapshot.evidence.length?<ul>{state.snapshot.evidence.map((x,i)=><li key={i}>{display(x)}</li>)}</ul>:<p className="muted">Nenhuma evidência listada.</p>}</div>
     <div><span className="detailLabel">Lacunas restantes</span>{state.snapshot.gaps.length?<ul>{state.snapshot.gaps.map((x,i)=><li key={i}>{display(x)}</li>)}</ul>:<p className="muted">Nenhuma lacuna registrada.</p>}</div>
    </div>
    <div><span className="detailLabel">Restrições preservadas</span>{state.snapshot.constraints.length?<ul>{state.snapshot.constraints.map((x,i)=><li key={i}>{display(x)}</li>)}</ul>:<p className="muted">Nenhuma restrição adicional registrada.</p>}</div>
    {Object.keys(state.snapshot.sourceStatus).length?<div><span className="detailLabel">Fontes reconciliadas</span><div className="valueList">{Object.entries(state.snapshot.sourceStatus).map(([source,value])=><div className="valueRow" key={source}><strong>{source}</strong><span className="muted">{display(value)}</span></div>)}</div></div>:null}
   </div>}
  </section>:null}
  {hasPendingDatabase?<section className="section" id="databases"><SectionHeader title="Banco de dados · ação necessária" action={<span className="muted">{databases.filter(db=>db.status==="pending_access").length} pendente{databases.filter(db=>db.status==="pending_access").length===1?"":"s"}</span>}/>
   {databases.length===0?<EmptyState>Nenhum banco foi vinculado a este projeto. A Factory pode registrar um banco existente ou preparar o provisionamento de um novo banco, sujeito aos gates aplicáveis.</EmptyState>:<div className="table">
    <div className="tableRow tableHeader"><span>Banco</span><span>Acesso</span><span>Estado</span><span>Verificação</span></div>
    {databases.map(db=><div className="tableRow" key={db.id}>
     <div><strong>{db.provider==="supabase"?"Supabase":db.provider}</strong><div className="muted mono">{db.projectRef||"project_ref pendente"} · {db.environment}</div></div>
     <div><StatusPill status={db.permissionMode} label={db.permissionMode==="read"?"Somente leitura":db.permissionMode==="read_write"?"Leitura e escrita":"Não configurado"}/><div className="muted">{db.accessMode==="oauth"?"OAuth":db.accessMode==="management_api"?"Management API":"Conexão pendente"}</div></div>
     <StatusPill status={db.status} label={db.status==="pending_access"?"Aguardando conexão":db.status==="ready_read"?"Leitura verificada":db.status==="ready_write"?"Escrita verificada":humanizeStatus(db.status)}/>
     <span className="muted">{db.lastVerifiedAt?new Date(db.lastVerifiedAt).toLocaleString("pt-BR"):"Ainda não verificado"}</span>
    </div>)}
   </div>}
   {databases.some(db=>db.status==="pending_access")?<div className="card" style={{marginTop:12}}><strong>Próxima ação</strong><p className="muted">Conecte o Supabase com acesso mínimo. A Factory valida a identidade do projeto e uma consulta somente leitura antes de considerar o banco pronto. Nenhuma credencial é exibida nesta tela.</p>{oauthReady&&operator.role==="admin"?<div className="actions">{databases.filter(db=>db.status==="pending_access"&&db.provider==="supabase").map(db=><a className="primary linkButton" key={db.id} href={`/api/integrations/supabase/connect?project=${encodeURIComponent(p.key)}&database=${encodeURIComponent(db.id)}`}>Conectar Supabase</a>)}</div>:oauthReady?<div className="badgeLine"><StatusPill status="blocked" label="Administrador necessário"/><span className="muted">A conexão OAuth altera credenciais server-side e só pode ser iniciada por um administrador da Factory.</span></div>:<div className="badgeLine"><StatusPill status="blocked" label="OAuth do Supabase não configurado"/><span className="muted">A Factory permanece fail-closed até o client ID e o client secret existirem no ambiente server-side.</span></div>}</div>:null}
  </section>:null}

  <details className="projectTechnicalDetails">
   <summary>
    <span><strong>Detalhes técnicos do projeto</strong><small>Plano de trabalho, equipe/agentes, custo, integrações prontas e linha do tempo.</small></span>
    <span className="muted">{p.tasks.length} tarefas · {teamPlan?.profilesSelected||0} perfis · {ops.timeline.length} eventos</span>
   </summary>
   <div className="projectTechnicalBody">
    <div className="grid compact">
     <MetricCard label="Custo conhecido" value={ops.estimatedCost.toFixed(4)} note={ops.usageUnits+" unidades de uso"}/>
     <MetricCard label="Avaliações" value={ops.evaluations} note="evidências de qualidade"/>
     <MetricCard label="Implantações" value={ops.deployments} note="evidências de entrega"/>
    </div>
    {databases.length&&!hasPendingDatabase?<section className="section"><SectionHeader title="Bancos de dados" action={<span className="muted">{databases.length} integração{databases.length===1?"":"ões"}</span>}/><div className="table">
     <div className="tableRow tableHeader"><span>Banco</span><span>Acesso</span><span>Estado</span><span>Verificação</span></div>
     {databases.map(db=><div className="tableRow" key={db.id}><div><strong>{db.provider==="supabase"?"Supabase":db.provider}</strong><div className="muted mono">{db.projectRef||"project_ref pendente"} · {db.environment}</div></div><div><StatusPill status={db.permissionMode} label={db.permissionMode==="read"?"Somente leitura":db.permissionMode==="read_write"?"Leitura e escrita":"Não configurado"}/><div className="muted">{db.accessMode==="oauth"?"OAuth":db.accessMode==="management_api"?"Management API":"Conexão pendente"}</div></div><StatusPill status={db.status} label={db.status==="ready_read"?"Leitura verificada":db.status==="ready_write"?"Escrita verificada":humanizeStatus(db.status)}/><span className="muted">{db.lastVerifiedAt?new Date(db.lastVerifiedAt).toLocaleString("pt-BR"):"Ainda não verificado"}</span></div>)}
    </div></section>:null}
    <section className="section"><SectionHeader title="Plano de trabalho" action={<span className="muted">{p.tasks.length} tarefas</span>}/><div className="table">
   <div className="tableRow tableHeader"><span>Tarefa</span><span>Complexidade</span><span>Estado</span><span>Chave</span></div>
   {p.tasks.length===0?<EmptyState>Nenhuma tarefa registrada.</EmptyState>:p.tasks.map(t=><div className="tableRow" key={t.id}><strong>{t.title}</strong><StatusPill status={t.complexity}/><StatusPill status={t.status}/><span className="muted mono">{t.externalKey||t.id.slice(0,8)}</span></div>)}
  </div></section>
  <section className="section"><SectionHeader title="Equipe de execução" action={teamPlan?<span className="muted">plano v{teamPlan.version} · {teamPlan.profilesSelected} perfil{teamPlan.profilesSelected===1?"":"is"} · pico {teamPlan.plannedWorkerPeak} worker{teamPlan.plannedWorkerPeak===1?"":"s"}</span>:undefined}/>
   {!teamPlan?<EmptyState>A equipe será definida automaticamente quando o planejamento de engenharia for concluído.</EmptyState>:<div className="stack">
    <div className="grid compact">
     <MetricCard label="Perfis selecionados" value={teamPlan.profilesSelected} note="menor conjunto que cobre o plano"/>
     <MetricCard label="Pico de workers" value={teamPlan.plannedWorkerPeak} note="paralelismo máximo planejado"/>
     <MetricCard label="Ondas" value={teamPlan.waves.length} note="dependências e conflitos de escopo"/>
     <MetricCard label="Estado do plano" value={teamPlan.status==="ready"?"Pronto":"Bloqueado"} note={"gerado em "+new Date(teamPlan.createdAt).toLocaleString("pt-BR")}/>
    </div>
    <div className="threeCol">
     {teamPlan.selectedAgents.map(agent=><div className="card denseStack" key={agent.agent_key}>
      <div className="panelHeading"><strong>{agent.role}</strong><StatusPill status={agent.execution_ready?"active":"blocked"} label={agent.execution_ready?agent.workers_planned+" worker"+(agent.workers_planned===1?"":"s"):"lane pendente"}/></div>
      <div className="muted mono">{agent.agent_key}</div>
      <div><span className="detailLabel">Tarefas</span><div className="badgeLine">{agent.task_keys.map(key=><code key={key}>{key}</code>)}</div></div>
      <div><span className="detailLabel">Por que foi escolhido</span><ul>{agent.reasons.map((reason,i)=><li key={i}>{reason}</li>)}</ul></div>
      <div className="muted">capacidade máxima: {agent.max_concurrency}</div>
     </div>)}
    </div>
    {teamPlan.waves.length?<div className="card"><span className="detailLabel">Ondas de execução</span><div className="timeline">{teamPlan.waves.map(wave=><div className="timelineItem" key={wave.wave}><div className="badgeLine"><StatusPill status="policy" label={"Onda "+wave.wave}/><strong>{wave.parallel_workers} worker{wave.parallel_workers===1?"":"s"} em paralelo</strong></div><div className="badgeLine">{wave.task_keys.map(key=><code key={key}>{key}</code>)}</div></div>)}</div></div>:null}
    {teamPlan.advisorySpecialistLanes.length?<div className="card"><span className="detailLabel">Especialistas recomendados para fases independentes</span><p className="muted">Estas participações foram identificadas pela política, mas permanecem fail-closed até existir uma lane própria sem escrita para review/QA/operações.</p><div className="valueList">{teamPlan.advisorySpecialistLanes.map(item=><div className="valueRow" key={item.role}><strong>{item.role}</strong><span className="muted">{item.reasons.join(" · ")}</span></div>)}</div></div>:null}
    {teamPlan.blockers.length?<div className="card"><span className="detailLabel">Bloqueios do plano</span><ul>{teamPlan.blockers.map((item,i)=><li key={i}><strong>{item.code}</strong>{item.task_key?" · "+item.task_key:""}{item.dependency?" · dependência "+item.dependency:""}</li>)}</ul></div>:null}
    {teamPlan.excludedAgents.length?<div className="card"><span className="detailLabel">Perfis não usados neste trabalho</span><div className="valueList">{teamPlan.excludedAgents.map(item=><div className="valueRow" key={item.agent_key}><strong>{item.role}</strong><span className="muted">{item.reason}</span></div>)}</div></div>:null}
   </div>}
  </section>
  <section className="section"><SectionHeader title="Linha do tempo operacional" action={<span className="muted">{ops.timeline.length} eventos de evidência</span>}/>
   {ops.timeline.length===0?<EmptyState>Ainda não há evidências operacionais para este projeto.</EmptyState>:<div className="card"><div className="timeline">{ops.timeline.slice(0,40).map(item=><div className="timelineItem" key={item.id}><div className="badgeLine"><StatusPill status={item.kind}/><strong>{item.title}</strong>{item.status?<StatusPill status={item.status}/>:null}</div><div className="timelineMeta"><span>{new Date(item.at).toLocaleString("pt-BR")}</span>{item.detail?<span>{item.detail}</span>:null}{item.cost!=null?<span>custo {item.cost}</span>:null}{item.ref?<code>{item.ref}</code>:null}</div></div>)}</div></div>}
  </section>
   </div>
  </details>
 </>;
}