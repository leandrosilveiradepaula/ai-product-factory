import Link from "next/link";
import type {ProductSituation} from "../lib/product-status";
import {describeProductJourney} from "../lib/product-journey";
function lastRunLabel(status:string):string{
 switch(status){
  case "completed":return "Execução técnica concluída";
  case "integrated":return "Integração registrada, publicação não comprovada";
  case "merged":return "Integração registrada, publicação não comprovada";
  case "failed":return "Falha registrada";
  case "failed_gate":return "Falha em verificação";
  case "blocked":return "Execução bloqueada";
  case "cancelled":case "canceled":return "Execução cancelada";
  default:return "Estado registrado: "+status.replaceAll("_"," ");
 }
}
/* One read-only, navigable product journey used by Home, Projects and Detail.
 * Lifecycle positions are not readiness checks. No click changes phase. */
export function ProductSituationCard({item,showOpen=true}:{item:ProductSituation;showOpen?:boolean}){
 const journey=describeProductJourney(item),a=journey.action;
 return <article className={"productSituationCard journeyCard state-"+item.state}>
  <div className="productSituationTop journeyCardTop">
   <div>
    <h3><Link prefetch={false} href={"/projects/"+encodeURIComponent(item.key)}>{item.name}</Link></h3>
    <span>Jornada do produto · etapa registrada no Control Plane, não uma certificação</span>
   </div>
   <span className={"productSituationStatus "+item.state}>Execução: {item.controlState==="draft"?"Projeto ainda não iniciado":item.headline}</span>
  </div>
  <section className="journeyPath" aria-label={"Caminho de "+item.name}>
   <div className="journeyPathHeading">
    <h4>Caminho do produto</h4>
    <span>{journey.phaseKnown?"Fase "+(journey.phaseIndex+1)+" de 6":"Etapa não identificada"}</span>
   </div>
   <ol className="productJourneyTrack" aria-label="Fases do desenvolvimento do produto">
    {journey.phaseSteps.map(step=>
     <li key={step.key} className={"journeyStep "+step.mark} aria-current={step.mark==="atual"?"step":undefined}>
      <span className="journeyStepNumber" aria-hidden="true">{step.position}</span>
      <strong>{step.label}</strong>
      <small>{step.mark==="atual"?"Você está aqui":step.mark==="proxima"?"Vem depois":step.mark==="anterior"?"Fase anterior":step.mark==="desconhecida"?"Não confirmada":"Etapa futura"}</small>
     </li>)}
   </ol>
  </section>
  <div className="journeyPhaseOverview">
   <div className="journeyCurrent">
    <span className="journeyOverline">ETAPA ATUAL</span>
    <h4>{journey.phaseLabel}</h4>
    <p>{journey.phasePurpose}</p>
    <small>Dentro desta fase: {journey.substage}</small>
   </div>
   <div className="journeyUpcoming">
    <span className="journeyOverline">PRÓXIMA FASE</span>
    <h4>{journey.nextPhaseLabel}</h4>
    <p><strong>O que falta para avançar:</strong> {journey.conditionToAdvance}</p>
   </div>
  </div>
  <aside className={"journeyAction "+(a.humanRequired?"needsHuman":item.state==="stopped"||item.state==="paused"?"inactive":"routine")} aria-label="O que fazer agora">
   <div className="journeyActionText">
    <span className="journeyOverline">PRÓXIMO PASSO</span>
    <h4>{a.title}</h4>
    <p>{a.description}</p>
    <small><strong>Quem age:</strong> {a.owner}{a.humanRequired?" · Sua decisão é necessária":a.owner==="Você"?" · Seu pedido inicia o trabalho":" · Nenhuma aprovação sua pendente identificada"}</small>
   </div>
   <div className="journeyActionLinks">
    <Link prefetch={false} className="productSituationButton" href={a.href}>{a.label}
     <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
    </Link>
    {showOpen?<Link prefetch={false} className="productSituationSecondary" href={"/projects/"+encodeURIComponent(item.key)}>Abrir detalhes do produto</Link>:null}
   </div>
  </aside>
  <details className="journeyEvidence">
   <summary>Ver último pedido e evidências da execução</summary>
   <div className="journeyEvidenceContent">
    <div><strong>O QUE ESTÁ ACONTECENDO</strong><p>{item.explanation}</p></div>
    <div><strong>ÚLTIMA SOLICITAÇÃO</strong><p>{item.lastRequest||"Nenhum pedido recente deste canal. Solicitações em outros canais podem não aparecer aqui."}</p></div>
    <div><strong>ÚLTIMA TENTATIVA</strong>
     {item.lastRun?<p>{lastRunLabel(item.lastRun.status)} em {new Date(item.lastRun.at).toLocaleString("pt-BR")}. <Link prefetch={false} href={"/runs/"+item.lastRun.id}>Ver evidência técnica</Link></p>:<p>Nenhuma execução vinculada ao produto foi encontrada.</p>}
    </div>
   </div>
  </details>
 </article>;
}
