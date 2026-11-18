import Link from "next/link";
import {getGitHubAppInstallActions,getHumanGates,getOperationsHealth,getUsageOverview} from "../lib/control-plane";
import {getGitHubAppStatus} from "../lib/github-app";
import {getProductSituations} from "../lib/product-status";
import {summarizeOperatorAttention} from "../lib/operator-home";
import {ProductSituationCard} from "./product-situation-card";
import {PageHeader} from "./ui";

/** Read-only owner cockpit. The shell refreshes passive views periodically;
 * these snapshots never initiate workers, paid models or releases. */
export default async function Home(){
 const [gates,installations,app,health,usage,pulse]=await Promise.all([
  getHumanGates(100,true),getGitHubAppInstallActions(),
  getGitHubAppStatus(),getOperationsHealth(),getUsageOverview(),getProductSituations(),
 ]);
 const attention=summarizeOperatorAttention(gates,installations,app.configured);
 const products=pulse.products.filter(p=>!p.isInternalRecord);
 const stoppedProducts=products.filter(p=>!p.isActive||["stopped","paused","pausing","stopping"].includes(p.controlState));
 const visibleProducts=products.filter(p=>!stoppedProducts.includes(p));
 const internalRecords=pulse.products.filter(p=>p.isInternalRecord);
 const running=visibleProducts.reduce((n,p)=>n+p.confirmedRunning,0);
 const historicalProblems=health.failedRuns+health.blockedRuns;
 const latestChanges=products.flatMap(item=>item.activities.map(event=>({
  key:item.key+"-"+event.kind+"-"+event.at+"-"+(event.href||""),
  product:item.name,at:event.at,title:event.title,href:event.href,
 }))).sort((a,b)=>Date.parse(b.at)-Date.parse(a.at)).slice(0,6);
 return <>
  <PageHeader eyebrow="Visão geral" title="Sua Factory hoje"
   subtitle="O que já foi entregue, o que está acontecendo e o que depende de você."
   actions={<Link prefetch={false} href="/projects/new" className="factoryNewRequest">Novo produto</Link>}/>
  <section className="factoryCommandBar" aria-label="Situação da Factory">
   <div className="factoryAttentionState">
    <span className="factoryOverline">SUA PARTICIPAÇÃO</span>
    {attention.count>0?<div className="factoryAttentionNeedsAction" role="status">
     <h2>{attention.title}</h2><p>{attention.description}</p>
     <Link prefetch={false} href="/gates">Revisar o que depende de mim →</Link>
    </div>:<div className="factoryAttentionClear" role="status">
     <h2>Nenhuma decisão sua neste momento</h2>
     <p>A Factory segue as tarefas permitidas. Isso não significa que todos os produtos estejam prontos.</p>
    </div>}
   </div>
   <div className="factoryExecutionState">
    <span className="factoryOverline">ATIVIDADE OBSERVADA</span>
    <strong>{running>0?running+" execução"+(running===1?"":"ões")+" com lease vigente":"Nenhuma execução ativa comprovada"}</strong>
    <p>Projeto habilitado não é o mesmo que worker executando.</p>
   </div>
  </section>
  <section className="section operatorPortfolio" aria-labelledby="operator-products-title">
   <div className="productPulseHeader"><div>
    <h2 id="operator-products-title">Produtos acompanhados</h2>
    <p>Entrega comprovada, situação atual e próxima verificação.</p>
   </div><Link prefetch={false} className="productSituationSecondary" href="/projects">Ver todos os produtos →</Link></div>
   <div className="factoryObservationLine">
    <span>Consulta ao Control Plane: <time dateTime={pulse.observedAt}>{new Date(pulse.observedAt).toLocaleString("pt-BR")}</time></span>
    <span>Atualização automática a cada minuto enquanto online.</span>
   </div>
   <div className="productSituationList">
    {visibleProducts.length===0?<div className="operatorPortfolioEmpty">Nenhum produto ativo registrado. <Link href="/projects/new">Descrever produto →</Link></div>:
     visibleProducts.map(item=><ProductSituationCard key={item.key} item={item} compact/>)}
   </div>
   {stoppedProducts.length>0?<details className="productInactiveDisclosure">
    <summary>Produtos parados ou aposentados ({stoppedProducts.length})</summary>
    <div className="productSituationList">{stoppedProducts.map(item=><ProductSituationCard key={item.key} item={item} compact/>)}</div>
   </details>:null}
   {internalRecords.length>0?<details className="productInactiveDisclosure">
    <summary>Registros técnicos de teste ({internalRecords.length})</summary>
    <div className="productSituationList">{internalRecords.map(item=><ProductSituationCard key={item.key} item={item} compact/>)}</div>
   </details>:null}
  </section>
  <section className="factoryRecent" aria-labelledby="factory-recent-title">
   <div className="factorySectionHeading"><h2 id="factory-recent-title">Últimos acontecimentos registrados</h2>
    <p>Eventos históricos, não prova de que o worker continua ativo.</p></div>
   {latestChanges.length===0?<p className="factoryEmptyActivity">Nenhuma atividade disponível nesta consulta.</p>:
    <ol className="factoryActivityList">{latestChanges.map(event=><li key={event.key}>
     <span className="factoryActivityDate"><time dateTime={event.at}>{new Date(event.at).toLocaleString("pt-BR")}</time></span>
     <span className="factoryActivityCopy"><strong>{event.product}</strong><span>{event.title}</span></span>
     {event.href?<Link prefetch={false} href={event.href} aria-label={"Ver registro: "+event.product+" — "+event.title}>Ver registro →</Link>:null}
    </li>)}</ol>}
  </section>
  <details className="productOverviewTechnical">
   <summary>Indicadores técnicos do portfólio</summary>
   <div className="productPulseStats" role="group" aria-label="Situação observada">
    <div><strong>{products.length}</strong><span>Produtos cadastrados</span></div>
    <div><strong>{running}</strong><span>Execuções com lease vigente</span></div>
    <div><strong>{stoppedProducts.length}</strong><span>Produtos parados ou pausados</span></div>
    <div><strong>{attention.count}</strong><span>Ações humanas registradas</span></div>
   </div>
  </details>
  <details className="operatorDiagnostics">
   <summary><span><strong>Diagnóstico do sistema</strong><small>Custos, incidentes e outras evidências para investigação.</small></span>
    <span className="operatorDiagnosticCount">{historicalProblems} falhas ou bloqueios históricos</span></summary>
   <div className="operatorDiagnosticsBody">
    <p>Histórico não é a lista de impedimentos atuais. Verifique cada execução antes de solicitar recuperação.</p>
    <div className="operatorDiagnosticMetrics">
     <div><span>Falhas históricas</span><strong>{health.failedRuns}</strong></div>
     <div><span>Bloqueios históricos</span><strong>{health.blockedRuns}</strong></div>
     <div><span>Fila registrada</span><strong>{health.queuedRuns}</strong></div>
     <div><span>Custo conhecido (USD)</span><strong>{usage.knownCost.toFixed(2)}</strong></div>
    </div>
    <div className="operatorDiagnosticLinks">
     <Link href="/runs">Execuções →</Link><Link href="/usage">Custos →</Link><Link href="/audit">Auditoria →</Link>
    </div>
   </div>
  </details>
 </>;
}
