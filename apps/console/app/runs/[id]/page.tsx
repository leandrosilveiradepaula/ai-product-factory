import {notFound} from "next/navigation";
import {getRunDetail} from "../../../lib/control-plane";
import {EmptyState,humanizeStatus,PageHeader,SectionHeader,StatusPill} from "../../ui";

export default async function RunDetailPage({params}:{params:Promise<{id:string}>}){
 const {id}=await params;const r=await getRunDetail(id);if(!r)notFound();
 const codexCalls=r.codex.reduce((s,x)=>s+x.invocations,0);
 return <>
  <PageHeader eyebrow="Run Detail" title={r.taskTitle} subtitle={r.projectName+" · "+r.id} actions={<><StatusPill status={r.route||"unrouted"}/><StatusPill status={r.status}/></>}/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Tentativas</span><strong>{r.attemptCount}</strong></div>
   <div className="operationalStat"><span>Avaliações</span><strong>{r.evaluations.length}</strong></div>
   <div className="operationalStat"><span>Implantações</span><strong>{r.deployments.length}</strong></div>
   <div className="operationalStat"><span>Codex</span><strong>{codexCalls}</strong></div>
  </div>
  <div className="overviewGrid">
   <section className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Execução</strong><StatusPill status={r.status}/></div>
     <div className="detailGrid">
      <div className="detailItem"><span className="detailLabel">Etapa</span><strong>{humanizeStatus(r.projectStage)}</strong></div>
      <div className="detailItem"><span className="detailLabel">Tarefa</span><strong>{humanizeStatus(r.taskStatus)}</strong></div>
      <div className="detailItem"><span className="detailLabel">Complexidade</span><strong>{humanizeStatus(r.taskComplexity)}</strong></div>
      <div className="detailItem"><span className="detailLabel">Rota</span><strong>{humanizeStatus(r.route||"unrouted")}</strong></div>
      <div className="detailItem"><span className="detailLabel">Branch</span><code>{r.branchName||"—"}</code></div>
      <div className="detailItem"><span className="detailLabel">Commit candidato</span><code>{r.candidateCommit||"—"}</code></div>
     </div>
     {r.lastError?<div className="errorText" style={{marginTop:10}}>{r.lastError}</div>:null}
    </div>
    <div className="twoCol">
     <div className="card">
      <SectionHeader title="Qualidade"/>
      <div className="compactList">{r.evaluations.length===0?<span className="muted">Nenhuma avaliação.</span>:r.evaluations.map(x=><div className="compactRow" key={x.id}><span><strong>{x.type}</strong><br/><span className="muted">{x.baselineRef||"sem linha de base"}</span></span><StatusPill status={x.status} label={humanizeStatus(x.status)+(x.score==null?"":" · "+x.score)}/></div>)}</div>
     </div>
     <div className="card">
      <SectionHeader title="Implantações"/>
      <div className="compactList">{r.deployments.length===0?<span className="muted">Nenhuma implantação.</span>:r.deployments.map(x=><div className="compactRow" key={x.id}><span><strong>{humanizeStatus(x.environment)}</strong><br/><code>{x.deploymentRef||"sem referência"}</code></span><StatusPill status={x.status}/></div>)}</div>
     </div>
    </div>
    <div className="card">
     <SectionHeader title="Trilha de auditoria" action={<span className="muted">{r.audit.length} eventos</span>}/>
     {r.audit.length===0?<EmptyState>Nenhum evento de auditoria.</EmptyState>:<div className="timeline">{r.audit.map(x=><div className="timelineItem" key={x.id}><strong>{x.eventType}</strong><div className="timelineMeta"><span>{new Date(x.createdAt).toLocaleString("pt-BR")}</span><span>{x.actorType}{x.actorRef?" · "+x.actorRef:""}</span></div></div>)}</div>}
    </div>
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Contexto</strong></div>
     <div className="compactList">
      <div className="compactRow"><span className="muted">Lease owner</span><span>{r.leaseOwner||"—"}</span></div>
      <div className="compactRow"><span className="muted">Expiração</span><span>{r.leaseExpiresAt?new Date(r.leaseExpiresAt).toLocaleString("pt-BR"):"—"}</span></div>
      <div className="compactRow"><span className="muted">Uso de ferramentas</span><span>{r.toolUsage.length}</span></div>
      <div className="compactRow"><span className="muted">Políticas Codex</span><span>{r.codex.length}</span></div>
     </div>
    </div>
    <div className="card">
     <SectionHeader title="Uso"/>
     <div className="compactList">{r.toolUsage.length===0?<span className="muted">Nenhum uso de ferramenta registrado.</span>:r.toolUsage.map(x=><div className="compactRow" key={x.id}><span><strong>{x.family}</strong><br/><span className="muted">{x.operation||"operação"}</span></span><span>{x.cost==null?"—":x.cost.toFixed(4)}</span></div>)}</div>
    </div>
    <div className="logPanel">run.id = {r.id}<br/>candidate = {r.candidateCommit||"none"}<br/>route = {r.route||"unrouted"}<br/>status = {r.status}</div>
   </aside>
  </div>
 </>;
}