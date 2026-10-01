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
  <PageHeader eyebrow="Liberação · ambientes" title="Implantações" subtitle="Histórico de Prévia e produção registrado pela Factory. Use para confirmar qual versão foi implantada e se a verificação terminou." actions={<StatusPill status={failed?"attention":"healthy"} label={failed?"falhas observadas":"ambientes saudáveis"}/>}/>
  <div className="deploymentEnvGrid">
   <div className="card envCard"><span className="detailLabel">Preview</span><strong>{previews}</strong><p className="muted">candidatos observados</p></div>
   <div className="card envCard"><span className="detailLabel">Produção</span><strong>{production}</strong><p className="muted">registros duráveis</p></div>
   <div className="card envCard"><span className="detailLabel">Prontas / verificadas</span><strong>{ready}</strong><p className="muted">estado positivo</p></div>
   <div className="card envCard danger"><span className="detailLabel">Falhas</span><strong>{failed}</strong><p className="muted">requerem atenção</p></div>
  </div>

  <div className="overviewGrid section">
   <section>
    <SectionHeader title="Histórico de implantações" action={<span className="muted">{rows.length} registros</span>}/>
    <div className="table deploymentTable">
     <div className="tableRow tableHeader"><span>Ambiente / Tarefa</span><span>Projeto</span><span>Estado</span><span>Referência</span><span>Data</span></div>
     {rows.length===0?<EmptyState>Nenhuma implantação registrada.</EmptyState>:rows.map(x=><div className="tableRow" key={x.id}>
      <div><strong>{humanizeStatus(x.environment)}</strong><div><Link className="muted" href={"/runs/"+x.runId}>{x.taskTitle}</Link></div></div>
      <Link href={"/projects/"+x.projectKey}>{x.projectName}</Link>
      <StatusPill status={x.status}/>
      <div><code>{x.deploymentRef||"—"}</code>{x.rollbackRef?<div className="muted">reversão {x.rollbackRef}</div>:null}</div>
      <span className="muted">{new Date(x.deployedAt||x.createdAt).toLocaleString("pt-BR")}</span>
     </div>)}
    </div>
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Como uma versão chega à produção</strong><StatusPill status="active" label="vigente"/></div>
     <div className="compactList">
      <div className="compactRow"><span>Preview exato</span><span className="muted">mesmo SHA</span></div>
      <div className="compactRow"><span>Verificação no navegador</span><span className="muted">obrigatória</span></div>
      <div className="compactRow"><span>Merge em main</span><span className="muted">humano</span></div>
      <div className="compactRow"><span>Observer de release</span><span className="muted">somente leitura</span></div>
     </div>
    </div>
    <div className="logPanel">deployments.total = {rows.length}<br/>preview.count = {previews}<br/>production.count = {production}<br/>failed.count = {failed}</div>
   </aside>
  </div>
 </>;
}
