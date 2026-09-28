import Link from "next/link";
import {getDeployments} from "../../lib/control-plane";
import {EmptyState,humanizeStatus,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Deployments(){
 const rows=await getDeployments();
 const previews=rows.filter(x=>x.environment.toLowerCase().includes("preview")).length;
 const production=rows.filter(x=>x.environment.toLowerCase().includes("production")).length;
 const ready=rows.filter(x=>["ready","success","verified","released"].includes(x.status.toLowerCase())).length;
 const failed=rows.filter(x=>["failed","error"].includes(x.status.toLowerCase())).length;
 return <>
  <PageHeader eyebrow="Implantações · Liberações" title="Implantações" subtitle="Evidências duráveis de Preview, liberação e reversão registradas pelo Control Plane."/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Previews</span><strong>{previews}</strong></div>
   <div className="operationalStat"><span>Produção</span><strong>{production}</strong></div>
   <div className="operationalStat"><span>Prontas</span><strong>{ready}</strong></div>
   <div className="operationalStat"><span>Falhas</span><strong>{failed}</strong></div>
  </div>
  <div className="overviewGrid">
   <section>
    <SectionHeader title="Histórico de implantações" action={<span className="muted">{rows.length} registros</span>}/>
    <div className="table">
     <div className="tableRow tableHeader"><span>Ambiente / Tarefa</span><span>Projeto</span><span>Estado</span><span>Referência</span></div>
     {rows.length===0?<EmptyState>Nenhuma implantação registrada.</EmptyState>:rows.map(x=><div className="tableRow" key={x.id}>
      <div><strong>{humanizeStatus(x.environment)}</strong><div><Link className="muted" href={"/runs/"+x.runId}>{x.taskTitle}</Link></div></div>
      <Link href={"/projects/"+x.projectKey}>{x.projectName}</Link>
      <StatusPill status={x.status}/>
      <div><code>{x.deploymentRef||"—"}</code>{x.rollbackRef?<div className="muted">reversão {x.rollbackRef}</div>:null}</div>
     </div>)}
    </div>
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Release policy</strong><StatusPill status="active" label="vigente"/></div>
     <div className="compactList">
      <div className="compactRow"><span className="muted">Preview</span><span>evidência exata</span></div>
      <div className="compactRow"><span className="muted">Browser</span><span>verificação obrigatória</span></div>
      <div className="compactRow"><span className="muted">Merge em main</span><span>humano</span></div>
      <div className="compactRow"><span className="muted">Release observer</span><span>somente observa</span></div>
     </div>
    </div>
    <div className="logPanel">deployments.total = {rows.length}<br/>preview.count = {previews}<br/>production.count = {production}<br/>failed.count = {failed}</div>
   </aside>
  </div>
 </>;
}