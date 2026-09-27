import Link from "next/link";
import {getDashboard,getOperationsHealth,getUsageOverview} from "../lib/control-plane";
import {ActionLink,EmptyState,MetricCard,PageHeader,SectionHeader,StatusPill} from "./ui";

export default async function Home(){
 const [d,health,usage]=await Promise.all([getDashboard(),getOperationsHealth(),getUsageOverview()]);
 const attention=health.failedRuns+health.expiredLeases+d.pendingGates;
 return <>
  <PageHeader
   eyebrow="Factory Overview"
   title="Operational control plane"
   subtitle="Acompanhe o fluxo da ideia até operação, com autonomia, evidências e gates humanos onde realmente são necessários."
   actions={<><ActionLink href="/queue">Work Queue</ActionLink><ActionLink href="/projects/new" variant="primary">+ New Work</ActionLink></>}
  />
  <div className="kpiStrip">
   <MetricCard compact label="Projects" value={d.projects.length} note="ativos no Control Plane"/>
   <MetricCard compact label="Active runs" value={d.activeRuns} note="em execução ou fila"/>
   <MetricCard compact label="Human gates" value={d.pendingGates} note={d.pendingGates?"requerem decisão":"nenhum pendente"}/>
   <MetricCard compact label="Attention" value={attention} note="falhas, leases ou gates"/>
   <MetricCard compact label="Known cost" value={usage.knownCost.toFixed(4)} note="ledger acumulado"/>
   <MetricCard compact label="Codex calls" value={d.codexCalls} note="invocações reais"/>
  </div>
  <div className="split section">
   <section>
    <SectionHeader title="Projects" action={<ActionLink href="/projects" variant="ghostButton">View all</ActionLink>}/>
    <div className="stack">
     {d.projects.length===0?<EmptyState>Nenhum projeto registrado.</EmptyState>:d.projects.map(p=><Link href={"/projects/"+p.key} className="card projectCard" key={p.key}><div className="cardTop"><div><h3 className="cardTitle">{p.name}</h3><p className="cardMeta">{p.key}</p></div><StatusPill status={p.stage} tone="accent"/></div><div className="badgeLine" style={{marginTop:14}}><span className="status"><i className="statusDot"/>{p.status}</span><span className="muted">{new Date(p.updatedAt).toLocaleString("pt-BR")}</span></div></Link>)}
    </div>
   </section>
   <aside>
    <SectionHeader title="Operational health" action={<ActionLink href="/runs" variant="ghostButton">Runs</ActionLink>}/>
    <div className="card valueList">
     <div className="valueRow"><span className="muted">Failed runs</span><strong>{health.failedRuns}</strong></div>
     <div className="valueRow"><span className="muted">Expired leases</span><strong>{health.expiredLeases}</strong></div>
     <div className="valueRow"><span className="muted">Dead-letter</span><strong>{health.deadLetterRuns}</strong></div>
     <div className="valueRow"><span className="muted">Unknown paid cost</span><strong>{health.unknownCostEvents}</strong></div>
     <div className="valueRow"><span className="muted">Status</span><StatusPill status={attention?"attention":"healthy"} label={attention?"attention":"healthy"}/></div>
    </div>
    <div className="section"><SectionHeader title="Autonomy"/></div>
    <div className="card"><div className="badgeLine"><StatusPill status="healthy" label="Deterministic first"/><StatusPill status="policy" label="Paid providers fail closed"/><StatusPill status="policy" label="Production requires authority"/></div><p className="muted" style={{marginBottom:0}}>A Factory segue fail-closed para providers pagos e preserva o gate humano de produção.</p></div>
   </aside>
  </div>
 </>;
}