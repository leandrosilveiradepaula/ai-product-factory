import Link from "next/link";
import {getEvaluations} from "../../lib/control-plane";
import {EmptyState,humanizeStatus,MetricCard,PageHeader,StatusPill} from "../ui";

export default async function Evals(){
 const rows=await getEvaluations();const passed=rows.filter(x=>["passed","success"].includes(x.status)).length;const failed=rows.filter(x=>x.status==="failed").length;
 return <>
  <PageHeader eyebrow="Qualidade" title="Avaliações" subtitle="Evidências de qualidade associadas a execuções e candidatos específicos."/>
  <div className="grid compact"><MetricCard label="Avaliações" value={rows.length}/><MetricCard label="Aprovadas" value={passed}/><MetricCard label="Falharam" value={failed}/><MetricCard label="Com pontuação" value={rows.filter(x=>x.score!=null).length}/></div>
  <section className="section"><div className="table"><div className="tableRow tableHeader"><span>Avaliação / Tarefa</span><span>Projeto</span><span>Estado / Pontuação</span><span>Criada em</span></div>{rows.length===0?<EmptyState>Ainda não há evidências de avaliação.</EmptyState>:rows.map(x=><div className="tableRow" key={x.id}><div><strong>{x.type}</strong><div><Link className="muted" href={"/runs/"+x.runId}>{x.taskTitle}</Link></div></div><Link href={"/projects/"+x.projectKey}>{x.projectName}</Link><StatusPill status={x.status} label={humanizeStatus(x.status)+(x.score==null?"":" · "+x.score)}/><span className="muted">{new Date(x.createdAt).toLocaleString("pt-BR")}</span></div>)}</div></section>
 </>;
}