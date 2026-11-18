import Link from "next/link";
import type {ProductSituation} from "../lib/product-status";
import {describeProductJourney} from "../lib/product-journey";
function lastRunLabel(status:string):string{
 switch(status){
  case "completed":return "Execução técnica concluída";
  case "integrated":case "merged":return "Integração de código registrada";
  case "failed":return "Falha registrada";
  case "failed_gate":return "Verificação técnica interrompida";
  case "blocked":return "Execução bloqueada";
  case "cancelled":case "canceled":return "Execução cancelada";
  default:return "Estado registrado: "+status.replaceAll("_"," ");
 }
}
function EvidenceRibbon({item}:{item:ProductSituation}){
 const proof=item.proof;
 return <section className="productTruth" aria-label="O que foi realmente comprovado">
  <div className="productTruthMain">
   <span className="journeyOverline">ENTREGA REAL · EVIDÊNCIAS</span>
   <strong>{proof.headline}</strong>
   <p>{proof.explanation}</p>
  </div>
  <div className="productTruthMarkers">
   <span className={proof.hasHumanMerge?"truthRecorded":"truthUnknown"}>{proof.hasHumanMerge?"Merge humano registrado":"Merge não comprovado aqui"}</span>
   <span className={proof.hasPreviewRecord?"truthRecorded":"truthUnknown"}>{proof.hasPreviewRecord?"Preview registrado":"Preview não comprovado aqui"}</span>
   <span className={proof.productReady?"truthVerified":"truthUnverified"}>{proof.productReady?"Entrega certificada":"Entrega completa não certificada"}</span>
  </div>
 </section>;
}
function NextAction({item}:{item:ProductSituation}){
 const a=describeProductJourney(item).action;
 return <aside className={"journeyAction "+(a.humanRequired?"needsHuman":item.state==="stopped"||item.state==="paused"?"inactive":"routine")} aria-label="O que fazer agora">
  <div className="journeyActionText">
   <span className="journeyOverline">PRÓXIMO PASSO</span>
   <h4>{a.title}</h4><p>{a.description}</p>
   <small><strong>Responsável:</strong> {a.owner}{a.humanRequired?" · Sua decisão é obrigatória":a.owner==="Você"?" · Você pode iniciar este pedido":" · Nenhuma aprovação sua identificada"}</small>
  </div>
  <div className="journeyActionLinks">
   <Link prefetch={false} className="productSituationButton" href={a.href}>{a.label}
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
   </Link>
  </div>
 </aside>;
}
/** This is a read-only status report; there is no progress meter or implicit Start.
 * Compact variant prevents one six-step lifecycle from swallowing the home screen.
 */
export function ProductSituationCard({item,showOpen=true,compact=false}:{item:ProductSituation;showOpen?:boolean;compact?:boolean}){
 const journey=describeProductJourney(item);
 return <article className={"productSituationCard journeyCard state-"+item.state+(compact?" compact":"")}>
  <div className="productSituationTop journeyCardTop">
   <div><h3><Link prefetch={false} href={"/projects/"+encodeURIComponent(item.key)}>{item.name}</Link></h3>
    <span>{item.isInternalRecord?"Registro técnico, não produto de cliente":"Situação do produto com base em registros verificáveis"}</span>
   </div>
   <span className={"productSituationStatus "+item.state}>Trabalho: {item.controlState==="draft"?"Projeto ainda não iniciado":item.headline}</span>
  </div>
  <EvidenceRibbon item={item}/>
  {compact?
   <div className="productCompactDetails">
    <div><span>ETAPA DO CADASTRO</span><strong>{journey.phaseLabel}</strong><small>Este campo não certifica as etapas anteriores.</small></div>
    <div><span>ESTADO DO TRABALHO</span><strong>{item.headline}</strong><small>{item.explanation}</small></div>
   </div>:
   <>
    <section className="journeyPath" aria-label={"Etapas declaradas para "+item.name}>
     <div className="journeyPathHeading"><h4>Caminho previsto</h4>
      <span>{journey.phaseKnown?"Marco registrado: "+journey.substage:"Marco não identificado"}</span></div>
     <p className="journeyPathNotice">A posição abaixo vem do cadastro. Não significa que as fases anteriores tenham sido concluídas ou aprovadas.</p>
     <ol className="productJourneyTrack" aria-label="Fases previstas do desenvolvimento">
      {journey.phaseSteps.map(step=><li key={step.key} className={"journeyStep "+step.mark} aria-current={step.mark==="atual"?"step":undefined}>
       <span className="journeyStepNumber" aria-hidden="true">{step.position}</span>
       <strong>{step.label}</strong>
       <small>{step.mark==="atual"?"Marco cadastrado":step.mark==="proxima"?"Etapa seguinte prevista":step.mark==="anterior"?"Conclusão não verificada":step.mark==="desconhecida"?"Não identificado":"Etapa prevista"}</small>
      </li>)}
     </ol>
    </section>
    <div className="journeyPhaseOverview">
     <div className="journeyCurrent">
      <span className="journeyOverline">MARCO INFORMADO NO CADASTRO</span>
      <h4>{journey.phaseLabel}</h4><p>{journey.phasePurpose}</p>
      <small>Subetapa declarada: {journey.substage}</small>
     </div>
     <div className="journeyUpcoming">
      <span className="journeyOverline">PRÓXIMA ETAPA OU VERIFICAÇÃO</span>
      <h4>{journey.nextPhaseLabel}</h4>
      <p><strong>O que falta para avançar:</strong> {journey.conditionToAdvance}</p>
     </div>
    </div>
   </>}
  <NextAction item={item}/>
  {showOpen?<Link prefetch={false} className="productCompactOpen" href={"/projects/"+encodeURIComponent(item.key)}>Abrir acompanhamento do produto →</Link>:null}
  <details className="journeyEvidence">
   <summary>Ver último pedido, tentativa e dados técnicos</summary>
   <div className="journeyEvidenceContent">
    <div><strong>O QUE ESTÁ ACONTECENDO</strong><p>{item.explanation}</p></div>
    <div><strong>ÚLTIMA SOLICITAÇÃO REGISTRADA</strong><p>{item.lastRequest||"Nenhum pedido recente deste canal. Solicitações por GitHub podem existir separadamente."}</p></div>
    <div><strong>ÚLTIMA TENTATIVA</strong>
     {item.lastRun?<p>{lastRunLabel(item.lastRun.status)} em {new Date(item.lastRun.at).toLocaleString("pt-BR")}. <Link prefetch={false} href={"/runs/"+item.lastRun.id}>Ver execução</Link></p>:
      <p>Nenhuma execução vinculada foi encontrada.</p>}
    </div>
   </div>
  </details>
 </article>;
}
