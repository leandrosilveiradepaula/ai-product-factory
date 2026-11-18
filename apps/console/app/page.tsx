import Link from "next/link";
import {getGitHubAppInstallActions,getHumanGates,getOperationsHealth,getUsageOverview} from "../lib/control-plane";
import {getGitHubAppStatus} from "../lib/github-app";
import {getProductSituations} from "../lib/product-status";
import {summarizeOperatorAttention} from "../lib/operator-home";
import {ProductSituationCard} from "./product-situation-card";
import {PageHeader} from "./ui";

/** Human-readable product status; the Kanban remains a subordinate task view.
 * All evidence is read-only. This route never starts a worker or releases code.
 */
export default async function Home(){
 const [gates,installations,app,health,usage,pulse]=await Promise.all([
  getHumanGates(100,true),getGitHubAppInstallActions(),
  getGitHubAppStatus(),getOperationsHealth(),getUsageOverview(),getProductSituations(),
 ]);
 const attention=summarizeOperatorAttention(gates,installations,app.configured);
 const products=pulse.products.filter(p=>p.isActive);
 const running=products.reduce((n,p)=>n+p.confirmedRunning,0);
 const stoppedProducts=products.filter(p=>p.controlState==="stopped"||p.controlState==="paused");
 const visibleProducts=products.filter(p=>!stoppedProducts.includes(p));
 const stopped=stoppedProducts.length;
 const historicalProblems=health.failedRuns+health.blockedRuns;
 return <>
  <PageHeader eyebrow="Seu trabalho" title="Em que fase está cada produto?"
   subtitle="Para cada produto, veja onde está, qual é a próxima fase e se você precisa fazer alguma coisa."/>

  {attention.count>0?<section className="operatorAttention requiresAction" role="status" aria-label="O que depende de você">
   <div className="operatorAttentionContent">
    <span className="operatorEyebrow">DEPENDE DE VOCÊ · {attention.count}</span>
    <h2>{attention.title}</h2><p>{attention.description}</p>
   </div>
   <Link prefetch={false} href="/gates" className="operatorAttentionLink">{attention.label} →</Link>
  </section>:null}

  <section className="section operatorPortfolio" aria-labelledby="operator-products-title">
   <div className="productPulseHeader">
    <div><h2 id="operator-products-title">O caminho dos seus produtos</h2><p>As fases mostram a etapa registrada, não uma porcentagem de conclusão. A próxima ação aparece em cada produto.</p></div>
    <Link prefetch={false} className="productSituationSecondary" href="/projects">Abrir portfólio completo →</Link>
   </div>
   <details className="productOverviewTechnical">
    <summary>Consultar números técnicos do portfólio</summary>
   <div className="productPulseStats" role="group" aria-label="Situação observada">
    <div><strong>{products.length}</strong><span>Projetos listados no cadastro</span></div>
    <div><strong>{running}</strong><span>Execuções com início e lease vigente</span></div>
    <div><strong>{stopped}</strong><span>Projetos com controle parado ou pausado</span></div>
    <div><strong>{attention.count}</strong><span>Decisões ou acessos pendentes</span></div>
   </div>
   </details>
   <div className="productSituationList">
    {products.length===0?<div className="operatorPortfolioEmpty">Nenhum produto ativo cadastrado. <Link href="/projects/new">Criar um produto →</Link></div>:
    visibleProducts.map(item=><ProductSituationCard key={item.key} item={item}/>)}
   </div>
   {stoppedProducts.length>0?<details className="productInactiveDisclosure">
    <summary>{stoppedProducts.length} {stoppedProducts.length===1?"produto parado ou pausado":"produtos parados ou pausados"} · Ver registros</summary>
    <div className="productSituationList">{stoppedProducts.map(item=><ProductSituationCard key={item.key} item={item}/>)}</div>
   </details>:null}
   <p className="productSituationFootnote">“Projeto habilitado” não significa que exista um agente executando. “Execução concluída” não significa que o produto foi publicado ou certificado. O histórico técnico continua disponível.</p>
  </section>

  <section className="operatorWelcome" aria-labelledby="operator-start-heading">
   <div className="operatorWelcomeHeading">
    <span className="operatorEyebrow">QUANDO VOCÊ QUISER AGIR</span>
    <h2 id="operator-start-heading">O que você quer fazer agora?</h2>
    <p>Você descreve o objetivo. A Factory faz o planejamento e registra as evidências de entrega.</p>
   </div>
   <div className="operatorChoices">
    <Link prefetch={false} href="/projects/new" className="operatorChoice featured">
     <span className="operatorChoiceSymbol" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="M12 4v16M4 12h16"/></svg></span>
     <strong>Criar um produto</strong><span>Começar a partir de uma ideia.</span><b>Descrever minha ideia →</b>
    </Link>
    <Link prefetch={false} href="/projects" className="operatorChoice">
     <span className="operatorChoiceSymbol" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="m4 16 0 4 4 0 11-11-4-4zM13 7l4 4"/></svg></span>
     <strong>Melhorar um produto</strong><span>Pedir uma mudança ou corrigir algo.</span><b>Escolher produto →</b>
    </Link>
    <Link prefetch={false} href="/deliveries" className="operatorChoice">
     <span className="operatorChoiceSymbol" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/></svg></span>
     <strong>Acompanhar entregas</strong><span>Ver o Kanban de um produto.</span><b>Abrir entregas →</b>
    </Link>
   </div>
  </section>

  <details className="operatorHowItWorks">
   <summary>Como funciona uma entrega da Factory</summary>
   <ol className="operatorProcess">
    <li><span>1 · Você</span><strong>Descreve o pedido</strong><small>Ideia, melhoria ou correção</small></li>
    <li><span>2 · Factory</span><strong>Planeja</strong><small>Organiza escopo e tarefas</small></li>
    <li><span>3 · Factory</span><strong>Constrói e testa</strong><small>Registra testes e prévia</small></li>
    <li><span>4 · Você</span><strong>Revisa a entrega</strong><small>Aprova ou solicita ajustes</small></li>
    <li><span>5 · Factory</span><strong>Acompanha</strong><small>Registra a operação</small></li>
   </ol>
   <p>A Factory pode pedir uma decisão de escopo, acesso ou custo. Publicação em produção continua sempre sob gate humano.</p>
  </details>

  <details className="operatorDiagnostics">
   <summary>
    <span><strong>Diagnóstico técnico e histórico</strong><small>Execuções, custos e incidentes para investigação técnica.</small></span>
    <span className="operatorDiagnosticCount">{historicalProblems} registros com falha ou bloqueio</span>
   </summary>
   <div className="operatorDiagnosticsBody">
    <p>Os números são históricos. Não representam {historicalProblems} ações suas e não demonstram que todas as falhas ainda estejam ativas. Consulte a execução específica antes de solicitar recuperação.</p>
    <div className="operatorDiagnosticMetrics">
     <div><span>Execuções com falha</span><strong>{health.failedRuns}</strong></div>
     <div><span>Execuções bloqueadas</span><strong>{health.blockedRuns}</strong></div>
     <div><span>Fila registrada</span><strong>{health.queuedRuns}</strong></div>
     <div><span>Custo conhecido (USD)</span><strong>{usage.knownCost.toFixed(2)}</strong></div>
    </div>
    <div className="operatorDiagnosticLinks">
     <Link prefetch={false} href="/runs">Ver execuções →</Link>
     <Link prefetch={false} href="/usage">Ver custos →</Link>
     <Link prefetch={false} href="/audit">Consultar auditoria →</Link>
    </div>
   </div>
  </details>
 </>;
}
