import Link from "next/link";
import {getEvaluations} from "../../lib/control-plane";
import {EmptyState,MetricCard,PageHeader,StatusPill} from "../ui";

export default async function Evals(){
 const rows=await getEvaluations();const passed=rows.filter(x=>["passed","success"].includes(x.status)).length;const failed=rows.filter(x=>x.status==="failed").length;
 return <>
  <PageHeader eyebrow="Quality" title="Evals" subtitle="Evidências de qualidade associadas a runs e candidatos específicos."/>
  <div className="grid compact"><MetricCard label="Evaluations" value={rows.length}/><MetricCard label="Passed" value={passed}/><MetricCard label="Failed" value={failed}/><MetricCard label="With score" value={rows.filter(x=>x.score!=null).length}/></div>
  <section className="section"><div className="table"><div className="tableRow tableHeader"><span>Evaluation / Task</span><span>Project</span><span>Status / Score</span><span>Created</span></div>{rows.length===0?<EmptyState>No evaluation evidence yet.</EmptyState>:rows.map(x=><div className="tableRow" key={x.id}><div><strong>{x.type}</strong><div><Link className="muted" href={"/runs/"+x.runId}>{x.taskTitle}</Link></div></div><Link href={"/projects/"+x.projectKey}>{x.projectName}</Link><StatusPill status={x.status} label={x.status+(x.score==null?"":" · "+x.score)}/><span className="muted">{new Date(x.createdAt).toLocaleString("pt-BR")}</span></div>)}</div></section>
 </>;
}