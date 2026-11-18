import Link from "next/link";
import type {ProductSituation} from "../lib/product-status";
import {describeProductJourney} from "../lib/product-journey";
import {diagnoseProduct} from "../lib/product-diagnosis";

function lastRunLabel(status:string):string{
 switch(status){
  case "completed":return "Execução técnica concluída";
  case "integrated":case "merged":return "Código integrado";
  case "failed":case "blocked":case "failed_gate":return "Execução interrompida";
  default:return "Estado: "+status.replaceAll("_"," ");
 }
}
function EvidenceRibbon({item}:{item:ProductSituation}){
 const result=diagnoseProduct(item);
 return <section className="productTruth" aria-label="Estado verificável da entrega">
  <div className="productTruthMain">
   <span className="journeyOverline">SITUAÇÃO DO PRODUTO</span>
   <strong>{result.headline}</strong>
   <p>{result.summary}</p>
  </div>
  <div className="productTruthMarkers">
   <span className={item.proof?.hasHumanMerge?"truthRecorded":"truthUnknown"}>{item.proof?.hasHumanMerge?"Código integrado":"Integração não confirmada"}</span>
   <span className={item.proof?.productReady?"truthVerified":"truthUnverified"}>{item.proof?.productReady?"Entrega avaliada":"Uso funcional não comprovado"}</span>
  </div>
 </section>;
}
function FindingRows({item}:{item:ProductSituation}){
 const findings=diagnoseProduct(item).findings;
 return <section className="productCompactDetails" aria-label="Fatos do produto">
  {findings.map(f=><div key={f.label} className={"productFact "+f.kind}>
   <span>{f.label.toUpperCase()}</span><strong>{f.value}</strong>
  </div>)}
 </section>;
}
function NextAction({item,compact}:{item:ProductSituation;compact:boolean}){
 const diagnosed=diagnoseProduct(item);
 const human=describeProductJourney(item).action;
 const step=item.state==="decision"?
  {title:human.title,detail:human.description,href:human.href,cta:human.label,owner:"Operador, se houver gate" as const}:
  diagnosed.steps[0];
 if(!step)return null;
 return <aside className={"journeyAction "+(item.state==="decision"?"needsHuman":item.state==="stopped"||item.state==="paused"?"inactive":"routine")} aria-label="Próximo trabalho necessário">
  <div className="journeyActionText">
   <span className="journeyOverline">PRÓXIMO TRABALHO</span>
   <h4>{step.title}</h4>
   <p>{compact?step.detail.slice(0,210):step.detail}</p>
   <small><strong>Responsável:</strong> {step.owner}{item.state==="decision"?" · decisão humana acionável":" · sem aprovação exigida só por haver falha"}</small>
  </div>
  <div className="journeyActionLinks">
   <Link prefetch={false} className="productSituationButton" href={step.href}>{step.cta}
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
   </Link>
  </div>
 </aside>;
}
function RemainingWork({item}:{item:ProductSituation}){
 const result=diagnoseProduct(item);
 if(result.steps.length===0)return null;
 return <section className="productWorkPlan" aria-label="Plano de desbloqueio e aceite">
  <div className="productWorkTitle"><h4>O que falta resolver</h4><p>Ordem sugerida a partir do inventário e dos bloqueios registrados. Não autoriza acesso sensível, gastos nem merge.</p></div>
  <ol>
   {result.steps.map((step,i)=><li key={step.title} className="productWorkStep">
    <span className="productWorkNumber">{i+1}</span>
    <div className="productWorkCopy"><strong>{step.title}</strong><p>{step.detail}</p><small>Quem conduz: {step.owner}</small></div>
    <Link prefetch={false} href={step.href}>{step.cta} →</Link>
   </li>)}
  </ol>
 </section>;
}
/** A short operational answer comes before technical lifecycle history.
 * The stage is historical metadata, never a readiness score. */
export function ProductSituationCard({item,showOpen=true,compact=false}:{item:ProductSituation;showOpen?:boolean;compact?:boolean}){
 const journey=describeProductJourney(item);
 return <article className={"productSituationCard journeyCard state-"+item.state+(compact?" compact":"")}>
  <div className="productSituationTop journeyCardTop">
   <div><h3><Link prefetch={false} href={"/projects/"+encodeURIComponent(item.key)}>{item.name}</Link></h3>
    <span>{item.isInternalRecord?"Registro de teste interno":"Produto do portfólio"}</span>
   </div>
   <span className={"productSituationStatus "+item.state}>{item.state==="decision"?"Decisão sua pendente":item.state==="investigate"?"Execução técnica bloqueada":item.state==="executing"?"Trabalho em curso":item.state==="stopped"?"Parado":item.state==="paused"?"Pausado":item.proof?.productReady?"Entrega avaliada":"Entrega não comprovada"}</span>
  </div>
  <EvidenceRibbon item={item}/>
  <FindingRows item={item}/>
  {compact?<NextAction item={item} compact/>:
   <>
    <RemainingWork item={item}/>
    <details className="productJourneyDisclosure">
     <summary>Ver histórico da jornada cadastrada (não comprova conclusão)</summary>
     <section className="journeyPath" aria-label={"Etapas declaradas para "+item.name}>
      <div className="journeyPathHeading"><h4>Caminho previsto</h4>
       <span>{journey.phaseKnown?"Marco registrado: "+journey.substage:"Marco não identificado"}</span>
      </div>
      <p className="journeyPathNotice">Não significa que as fases anteriores tenham sido concluídas ou aprovadas.</p>
      <ol className="productJourneyTrack" aria-label="Etapas administrativas">
       {journey.phaseSteps.map(step=><li key={step.key} className={"journeyStep "+step.mark} aria-current={step.mark==="atual"?"step":undefined}>
        <span className="journeyStepNumber" aria-hidden="true">{step.position}</span>
        <strong>{step.label}</strong>
        <small>{step.mark==="atual"?"Marco cadastrado":step.mark==="anterior"?"Sem conclusão certificada":step.mark==="proxima"?"Próxima prevista":"Etapa prevista"}</small>
       </li>)}
      </ol>
     </section>
     <div className="journeyPhaseOverview">
      <div className="journeyCurrent"><span className="journeyOverline">MARCO INFORMADO NO CADASTRO</span>
       <h4>{journey.phaseLabel}</h4><p>{journey.phasePurpose}</p><small>Subetapa: {journey.substage}</small>
      </div>
      <div className="journeyUpcoming"><span className="journeyOverline">PRÓXIMA ETAPA OU VERIFICAÇÃO</span>
       <h4>{journey.nextPhaseLabel}</h4><p><strong>O que falta para avançar:</strong> {journey.conditionToAdvance}</p>
      </div>
     </div>
    </details>
   </>}
  {showOpen?<Link prefetch={false} className="productCompactOpen" href={"/projects/"+encodeURIComponent(item.key)}>Abrir situação e plano do produto →</Link>:null}
  <details className="journeyEvidence">
   <summary>Ver pedido, tentativas e evidência técnica</summary>
   <div className="journeyEvidenceContent">
    <div><strong>O QUE ESTÁ ACONTECENDO</strong><p>{item.headline}</p></div>
    <div><strong>ÚLTIMA SOLICITAÇÃO</strong><p>{item.lastRequest||"Sem pedido recente registrado neste canal."}</p></div>
    <div><strong>ÚLTIMA TENTATIVA</strong>
     {item.lastRun?<p>{lastRunLabel(item.lastRun.status)} · {item.lastRun.taskTitle}. <Link prefetch={false} href={"/runs/"+item.lastRun.id}>Abrir execução</Link></p>:
      <p>Sem execução registrada.</p>}
    </div>
    {item.sourceIssueUrl?<div><strong>ESCOPO ORIGINAL</strong><p><Link href={item.sourceIssueUrl}>Ver pedido e critérios de aceite no GitHub</Link></p></div>:null}
    <div><strong>MARCO DO CADASTRO</strong><p>{item.stage} · não é um certificado de entrega.</p></div>
    <div><strong>ENTREGA</strong><p>{item.proof?.productReady?"Entrega certificada":"Entrega completa não certificada"}</p></div>
   </div>
  </details>
 </article>;
}
