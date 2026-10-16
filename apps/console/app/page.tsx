import Link from "next/link";
import {isProviderCreditExhausted} from "../lib/operational-health-inventory";
import {getAuditEvents,getDashboard,getHumanGates,getOperationsHealth,getRuns,getUsageOverview} from "../lib/control-plane";
import {ActionLink,EmptyState,humanizeStatus,PageHeader,SectionHeader,StatusPill} from "./ui";

export default async function Home(){
 const [d,health,usage,gates,runs,audit]=await Promise.all([
  getDashboard(),getOperationsHealth(),getUsageOverview(),getHumanGates(30,true),getRuns(12),getAuditEvents(12),
 ]);
 // Historical or superseded pending rows are not operator actions.
 const pending=gates.filter(g=>g.status==="pending"&&g.actionable);
 const incidents=health.incidents.slice(0,2);
 const blocked=health.failedRuns+health.blockedRuns;
 const recentRuns=runs.slice(0,8);
 const recentAudit=audit.slice(0,8);
 const requiresDecision=pending.length>0;
 const hasIncident=incidents.length>0;
 const overviewAction=requiresDecision
  ?{heading:"Você tem decisões pendentes",description:"Existem aprovações humanas aguardando uma resposta. Revise cada motivo antes de decidir.",href:"/gates",label:"Abrir aprovações",kind:"warning"}
  :hasIncident
   ?{heading:"Existem ocorrências para investigar",description:"A Factory registrou um problema operacional. Consulte a execução e a evidência antes de intervir.",href:"/runs",label:"Ver execuções",kind:"warning"}
   :d.projects.length===0
    ?{heading:"Comece pelo primeiro projeto",description:"Descreva o produto que deseja desenvolver ou importe um projeto já existente.",href:"/projects/new",label:"Criar ou importar projeto",kind:"neutral"}
    :{heading:"Seus projetos estão no centro do trabalho",description:"Acompanhe a etapa de cada produto. Você só precisa intervir quando houver uma aprovação ou dependência explícita.",href:"/projects",label:"Ver todos os projetos",kind:"neutral"};
 return <>
  <PageHeader
   eyebrow="Área de trabalho"
   title="Visão geral"
   subtitle="Projetos, decisões e andamento. Os detalhes técnicos ficam disponíveis somente quando você precisar."
  />

  <section className={"homeFocus "+overviewAction.kind} aria-label="Próximo passo">
   <div className="homeFocusContent">
    <span className="homeFocusEyebrow">Onde começar</span>
    <h2>{overviewAction.heading}</h2>
    <p>{overviewAction.description}</p>
   </div>
   <ActionLink href={overviewAction.href} variant={requiresDecision||d.projects.length===0?"primary":"secondary"}>{overviewAction.label} →</ActionLink>
  </section>

  <section className="section homeProjects" aria-label="Seus projetos">
   <SectionHeader title="Seus projetos" action={<Link className="homeSectionLink" href="/projects">Ver portfólio completo →</Link>}/>
   {d.projects.length===0?
    <div className="homeEmptyProject"><EmptyState>Nenhum projeto cadastrado. Você pode começar com uma ideia ou importar um repositório existente.</EmptyState><ActionLink href="/projects/new" variant="primary">Novo projeto</ActionLink></div>
   :<div className="homeProjectGrid">
     {d.projects.slice(0,4).map(p=><Link className="homeProjectCard" href={"/projects/"+p.key} key={p.key}>
      <div className="homeProjectHeading"><strong>{p.name}</strong><StatusPill status={p.status}/></div>
      <span className="homeProjectStage">Etapa registrada: <b>{humanizeStatus(p.stage)}</b></span>
      <span className="homeProjectFooter">Atualizado em {new Date(p.updatedAt).toLocaleString("pt-BR")} <b>Ver projeto →</b></span>
     </Link>)}
    </div>}
  </section>

  <div className="homeSummary" aria-label="Resumo operacional">
   <Link href="/projects" className="homeSummaryItem"><span>Projetos no portfólio</span><strong>{d.projects.length}</strong></Link>
   <Link href="/runs" className="homeSummaryItem"><span>Execuções em andamento</span><strong>{d.activeRuns}</strong></Link>
   <Link href="/gates" className={d.pendingGates?"homeSummaryItem warning":"homeSummaryItem"}><span>Aprovações registradas como pendentes</span><strong>{d.pendingGates}</strong></Link>
   <Link href="/runs" className={blocked?"homeSummaryItem warning":"homeSummaryItem"}><span>Falhas / fila de erro</span><strong>{blocked}</strong></Link>
  </div>

  <section className="section homeAttention">
   <SectionHeader title="Acompanhamento de atenção" action={<Link className="homeSectionLink" href="/gates">Abrir todas as aprovações →</Link>}/>
   {!requiresDecision&&!hasIncident?
    <div className="homeQuietStatus" role="status">Nenhuma decisão humana acionável ou ocorrência recente foi encontrada nesta consulta. O acompanhamento dos demais bloqueios continua nas telas de cada projeto.</div>
   :<div className="attentionGrid">
     {pending.slice(0,2).map(g=><article className="card attentionCard warning" key={g.id}>
      <div className="attentionBanner"><StatusPill status={g.type}/><span className="muted">Decisão humana</span></div>
      <h3>{g.projectName||"Projeto"} precisa de uma decisão</h3>
      {g.taskTitle?<p className="muted">{g.taskTitle}</p>:null}
      <p>{Array.isArray(g.reasons)?g.reasons.map(r=>typeof r==="string"?r:JSON.stringify(r)).join(" · "):String(g.reasons||"A decisão humana é necessária para continuar.")}</p>
      <div className="attentionFooter"><Link href={"/runs/"+g.runId}>Ver execução</Link><ActionLink href="/gates" variant="ghostButton">Revisar decisão</ActionLink></div>
     </article>)}
     {incidents.map(i=><article className="card attentionCard danger" key={i.id}>
      <div className="attentionBanner"><StatusPill status={i.status}/><span className="muted">Ocorrência operacional</span></div>
      <h3>{isProviderCreditExhausted(i.error)?"Execução bloqueada por crédito da API":"Execução exige investigação"}</h3>
      <p>{isProviderCreditExhausted(i.error)?"A API OpenAI recusou esta tentativa por crédito insuficiente. O registro é histórico e não comprova o saldo atual. Verifique o faturamento do provedor antes de solicitar recuperação auditada; o teto interno da Factory não adiciona créditos.":i.error||"O processo ultrapassou a janela esperada ou registrou um bloqueio."}</p>
      <div className="attentionFooter"><span>{i.route?humanizeStatus(i.route):"Sem rota"}</span><ActionLink href={"/runs/"+i.id} variant="ghostButton">Ver execução</ActionLink></div>
     </article>)}
    </div>}
  </section>

  <details className="technicalDetails homeTechnicalDetails">
   <summary>Indicadores técnicos e custos</summary>
   <div className="technicalStats">
    <Link href="/audit"><span>Eventos de ferramenta</span><strong>{usage.toolEvents}</strong><small>Registros auditados</small></Link>
    <Link href="/usage"><span>Custo conhecido (USD)</span><strong>{usage.knownCost.toFixed(4)}</strong><small>Acumulado observado</small></Link>
    <Link href="/usage"><span>Codex real</span><strong>{d.codexCalls}</strong><small>Invocações registradas</small></Link>
    <Link href="/usage"><span>Custo desconhecido</span><strong>{health.unknownCostEvents}</strong><small>Bloqueia novas chamadas pagas</small></Link>
   </div>
   <div className="homeTechnicalNote">{health.queuedRuns} execuções registradas na fila · {health.expiredLeases} leases expirados. Valores do Control Plane, não prova de execução em tempo real.</div>
  </details>

  <details className="overviewActivityDetails">
   <summary><span><strong>Atividade técnica recente</strong><small>Execuções, SHAs e auditoria para investigação.</small></span><span className="muted">{recentRuns.length} execuções · {recentAudit.length} eventos</span></summary>
   <div className="overviewActivityBody">
    <section className="section">
     <SectionHeader title="Execuções recentes" action={<ActionLink href="/runs" variant="ghostButton">Todas as execuções</ActionLink>}/>
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
     <SectionHeader title="Auditoria recente" action={<ActionLink href="/audit" variant="ghostButton">Abrir auditoria</ActionLink>}/>
     {recentAudit.length===0?<EmptyState>Nenhum evento recente de auditoria.</EmptyState>:<div className="card recentActivity"><div className="timeline">
      {recentAudit.map(x=><div className="timelineItem" key={x.id}><div className="badgeLine"><StatusPill status={x.actorType}/><strong>{x.eventType}</strong></div><div className="timelineMeta"><span>{new Date(x.createdAt).toLocaleString("pt-BR")}</span>{x.projectName?<span>{x.projectName}</span>:null}{x.runId?<Link href={"/runs/"+x.runId} className="mono">execução {x.runId.slice(0,8)}</Link>:null}</div></div>)}
     </div></div>}
    </section>
   </div>
  </details>
 </>;
}
