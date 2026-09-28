import Link from "next/link";
import {getAuditEvents} from "../../lib/control-plane";
import {EmptyState,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Audit(){
 const rows=await getAuditEvents();
 const human=rows.filter(x=>x.actorType==="human"||x.actorType==="operator").length;
 const system=rows.filter(x=>x.actorType==="system").length;
 const withRun=rows.filter(x=>x.runId).length;
 return <>
  <PageHeader eyebrow="Compliance · trilha durável" title="Log de auditoria" subtitle="Eventos do Control Plane vinculados a atores, projetos, execuções e decisões operacionais." actions={<StatusPill status="healthy" label="auditoria ativa"/>}/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Eventos carregados</span><strong>{rows.length}</strong><small>janela atual</small></div>
   <div className="operationalStat"><span>Ações humanas</span><strong>{human}</strong><small>operador / humano</small></div>
   <div className="operationalStat"><span>Sistema</span><strong>{system}</strong><small>runtime e workers</small></div>
   <div className="operationalStat"><span>Ligados a run</span><strong>{withRun}</strong><small>rastreabilidade</small></div>
  </div>

  <div className="overviewGrid">
   <section>
    <SectionHeader title="Feed de auditoria" action={<span className="muted">{rows.length} registros</span>}/>
    {rows.length===0?<EmptyState>Nenhum evento de auditoria registrado.</EmptyState>:<div className="table auditTable">
     <div className="tableRow tableHeader"><span>Evento</span><span>Ator</span><span>Projeto / Execução</span><span>Horário</span></div>
     {rows.map(x=><div className="tableRow" key={x.id}>
      <div><strong>{x.eventType}</strong><div className="muted mono">{x.id.slice(0,12)}</div></div>
      <div><StatusPill status={x.actorType}/>{x.actorRef?<div className="muted">{x.actorRef}</div>:null}</div>
      <div>{x.projectKey?<Link href={"/projects/"+x.projectKey}>{x.projectName}</Link>:<span className="muted">—</span>}{x.runId?<div><Link href={"/runs/"+x.runId} className="mono muted">execução {x.runId.slice(0,8)}</Link></div>:null}</div>
      <span className="muted">{new Date(x.createdAt).toLocaleString("pt-BR")}</span>
     </div>)}
    </div>}
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Rastreabilidade</strong><StatusPill status="active" label="durável"/></div>
     <div className="compactList">
      <div className="compactRow"><span>Eventos com execução</span><strong>{withRun}</strong></div>
      <div className="compactRow"><span>Ações humanas</span><strong>{human}</strong></div>
      <div className="compactRow"><span>Ações de sistema</span><strong>{system}</strong></div>
      <div className="compactRow"><span>Fonte de verdade</span><span className="muted">Control Plane</span></div>
     </div>
    </div>
    <div className="logPanel">audit.events = {rows.length}<br/>audit.human = {human}<br/>audit.system = {system}<br/>audit.run_bound = {withRun}</div>
   </aside>
  </div>
 </>;
}
