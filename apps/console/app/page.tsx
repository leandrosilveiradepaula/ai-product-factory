import Link from "next/link";
import {
 getDashboard,getHumanGates,getProjectDetail,getProjectRecoveryStatus,
 getProjectStateContext,getProjectExecutionControl,getProjectWorkObservation
} from "../lib/control-plane";
import {PRODUCT_PHASES,summarizeProductExperience} from "../lib/product-experience-model";
import {ActionLink,PageHeader} from "./ui";

function formatWhen(value:string){
 const ms=Date.parse(value);
 return Number.isFinite(ms)?new Intl.DateTimeFormat("pt-BR",{dateStyle:"short",timeStyle:"short"}).format(new Date(ms)):"Data indisponível";
}

export default async function Home(){
 const [dashboard,gates]=await Promise.all([getDashboard(),getHumanGates(50,true)]);
 const pending=gates.filter(g=>g.actionable&&g.status==="pending");
 const fetchedAt=new Date().toISOString();
 const portfolio=await Promise.all(dashboard.projects.map(async project=>{
  const detail=await getProjectDetail(project.key);
  if(!detail)return{project,detail:null,view:summarizeProductExperience({
   project,detail:null,context:{objective:null,snapshot:null},recovery:null,
   control:{state:"unavailable",version:-1,generation:0},
   work:{kind:"unavailable",runId:null,at:null},
   actionableGates:pending.filter(g=>g.projectKey===project.key).length
  }),internal:false,paused:false};
  const [context,recovery,control,work]=await Promise.all([
   getProjectStateContext(detail.id),getProjectRecoveryStatus(detail.id),
   getProjectExecutionControl(detail.id),
   getProjectWorkObservation(detail.tasks.map(t=>String(t.id)))
  ]);
  const view=summarizeProductExperience({
   project,detail,context,recovery,control,work,
   actionableGates:pending.filter(g=>g.projectKey===project.key).length
  });
  return{project,detail,view,internal:detail.isInternalRecord,
   paused:view.tone==="paused"};
 }));
 const products=portfolio.filter(p=>!p.internal&&!p.paused);
 const paused=portfolio.filter(p=>!p.internal&&p.paused);
 const internal=portfolio.filter(p=>p.internal);
 const working=portfolio.filter(p=>!p.internal&&p.view.tone==="working").length;
 const blocked=portfolio.filter(p=>!p.internal&&p.view.tone==="blocked").length;
 const evaluated=portfolio.filter(p=>!p.internal&&p.detail?.productReadiness.ready===true).length;
 const unverifiable=portfolio.filter(p=>!p.internal&&p.view.tone==="unknown").length;
 const renderProduct=(entry:typeof portfolio[number])=>{
  const {project,view}=entry;
  return <article className={"productStory "+view.tone} key={project.key}>
   <div className="productStoryTop">
    <div className="productIdentity"><span className="productKind">Produto</span><h3>{project.name}</h3></div>
    <span className={"productTruthTag "+view.tone}>{view.label}</span>
   </div>
   <p className="productObjective">{view.objective}</p>
   <div className="productJourneyDeclared">
    <span>Etapa no cadastro: <strong>{view.declaredStageLabel}</strong> — não comprova conclusão</span>
    <div className="journeyRail" role="group" aria-label={"Etapa cadastrada: "+view.declaredStageLabel}>
     {PRODUCT_PHASES.map((step,i)=><span className={view.declaredStage===i?"current":""} key={step}>{step}</span>)}
    </div>
   </div>
   <div className="productVerdict">
    <span>{view.execution}</span>
    <strong>{view.headline}</strong>
    <p>{view.description}</p>
   </div>
   <div className="productResponsibilities">
    <div><span>PRÓXIMA RESPONSABILIDADE DA FACTORY</span><strong>{view.nextTitle}</strong><p>{view.nextDetail}</p></div>
    <div><span>SUA PARTICIPAÇÃO</span><strong>{view.userAction}</strong>
     {view.tone==="decision"?<Link href="/gates" className="productOpen">Abrir decisão →</Link>:null}
    </div>
   </div>
   <p className="productReadinessCaption">{view.proof}</p>
   <div className="productStoryFooter">
    <span>Cadastro atualizado: {formatWhen(project.updatedAt)}</span>
    <Link href={"/projects/"+encodeURIComponent(project.key)} className="productOpen">Abrir espaço do produto →</Link>
   </div>
  </article>;
 };
 return <>
  <PageHeader eyebrow="Central de produtos" title="Sua Factory, de ponta a ponta"
   subtitle="Entregas comprovadas, trabalho real e próximas responsabilidades. Sem gestão de pipelines."
   actions={<ActionLink href="/projects/new" variant="primary">Descrever um produto</ActionLink>}/>
  <section className="factoryPulse" aria-label="Situação observada da Factory">
   <div><span className="pulseKicker">Agora</span>
    <h2>{working>0?"Execução com lease comprovado":unverifiable>0?"Execução parcialmente não verificável":"Nenhuma execução ativa comprovada"}</h2>
    <p>Atividade é verificada por início de run e lease vigente. Um pedido registrado não significa que alguém já está executando.</p>
    <small className="factoryObservedAt">Control Plane consultado: <time dateTime={fetchedAt}>{formatWhen(fetchedAt)}</time></small>
   </div>
   <div className="pulseStats">
    <span><b>{working}</b> execuções comprovadas</span>
    <span><b>{blocked}</b> reparos técnicos bloqueados</span>
    <span><b>{evaluated}</b> avaliações de prontidão registradas</span>
    <span><b>{pending.length}</b> decisões humanas acionáveis</span>
   </div>
  </section>
  {pending.length>0?<section className="humanInbox" aria-labelledby="human-inbox-title">
   <div><span className="eyebrow">Sua decisão</span>
    <h2 id="human-inbox-title">{pending.length} {pending.length===1?"decisão exige":"decisões exigem"} seu julgamento</h2>
    <p>Somente gates acionáveis. Falhas técnicas não geram aprovação humana.</p>
   </div><ActionLink href="/gates" variant="primary">Revisar decisões</ActionLink>
  </section>:null}
  <section className="portfolio" aria-labelledby="portfolio-title">
   <div className="portfolioHeading"><div><span className="eyebrow">Produtos</span>
    <h2 id="portfolio-title">O que a Factory está construindo</h2></div>
    <Link href="/projects" className="textLink">Ver portfólio completo</Link>
   </div>
   {products.length>0?<div className="productBoard">{products.map(renderProduct)}</div>:
    <p className="factoryPortfolioEmpty">Nenhum produto em desenvolvimento encontrado nesta consulta.</p>}
   {paused.length>0?<details className="portfolioSecondary">
    <summary>Produtos parados ou não iniciados ({paused.length})</summary>
    <div className="productBoard">{paused.map(renderProduct)}</div>
   </details>:null}
   {internal.length>0?<details className="portfolioSecondary">
    <summary>Registros técnicos da Factory ({internal.length})</summary>
    <p>Não são produtos disponíveis para utilização.</p>
    <div className="productBoard">{internal.map(renderProduct)}</div>
   </details>:null}
  </section>
 </>;
}
