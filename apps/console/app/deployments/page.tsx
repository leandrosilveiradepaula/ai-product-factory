import Link from "next/link";
import {getDeployments} from "../../lib/control-plane";
import {EmptyState,PageHeader,StatusPill} from "../ui";

export default async function Deployments(){
 const rows=await getDeployments();
 return <>
  <PageHeader eyebrow="Delivery" title="Deployments" subtitle="Preview, release e rollback evidence registrados pelo Control Plane."/>
  <div className="table"><div className="tableRow tableHeader"><span>Environment / Task</span><span>Project</span><span>Status</span><span>Reference</span></div>{rows.length===0?<EmptyState>No deployments recorded.</EmptyState>:rows.map(x=><div className="tableRow" key={x.id}><div><strong>{x.environment}</strong><div><Link className="muted" href={"/runs/"+x.runId}>{x.taskTitle}</Link></div></div><Link href={"/projects/"+x.projectKey}>{x.projectName}</Link><StatusPill status={x.status}/><div><code>{x.deploymentRef||"—"}</code>{x.rollbackRef?<div className="muted">rollback {x.rollbackRef}</div>:null}</div></div>)}</div>
 </>;
}