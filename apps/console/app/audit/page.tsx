import Link from "next/link";
import {getAuditEvents} from "../../lib/control-plane";
import {EmptyState,PageHeader,StatusPill} from "../ui";

export default async function Audit(){
 const rows=await getAuditEvents();
 return <>
  <PageHeader eyebrow="Observability" title="Audit Log" subtitle="Trilha cronológica de ações humanas, runtime, workers e decisões persistidas."/>
  {rows.length===0?<EmptyState>No audit events recorded.</EmptyState>:<div className="card"><div className="timeline">{rows.map(x=><div className="timelineItem" key={x.id}><div className="badgeLine"><StatusPill status={x.actorType}/><strong>{x.eventType}</strong>{x.projectKey?<Link className="pill accent" href={"/projects/"+x.projectKey}>{x.projectName}</Link>:null}</div><div className="timelineMeta"><span>{new Date(x.createdAt).toLocaleString("pt-BR")}</span>{x.actorRef?<span>{x.actorRef}</span>:null}{x.runId?<Link href={"/runs/"+x.runId} className="mono">run {x.runId.slice(0,8)}</Link>:null}</div></div>)}</div></div>}
 </>;
}