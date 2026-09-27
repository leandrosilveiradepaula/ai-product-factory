import Link from "next/link";
import {getDashboard,getOperationsHealth,getUsageOverview} from "../lib/control-plane";

function metric(label:string,value:string|number,note:string){return <div className="card metricCard"><span className="metricLabel">{label}</span><div className="metric">{value}</div><div className="metricNote">{note}</div></div>}

export default async function Home(){
 const [d,health,usage]=await Promise.all([getDashboard(),getOperationsHealth(),getUsageOverview()]);
 const attention=health.failedRuns+health.expiredLeases+d.pendingGates;
 return <>
  <div className="pageHeader">
   <div><div className="eyebrow">Factory Overview</div><h1 className="title">Operational control plane</h1><p className="subtitle">Acompanhe o fluxo da ideia até operação, com autonomia, evidências e gates humanos onde realmente são necessários.</p></div>
   <div className="toolbar"><Link className="secondary linkButton" href="/queue">Work Queue</Link><Link className="primary linkButton" href="/projects/new">+ New Work</Link></div>
  </div>
  <div className="kpiStrip">
   {metric("Projects",d.projects.length,"ativos no Control Plane")}
   {metric("Active runs",d.activeRuns,"em execução ou fila")}
   {metric("Human gates",d.pendingGates,d.pendingGates?"requerem decisão":"nenhum pendente")}
   {metric("Attention",attention,"falhas, leases ou gates")}
   {metric("Known cost",usage.knownCost.toFixed(4),"ledger acumulado")}
   {metric("Codex calls",d.codexCalls,"invocações reais")}
  </div>
  <div className="split section">
   <section>
    <div className="sectionHeader"><h2>Projects</h2><Link className="ghostButton" href="/projects">View all</Link></div>
    <div className="stack">
     {d.projects.length===0?<div className="emptyState">Nenhum projeto registrado.</div>:d.projects.map(p=><Link href={`/projects/${p.key}`} className="card projectCard" key={p.key}><div className="cardTop"><div><h3 className="cardTitle">{p.name}</h3><p className="cardMeta">{p.key}</p></div><span className="pill accent">{p.stage}</span></div><div className="badgeLine" style={{marginTop:14}}><span className="status"><i className="statusDot"/>{p.status}</span><span className="muted">{new Date(p.updatedAt).toLocaleString("pt-BR")}</span></div></Link>)}
    </div>
   </section>
   <aside>
    <div className="sectionHeader"><h2>Operational health</h2><Link className="ghostButton" href="/runs">Runs</Link></div>
    <div className="card valueList">
     <div className="valueRow"><span className="muted">Failed runs</span><strong>{health.failedRuns}</strong></div>
     <div className="valueRow"><span className="muted">Expired leases</span><strong>{health.expiredLeases}</strong></div>
     <div className="valueRow"><span className="muted">Dead-letter</span><strong>{health.deadLetterRuns}</strong></div>
     <div className="valueRow"><span className="muted">Unknown paid cost</span><strong>{health.unknownCostEvents}</strong></div>
     <div className="valueRow"><span className="muted">Status</span><span className={attention?"pill warning":"pill success"}>{attention?"attention":"healthy"}</span></div>
    </div>
    <div className="sectionHeader section"><h2>Autonomy</h2></div>
    <div className="card"><div className="badgeLine"><span className="pill success">Direct ready</span><span className="pill warning">Primary gated</span><span className="pill warning">Codex WIF gated</span></div><p className="muted" style={{marginBottom:0}}>A Factory segue fail-closed para providers pagos e preserva o gate humano de produção.</p></div>
   </aside>
  </div>
 </>;
}