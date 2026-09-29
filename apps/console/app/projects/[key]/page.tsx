import {notFound} from "next/navigation";
import {getProjectDatabases,getProjectDetail,getProjectExecutionTeamPlan,getProjectOperations,getProjectStateContext} from "../../../lib/control-plane";
import {ActionLink,EmptyState,humanizeStatus,MetricCard,PageHeader,SectionHeader,StatusPill} from "../../ui";

const stages=["discovery","specification","planning","implementation","review","validation","preview","human_gate","release","operations"];
const stageLabels=["Descoberta","Especificação","Plano","Implementação","Revisão","Testes / Avaliações","Prévia","Aprovação","Liberação","Operação"];
function progress(stage:string){const i=stages.indexOf(stage);return i<0?0:Math.round(((i+1)/stages.length)*100)}
function display(value:unknown){return typeof value==="string"?value:JSON.stringify(value)}

export default async function Project({params}:{params:Promise<{key:string}>}){
 const {key}=await params;const p=await getProjectDetail(key);if(!p)notFound();const [ops,state,databases,teamPlan]=await Promise.all([getProjectOperations(p.id),getProjectStateContext(p.id),getProjectDatabases(p.id),getProjectExecutionTeamPlan(p.id)]);const activeTasks=p.tasks.filter(t=>!["completed","cancelled"].includes(t.status));
 return <>
  <PageHeader eyebrow="Detalhes do projeto" title={p.name} subtitle={p.repository||p.key} actions={<><StatusPill status={p.stage} tone="accent"/><ActionLink href="/queue">Fila de trabalho</ActionLink></>}/>
  <div className="lifecycleRail" aria-label="Ciclo do produto"><span className="lifecycleIdea done">Ideia</span>{stageLabels.map((label,i)=><span key={label} className={i<stages.indexOf(p.stage)?"done":i===stages.indexOf(p.stage)?"current":""}>{label}</span>)}</div>
  <div className="grid compact">
   <MetricCard label="Ciclo de vida" value={progress(p.stage)+"%"} note={<div className="progressTrack"><div className="progressFill" style={{width:progress(p.stage)+"%"}}/></div>}/>
   <MetricCard label="Tarefas abertas" value={activeTasks.length} note={p.tasks.length+" no total"}/>
   <MetricCard label="Custo conhecido" value={ops.estimatedCost.toFixed(4)} note={ops.usageUnits+" unidades de uso"}/>
   <MetricCard label="Evidências" value={ops.evaluations+ops.deployments} note={ops.evaluations+" avaliações · "+ops.deployments+" implantações"}/>
  </div>
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
  <section className="section"><SectionHeader title="Bancos de dados" action={<span className="muted">{databases.length} integração{databases.length===1?"":"ões"}</span>}/>
   {databases.length===0?<EmptyState>Nenhum banco foi vinculado a este projeto. A Factory pode registrar um banco existente ou preparar o provisionamento de um novo banco, sujeito aos gates aplicáveis.</EmptyState>:<div className="table">
    <div className="tableRow tableHeader"><span>Banco</span><span>Acesso</span><span>Estado</span><span>Verificação</span></div>
    {databases.map(db=><div className="tableRow" key={db.id}>
     <div><strong>{db.provider==="supabase"?"Supabase":db.provider}</strong><div className="muted mono">{db.projectRef||"project_ref pendente"} · {db.environment}</div></div>
     <div><StatusPill status={db.permissionMode} label={db.permissionMode==="read"?"Somente leitura":db.permissionMode==="read_write"?"Leitura e escrita":"Não configurado"}/><div className="muted">{db.accessMode==="oauth"?"OAuth":db.accessMode==="management_api"?"Management API":"Conexão pendente"}</div></div>
     <StatusPill status={db.status} label={db.status==="pending_access"?"Aguardando conexão":db.status==="ready_read"?"Leitura verificada":db.status==="ready_write"?"Escrita verificada":humanizeStatus(db.status)}/>
     <span className="muted">{db.lastVerifiedAt?new Date(db.lastVerifiedAt).toLocaleString("pt-BR"):"Ainda não verificado"}</span>
    </div>)}
   </div>}
   {databases.some(db=>db.status==="pending_access")?<div className="card" style={{marginTop:12}}><strong>Próxima ação</strong><p className="muted">Conecte o Supabase com acesso mínimo. A Factory valida a identidade do projeto e uma consulta somente leitura antes de considerar o banco pronto. Nenhuma credencial é exibida nesta tela.</p></div>:null}
  </section>
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
      <div className="panelHeading"><strong>{agent.role}</strong><StatusPill status="active" label={agent.workers_planned+" worker"+(agent.workers_planned===1?"":"s")}/></div>
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
 </>;
}