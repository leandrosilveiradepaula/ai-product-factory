import Link from "next/link";
import {getAuditEvents,getDashboard,getHumanGates,getOperationsHealth,getRuns,getUsageOverview} from "../lib/control-plane";
import {ActionLink,EmptyState,humanizeStatus,PageHeader,SectionHeader,StatusPill} from "./ui";

export default async function Home(){
 const [d,health,usage,gates,runs,audit]=await Promise.all([getDashboard(),getOperationsHealth(),getUsageOverview(),getHumanGates(8),getRuns(12),getAuditEvents(12)]);
 const pending=gates.filter(g=>g.status==="pending");
 const blocked=health.failedRuns+health.deadLetterRuns;
 const recentRuns=runs.slice(0,8);
 const recentAudit=audit.slice(0,8);
 const incidents=health.incidents.slice(0,2);
 return <>
  <PageHeader
   eyebrow="Control Plane · sessão ativa"
   title="Visão geral da Factory"
   subtitle="Plano de controle autônomo de desenvolvimento, com evidências duráveis, execução determinística primeiro e autoridade humana na produção."
   actions={<><StatusPill status={blocked||pending.length?"attention":"healthy"} label={blocked||pending.length?"atenção necessária":"orquestrador online"}/><ActionLink href="/projects/new" variant="primary">+ Novo trabalho</ActionLink></>}
  />

  <div className="overviewStats">
   <div className="operationalStat"><span>Projetos ativos</span><strong>{d.projects.length}</strong><small>{d.projects.filter(p=>p.status==="active").length} ativos</small></div>
   <div className="operationalStat"><span>Execuções ativas</span><strong>{d.activeRuns}</strong><small>{health.queuedRuns} na fila</small></div>
   <div className="operationalStat warning"><span>Aguardando humano</span><strong>{d.pendingGates}</strong><small>gates pendentes</small></div>
   <div className="operationalStat danger"><span>Falhas / bloqueios</span><strong>{blocked}</strong><small>{health.expiredLeases} leases expirados</small></div>
   <div className="operationalStat"><span>Eventos de ferramenta</span><strong>{usage.toolEvents}</strong><small>ledger operacional</small></div>
   <div className="operationalStat"><span>Custo conhecido</span><strong>{usage.knownCost.toFixed(4)}</strong><small>custo acumulado</small></div>
   <div className="operationalStat"><span>Codex real</span><strong>{d.codexCalls}</strong><small>invocações registradas</small></div>
   <div className="operationalStat"><span>Custo desconhecido</span><strong>{health.unknownCostEvents}</strong><small>pago · fail-closed</small></div>
  </div>

  <section className="section">
   <SectionHeader title="Precisa de atenção" action={<span className="muted">{pending.length+incidents.length} itens observados</span>}/>
   {pending.length===0&&incidents.length===0?<EmptyState>Nenhum bloqueio, falha ou gate humano pendente.</EmptyState>:<div className="attentionGrid">
    {pending.slice(0,2).map(g=><article className="card attentionCard warning" key={g.id}>
     <div className="attentionBanner"><StatusPill status={g.type}/><span className="mono">gate {g.id.slice(0,8)}</span></div>
     <h3>Aprovação humana pendente</h3>
     <p>{Array.isArray(g.reasons)?g.reasons.join(", "):String(g.reasons||"A decisão humana é necessária para continuar.")}</p>
     <div className="attentionFooter"><span>execução {g.runId.slice(0,8)}</span><ActionLink href="/gates" variant="ghostButton">Abrir gate</ActionLink></div>
    </article>)}
    {incidents.map(i=><article className="card attentionCard danger" key={i.id}>
     <div className="attentionBanner"><StatusPill status={i.status}/><span className="mono">run {i.id.slice(0,8)}</span></div>
     <h3>Execução requer atenção</h3>
     <p>{i.error||"A execução está bloqueada ou excedeu a janela operacional esperada."}</p>
     <div className="attentionFooter"><span>{i.route?humanizeStatus(i.route):"sem rota"}</span><ActionLink href={"/runs/"+i.id} variant="ghostButton">Inspecionar</ActionLink></div>
    </article>)}
   </div>}
  </section>

  <section className="section">
   <SectionHeader title="Atividade da Factory" action={<ActionLink href="/runs" variant="ghostButton">Todas as execuções</ActionLink>}/>
   <div className="table factoryActivityTable">
    <div className="tableRow tableHeader"><span>Tarefa / execução</span><span>Rota</span><span>Estado</span><span>Tentativas</span><span>Commit</span></div>
    {recentRuns.length===0?<EmptyState>Nenhuma execução registrada.</EmptyState>:recentRuns.map(r=><Link className="tableRow" href={"/runs/"+r.id} key={r.id}>
     <div><strong>{r.taskTitle}</strong><div className="muted mono">{r.id.slice(0,12)}</div></div>
     <StatusPill status={r.route||"unrouted"}/>
     <StatusPill status={r.status}/>
     <span>{r.attemptCount}</span>
     <code>{r.candidateCommit?r.candidateCommit.slice(0,12):"—"}</code>
    </Link>)}
   </div>
  </section>

  <section className="section">
   <SectionHeader title="Atividade recente" action={<ActionLink href="/audit" variant="ghostButton">Abrir auditoria</ActionLink>}/>
   {recentAudit.length===0?<EmptyState>Nenhum evento recente de auditoria.</EmptyState>:<div className="card recentActivity"><div className="timeline">
    {recentAudit.map(x=><div className="timelineItem" key={x.id}><div className="badgeLine"><StatusPill status={x.actorType}/><strong>{x.eventType}</strong></div><div className="timelineMeta"><span>{new Date(x.createdAt).toLocaleString("pt-BR")}</span>{x.projectName?<span>{x.projectName}</span>:null}{x.runId?<Link href={"/runs/"+x.runId} className="mono">execução {x.runId.slice(0,8)}</Link>:null}</div></div>)}
   </div></div>}
  </section>
 </>;
}
