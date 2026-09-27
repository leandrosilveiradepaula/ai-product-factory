import Link from "next/link";
import {getAuditEvents} from "../../lib/control-plane";
export default async function Audit(){
 const rows=await getAuditEvents();
 return <><div className="pageHeader"><div><div className="eyebrow">Observability</div><h1 className="title">Audit Log</h1><p className="subtitle">Trilha cronológica de ações humanas, runtime, workers e decisões persistidas.</p></div></div>
 {rows.length===0?<div className="emptyState">No audit events recorded.</div>:<div className="card"><div className="timeline">{rows.map(x=><div className="timelineItem" key={x.id}><div className="badgeLine"><span className="pill">{x.actorType}</span><strong>{x.eventType}</strong>{x.projectKey?<Link className="pill accent" href={`/projects/${x.projectKey}`}>{x.projectName}</Link>:null}</div><div className="timelineMeta"><span>{new Date(x.createdAt).toLocaleString("pt-BR")}</span>{x.actorRef?<span>{x.actorRef}</span>:null}{x.runId?<Link href={`/runs/${x.runId}`} className="mono">run {x.runId.slice(0,8)}</Link>:null}</div></div>)}</div></div>}
 </>;
}