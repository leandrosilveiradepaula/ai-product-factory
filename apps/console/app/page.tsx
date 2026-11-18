import Link from "next/link";
import {getDashboard,getGitHubAppInstallActions,getHumanGates,getOperationsHealth,getUsageOverview} from "../lib/control-plane";
import {getGitHubAppStatus} from "../lib/github-app";
import {operatorStageLabel,summarizeOperatorAttention} from "../lib/operator-home";
import {PageHeader,SectionHeader} from "./ui";

/** Home is an operator workspace, not a console for internal subsystems.
 * All actions link to existing governed flows. No mutation occurs here. */
export default async function Home(){
 const [dashboard,gates,installations,app,health,usage]=await Promise.all([
  getDashboard(),getHumanGates(100,true),getGitHubAppInstallActions(),
  getGitHubAppStatus(),getOperationsHealth(),getUsageOverview(),
 ]);
 const attention=summarizeOperatorAttention(gates,installations,app.configured);
 const historicalProblems=health.failedRuns+health.blockedRuns;
 return <>
  <PageHeader eyebrow="Início" title="Sua área de trabalho"
   subtitle="Diga o que você quer desenvolver. A Factory organiza o trabalho e avisa quando uma decisão sua for necessária."/>

  <section className="operatorWelcome" aria-labelledby="operator-start-heading">
   <div className="operatorWelcomeHeading">
    <span className="operatorEyebrow">COMECE POR AQUI</span>
    <h2 id="operator-start-heading">O que você quer fazer agora?</h2>
    <p>Escolha uma opção. Você não precisa conhecer agentes, filas ou ferramentas técnicas para começar.</p>
   </div>
   <div className="operatorChoices">
    <Link prefetch={false} href="/projects/new" className="operatorChoice featured">
     <span className="operatorChoiceSymbol" aria-hidden="true">＋</span>
     <strong>Criar um produto</strong>
     <span>Tenho uma ideia e quero que a Factory a transforme em produto.</span>
     <b>Descrever minha ideia <span aria-hidden="true">→</span></b>
    </Link>
    <Link prefetch={false} href="/projects" className="operatorChoice">
     <span className="operatorChoiceSymbol" aria-hidden="true">✎</span>
     <strong>Melhorar um produto</strong>
     <span>Quero corrigir algo, acrescentar uma função ou solicitar outra evolução.</span>
     <b>Escolher o produto <span aria-hidden="true">→</span></b>
    </Link>
    <Link prefetch={false} href="/deliveries" className="operatorChoice">
     <span className="operatorChoiceSymbol" aria-hidden="true">◎</span>
     <strong>Acompanhar entregas</strong>
     <span>Quero ver o quadro de trabalho, identificar bloqueios e acompanhar o resultado.</span>
     <b>Abrir quadro de entregas <span aria-hidden="true">→</span></b>
    </Link>
   </div>
  </section>

  <section className={"operatorAttention "+(attention.kind==="clear"?"clear":"requiresAction")} aria-label="O que depende de você" role="status">
   <div className="operatorAttentionContent">
    <span className="operatorEyebrow">{attention.kind==="clear"?"SUAS DECISÕES":"PRECISA DE VOCÊ · "+attention.count}</span>
    <h2>{attention.title}</h2>
    <p>{attention.description}</p>
   </div>
   {attention.count>0
    ?<Link prefetch={false} href="/gates" className="operatorAttentionLink">{attention.label} <span aria-hidden="true">→</span></Link>
    :<span className="operatorAttentionQuiet">Nenhuma aprovação necessária agora</span>}
  </section>

  <section className="section operatorPortfolio" aria-label="Seus produtos">
   <SectionHeader title="Seus produtos" action={<Link prefetch={false} className="homeSectionLink" href="/projects">Ver todos os produtos →</Link>}/>
   <p className="operatorSectionHint">Clique em um produto para solicitar uma melhoria ou ver seu próximo passo. A etapa registrada não comprova que um agente esteja executando neste instante.</p>
   {dashboard.projects.length===0
    ?<div className="operatorPortfolioEmpty">Ainda não há produtos cadastrados. <Link href="/projects/new">Criar primeiro produto →</Link></div>
    :<div className="homeProjectGrid">
     {dashboard.projects.slice(0,4).map(p=><Link prefetch={false} className="operatorProjectCard" href={"/projects/"+p.key} key={p.key}>
      <span className="operatorProjectHeading">
       <strong>{p.name}</strong>
       <span className="operatorPortfolioBadge">{p.status==="active"?"No portfólio":"Inativo"}</span>
      </span>
      <span className="operatorProjectStep">Etapa registrada: <b>{operatorStageLabel(p.stage)}</b></span>
      <span className="operatorProjectFooter"><small>Atualizado em {new Date(p.updatedAt).toLocaleDateString("pt-BR")}</small><b>Abrir produto →</b></span>
     </Link>)}
    </div>}
  </section>

  <section className="operatorHowItWorks" aria-labelledby="operator-how-title">
   <h2 id="operator-how-title">Como a Factory entrega seu pedido</h2>
   <ol className="operatorProcess">
    <li><span>1 · Você</span><strong>Descreve o pedido</strong><small>Ideia, melhoria ou correção</small></li>
    <li><span>2 · Factory</span><strong>Planeja</strong><small>Organiza escopo e trabalho</small></li>
    <li><span>3 · Factory</span><strong>Constrói e testa</strong><small>Registra testes e prévia</small></li>
    <li><span>4 · Você</span><strong>Revisa a entrega</strong><small>Aprova ou solicita ajustes</small></li>
    <li><span>5 · Factory</span><strong>Acompanha</strong><small>Registra a operação</small></li>
   </ol>
   <p>Quando houver dependência de escopo, acesso ou custo, a Factory pede sua decisão. Publicação em produção continua sempre sob gate humano.</p>
  </section>

  <details className="operatorDiagnostics">
   <summary>
    <span><strong>Diagnóstico técnico e histórico</strong><small>Para investigar execuções, filas e custos. Não é necessário para iniciar um pedido.</small></span>
    <span className="operatorDiagnosticCount">{historicalProblems} registros com falha ou bloqueio</span>
   </summary>
   <div className="operatorDiagnosticsBody">
    <p>Esses números vêm do histórico do Control Plane. Não representam {historicalProblems} decisões suas, nem demonstram que todas as falhas ainda estejam ativas. Consulte a execução específica antes de solicitar recuperação.</p>
    <div className="operatorDiagnosticMetrics">
     <div><span>Execuções falhadas</span><strong>{health.failedRuns}</strong></div>
     <div><span>Execuções bloqueadas</span><strong>{health.blockedRuns}</strong></div>
     <div><span>Fila registrada</span><strong>{health.queuedRuns}</strong></div>
     <div><span>Custo conhecido (USD)</span><strong>{usage.knownCost.toFixed(2)}</strong></div>
    </div>
    <div className="operatorDiagnosticLinks">
     <Link prefetch={false} href="/runs">Investigar execuções →</Link>
     <Link prefetch={false} href="/usage">Ver custos →</Link>
     <Link prefetch={false} href="/audit">Consultar auditoria →</Link>
    </div>
   </div>
  </details>
 </>;
}
