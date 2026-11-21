import Link from "next/link";
import {revalidatePath} from "next/cache";
import {redirect} from "next/navigation";
import {getDashboard,getHumanGates,getProjectDetail,getProjectRecoveryStatus,
 getProjectStateContext,getProjectExecutionControl,getProjectWorkObservation,getProjectDatabases,
 commandProjectExecution,restartBlockedProjectWork} from "../lib/control-plane";
import {summarizeProductExperience} from "../lib/product-experience-model";
import {getPrimaryCostPolicyView} from "../lib/primary-cost-policy";
import {ownerFinancialBlocker} from "../lib/owner-financial-blocker";
import {ProjectControlForm} from "./projects/[key]/control-confirm";
import {ActionLink,PageHeader} from "./ui";

// All controls call authenticated Control Plane RPCs server-side.
// A successfully recorded intent is not evidence that a worker has started.
async function ownerControl(formData:FormData){
 "use server";
 const key=String(formData.get("project_key")||"");
 const command=String(formData.get("command")||"");
 const id=String(formData.get("command_id")||"");
 const version=String(formData.get("version")||"");
 if(!/^[a-z0-9][a-z0-9-]{0,63}$/.test(key)||
    !["start","pause","resume","stop","restart"].includes(command)||
    !/^(0|[1-9][0-9]*)$/.test(version))throw new Error("Comando inválido.");
 const receipt=await commandProjectExecution(key,
  command as "start"|"pause"|"resume"|"stop"|"restart",Number(version),id);
 revalidatePath("/");
 revalidatePath("/projects/"+key);
 redirect("/?control="+(receipt.wakeStatus==="requested"?"requested":"recorded"));
}
async function ownerRestartBlocked(formData:FormData){
 "use server";
 const key=String(formData.get("project_key")||"");
 const version=String(formData.get("version")||"");
 const id=String(formData.get("command_id")||"");
 if(!/^[a-z0-9][a-z0-9-]{0,63}$/.test(key)||
    !/^(0|[1-9][0-9]*)$/.test(version))throw new Error("Comando inválido.");
 const receipt=await restartBlockedProjectWork(key,Number(version),id);
 revalidatePath("/");
 revalidatePath("/projects/"+key);
 redirect("/?control="+(receipt.wakeStatus==="requested"?"recovery_requested":"recovery_recorded"));
}
const feedback:Record<string,string>={
 requested:"Comando registrado. A Factory vai verificar o desenvolvimento.",
 recorded:"Comando registrado. A Factory ainda precisa confirmar a execução.",
 recovery_requested:"Reinício solicitado. A Factory recebeu o pedido de recuperação.",
 recovery_recorded:"Reinício registrado. A Factory ainda precisa assumir o trabalho."
};
export default async function Home({searchParams}:{
 searchParams?:Promise<{control?:string}>;
}){
 const [dashboard,gates,query]=await Promise.all([
  getDashboard(),getHumanGates(50,true),searchParams??Promise.resolve({control:undefined})
 ]);
 const pending=gates.filter(g=>g.actionable&&g.status==="pending");
 const products=await Promise.all(dashboard.projects.map(async project=>{
  const detail=await getProjectDetail(project.key);
  if(!detail)return{project,detail:null,recovery:null,databaseLink:"unavailable" as const,
   control:{state:"unavailable" as const,version:-1,generation:0},
   view:summarizeProductExperience({project,detail:null,
    context:{objective:null,snapshot:null},recovery:null,
    control:{state:"unavailable",version:-1,generation:0},
    work:{kind:"unavailable",runId:null,at:null},
    actionableGates:pending.filter(g=>g.projectKey===project.key).length})
  };
  const [context,recovery,control,work,databases]=await Promise.all([
   getProjectStateContext(detail.id),getProjectRecoveryStatus(detail.id),
   getProjectExecutionControl(detail.id),
   getProjectWorkObservation(detail.tasks.map(t=>String(t.id))),
   getProjectDatabases(detail.id).then(rows=>Array.isArray(rows)?rows:null).catch(()=>null)
  ]);
  const databaseLink=databases===null?"unavailable" as const:
   databases.length>0?"registered" as const:"none" as const;
  return{project,detail,recovery,control,databaseLink,view:summarizeProductExperience({
   project,detail,context,recovery,control,work,
   actionableGates:pending.filter(g=>g.projectKey===project.key).length
  })};
 }));
 // One complete-ledger read for the whole portfolio, only when an audited
 // pending run indicates a financial blocker. No per-project price guesses.
 const financialPolicy=products.some(p=>p.detail?.wakeEvidence?.blockerCode==="budget_exhausted")
  ?await getPrimaryCostPolicyView():null;
 const ownerProducts=products.filter(p=>!p.detail?.isInternalRecord);
 const active=ownerProducts.filter(p=>!["draft","paused","stopped"].includes(p.control.state));
 const inactive=ownerProducts.filter(p=>["draft","paused","stopped"].includes(p.control.state));
 const internal=products.filter(p=>p.detail?.isInternalRecord);
 const renderProduct=(entry:typeof products[number])=>{
  const {project,view,control,recovery}=entry;
  const financial=ownerFinancialBlocker(entry.detail,financialPolicy);
  const key=project.key;
  const path="/projects/"+encodeURIComponent(key);
  const needsDecision=view.tone==="decision";
  // A historical blocked repair is restartable only until a durable
  // continuation is already present. Never offer a no-op retry button.
  const canRestart=control.state==="running"&&recovery?.status==="blocked"&&view.tone==="blocked";
  const lifecycleCommand=control.state==="draft"?"start":
   control.state==="paused"?"resume":control.state==="stopped"?"restart":null;
  const lifecycleLabel=control.state==="draft"?"Iniciar":control.state==="paused"?"Retomar":"Reiniciar";
  const status=financial?financial.title:needsDecision?"Aguardando sua decisão":
   control.state==="draft"?"Não iniciado":control.state==="paused"?"Pausado":
   control.state==="stopped"?"Desativado":view.label;
  const summary=financial?financial.description:view.headline;
  const nextStep=financial?"Revisar o limite antes de solicitar trabalho pago":view.nextTitle;
  const nextExplanation=financial?financial.detail:view.nextDetail;
  const responsible=needsDecision?"Você":financial?"Você":
   ["draft","paused","stopped"].includes(control.state)?"Você":"Factory";
  const ownerInstruction=needsDecision?"Há uma decisão de produto para revisar.":
   financial?"O limite financeiro depende da sua decisão.":
   ["draft","paused","stopped"].includes(control.state)?"Você decide quando iniciar ou retomar.":
   "Nenhuma aprovação sua está pendente neste projeto.";
  const manageCommand=control.state==="running"&&Number.isSafeInteger(control.version)&&control.version>=0;
  const canManage=!needsDecision&&(manageCommand||Boolean(!financial&&(canRestart||lifecycleCommand)));
  return <article className={"ownerProductItem owner-"+(financial?"blocked":view.tone)} key={key}>
   <div className="ownerProductIdentity">
    <div className="ownerProductHeading">
     <h3>{project.name}</h3>
     <strong className={"ownerProductState owner-"+(financial?"blocked":view.tone)}>{status}</strong>
    </div>
    <p className="ownerProductSummary">{summary}</p>
    <p className="ownerProductExplanation">{financial?financial.detail:view.description}</p>
    <dl className="ownerProductFacts" aria-label={"Situação comprovada de "+project.name}>
     <div><dt>Último marco registrado</dt><dd>{view.recordedMilestone}</dd></div>
     <div><dt>Produto em funcionamento</dt><dd>{view.readinessLabel}</dd></div>
     <div><dt>Execução agora</dt><dd>{view.executionLabel}</dd></div>
    </dl>
    <div className="ownerProductNext">
     <div>
      <span>O que precisa acontecer agora</span>
      <strong>{nextStep}</strong>
      <p>{nextExplanation}</p>
     </div>
     <div>
      <span>Quem precisa agir</span>
      <strong>{responsible}</strong>
      <p>{ownerInstruction}</p>
     </div>
    </div>
    {view.readinessGapCount!==null&&view.readinessGapCount>0?
     <p className="ownerProductMissing">Último levantamento: {view.readinessGapCount} {view.readinessGapCount===1?"área ainda sem avaliação de prontidão":"áreas ainda sem avaliação de prontidão"}.</p>:null}
    {entry.databaseLink==="none"?
     <p className="ownerProductMissing">Banco de dados: nenhum vínculo registrado na Factory. Isso não comprova que o produto não tenha um banco externo.</p>:null}
    {entry.databaseLink==="unavailable"?
     <p className="ownerProductMissing">Conexão com banco: cadastro não pôde ser verificado.</p>:null}
   </div>
   <div className="ownerProductActions">
    {needsDecision?<Link className="ownerDecisionLink" href="/gates">Revisar decisão</Link>:null}
    {financial?<Link className="ownerFinanceAction" href={financial.href}>{financial.actionLabel}</Link>:null}
    <Link href={path} className="ownerProductDetail">Abrir projeto e acompanhar</Link>
    <details className="ownerProductEvidence">
     <summary>Ver evidências e histórico</summary>
     <dl>
      <div><dt>Fase no cadastro</dt><dd>{view.declaredStageLabel} — não certifica a entrega</dd></div>
      <div><dt>Vínculo de banco na Factory</dt><dd>{entry.databaseLink==="registered"?"Cadastrado":entry.databaseLink==="none"?"Não cadastrado":"Não verificável"}</dd></div>
     </dl>
     <p>{view.proof}</p>
     <p>{view.execution}.</p>
    </details>
    {canManage?<details className="ownerProjectControls">
     <summary>Gerenciar execução</summary>
     <p>Estes comandos alteram o controle administrativo; não comprovam que existe trabalho executando.</p>
     <div className="ownerProjectControlButtons">
      {!needsDecision&&!financial&&canRestart?
       <ProjectControlForm projectKey={key} command="restart" label="Reiniciar"
        version={control.version} action={ownerRestartBlocked} recovery/>:null}
      {!needsDecision&&!financial&&!canRestart&&lifecycleCommand?
       <ProjectControlForm projectKey={key} command={lifecycleCommand}
        label={lifecycleLabel} version={control.version} action={ownerControl}/>:null}
      {!needsDecision&&!financial&&manageCommand&&!canRestart?
       <ProjectControlForm projectKey={key} command="pause" label="Pausar"
        version={control.version} action={ownerControl}/>:null}
      {!needsDecision&&manageCommand?
       <ProjectControlForm projectKey={key} command="stop" label="Parar"
        version={control.version} action={ownerControl}/>:null}
      {!needsDecision&&!financial&&manageCommand?
       <Link href={path+"/request"} className="ownerProductChange">Solicitar alteração</Link>:null}
     </div>
    </details>:null}
   </div>
  </article>;
 };
 return <>
  <PageHeader eyebrow="Sua esteira" title="Meus produtos"
   subtitle="A Factory desenvolve. Você inicia, pausa, reinicia ou pede mudanças."
   actions={<ActionLink href="/projects/new" variant="primary">Novo produto</ActionLink>}/>
  {feedback[query.control||""]?
   <p className="ownerCommandNotice" role="status">{feedback[query.control||""]}</p>:null}
  {pending.length>0?<section className="ownerHumanGates" aria-labelledby="human-inbox-title">
   <h2 id="human-inbox-title">{pending.length} {pending.length===1?"decisão pendente":"decisões pendentes"}</h2>
   <Link href="/gates">Revisar decisões</Link>
  </section>:null}
  <section className="portfolio" aria-labelledby="portfolio-title">
   <h2 id="portfolio-title" className="ownerPortfolioTitle">Andamento dos produtos</h2>
   <p className="ownerPortfolioIntro">O que já foi registrado, o que falta comprovar e quem pode agir agora.</p>
   <div className="productBoard ownerProductList">
    {active.length?active.map(renderProduct):<p className="ownerEmpty">Nenhum produto com processamento habilitado.</p>}
   </div>
   {inactive.length>0?<details className="portfolioSecondary">
    <summary>Produtos pausados ou não iniciados ({inactive.length})</summary>
    <div className="productBoard ownerProductList">{inactive.map(renderProduct)}</div>
   </details>:null}
   {internal.length>0?<details className="portfolioSecondary">
    <summary>Registros técnicos ({internal.length})</summary>
    <div className="productBoard ownerProductList">{internal.map(renderProduct)}</div>
   </details>:null}
  </section>
 </>;
}
