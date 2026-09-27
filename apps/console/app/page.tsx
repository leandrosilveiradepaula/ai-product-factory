import Link from "next/link";
import {getDashboard,getHumanGates,getOperationsHealth,getRuns,getUsage} from "../lib/control-plane";

function statusTone(status:string){const s=status.toLowerCase();if(s.includes("fail")||s.includes("blocked"))return"danger";if(s.includes("await")||s.includes("pending"))return"warn";if(s.includes("running")||s.includes("implement")||s.includes("preview"))return"info";if(s.includes("complete")||s.includes("merged")||s.includes("released"))return"ok";return""}
function fmt(value:string){const d=new Date(value);return Number.isNaN(d.getTime())?value:d.toLocaleString("pt-BR",{dateStyle:"short",timeStyle:"short"})}

export default async function Home(){
 const[d,health,runs,gates,usage]=await Promise.all([getDashboard(),getOperationsHealth(),getRuns(40),getHumanGates(20),getUsage(200)]);
 const waiting=gates.filter(g=>g.status==="pending").length;
 const previewReady=runs.filter(r=>r.status==="preview_ready").length;
 const awaitingRelease=runs.filter(r=>r.status==="awaiting_release").length;
 const knownCost=usage.reduce((sum,u)=>sum+(u.cost||0),0);
 const recentRuns=runs.slice(0,8);
 const incidents=health.incidents.slice(0,4);
 return <>
  <div className="page-heading">
   <div><div className="eyebrow">Factory Overview</div><h1 className="title">Control Center</h1><p>Estado operacional da fábrica, filas, gates, custos e prontidão para release.</p></div>
   <div className="toolbar"><span className="chip"><i/> Control Plane live</span><Link className="secondary" href="/projects/new">New Work</Link></div>
  </div>
  <div className="metric-grid">
   <div className="metric-card"><div className="metric-label">Active Projects</div><div className="metric-value">{d.projects.filter(p=>p.status==="active").length}</div><div className="metric-foot">Control Plane</div></div>
   <div className="metric-card"><div className="metric-label">Running Jobs</div><div className="metric-value">{d.activeRuns}</div><div className="metric-foot">{health.queuedRuns} queued</div></div>
   <div className="metric-card"><div className="metric-label">Waiting for Human</div><div className="metric-value">{waiting}</div><div className="metric-foot">{awaitingRelease} awaiting release</div></div>
   <div className="metric-card"><div className="metric-label">Failed / Blocked</div><div className="metric-value">{health.failedRuns}</div><div className="metric-foot">{health.deadLetterRuns} dead-letter</div></div>
   <div className="metric-card"><div className="metric-label">Preview Ready</div><div className="metric-value">{previewReady}</div><div className="metric-foot">verified preview queue</div></div>
   <div className="metric-card"><div className="metric-label">Codex Calls</div><div className="metric-value">{d.codexCalls}</div><div className="metric-foot">durable ledger</div></div>
   <div className="metric-card"><div className="metric-label">Model Calls</div><div className="metric-value">{d.modelCalls}</div><div className="metric-foot">observed usage</div></div>
   <div className="metric-card"><div className="metric-label">Known Spend</div><div className="metric-value">{knownCost.toFixed(4)}</div><div className="metric-foot">{health.unknownCostEvents} unknown paid-cost events</div></div>
  </div>
  <div className="split">
   <section className="panel">
    <div className="panel-header"><div><h2>Factory Activity</h2><p>Runs mais recentes registrados no Control Plane.</p></div><Link href="/runs" className="secondary">View all</Link></div>
    {recentRuns.length===0?<div className="empty">The Factory is currently idle.</div>:<table className="data-table"><thead><tr><th>Work item</th><th>Route</th><th>Status</th><th>Attempts</th><th>Updated</th></tr></thead><tbody>
     {recentRuns.map(r=><tr key={r.id}><td><Link className="cell-title" href={"/runs/"+r.id}>{r.taskTitle}</Link><div className="cell-sub mono">{r.id.slice(0,8)}</div></td><td><span className="pill">{r.route||"unrouted"}</span></td><td><span className={"status-badge "+statusTone(r.status)}>{r.status}</span></td><td>{r.attemptCount}</td><td>{fmt(r.createdAt)}</td></tr>)}
    </tbody></table>}
   </section>
   <section className="panel">
    <div className="panel-header"><div><h2>Needs Attention</h2><p>Somente condições que exigem ação ou investigação.</p></div></div>
    <div className="panel-body stack">
     {waiting===0&&incidents.length===0?<div className="empty">All human decisions are resolved.</div>:null}
     {waiting>0?<div className="attention-card"><h3>{waiting} human gate{waiting===1?"":"s"} pending</h3><p>Review required before the affected work can continue.</p><div className="actions" style={{marginTop:8}}><Link className="secondary" href="/decisions">Open gates</Link></div></div>:null}
     {incidents.map(i=><div className="attention-card danger" key={i.id}><h3>{i.status} · {i.route||"unrouted"}</h3><p>{i.error||"Operational incident recorded without additional error detail."}</p><div className="cell-sub mono">{i.id.slice(0,8)} · attempts {i.attempts}</div></div>)}
    </div>
   </section>
  </div>
  <section className="panel">
   <div className="panel-header"><div><h2>Projects</h2><p>Produtos e repositórios sob controle da Factory.</p></div><Link className="secondary" href="/projects">Portfolio</Link></div>
   <table className="data-table"><thead><tr><th>Project</th><th>Stage</th><th>Status</th><th>Updated</th></tr></thead><tbody>
    {d.projects.map(p=><tr key={p.key}><td><Link href={"/projects/"+p.key} className="cell-title">{p.name}</Link><div className="cell-sub mono">{p.key}</div></td><td><span className="pill">{p.stage}</span></td><td><span className={"status-badge "+(p.status==="active"?"ok":"")}>{p.status}</span></td><td>{fmt(p.updatedAt)}</td></tr>)}
   </tbody></table>
  </section>
 </>;
}