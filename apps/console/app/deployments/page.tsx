import Link from "next/link";
import {getDeployments} from "../../lib/control-plane";
import {EmptyState,humanizeStatus,PageHeader,StatusPill} from "../ui";

export default async function Deployments(){
 const rows=await getDeployments();
 return <>
  <PageHeader eyebrow="Entrega" title="Implantações" subtitle="Evidências de prévia, liberação e reversão registradas pelo Painel de Controle."/>
  <div className="table"><div className="tableRow tableHeader"><span>Ambiente / Tarefa</span><span>Projeto</span><span>Estado</span><span>Referência</span></div>{rows.length===0?<EmptyState>Nenhuma implantação registrada.</EmptyState>:rows.map(x=><div className="tableRow" key={x.id}><div><strong>{humanizeStatus(x.environment)}</strong><div><Link className="muted" href={"/runs/"+x.runId}>{x.taskTitle}</Link></div></div><Link href={"/projects/"+x.projectKey}>{x.projectName}</Link><StatusPill status={x.status}/><div><code>{x.deploymentRef||"—"}</code>{x.rollbackRef?<div className="muted">reversão {x.rollbackRef}</div>:null}</div></div>)}</div>
 </>;
}