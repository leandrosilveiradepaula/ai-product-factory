import Link from "next/link";
import {getDashboard,getOperationsHealth,getUsageOverview} from "../lib/control-plane";
import {ActionLink,EmptyState,MetricCard,PageHeader,SectionHeader,StatusPill} from "./ui";

export default async function Home(){
 const [d,health,usage]=await Promise.all([getDashboard(),getOperationsHealth(),getUsageOverview()]);
 const attention=health.failedRuns+health.expiredLeases+d.pendingGates;
 return <>
  <PageHeader
   eyebrow="Visão geral da Factory"
   title="Painel de controle operacional"
   subtitle="Acompanhe o fluxo da ideia até operação, com autonomia, evidências e gates humanos onde realmente são necessários."
   actions={<><ActionLink href="/queue">Fila de trabalho</ActionLink><ActionLink href="/projects/new" variant="primary">+ Novo projeto</ActionLink></>}
  />
  <div className="kpiStrip">
   <MetricCard compact label="Projetos" value={d.projects.length} note="ativos no Control Plane"/>
   <MetricCard compact label="Execuções ativas" value={d.activeRuns} note="em execução ou fila"/>
   <MetricCard compact label="Aprovações humanas" value={d.pendingGates} note={d.pendingGates?"requerem decisão":"nenhum pendente"}/>
   <MetricCard compact label="Atenção" value={attention} note="falhas, leases ou gates"/>
   <MetricCard compact label="Custo conhecido" value={usage.knownCost.toFixed(4)} note="ledger acumulado"/>
   <MetricCard compact label="Chamadas do Codex" value={d.codexCalls} note="invocações reais"/>
  </div>
  <div className="split section">
   <section>
    <SectionHeader title="Projetos" action={<ActionLink href="/projects" variant="ghostButton">Ver todos</ActionLink>}/>
    <div className="stack">
     {d.projects.length===0?<EmptyState>Nenhum projeto registrado.</EmptyState>:d.projects.map(p=><Link href={"/projects/"+p.key} className="card projectCard" key={p.key}><div className="cardTop"><div><h3 className="cardTitle">{p.name}</h3><p className="cardMeta">{p.key}</p></div><StatusPill status={p.stage} tone="accent"/></div><div className="badgeLine" style={{marginTop:14}}><span className="status"><i className="statusDot"/>{p.status}</span><span className="muted">{new Date(p.updatedAt).toLocaleString("pt-BR")}</span></div></Link>)}
    </div>
   </section>
   <aside>
    <SectionHeader title="Saúde operacional" action={<ActionLink href="/runs" variant="ghostButton">Execuções</ActionLink>}/>
    <div className="card valueList">
     <div className="valueRow"><span className="muted">Execuções com falha</span><strong>{health.failedRuns}</strong></div>
     <div className="valueRow"><span className="muted">Leases expirados</span><strong>{health.expiredLeases}</strong></div>
     <div className="valueRow"><span className="muted">Fila de erro</span><strong>{health.deadLetterRuns}</strong></div>
     <div className="valueRow"><span className="muted">Custo pago desconhecido</span><strong>{health.unknownCostEvents}</strong></div>
     <div className="valueRow"><span className="muted">Estado</span><StatusPill status={attention?"attention":"healthy"} label={attention?"atenção":"saudável"}/></div>
    </div>
    <div className="section"><SectionHeader title="Autonomia"/></div>
    <div className="card"><div className="badgeLine"><StatusPill status="healthy" label="Determinístico primeiro"/><StatusPill status="policy" label="Provedores pagos falham de forma fechada"/><StatusPill status="policy" label="Produção exige autoridade humana"/></div><p className="muted" style={{marginBottom:0}}>A Factory segue fail-closed para providers pagos e preserva o gate humano de produção.</p></div>
   </aside>
  </div>
 </>;
}