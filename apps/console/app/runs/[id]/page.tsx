import Link from "next/link";
import {notFound} from "next/navigation";
import {getRunDetail} from "../../../lib/control-plane";
import {EmptyState,MetricCard,PageHeader,SectionHeader,StatusPill} from "../../ui";

export default async function RunDetailPage({params}:{params:Promise<{id:string}>}){
 const {id}=await params;const r=await getRunDetail(id);if(!r)notFound();
 return <>
  <PageHeader eyebrow="Run Detail" title={r.taskTitle} subtitle={r.projectName+" · "+r.id} actions={<><StatusPill status={r.route||"unrouted"}/><StatusPill status={r.status}/></>}/>
  <div className="grid compact">
   <MetricCard label="Attempts" value={r.attemptCount} note={r.leaseOwner||"no lease owner"}/>
   <MetricCard label="Evaluations" value={r.evaluations.length} note="quality evidence"/>
   <MetricCard label="Deployments" value={r.deployments.length} note="preview / release evidence"/>
   <MetricCard label="Codex invocations" value={r.codex.reduce((s,x)=>s+x.invocations,0)} note={r.codex.length+" policy rows"}/>
  </div>
  <div className="split section">
   <section className="card">
    <SectionHeader title="Run state"/>
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
   <aside className="card"><SectionHeader title="Usage"/><div className="valueList">{r.toolUsage.length===0?<span className="muted">No tool usage recorded.</span>:r.toolUsage.map(x=><div className="valueRow" key={x.id}><span><strong>{x.family}</strong><br/><span className="muted">{x.operation||"operation"}</span></span><span className="muted">{x.cost==null?"cost —":x.cost.toFixed(4)}</span></div>)}</div></aside>
  </div>
  <section className="section"><SectionHeader title="Quality & deployments"/><div className="twoCol">
   <div className="card stack">{r.evaluations.length===0?<span className="muted">No evaluations.</span>:r.evaluations.map(x=><div className="valueRow" key={x.id}><span><strong>{x.type}</strong><br/><span className="muted">{x.baselineRef||"no baseline"}</span></span><StatusPill status={x.status} label={x.status+(x.score==null?"":" · "+x.score)}/></div>)}</div>
   <div className="card stack">{r.deployments.length===0?<span className="muted">No deployments.</span>:r.deployments.map(x=><div className="valueRow" key={x.id}><span><strong>{x.environment}</strong><br/><code>{x.deploymentRef||"no ref"}</code></span><StatusPill status={x.status}/></div>)}</div>
  </div></section>
  <section className="section"><SectionHeader title="Audit trail" action={<span className="muted">{r.audit.length} events</span>}/>{r.audit.length===0?<EmptyState>No audit events.</EmptyState>:<div className="card"><div className="timeline">{r.audit.map(x=><div className="timelineItem" key={x.id}><strong>{x.eventType}</strong><div className="timelineMeta"><span>{new Date(x.createdAt).toLocaleString("pt-BR")}</span><span>{x.actorType}{x.actorRef?" · "+x.actorRef:""}</span></div></div>)}</div></div>}</section>
 </>;
}