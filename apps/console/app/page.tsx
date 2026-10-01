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
   actions={<StatusPill status={blocked||pending.length?"attention":"healthy"} label={blocked||pending.length?"atenção necessária":"orquestrador online"}/>}
  />

  <div className="gettingStarted" aria-label="Como usar a Factory">
   <Link className="guideStep guideStepLink" href="/projects/new">
    <span className="guideStepNumber">1</span>
    <strong>Crie ou importe um projeto</strong>
    <p>Descreva o objetivo. Para projeto existente, informe o repositório e a Factory reconcilia o estado real antes de continuar.</p>
    <span className="cardAction">Novo projeto →</span>
   </Link>
   <Link className="guideStep guideStepLink" href="/projects">
    <span className="guideStepNumber">2</span>
    <strong>A Factory trabalha e mostra o progresso</strong>
    <p>Descoberta, planejamento, implementação, revisão e testes seguem automaticamente sempre que os gates permitirem.</p>
    <span className="cardAction">Ver projetos →</span>
   </Link>
   <Link className="guideStep guideStepLink" href="/gates">
    <span className="guideStepNumber">3</span>
    <strong>Intervenha somente quando solicitado</strong>
    <p>Use “Precisa de atenção” como sua caixa de entrada. Produção continua exigindo merge humano explícito.</p>
    <span className="cardAction">Ver aprovações →</span>
   </Link>
  </div>

  <div className="overviewControlBar">
   <span className="overviewControl">Escopo <strong>{d.projects.length} projetos</strong></span>
   <span className="overviewControl">Atualização <strong>dados ao vivo</strong></span>
   <Link className="overviewControl overviewControlLink" href="/audit">Diagnósticos</Link>
  </div>

  <div className="overviewStats">
   <Link className="operationalStat operationalStatLink" href="/projects"><span>Projetos ativos</span><strong>{d.projects.length}</strong><small>{d.projects.filter(p=>p.status==="active").length} ativos · abrir portfólio →</small></Link>
   <Link className="operationalStat operationalStatLink" href="/runs"><span>Execuções ativas</span><strong>{d.activeRuns}</strong><small>{health.queuedRuns} na fila · inspecionar →</small></Link>
   <Link className="operationalStat operationalStatLink warning" href="/gates"><span>Aguardando humano</span><strong>{d.pendingGates}</strong><small>decisões pendentes · abrir →</small></Link>
   <Link className="operationalStat operationalStatLink danger" href="/runs"><span>Falhas / bloqueios</span><strong>{blocked}</strong><small>{health.expiredLeases} execuções travadas · inspecionar →</small></Link>
  </div>

  <details className="technicalDetails">
   <summary>Detalhes técnicos da operação</summary>
   <div className="technicalStats">
    <Link href="/audit"><span>Eventos de ferramenta</span><strong>{usage.toolEvents}</strong><small>registro operacional</small></Link>
    <Link href="/usage"><span>Custo conhecido</span><strong>{usage.knownCost.toFixed(4)}</strong><small>custo acumulado</small></Link>
    <Link href="/usage"><span>Codex real</span><strong>{d.codexCalls}</strong><small>invocações registradas</small></Link>
    <Link href="/usage"><span>Custo desconhecido</span><strong>{health.unknownCostEvents}</strong><small>pago · bloqueia novas chamadas</small></Link>
   </div>
  </details>

  <section className="section">
   <SectionHeader title="Precisa de atenção" action={<span className="muted">{pending.length+incidents.length} itens observados</span>}/>
   {pending.length===0&&incidents.length===0?<EmptyState>Nenhum bloqueio, falha ou gate humano pendente.</EmptyState>:<div className="attentionGrid">
    {pending.slice(0,2).map(g=><article className="card attentionCard warning" key={g.id}>
     <div className="attentionBanner"><StatusPill status={g.type}/><span className="mono">gate {g.id.slice(0,8)}</span></div>
     <h3>{g.projectName?g.projectName+" precisa de uma decisão":"Aprovação humana pendente"}</h3>
     {g.taskTitle?<p className="muted">{g.taskTitle}</p>:null}
     <p>{Array.isArray(g.reasons)?g.reasons.join(", "):String(g.reasons||"A decisão humana é necessária para continuar.")}</p>
     <div className="attentionFooter"><Link href={"/runs/"+g.runId}>execução {g.runId.slice(0,8)} →</Link><ActionLink href="/gates" variant="ghostButton">Revisar decisão</ActionLink></div>
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
