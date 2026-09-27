import Link from "next/link";
import {getDeployments} from "../../lib/control-plane";
function tone(status:string){return status==="ready"||status==="success"||status==="verified"?"success":status==="failed"?"danger":status.includes("pending")?"warning":""}
export default async function Deployments(){
 const rows=await getDeployments();
 return <><div className="pageHeader"><div><div className="eyebrow">Delivery</div><h1 className="title">Deployments</h1><p className="subtitle">Preview, release e rollback evidence registrados pelo Control Plane.</p></div></div>
 <div className="table"><div className="tableRow tableHeader"><span>Environment / Task</span><span>Project</span><span>Status</span><span>Reference</span></div>{rows.length===0?<div className="emptyState">No deployments recorded.</div>:rows.map(x=><div className="tableRow" key={x.id}><div><strong>{x.environment}</strong><div><Link className="muted" href={`/runs/${x.runId}`}>{x.taskTitle}</Link></div></div><Link href={`/projects/${x.projectKey}`}>{x.projectName}</Link><span className={`pill ${tone(x.status)}`}>{x.status}</span><div><code>{x.deploymentRef||"—"}</code>{x.rollbackRef?<div className="muted">rollback {x.rollbackRef}</div>:null}</div></div>)}</div></>;
}