import Link from "next/link";
import {notFound} from "next/navigation";
import {getRunDetail} from "../../../lib/control-plane";
import {EmptyState,humanizeStatus,MetricCard,PageHeader,SectionHeader,StatusPill} from "../../ui";

export default async function RunDetailPage({params}:{params:Promise<{id:string}>}){
 const {id}=await params;const r=await getRunDetail(id);if(!r)notFound();
 return <>
  <PageHeader eyebrow="Detalhes da execução" title={r.taskTitle} subtitle={r.projectName+" · "+r.id} actions={<><StatusPill status={r.route||"unrouted"}/><StatusPill status={r.status}/></>}/>
  <div className="grid compact">
   <MetricCard label="Tentativas" value={r.attemptCount} note={r.leaseOwner||"sem responsável pelo lease"}/>
   <MetricCard label="Avaliações" value={r.evaluations.length} note="evidências de qualidade"/>
   <MetricCard label="Implantações" value={r.deployments.length} note="evidências de prévia / liberação"/>
   <MetricCard label="Invocações do Codex" value={r.codex.reduce((s,x)=>s+x.invocations,0)} note={r.codex.length+" registros de política"}/>
  </div>
  <div className="split section">
   <section className="card">
    <SectionHeader title="Estado da execução"/>
    <div className="detailGrid">
     <div className="detailItem"><span className="detailLabel">Etapa do projeto</span><strong>{humanizeStatus(r.projectStage)}</strong></div>
     <div className="detailItem"><span className="detailLabel">Estado da tarefa</span><strong>{humanizeStatus(r.taskStatus)}</strong></div>
     <div className="detailItem"><span className="detailLabel">Complexidade</span><strong>{humanizeStatus(r.taskComplexity)}</strong></div>
     <div className="detailItem"><span className="detailLabel">Branch</span><code>{r.branchName||"—"}</code></div>
     <div className="detailItem"><span className="detailLabel">Commit candidato</span><code>{r.candidateCommit||"—"}</code></div>
     <div className="detailItem"><span className="detailLabel">Lease expira em</span><strong>{r.leaseExpiresAt?new Date(r.leaseExpiresAt).toLocaleString("pt-BR"):"—"}</strong></div>
    </div>
    {r.lastError?<div className="errorText" style={{marginTop:14}}>{r.lastError}</div>:null}
   </section>
   <aside className="card"><SectionHeader title="Uso"/><div className="valueList">{r.toolUsage.length===0?<span className="muted">Nenhum uso de ferramenta registrado.</span>:r.toolUsage.map(x=><div className="valueRow" key={x.id}><span><strong>{x.family}</strong><br/><span className="muted">{x.operation||"operação"}</span></span><span className="muted">{x.cost==null?"custo —":x.cost.toFixed(4)}</span></div>)}</div></aside>
  </div>
  <section className="section"><SectionHeader title="Qualidade e implantações"/><div className="twoCol">
   <div className="card stack">{r.evaluations.length===0?<span className="muted">Nenhuma avaliação.</span>:r.evaluations.map(x=><div className="valueRow" key={x.id}><span><strong>{x.type}</strong><br/><span className="muted">{x.baselineRef||"sem baseline"}</span></span><StatusPill status={x.status} label={x.status+(x.score==null?"":" · "+x.score)}/></div>)}</div>
   <div className="card stack">{r.deployments.length===0?<span className="muted">Nenhuma implantação.</span>:r.deployments.map(x=><div className="valueRow" key={x.id}><span><strong>{x.environment}</strong><br/><code>{x.deploymentRef||"sem referência"}</code></span><StatusPill status={x.status}/></div>)}</div>
  </div></section>
  <section className="section"><SectionHeader title="Trilha de auditoria" action={<span className="muted">{r.audit.length} eventos</span>}/>{r.audit.length===0?<EmptyState>Nenhum evento de auditoria.</EmptyState>:<div className="card"><div className="timeline">{r.audit.map(x=><div className="timelineItem" key={x.id}><strong>{x.eventType}</strong><div className="timelineMeta"><span>{new Date(x.createdAt).toLocaleString("pt-BR")}</span><span>{x.actorType}{x.actorRef?" · "+x.actorRef:""}</span></div></div>)}</div></div>}</section>
 </>;
}