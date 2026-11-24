import Link from "next/link";
import {portfolioProjectControlLabel,portfolioPendingReason} from "../lib/operational-health-inventory";
import {getCurrentFactoryCertificate} from "../lib/factory-certification";
import {getAuditEvents,getDashboard,getHumanGates,getOperationsHealth,getPortfolioOverview,getRuns,getUsageOverview} from "../lib/control-plane";
import {ActionLink,EmptyState,humanizeStatus,PageHeader,SectionHeader,StatusPill} from "./ui";

export default async function Home(){
 const [d,health,usage,gates,runs,audit,factoryCert,portfolio]=await Promise.all([
  getDashboard(),getOperationsHealth(),getUsageOverview(),getHumanGates(30,true),getRuns(12),getAuditEvents(12),getCurrentFactoryCertificate(),getPortfolioOverview(),
 ]);
 // Historical or superseded pending rows are not operator actions.
 const pending=gates.filter(g=>g.status==="pending"&&g.actionable);
 const trackedProjects=portfolio.projects.filter(p=>p.active&&p.controlState!=="stopped");
 const stoppedProjects=portfolio.projects.filter(p=>!p.active||p.controlState==="stopped");
 const pendingProjects=trackedProjects.filter(p=>p.pendingTasks.length>0);
 const unverifiedControls=trackedProjects.filter(p=>p.controlState==="unavailable");
 const blocked=portfolio.trackedPendingTasks;
 const recentRuns=runs.slice(0,8);
 const recentAudit=audit.slice(0,8);
 const requiresDecision=pending.length>0;
 const hasIncident=pendingProjects.length>0||health.expiredLeases>0||unverifiedControls.length>0;
 // A next-action banner is justified only by an actionable human gate.
 // The project grid already provides navigation and its empty state provides creation.
 return <>
  <PageHeader
   eyebrow="Área de trabalho"
   title="Visão geral"
   subtitle="Projetos, decisões e andamento. Os detalhes técnicos ficam disponíveis somente quando você precisar."
  />

  <section className={"factoryCertification "+factoryCert.state} aria-labelledby="factory-certification-heading">
   <div className="factoryCertificationContent">
    <span className="factoryCertificationKicker">Estado da própria Factory</span>
    <h2 id="factory-certification-heading">{factoryCert.state==="certified"?"Certificação independente aprovada":factoryCert.state==="not_certified"?"Certificação do commit atual pendente":"Certificação atual indisponível"}</h2>
    <p>{factoryCert.state==="certified"?"19 de 19 critérios aprovados no mesmo commit da main. A certificação não substitui a monitorização da operação nem comprova que outros produtos foram entregues.":factoryCert.state==="not_certified"?"Ainda não existe um certificado independente aprovado para o commit atual. Resultados de commits anteriores não são automaticamente válidos.":"Não foi possível confrontar o commit principal com o certificado do Control Plane. Não é seguro afirmar que a versão atual está certificada."}</p>
    {factoryCert.sha?<p className="factoryCertificationMeta">Commit verificado: <code>{factoryCert.sha.slice(0,12)}</code>{factoryCert.persistedAt?" · Certificado em "+new Date(factoryCert.persistedAt).toLocaleString("pt-BR",{timeZone:"America/Sao_Paulo"}):""}</p>:null}
   </div>
   <Link href="/evals" className="factoryCertificationLink">Ver evidências e testes →</Link>
  </section>

  {requiresDecision?<section className="homeFocus warning" aria-labelledby="home-decisions-heading">
   <div className="homeFocusContent">
    <h2 id="home-decisions-heading">{pending.length===1?"Uma decisão aguarda sua aprovação":pending.length+" decisões aguardam sua aprovação"}</h2>
    <p>Revise as solicitações que precisam de uma resposta para o trabalho continuar.</p>
   </div>
   <ActionLink href="/gates" variant="primary">Revisar decisões →</ActionLink>
  </section>:null}

  <section className="section homeProjects" aria-label="Seus projetos">
   <SectionHeader title="Seus projetos" action={<Link className="homeSectionLink" href="/projects">Ver portfólio completo →</Link>}/>
   {trackedProjects.length===0?
    <div className="homeEmptyProject"><EmptyState>Nenhum projeto em acompanhamento. Você pode consultar projetos parados abaixo ou cadastrar um novo.</EmptyState><ActionLink href="/projects/new" variant="primary">Novo projeto</ActionLink></div>
   :<div className="homeProjectGrid">
     {trackedProjects.map(p=><Link className="homeProjectCard" href={"/projects/"+p.key} key={p.key}>
      <div className="homeProjectHeading"><strong>{p.name}</strong><span className="homeControlLabel">{portfolioProjectControlLabel(p)}</span></div>
      <span className="homeProjectStage">{p.key==="ai-product-factory"&&factoryCert.state==="certified"?"Prontidão da Factory verificada.":<>Última etapa registrada: <b>{humanizeStatus(p.stage)}</b> · funcionamento do produto não comprovado nesta tela.</>}</span>
      {p.pendingTasks.length>0?<span className="homeOperationalNote">{p.pendingTasks.length} {p.pendingTasks.length===1?"tarefa sem encerramento confirmado":"tarefas sem encerramento confirmado"}.</span>:null}
      {p.key==="ai-product-factory"?<span className={"homeFactoryProof"+(factoryCert.state==="certified"?"":" unverified")}>{factoryCert.state==="certified"?"Certificação da Factory: "+factoryCert.passed+"/"+factoryCert.total+" no commit atual":factoryCert.state==="not_certified"?"Certificação do commit atual pendente":"Certificação do commit atual não verificável"}</span>:null}
      <span className="homeProjectFooter">Atualizado em {new Date(p.updatedAt).toLocaleString("pt-BR")} <b>Ver projeto →</b></span>
     </Link>)}
    </div>}
   {stoppedProjects.length>0?<details className="technicalDetails homeStoppedProjects"><summary>Projetos parados ou inativos ({stoppedProjects.length})</summary><div className="homeStoppedList">{stoppedProjects.map(p=><Link key={p.key} href={"/projects/"+p.key}><strong>{p.name}</strong><span>{portfolioProjectControlLabel(p)} · {p.pendingTasks.length} pendências registradas</span></Link>)}</div></details>:null}
  </section>

  <section className="homeSummary" aria-label="Resumo operacional">
   <Link href="/projects" className="homeSummaryItem"><span>Projetos em acompanhamento</span><strong>{trackedProjects.length}</strong></Link>
   <Link href="/runs" className="homeSummaryItem"><span>Execuções com reserva vigente</span><strong>{portfolio.activeLeases}</strong></Link>
   <Link href="/gates" className={pending.length?"homeSummaryItem warning":"homeSummaryItem"}><span>Decisões humanas pendentes</span><strong>{pending.length}</strong></Link>
   <Link href="/runs" className={blocked?"homeSummaryItem warning":"homeSummaryItem"}><span>Tarefas a reconciliar</span><strong>{blocked}</strong></Link>
  </section>

  <section className="section homeAttention">
   <SectionHeader title="O que precisa de atenção" action={<Link className="homeSectionLink" href="/gates">Ver aprovações humanas →</Link>}/> 
   <p className="homeOperationalNote">As pendências técnicas abaixo são agrupadas por projeto e tarefa, não por tentativa. Não equivalem a decisões suas ou falhas em execução agora. Jornadas substituídas ou encerradas permanecem no histórico.</p>
   {!requiresDecision&&!hasIncident?
    <div className="homeQuietStatus" role="status">Nenhuma decisão humana ou tarefa pendente de reconciliação foi encontrada no portfólio em acompanhamento nesta consulta. Isso não comprova a prontidão dos produtos.</div>
   :<div className="attentionGrid">
     {pending.slice(0,2).map(g=><article className="card attentionCard warning" key={g.id}>
      <div className="attentionBanner"><StatusPill status={g.type}/><span className="muted">Decisão humana</span></div>
      <h3>{g.projectName||"Projeto"} precisa de uma decisão</h3>
      {g.taskTitle?<p className="muted">{g.taskTitle}</p>:null}
      <p>{Array.isArray(g.reasons)?g.reasons.map(r=>typeof r==="string"?r:JSON.stringify(r)).join(" · "):String(g.reasons||"A decisão humana é necessária para continuar.")}</p>
      <div className="attentionFooter"><Link href={"/runs/"+g.runId}>Ver execução</Link><ActionLink href="/gates" variant="ghostButton">Revisar decisão</ActionLink></div>
     </article>)}
     {pendingProjects.map(p=>{
      const latest=p.pendingTasks[0];
      const legacy=p.pendingTasks.filter(t=>t.legacy).length;
      return <article className="card homeReconciliationCard" key={p.key}>
       <span className="homeOperationalNote">Pendência técnica registrada · {p.pendingTasks.length} {p.pendingTasks.length===1?"tarefa":"tarefas"}</span>
       <h3>{p.name}</h3>
       <p>{portfolioPendingReason(latest.error)}</p>
       <p className="homeOperationalNote">Último registro em {new Date(latest.updatedAt).toLocaleString("pt-BR",{timeZone:"America/Sao_Paulo"})}. {legacy>0?legacy+" sem jornada vinculada. ":""}Nenhuma retomada é disparada por esta consulta.</p>
       <div className="attentionFooter"><Link href={"/projects/"+p.key}>Acompanhar projeto →</Link>{latest.runId?<Link href={"/runs/"+latest.runId}>Ver última execução</Link>:null}</div>
      </article>;
     })}
     {health.expiredLeases>0?<article className="card homeReconciliationCard"><h3>{health.expiredLeases} reservas expiradas</h3><p>O histórico indica reservas de execução expiradas. Consulte o diagnóstico para verificar a recuperação.</p><Link href="/runs">Ver execuções →</Link></article>:null}
     {unverifiedControls.map(p=><article className="card homeReconciliationCard" key={"control-"+p.key}><h3>{p.name}</h3><p>Não foi possível verificar o controle de execução. Não é seguro afirmar que o projeto está em espera.</p><Link href={"/projects/"+p.key}>Ver projeto →</Link></article>)}
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
   <div className="homeTechnicalNote">{portfolio.historicalFailureRecords} registros de falha ou bloqueio no histórico completo · {portfolio.stoppedPendingTasks} tarefas sem encerramento confirmado em projetos parados/inativos · {health.queuedRuns} execuções registradas na fila · {health.expiredLeases} reservas expiradas. Valores observados no Control Plane, não prova de execução em tempo real.</div>
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
