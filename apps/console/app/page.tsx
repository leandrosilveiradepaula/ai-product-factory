import Link from "next/link";
import {getDashboard,getOperationsHealth,getUsageOverview} from "../lib/control-plane";
import {ActionLink,EmptyState,humanizeStatus,PageHeader,SectionHeader,StatusPill} from "./ui";

export default async function Home(){
 const [d,health,usage]=await Promise.all([getDashboard(),getOperationsHealth(),getUsageOverview()]);
 const attention=health.failedRuns+health.expiredLeases+d.pendingGates;
 const recent=d.projects.slice(0,6);
 return <>
  <PageHeader
   eyebrow="Visão geral da Factory"
   title="Visão geral operacional"
   subtitle="Estado atual da fábrica, filas, gates, custos e evidências do ciclo de entrega."
   actions={<><ActionLink href="/queue">Fila</ActionLink><ActionLink href="/projects/new" variant="primary">+ Novo projeto</ActionLink></>}
  />

  <div className="operationalStrip">
   <div className="operationalStat"><span>Projetos ativos</span><strong>{d.projects.length}</strong></div>
   <div className="operationalStat"><span>Execuções ativas</span><strong>{d.activeRuns}</strong></div>
   <div className="operationalStat"><span>Gates pendentes</span><strong>{d.pendingGates}</strong></div>
   <div className="operationalStat"><span>Custo conhecido</span><strong>{usage.knownCost.toFixed(4)}</strong></div>
  </div>

  <div className="overviewGrid">
   <section className="card overviewPanel">
    <div className="panelHeading"><strong>Estado da fábrica</strong><StatusPill status={attention?"attention":"healthy"} label={attention?"atenção":"saudável"}/></div>
    <div className="detailGrid">
     <div className="detailItem"><span className="detailLabel">Falhas</span><strong>{health.failedRuns}</strong></div>
     <div className="detailItem"><span className="detailLabel">Leases expirados</span><strong>{health.expiredLeases}</strong></div>
     <div className="detailItem"><span className="detailLabel">Fila de erro</span><strong>{health.deadLetterRuns}</strong></div>
     <div className="detailItem"><span className="detailLabel">Custo desconhecido</span><strong>{health.unknownCostEvents}</strong></div>
    </div>
   </section>

   <aside className="card overviewPanel">
    <div className="panelHeading"><strong>Política operacional</strong><StatusPill status="active" label="ativa"/></div>
    <div className="compactList">
     <div className="compactRow"><span className="muted">Execução padrão</span><strong>Direto / API</strong></div>
     <div className="compactRow"><span className="muted">Codex</span><span>seletivo · {d.codexCalls} chamadas</span></div>
     <div className="compactRow"><span className="muted">Preview</span><span>fail-closed</span></div>
     <div className="compactRow"><span className="muted">Produção</span><span>gate humano</span></div>
    </div>
   </aside>
  </div>

  <section className="section">
   <SectionHeader title="Projetos recentes" action={<ActionLink href="/projects" variant="ghostButton">Ver todos</ActionLink>}/>
   <div className="table">
    <div className="tableRow tableHeader"><span>Projeto</span><span>Etapa</span><span>Estado</span><span>Atualização</span></div>
    {recent.length===0?<EmptyState>Nenhum projeto registrado.</EmptyState>:recent.map(p=><Link className="tableRow" href={"/projects/"+p.key} key={p.key}>
     <div><strong>{p.name}</strong><div className="muted mono">{p.key}</div></div>
     <StatusPill status={p.stage} tone="accent"/>
     <StatusPill status={p.status}/>
     <span className="muted">{new Date(p.updatedAt).toLocaleString("pt-BR")}</span>
    </Link>)}
   </div>
  </section>

  <section className="section">
   <SectionHeader title="Registro operacional" action={<ActionLink href="/audit" variant="ghostButton">Abrir auditoria</ActionLink>}/>
   <div className="logPanel">
    <div><span className="muted">factory.status</span> {attention?"ATTENTION":"HEALTHY"}</div>
    <div><span className="muted">primary.auth</span> api_key · budget bounded</div>
    <div><span className="muted">codex.invocations</span> {d.codexCalls}</div>
    <div><span className="muted">human_gates.pending</span> {d.pendingGates}</div>
    <div><span className="muted">cost.known</span> {usage.knownCost.toFixed(6)}</div>
   </div>
  </section>
 </>;
}