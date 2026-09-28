import Link from "next/link";
import {getAuditEvents} from "../../lib/control-plane";
import {EmptyState,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Audit(){
 const rows=await getAuditEvents();
 const human=rows.filter(x=>x.actorType==="human"||x.actorType==="operator").length;
 const system=rows.filter(x=>x.actorType==="system").length;
 const withRun=rows.filter(x=>x.runId).length;
 return <>
  <PageHeader eyebrow="Audit Log" title="Log de auditoria" subtitle="Trilha cronológica e imutável de ações humanas, runtime, workers e decisões persistidas."/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Eventos</span><strong>{rows.length}</strong></div>
   <div className="operationalStat"><span>Humanos</span><strong>{human}</strong></div>
   <div className="operationalStat"><span>Sistema</span><strong>{system}</strong></div>
   <div className="operationalStat"><span>Com execução</span><strong>{withRun}</strong></div>
  </div>
  <section>
   <SectionHeader title="Eventos recentes" action={<span className="muted">{rows.length} registros</span>}/>
   {rows.length===0?<EmptyState>Nenhum evento de auditoria registrado.</EmptyState>:<div className="table">
    <div className="tableRow tableHeader"><span>Evento</span><span>Ator</span><span>Projeto / Execução</span><span>Horário</span></div>
    {rows.map(x=><div className="tableRow" key={x.id}>
     <div><strong>{x.eventType}</strong></div>
     <div><StatusPill status={x.actorType}/>{x.actorRef?<div className="muted">{x.actorRef}</div>:null}</div>
     <div>{x.projectKey?<Link href={"/projects/"+x.projectKey}>{x.projectName}</Link>:<span className="muted">—</span>}{x.runId?<div><Link href={"/runs/"+x.runId} className="mono muted">execução {x.runId.slice(0,8)}</Link></div>:null}</div>
     <span className="muted">{new Date(x.createdAt).toLocaleString("pt-BR")}</span>
    </div>)}
   </div>}
  </section>
  <section className="section"><div className="logPanel">audit.events = {rows.length}<br/>audit.human = {human}<br/>audit.system = {system}<br/>audit.run_bound = {withRun}</div></section>
 </>;
}