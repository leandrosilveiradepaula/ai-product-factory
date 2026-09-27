import Link from "next/link";
import {notFound} from "next/navigation";
import {getRunDetail} from "../../../lib/control-plane";

function tone(status:string){return status==="failed"?"danger":status==="awaiting_human"?"warning":status==="merged"||status==="completed"||status==="passed"?"success":""}

export default async function RunDetailPage({params}:{params:Promise<{id:string}>}){
 const {id}=await params;const r=await getRunDetail(id);if(!r)notFound();
 return <>
  <div className="pageHeader"><div><div className="eyebrow">Run Detail</div><h1 className="title">{r.taskTitle}</h1><p className="subtitle"><Link href={`/projects/${r.projectKey}`}>{r.projectName}</Link> · <span className="mono">{r.id}</span></p></div><div className="toolbar"><span className="pill">{r.route||"unrouted"}</span><span className={`pill ${tone(r.status)}`}>{r.status}</span></div></div>
  <div className="grid compact">
   <div className="card metricCard"><span className="metricLabel">Attempts</span><div className="metric">{r.attemptCount}</div><div className="metricNote">{r.leaseOwner||"no lease owner"}</div></div>
   <div className="card metricCard"><span className="metricLabel">Evaluations</span><div className="metric">{r.evaluations.length}</div><div className="metricNote">quality evidence</div></div>
   <div className="card metricCard"><span className="metricLabel">Deployments</span><div className="metric">{r.deployments.length}</div><div className="metricNote">preview / release evidence</div></div>
   <div className="card metricCard"><span className="metricLabel">Codex invocations</span><div className="metric">{r.codex.reduce((s,x)=>s+x.invocations,0)}</div><div className="metricNote">{r.codex.length} policy rows</div></div>
  </div>
  <div className="split section">
   <section className="card">
    <div className="sectionHeader"><h2>Run state</h2></div>
    <div className="detailGrid">
     <div className="detailItem"><span className="detailLabel">Project stage</span><strong>{r.projectStage}</strong></div>
     <div className="detailItem"><span className="detailLabel">Task status</span><strong>{r.taskStatus}</strong></div>
     <div className="detailItem"><span className="detailLabel">Complexity</span><strong>{r.taskComplexity}</strong></div>
     <div className="detailItem"><span className="detailLabel">Branch</span><code>{r.branchName||"—"}</code></div>
     <div className="detailItem"><span className="detailLabel">Candidate commit</span><code>{r.candidateCommit||"—"}</code></div>
     <div className="detailItem"><span className="detailLabel">Lease expires</span><strong>{r.leaseExpiresAt?new Date(r.leaseExpiresAt).toLocaleString("pt-BR"):"—"}</strong></div>
    </div>
    {r.lastError?<div className="errorText" style={{marginTop:14}}>{r.lastError}</div>:null}
   </section>
   <aside className="card"><div className="sectionHeader"><h2>Usage</h2></div><div className="valueList">{r.toolUsage.length===0?<span className="muted">No tool usage recorded.</span>:r.toolUsage.map(x=><div className="valueRow" key={x.id}><span><strong>{x.family}</strong><br/><span className="muted">{x.operation||"operation"}</span></span><span className="muted">{x.cost==null?"cost —":x.cost.toFixed(4)}</span></div>)}</div></aside>
  </div>
  <section className="section"><div className="sectionHeader"><h2>Quality & deployments</h2></div><div className="twoCol">
   <div className="card stack">{r.evaluations.length===0?<span className="muted">No evaluations.</span>:r.evaluations.map(x=><div className="valueRow" key={x.id}><span><strong>{x.type}</strong><br/><span className="muted">{x.baselineRef||"no baseline"}</span></span><span className={`pill ${tone(x.status)}`}>{x.status}{x.score==null?"":` · ${x.score}`}</span></div>)}</div>
   <div className="card stack">{r.deployments.length===0?<span className="muted">No deployments.</span>:r.deployments.map(x=><div className="valueRow" key={x.id}><span><strong>{x.environment}</strong><br/><code>{x.deploymentRef||"no ref"}</code></span><span className={`pill ${tone(x.status)}`}>{x.status}</span></div>)}</div>
  </div></section>
  <section className="section"><div className="sectionHeader"><h2>Audit trail</h2><span className="muted">{r.audit.length} events</span></div>{r.audit.length===0?<div className="emptyState">No audit events.</div>:<div className="card"><div className="timeline">{r.audit.map(x=><div className="timelineItem" key={x.id}><strong>{x.eventType}</strong><div className="timelineMeta"><span>{new Date(x.createdAt).toLocaleString("pt-BR")}</span><span>{x.actorType}{x.actorRef?` · ${x.actorRef}`:""}</span></div></div>)}</div></div>}</section>
 </>;
}