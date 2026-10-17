import {cookies} from "next/headers";
import {redirect} from "next/navigation";
import {notFound} from "next/navigation";
import {revalidatePath} from "next/cache";
import {getProjectContinuationContext,getProjectContinuationHistory,getProjectDatabases,getProjectDetail,getProjectExecutionTeamPlan,getProjectGitHubAccess,getProjectOperations,getProjectStateContext,requestProjectGitHubRecheck,enqueueProjectReconciliation,getProjectExecutionControl,commandProjectExecution} from "../../../lib/control-plane";
import {isSupabaseOAuthConfigured} from "../../../lib/supabase-oauth";
import {getGitHubAppStatus} from "../../../lib/github-app";
import {RepositoryLinkForm} from "./repository-link-form";
import {ProjectControlSubmit} from "./control-confirm";
import {requireConsoleOperator} from "../../../lib/auth-server";
import {ActionLink,EmptyState,humanizeStatus,MetricCard,PageHeader,SectionHeader,StatusPill} from "../../ui";

const stages=["discovery","specification","planning","implementation","review","validation","preview","human_gate","release","operations"];
const stageLabels=["Descoberta","Especificação","Plano","Implementação","Revisão","Testes / Avaliações","Prévia","Aprovação","Liberação","Operação"];
const macroStages=[
 {label:"Entender",detail:"Descoberta e especificação",members:["discovery","specification"]},
 {label:"Planejar",detail:"Plano técnico e backlog",members:["planning"]},
 {label:"Construir",detail:"Implementação e revisão",members:["implementation","review"]},
 {label:"Validar",detail:"Testes, avaliações e prévia",members:["validation","preview"]},
 {label:"Liberar",detail:"Aprovação, release e operação",members:["human_gate","release","operations"]},
];
function macroStageIndex(stage:string){return macroStages.findIndex(item=>item.members.includes(stage))}
function display(value:unknown){return typeof value==="string"?value:JSON.stringify(value)}
function nextAction(stage:string,hasPendingDatabase:boolean,activeTasks:number){
 if(hasPendingDatabase)return {title:"Conectar o banco de dados",body:"A Factory está aguardando a conexão mínima necessária para reconciliar e executar o trabalho com evidência real.",href:"#databases",label:"Ver banco de dados"};
 if(stage==="human_gate")return {title:"Tomar a decisão pendente",body:"A automação chegou a um gate humano. Revise o motivo e decida antes de a Factory continuar.",href:"/gates",label:"Abrir aprovações"};
 if(stage==="release")return {title:"Verificar as condições do release",body:"A etapa registrada não comprova CI, auditoria ou Preview. Verifique as evidências antes de qualquer merge humano de produção.",href:"/deployments",label:"Ver implantações"};
 if(stage==="operations")return {title:"Acompanhar a operação",body:"O projeto já está em operação. Use as evidências e implantações para acompanhar saúde e novos trabalhos.",href:"/deployments",label:"Ver implantações"};
 if(activeTasks===0)return {title:"Nenhuma ação necessária agora",body:"Não há tarefas abertas neste projeto. Acompanhe novas evidências ou inicie um novo trabalho quando necessário.",href:"/projects",label:"Voltar aos projetos"};
 if(["discovery","specification"].includes(stage))return {title:"Descoberta registrada; verificar execução",body:"O projeto pode estar apenas enfileirado. O processamento depende de um worker ativo e, para etapas semânticas, de autenticação, quota e orçamento de modelo aprovados. A existência da tarefa não comprova que a Descoberta começou.",href:"/runs",label:"Ver execuções"};
 if(stage==="planning")return {title:"Aguardar o plano de execução",body:"A Factory está decompondo o trabalho, escolhendo agentes e organizando dependências. Nenhuma escolha técnica manual é necessária.",href:"/queue",label:"Ver fila"};
 if(["implementation","review"].includes(stage))return {title:"Acompanhar construção e revisão",body:"A execução está com os agentes e revisores. Use a fila para acompanhar o trabalho sem interferir no roteamento.",href:"/queue",label:"Ver fila"};
 return {title:"Acompanhar validação e prévia",body:"A Factory está validando qualidade e preparando evidências antes do gate humano de produção.",href:"/runs",label:"Ver execuções"};
}

const supabaseMessages:Record<string,{status:string;message:string}>={
 connected:{status:"success",message:"Supabase conectado e acesso somente leitura verificado."},
 oauth_invalid:{status:"failed",message:"A autorização do Supabase expirou ou não corresponde ao fluxo iniciado. Tente conectar novamente."},
 control_plane_unavailable:{status:"failed",message:"O Control Plane não estava disponível para concluir a conexão."},
 project_lookup_failed:{status:"failed",message:"Não foi possível localizar o projeto durante a conexão com o Supabase."},
 project_missing:{status:"failed",message:"O projeto não foi encontrado durante a conexão com o Supabase."},
 lookup_failed:{status:"failed",message:"Não foi possível localizar o vínculo de banco durante a conexão."},
 project_ref_missing:{status:"failed",message:"O vínculo do Supabase não possui project_ref válido."},
 verification_failed:{status:"failed",message:"A autorização retornou, mas a verificação do acesso não foi concluída. Nenhuma ampliação de permissão foi aplicada."},
};

const githubAppMessages:Record<string,{status:string;message:string}>={
 registered:{status:"success",message:"GitHub App da Factory registrada. Agora instale a App no repositório desejado e verifique o acesso."},
 installed:{status:"attention",message:"O GitHub informou uma instalação/atualização. A Factory ainda valida a instalação pelo próprio GitHub antes de confiar nela."},
 verified:{status:"success",message:"GitHub App verificada para este projeto com token temporário e capacidades mínimas."},
 blocked:{status:"failed",message:"A GitHub App foi encontrada, mas não possui todas as capacidades mínimas exigidas para este projeto."},
 manifest_invalid:{status:"failed",message:"O retorno do registro da GitHub App não corresponde ao fluxo iniciado. Nenhum segredo foi salvo."},
 registration_failed:{status:"failed",message:"Não foi possível concluir o registro da GitHub App. Nenhum segredo foi exposto ao navegador."},
 verification_failed:{status:"failed",message:"Não foi possível verificar a instalação da GitHub App para este projeto."},
};

const repoLinkMessages:Record<string,{status:string;message:string}>={
 linked:{status:"success",message:"Repositório privado vinculado; permissões da GitHub App verificadas pelo servidor."},
 not_ready:{status:"attention",message:"Ainda não foi possível validar o repositório privado, a branch main e as permissões da GitHub App. Crie o repositório com README e autorize a App antes de tentar novamente."},
 already_bound:{status:"failed",message:"O repositório já está associado a outro projeto ou este projeto possui outro vínculo. Nenhuma alteração foi feita."},
 not_eligible:{status:"failed",message:"A vinculação está disponível apenas para projetos novos ativos."},
 verify_pending:{status:"attention",message:"O repositório foi encontrado, mas a verificação final ainda não foi concluída. Consulte o estado GitHub abaixo ou tente verificar novamente."},
 unavailable:{status:"failed",message:"O Control Plane não conseguiu registrar o vínculo. Nenhuma execução paga foi solicitada."},
};

const githubCapabilityLabels:Record<string,string>={
 metadata_read:"Repositório conectado",
 contents_read:"Leitura do código",
 contents_write:"Criar branch / commit",
 issues_read:"Issues · leitura",
 issues_write:"Issues · escrita",
 pull_requests_read:"Pull Requests · leitura",
 pull_requests_write:"Pull Requests · escrita",
 actions_read:"Actions / logs",
 commit_statuses_read:"Commit Statuses",
 checks_read:"Checks API · leitura",
 ci_evidence_read:"Checks / evidência de CI",
};
function githubCapabilityLabel(status:string){return status==="verified"?"Verificado":status==="missing"?"Permissão faltando":status==="unverified"?"Ainda não verificado":humanizeStatus(status)}
async function controlProject(formData:FormData){
 "use server";
 const key=String(formData.get("project_key")||"");
 const cmd=String(formData.get("command")||"");
 const version=Number(formData.get("version"));
 const id=String(formData.get("command_id")||"");
 if(!["start","pause","resume","stop","restart"].includes(cmd))throw new Error("Comando não permitido.");
 await commandProjectExecution(key,cmd as "start"|"pause"|"resume"|"stop"|"restart",version,id);
 revalidatePath("/projects/"+key);
}
async function reconcileProject(formData:FormData){
 "use server";
 const projectKey=String(formData.get("project_key")||"");
 if(!projectKey)throw new Error("Projeto inválido para reconciliação.");
 const result=await enqueueProjectReconciliation(projectKey);
 revalidatePath("/projects/"+projectKey);
 redirect("/projects/"+projectKey+"?reconciliation="+(result.created?"enqueued":"already_active"));
}
async function requestGitHubRecheck(formData:FormData){
 "use server";
 const projectId=String(formData.get("project_id")||"");
 const projectKey=String(formData.get("project_key")||"");
 if(!projectId||!projectKey)throw new Error("Projeto inválido para revalidação GitHub.");
 await requestProjectGitHubRecheck(projectId);
 revalidatePath("/projects/"+projectKey);
}

function productWorkerBlockerMessage(reason:string){
 const reasons:Record<string,string>={
  model_disabled:"Modelo principal desabilitado na configuração do GitHub Actions. A tarefa permanece preservada, sem consumo de API.",
  primary_auth_missing:"Autenticação do modelo principal indisponível ou incompleta no runner.",
  budget_not_configured:"Orçamento ou reserva por chamada ausente ou inválida.",
  cost_ledger_unavailable:"Não foi possível verificar com segurança o ledger de custos da Factory.",
  paid_cost_unknown:"O ledger contém custo pago desconhecido; nenhuma nova execução paga é permitida.",
  budget_exhausted:"Saldo do orçamento interno insuficiente para a reserva obrigatória.",
 };
 return reasons[reason]||"Motivo de bloqueio não reconhecido.";
}

export default async function Project({params,searchParams}:{params:Promise<{key:string}>;searchParams:Promise<{supabase?:string;github_app?:string;setup_action?:string;reconciliation?:string;wake_recovery?:string;repo_link?:string}>}){
 const [{key},query,operator]=await Promise.all([params,searchParams,requireConsoleOperator()]);
 if(query.github_app==="installed"||query.setup_action==="install"||query.setup_action==="update"){
  const jar=await cookies();
  const project=jar.get("factory_github_app_install_project")?.value||"";
  if(project===key&&/^[a-z0-9][a-z0-9-]{0,63}$/.test(project))redirect("/api/integrations/github-app/verify?project="+encodeURIComponent(project));
 }
 const p=await getProjectDetail(key);if(!p)notFound();
 const [ops,state,databases,teamPlan,githubAccess,githubAppStatus,continuation,continuationHistory,executionControl]=await Promise.all([getProjectOperations(p.id),getProjectStateContext(p.id),getProjectDatabases(p.id),getProjectExecutionTeamPlan(p.id),getProjectGitHubAccess(p.id,p.repository),getGitHubAppStatus(),getProjectContinuationContext(p.id),getProjectContinuationHistory(p.id),getProjectExecutionControl(p.id)]);
 const activeTasks=p.tasks.filter(t=>!["completed","cancelled","failed","merged"].includes(t.status));const oauthReady=isSupabaseOAuthConfigured();
 const hasPendingDatabase=databases.some(db=>db.status==="pending_access");
 const observedBlocker=p.pendingRun&&p.wakeEvidence?.blockerCode?p.wakeEvidence.blockerCode:null;
 const action=observedBlocker?{
   title:observedBlocker==="budget_exhausted"?"Execução pausada: limite do modelo atingido":"Execução pausada: dependência do modelo",
   body:productWorkerBlockerMessage(observedBlocker)+" O trabalho permanece preservado na fila; nenhum novo run precisa ser criado.",
   href:observedBlocker==="budget_exhausted"?"/usage":"/configuration",
   label:observedBlocker==="budget_exhausted"?"Ver orçamento e uso":"Ver configuração",
 }:!p.repository&&p.kind==="greenfield"?{
  title:"Vincular repositório GitHub",
  body:"O projeto possui planejamento, mas precisa de um repositório privado autorizado pela GitHub App para iniciar a implementação. O orçamento do modelo permanece independente.",
  href:"#repository-setup",label:"Preparar repositório",
 }:nextAction(p.stage,hasPendingDatabase,activeTasks.length);
 const currentMacro=macroStageIndex(p.stage);
 const supabaseNotice=query.supabase?supabaseMessages[query.supabase]:undefined;
 const githubAppNotice=query.github_app?githubAppMessages[query.github_app]:undefined;
 const repositoryNotice=query.repo_link?repoLinkMessages[query.repo_link]:undefined;
 const reconciliationNotice=query.reconciliation==="enqueued"?"Reconciliação enfileirada. A Factory vai atualizar o estado do projeto antes de planejar o trabalho restante.":query.reconciliation==="already_active"?"Já existe uma reconciliação ativa para este projeto; nenhuma duplicata foi criada.":undefined;
 const previewPolicy=p.previewPolicy;
 const previewConfigured=Boolean(previewPolicy&&(previewPolicy.required!==null||previewPolicy.provider||previewPolicy.mode));
 const humanActionNeeded=Boolean(observedBlocker||hasPendingDatabase||(!p.repository&&p.kind==="greenfield")||["human_gate","release"].includes(p.stage));
 const integrationNeedsAttention=!previewConfigured||(githubAccess!==null&&githubAccess.status!=="ready");
 return <>
  <PageHeader eyebrow="Projeto" title={p.name} subtitle={p.repository||p.key} actions={<><ActionLink href={"/projects/"+p.key+"/request"} variant={humanActionNeeded?"secondary":"primary"}>Solicitar alteração</ActionLink><details className="projectMoreActions"><summary>Mais opções</summary><div className="projectMoreActionsMenu"><ActionLink href="/queue">Ver fila de trabalho</ActionLink>{p.kind==="existing"?<form action={reconcileProject}><input type="hidden" name="project_key" value={p.key}/><button type="submit" className="linkButton">Reconciliar projeto</button></form>:null}</div></details></>}/>
  <section className="section" aria-label="Controle de execução do projeto">
   <div className="card denseStack"><strong>Execução do projeto: {executionControl.state==="draft"?"Não iniciado":executionControl.state==="running"?"Em execução":executionControl.state==="pausing"?"Pausando":executionControl.state==="paused"?"Pausado":executionControl.state==="stopping"?"Parando":executionControl.state==="unavailable"?"Aguardando ativação segura":"Parado"}</strong>
    <p>O cadastro não inicia o desenvolvimento. Somente você pode iniciar, pausar, retomar, parar ou reiniciar.</p>
    <div className="actions">{([
     ["draft","start","Iniciar projeto"],["running","pause","Pausar"],["running","stop","Parar"],
     ["paused","resume","Retomar"],["paused","stop","Parar"],["stopped","restart","Reiniciar"]
    ] as const).filter(([state])=>state===executionControl.state).map(([,command,label])=>
      <form action={controlProject} key={command}>
       <input type="hidden" name="project_key" value={p.key}/>
       <input type="hidden" name="command" value={command}/>
       <input type="hidden" name="version" value={executionControl.version}/>
       <input type="hidden" name="command_id" value={crypto.randomUUID()}/>
       <ProjectControlSubmit command={command} label={label}/>
      </form>
    )}</div>
    {["pausing","stopping"].includes(executionControl.state)?<p role="status">Aguardando conclusão segura dos trabalhos em andamento. Nenhuma tarefa nova deve ser iniciada.</p>:null}
   </div>
  </section>
  {supabaseNotice?<div className={supabaseNotice.status==="success"?"card noticeCard success":"card noticeCard danger"} role="status"><StatusPill status={supabaseNotice.status}/><span>{supabaseNotice.message}</span></div>:null}
  {reconciliationNotice?<div className="card noticeCard success" role="status"><StatusPill status="success"/><span>{reconciliationNotice}</span></div>:null}
  {githubAppNotice?<div className={githubAppNotice.status==="success"?"card noticeCard success":githubAppNotice.status==="attention"?"card noticeCard":"card noticeCard danger"} role="status"><StatusPill status={githubAppNotice.status}/><span>{githubAppNotice.message}</span></div>:null}
  {repositoryNotice?<div className={repositoryNotice.status==="success"?"card pendingProjectNotice success":repositoryNotice.status==="attention"?"card pendingProjectNotice":"card pendingProjectNotice danger"} role="status"><strong>Repositório GitHub:</strong><p>{repositoryNotice.message}</p></div>:null}
  {!p.repository&&p.kind==="greenfield"?<section className="section" id="repository-setup">
   <SectionHeader title="Preparar repositório para implementação" action={<StatusPill status="attention" label="Ação administrativa"/>}/>
   <div className="card denseStack">
    <p>O Service Desk precisa de um repositório GitHub próprio antes de receber issues, branches e código. A Factory não criará repositórios usando credenciais que não possua, nem ampliará a instalação da GitHub App sem sua autorização.</p>
    <p><strong>Nome previsto:</strong> <code>{"leandrosilveiradepaula/"+p.key}</code>. Crie um repositório <strong>privado</strong>, com README e branch <code>main</code>.</p>
    <div className="actions">
     <a className="linkButton primary" href={"https://github.com/new?name="+encodeURIComponent(p.key)+"&visibility=private"} target="_blank" rel="noreferrer">1. Criar repositório privado no GitHub</a>
     <a className="linkButton" href="https://github.com/settings/installations" target="_blank" rel="noreferrer">2. Autorizar repositório na GitHub App</a>
    </div>
    {operator.role==="admin"?<RepositoryLinkForm projectKey={p.key}/>:<p className="muted">Somente um administrador pode concluir a vinculação.</p>}
    <p className="muted">O servidor exige repositório privado, identidade exata, branch inicializada e token temporário com permissões de implementação. Esta ação não inicia modelos pagos nem libera merge automático.</p>
   </div>
  </section>:null}
  {query.wake_recovery?<div className="card noticeCard" role="status"><strong>Recuperação do worker:</strong> {query.wake_recovery==="requested"?"Solicitação aceita pelo GitHub; aguarde a execução real.":query.wake_recovery==="cooldown"?"Já houve uma tentativa recente. Aguarde pelo menos 15 minutos.":query.wake_recovery==="unconfigured"?"A integração de disparo não está configurada para a Factory.":query.wake_recovery==="not_eligible"?"Não foi encontrada uma execução inicial pendente elegível.":query.wake_recovery==="failed"?"Falha no acionamento. A tarefa continua preservada.":"Não foi possível verificar a recuperação."}</div>:null}
  {p.pendingRun&&p.stage==="discovery"?<div className="card pendingProjectNotice" role="status">
   <div className="badgeLine"><StatusPill status="queued" label="Aguardando execução"/><strong>Descoberta ainda não iniciada</strong></div>
   <p>O Control Plane preservou a execução <code>{p.pendingRun.id.slice(0,8)}</code>, ainda com {p.pendingRun.attemptCount} tentativas. Criar o projeto não significa que um worker já iniciou o processamento.</p>
   {p.wakeEvidence?.wakeStatus==="requested"?<p>O Console registrou um pedido de acionamento aceito pelo GitHub. Isso não comprova que o worker executou.</p>:p.wakeEvidence?.wakeStatus==="failed"?<p>O Console registrou falha ao solicitar o acionamento imediato. A execução permanece na fila para recuperação.</p>:p.wakeEvidence?.wakeStatus==="unconfigured"?<p>O Console não encontrou uma identidade autorizada para o acionamento imediato. A execução permanece na fila.</p>:<p>Não há evidência registrada de acionamento imediato para esta execução.</p>}
   {p.wakeEvidence?.workerObservedAt?<p>Última observação global do scheduler: {new Date(p.wakeEvidence.workerObservedAt).toLocaleString("pt-BR")}. {p.wakeEvidence.productQueueDetected?"A fila de trabalho de produto foi detectada; isso não confirma que esta execução foi assumida.":"Nenhum trabalho de produto foi indicado nessa observação."} O botão Iniciar desenvolvimento solicita o acionamento imediato do worker existente; não ignora bloqueios de modelo, quota ou orçamento.</p>:<p>Ainda não existe observação do scheduler posterior ao enfileiramento.</p>}
   {p.wakeEvidence?.blockerCode?<p role="status"><strong>Bloqueio registrado para esta execução:</strong> {productWorkerBlockerMessage(p.wakeEvidence.blockerCode)} {p.wakeEvidence.blockedAt?<span className="muted">Evidência de {new Date(p.wakeEvidence.blockedAt).toLocaleString("pt-BR")}{p.wakeEvidence.workerRunId?" · Actions #"+p.wakeEvidence.workerRunId:""}. O worker não assumiu o run.</span>:null}</p>:null}
   <div className="actions"><ActionLink href="/runs">Ver execuções</ActionLink>{operator.role==="admin"?<form method="POST" action="/api/projects/wake-recovery"><input type="hidden" name="project_key" value={p.key}/><button className="linkButton" type="submit">Iniciar desenvolvimento</button></form>:null}</div>
  </div>:null}
  {p.pendingRun&&p.stage!=="discovery"&&observedBlocker?<div className="card pendingProjectNotice" role="status" aria-live="polite">
   <div className="badgeLine"><StatusPill status="blocked" label="Execução pausada"/><strong>{observedBlocker==="budget_exhausted"?"Orçamento do modelo insuficiente":"Execução aguardando dependência do modelo"}</strong></div>
   <p><strong>Motivo registrado:</strong> {productWorkerBlockerMessage(observedBlocker)} A execução <code>{p.pendingRun.id.slice(0,8)}</code> não foi assumida e permanece na fila, com {p.pendingRun.attemptCount} tentativas.</p>
   {p.wakeEvidence?.blockedAt?<p className="muted">Evidência no Control Plane em {new Date(p.wakeEvidence.blockedAt).toLocaleString("pt-BR")}{p.wakeEvidence.workerRunId?" · Actions #"+p.wakeEvidence.workerRunId:""}. Não houve chamada ao modelo nesta tentativa.</p>:null}
   <div className="actions"><ActionLink href="/usage">Ver modelos e consumo</ActionLink><ActionLink href={"/runs/"+p.pendingRun.id}>Ver execução</ActionLink></div>
  </div>:null}
  <div className="projectOrientation">
   <div>
    <div className="macroLifecycle" aria-label="Ciclo do produto em cinco macroetapas">
     {macroStages.map((item,i)=><div className={"macroStage "+(i<currentMacro?"done":i===currentMacro?"current":"")} key={item.label}><span>Etapa {i+1}</span><strong>{item.label}</strong><small>{item.detail}</small></div>)}
    </div>
    <div className="microStageLine"><span>Etapa detalhada atual:</span><StatusPill status={p.stage} tone="accent"/><span className="muted">{stageLabels[stages.indexOf(p.stage)]||humanizeStatus(p.stage)}</span></div>
   </div>
   <aside className={humanActionNeeded?"nextActionCard needsHuman":"nextActionCard routine"} aria-label="Próxima etapa">
    <span className="detailLabel">{humanActionNeeded?"O que precisa da sua atenção":"A Factory está cuidando desta etapa"}</span>
    <h2>{action.title}</h2>
    <p>{action.body}</p>
    <div className="actions"><ActionLink href={action.href} variant={humanActionNeeded?"primary":"secondary"}>{action.label}</ActionLink></div>
   </aside>
  </div>
  <div className="grid compact projectPrimaryMetrics">
   <MetricCard label="Etapa do fluxo" value={currentMacro>=0?(currentMacro+1)+" de 5":"—"} note="Posição registrada, não prontidão ou release verificado."/>
   <MetricCard label="Tarefas abertas" value={activeTasks.length} note={p.tasks.length+" no total"}/>
   <MetricCard label="Evidências" value={ops.evaluations+ops.deployments} note={ops.evaluations+" avaliações · "+ops.deployments+" implantações"}/>
  </div>
  <section className="section" id="product-readiness"><SectionHeader title="Prontidão global do produto" action={<StatusPill status={p.productReadiness.ready?"verified":p.productReadiness.status==="not_assessed"?"unverified":"blocked"} label={p.productReadiness.ready?"Auditoria aprovada":p.productReadiness.status==="not_assessed"?"Não avaliado":"Produto não pronto"}/>}/>
   <div className="card denseStack">
    <div className="badgeLine"><strong>{p.productReadiness.ready?"A avaliação global passou para o SHA registrado. Isso não comprova que o HEAD atual permanece igual nem libera produção.":p.productReadiness.status==="not_assessed"?"Nenhuma auditoria global de produto foi registrada ainda.":"Existem domínios ou blockers que impedem declarar o produto pronto."}</strong>{p.productReadiness.assessedCommit?<span className="muted mono">{p.productReadiness.assessedCommit.slice(0,12)}</span>:null}</div>
    {p.productReadiness.blockers.length?<div><span className="detailLabel">Bloqueios que impedem a liberação</span><ul>{p.productReadiness.blockers.map((item,i)=><li key={i}>{item}</li>)}</ul></div>:null}
    <details className="readinessEvidence"><summary>Ver avaliação detalhada e evidências</summary>
    {Object.keys(p.productReadiness.domains).length?<div className="detailGrid">{Object.entries(p.productReadiness.domains).map(([key,value])=><div className="detailItem" key={key}><span className="detailLabel">{humanizeStatus(key)}</span><StatusPill status={value.status} label={humanizeStatus(value.status)}/>{value.verification_state?<span className="muted">verificação · {humanizeStatus(value.verification_state)}</span>:null}{value.coverage?.length?<span className="muted">cobertura · {value.coverage.map(humanizeStatus).join(" · ")}</span>:null}{value.reason?<span className="muted">{value.reason}</span>:null}</div>)}</div>:<p className="muted" style={{margin:0}}>A Factory não infere prontidão a partir de CI, Preview, release ou ausência de issues. É necessária uma avaliação global explícita.</p>}
    </details>
    <div className="badgeLine"><span className="muted">{p.productReadiness.assessmentRef||"Sem assessment_ref"}</span>{p.productReadiness.createdAt?<span className="muted">avaliado em {new Date(p.productReadiness.createdAt).toLocaleString("pt-BR")}</span>:null}</div>
   </div>
  </section>
  {continuation?<section className="section" id="latest-request"><SectionHeader title="Último pedido" action={<span className="muted">{new Date(continuation.requestedAt).toLocaleString("pt-BR")}</span>}/>
   <div className="card denseStack">
    <p style={{margin:0}}>{continuation.summary}</p>
    <div className="badgeLine"><StatusPill status="verified" label="Registrado no projeto"/><span className="muted">{continuation.attachmentCount+" anexo"+(continuation.attachmentCount===1?"":"s")}</span></div>
    {continuation.attachments.length?<div className="compactList">{continuation.attachments.map(file=><div className="compactRow" key={file.id}><strong>{file.name}</strong><div className="badgeLine"><span className="muted">{file.mimeType+" · "+(file.sizeBytes/1024/1024).toFixed(2)+" MB"}</span><a className="linkButton" href={"/api/projects/"+encodeURIComponent(p.key)+"/attachments/"+encodeURIComponent(file.id)}>Baixar</a></div></div>)}</div>:continuation.attachmentCount?<p className="muted" style={{margin:0}}>Os anexos foram registrados, mas a listagem privada não está disponível neste momento.</p>:null}
   </div>
  </section>:null}
  {continuationHistory.length>1?<details className="projectTechnicalDetails">
   <summary><span><strong>Pedidos anteriores</strong><small>Histórico durável registrado pela Factory.</small></span><span className="muted">{continuationHistory.length-1} pedido{continuationHistory.length===2?"":"s"} anterior{continuationHistory.length===2?"":"es"}</span></summary>
   <div className="projectTechnicalBody"><div className="timeline">{continuationHistory.slice(1).map(item=><div className="timelineItem" key={item.id}><div className="badgeLine"><strong>{item.summary}</strong><span className="muted">{new Date(item.requestedAt).toLocaleString("pt-BR")}</span></div><div className="timelineMeta"><span>{item.attachmentCount+" anexo"+(item.attachmentCount===1?"":"s")}</span></div></div>)}</div></div>
  </details>:null}
  <details className="projectTechnicalDetails projectIntegrations" open={integrationNeedsAttention}>
   <summary><span><strong>Configurações e integrações</strong><small>Política de Preview e acesso ao GitHub. Pendências permanecem visíveis.</small></span><span className="muted">{integrationNeedsAttention?"Precisa de verificação":"Configuradas · ver detalhes"}</span></summary>
   <div className="projectTechnicalBody">
  <section className="section" id="preview-policy"><SectionHeader title="Prévia · política do projeto" action={<StatusPill status={previewPolicy?.required===false?"not_applicable":previewConfigured?"verified":"blocked"} label={previewPolicy?.required===false?"Não aplicável":previewConfigured?"Configurada":"Pendente"}/>}/>
   <div className="card denseStack">
    {previewConfigured?<><div className="detailGrid">
     <div className="detailItem"><span className="detailLabel">Provedor</span><strong>{previewPolicy?.provider==="vercel"?"Vercel":previewPolicy?.provider||"Definido por política"}</strong></div>
     <div className="detailItem"><span className="detailLabel">Modo</span><strong>{previewPolicy?.required===false?"Preview não requerido":previewPolicy?.mode==="github"?"Integração GitHub":previewPolicy?.mode||"Política por caminhos"}</strong></div>
    </div>
    <p className="muted" style={{margin:0}}>{previewPolicy?.required===false?(previewPolicy.reason||"A política explícita deste projeto declara Preview não aplicável."):"A Factory só considera a Prévia pronta quando a política explícita e as evidências do candidato forem verificadas."}</p>
    {previewPolicy?.evidenceSource?<div className="badgeLine"><span className="pill accent">Evidência</span><span className="muted">{previewPolicy.evidenceSource}{previewPolicy.evidenceCommit?" · "+previewPolicy.evidenceCommit.slice(0,12):""}</span></div>:null}</>:<>
     <div className="badgeLine"><StatusPill status="blocked" label="Fail-closed"/><strong>Nenhuma política explícita de Preview foi verificada.</strong></div>
     <p className="muted" style={{margin:0}}>Projetos importados não caem silenciosamente no modo Vercel API e a Factory nunca presume que Preview é dispensável. O preflight do GitHub pode confirmar uma integração Vercel existente e registrar automaticamente o modo GitHub; sem evidência, a etapa permanece bloqueada.</p>
     <div className="actions"><a className="linkButton" href="#github-access">Ver acesso GitHub e revalidar</a></div>
    </>}
   </div>
  </section>
  {githubAccess?<section className="section" id="github-access"><SectionHeader title="GitHub · acesso do projeto" action={<div className="badgeLine"><StatusPill status={githubAccess.status} label={githubAccess.status==="ready"?"Pronto":githubAccess.status==="partial"?"Parcial":githubAccess.status==="blocked"?"Bloqueado":"Aguardando verificação"}/><span className="muted">{githubAccess.lastVerifiedAt?"verificado em "+new Date(githubAccess.lastVerifiedAt).toLocaleString("pt-BR"):"sem preflight registrado"}</span></div>}/>
   <div className="card denseStack">
    <div className="panelHeading"><div><strong>{githubAccess.repository}</strong><div className="muted">Autenticação operacional: {githubAccess.authMode==="github_app"?"GitHub App":githubAccess.authMode==="native_github_token"?"token nativo do workflow":"token fine-grained"}</div></div><StatusPill status={githubAccess.status}/></div>
    <div className="table">
     <div className="tableRow tableHeader"><span>Capacidade</span><span>Necessária</span><span>Estado</span><span>Ação</span></div>
     {githubAccess.capabilities.map(cap=><div className="tableRow" key={cap.key}><strong>{githubCapabilityLabels[cap.key]||cap.key}</strong><span>{cap.required?"Sim":"Não"}</span><StatusPill status={cap.status} label={githubCapabilityLabel(cap.status)}/><span className="muted">{cap.status==="verified"?"nenhuma":cap.status==="missing"?"corrigir permissão":"revalidar acesso"}</span></div>)}
     <div className="tableRow"><strong>Release humano</strong><span>Separado</span><StatusPill status={githubAccess.releaseHuman.enabled?"verified":"blocked"} label={githubAccess.releaseHuman.enabled?"Habilitado":"Bloqueado"}/><span className="muted">{githubAccess.releaseHuman.reason||"merge somente por ação humana explícita"}</span></div>
    </div>
    {githubAccess.lastError?<div className="errorText">{githubAccess.lastError}</div>:null}
    <div className="actions">
     {operator.role==="admin"&&!githubAppStatus.configured?<a className="primary linkButton" href="/api/integrations/github-app/register">Registrar GitHub App da Factory</a>:null}
     {operator.role==="admin"&&githubAppStatus.configured&&githubAccess.authMode!=="github_app"?<a className="primary linkButton" href={"/api/integrations/github-app/install?project="+encodeURIComponent(p.key)}>Instalar GitHub App neste projeto</a>:null}
     {operator.role==="admin"&&githubAppStatus.configured&&githubAccess.authMode==="github_app"&&githubAccess.status!=="ready"?<a className="primary linkButton" href={"/api/integrations/github-app/verify?project="+encodeURIComponent(p.key)}>Verificar GitHub App neste projeto</a>:null}
     {githubAccess.authMode!=="github_app"?<a className="linkButton" href="https://github.com/settings/personal-access-tokens" target="_blank" rel="noreferrer">Fallback: token fine-grained</a>:null}
     {operator.role==="admin"&&githubAccess.status!=="ready"?<form action={requestGitHubRecheck}><input type="hidden" name="project_id" value={p.id}/><input type="hidden" name="project_key" value={p.key}/><button type="submit" className="linkButton">Reexecutar preflight</button></form>:null}
    </div>
    <div className="badgeLine"><StatusPill status={githubAppStatus.configured?"verified":"unverified"} label={githubAppStatus.configured?"GitHub App registrada":"GitHub App ainda não registrada"}/>{githubAppStatus.app_slug?<span className="muted">@{githubAppStatus.app_slug}</span>:null}</div>
    <p className="muted" style={{margin:0}}>A Factory só executa uma etapa quando as capacidades exigidas por aquela etapa estão comprovadas. A GitHub App usa tokens temporários, limitados ao repositório; a chave privada fica server-side no Vault e nunca é enviada ao navegador. Instalar ou ampliar acesso continua sendo uma ação humana no GitHub.</p>
   </div>
  </section>:null}
   </div>
  </details>
  {state.objective?<section className="section"><SectionHeader title="Objetivo atual"/><div className="card"><p style={{margin:0}}>{state.objective}</p></div></section>:null}
  {p.kind==="existing"?<section className="section"><SectionHeader title="Estado reconciliado" action={state.snapshot?<span className="muted">atualizado em {new Date(state.snapshot.createdAt).toLocaleString("pt-BR")}</span>:undefined}/>
   {!state.snapshot?<EmptyState>A reconciliação ainda não foi concluída. A Factory vai registrar aqui o estado real confirmado, as evidências e o trabalho que ainda falta.</EmptyState>:<div className="card stack">
    <div className="cardTop"><div><span className="detailLabel">Etapa observada</span><div style={{marginTop:7}}><StatusPill status={state.snapshot.observedStage||"unknown"} label={state.snapshot.observedStage?humanizeStatus(state.snapshot.observedStage):"Não determinada"}/></div></div><div className="muted mono">{state.snapshot.runId?"execução "+state.snapshot.runId.slice(0,8):"registro independente"}</div></div>
    <div><span className="detailLabel">Resumo do estado atual</span><p>{state.snapshot.summary}</p></div>
    <div className="twoCol">
     <div><span className="detailLabel">Evidências confirmadas</span>{state.snapshot.evidence.length?<ul>{state.snapshot.evidence.map((x,i)=><li key={i}>{display(x)}</li>)}</ul>:<p className="muted">Nenhuma evidência listada.</p>}</div>
     <div><span className="detailLabel">Lacunas restantes</span>{state.snapshot.gaps.length?<ul>{state.snapshot.gaps.map((x,i)=><li key={i}>{display(x)}</li>)}</ul>:<p className="muted">Nenhuma lacuna registrada.</p>}</div>
    </div>
    <div><span className="detailLabel">Restrições preservadas</span>{state.snapshot.constraints.length?<ul>{state.snapshot.constraints.map((x,i)=><li key={i}>{display(x)}</li>)}</ul>:<p className="muted">Nenhuma restrição adicional registrada.</p>}</div>
    {Object.keys(state.snapshot.sourceStatus).length?<div><span className="detailLabel">Fontes reconciliadas</span><div className="valueList">{Object.entries(state.snapshot.sourceStatus).map(([source,value])=><div className="valueRow" key={source}><strong>{source}</strong><span className="muted">{display(value)}</span></div>)}</div></div>:null}
   </div>}
  </section>:null}
  {hasPendingDatabase?<section className="section" id="databases"><SectionHeader title="Banco de dados · ação necessária" action={<span className="muted">{databases.filter(db=>db.status==="pending_access").length} pendente{databases.filter(db=>db.status==="pending_access").length===1?"":"s"}</span>}/>
   {databases.length===0?<EmptyState>Nenhum banco foi vinculado a este projeto. A Factory pode registrar um banco existente ou preparar o provisionamento de um novo banco, sujeito aos gates aplicáveis.</EmptyState>:<div className="table">
    <div className="tableRow tableHeader"><span>Banco</span><span>Acesso</span><span>Estado</span><span>Verificação</span></div>
    {databases.map(db=><div className="tableRow" key={db.id}>
     <div><strong>{db.provider==="supabase"?"Supabase":db.provider}</strong><div className="muted mono">{db.projectRef||"project_ref pendente"} · {db.environment}</div></div>
     <div><StatusPill status={db.permissionMode} label={db.permissionMode==="read"?"Somente leitura":db.permissionMode==="read_write"?"Leitura e escrita":"Não configurado"}/><div className="muted">{db.accessMode==="oauth"?"OAuth":db.accessMode==="management_api"?"Management API":"Conexão pendente"}</div></div>
     <StatusPill status={db.status} label={db.status==="pending_access"?"Aguardando conexão":db.status==="ready_read"?"Leitura verificada":db.status==="ready_write"?"Escrita verificada":humanizeStatus(db.status)}/>
     <span className="muted">{db.lastVerifiedAt?new Date(db.lastVerifiedAt).toLocaleString("pt-BR"):"Ainda não verificado"}</span>
    </div>)}
   </div>}
   {databases.some(db=>db.status==="pending_access")?<div className="card" style={{marginTop:12}}><strong>Próxima ação</strong><p className="muted">Conecte o Supabase com acesso mínimo. A Factory valida a identidade do projeto e uma consulta somente leitura antes de considerar o banco pronto. Nenhuma credencial é exibida nesta tela.</p>{oauthReady&&operator.role==="admin"?<div className="actions">{databases.filter(db=>db.status==="pending_access"&&db.provider==="supabase").map(db=><a className="primary linkButton" key={db.id} href={`/api/integrations/supabase/connect?project=${encodeURIComponent(p.key)}&database=${encodeURIComponent(db.id)}`}>Conectar Supabase</a>)}</div>:oauthReady?<div className="badgeLine"><StatusPill status="blocked" label="Administrador necessário"/><span className="muted">A conexão OAuth altera credenciais server-side e só pode ser iniciada por um administrador da Factory.</span></div>:<div className="badgeLine"><StatusPill status="blocked" label="OAuth do Supabase não configurado"/><span className="muted">A Factory permanece fail-closed até o client ID e o client secret existirem no ambiente server-side.</span></div>}</div>:null}
  </section>:null}

  <details className="projectTechnicalDetails">
   <summary>
    <span><strong>Detalhes técnicos do projeto</strong><small>Plano de trabalho, equipe/agentes, custo, integrações prontas e linha do tempo.</small></span>
    <span className="muted">{p.tasks.length} tarefas · {teamPlan?.profilesSelected||0} perfis · {ops.timeline.length} eventos</span>
   </summary>
   <div className="projectTechnicalBody">
    <div className="grid compact">
     <MetricCard label="Custo conhecido" value={ops.estimatedCost.toFixed(4)} note={ops.usageUnits+" unidades de uso"}/>
     <MetricCard label="Avaliações" value={ops.evaluations} note="evidências de qualidade"/>
     <MetricCard label="Implantações" value={ops.deployments} note="evidências de entrega"/>
    </div>
    {databases.length&&!hasPendingDatabase?<section className="section"><SectionHeader title="Bancos de dados" action={<span className="muted">{databases.length} integração{databases.length===1?"":"ões"}</span>}/><div className="table">
     <div className="tableRow tableHeader"><span>Banco</span><span>Acesso</span><span>Estado</span><span>Verificação</span></div>
     {databases.map(db=><div className="tableRow" key={db.id}><div><strong>{db.provider==="supabase"?"Supabase":db.provider}</strong><div className="muted mono">{db.projectRef||"project_ref pendente"} · {db.environment}</div></div><div><StatusPill status={db.permissionMode} label={db.permissionMode==="read"?"Somente leitura":db.permissionMode==="read_write"?"Leitura e escrita":"Não configurado"}/><div className="muted">{db.accessMode==="oauth"?"OAuth":db.accessMode==="management_api"?"Management API":"Conexão pendente"}</div></div><StatusPill status={db.status} label={db.status==="ready_read"?"Leitura verificada":db.status==="ready_write"?"Escrita verificada":humanizeStatus(db.status)}/><span className="muted">{db.lastVerifiedAt?new Date(db.lastVerifiedAt).toLocaleString("pt-BR"):"Ainda não verificado"}</span></div>)}
    </div></section>:null}
    <section className="section"><SectionHeader title="Plano de trabalho" action={<span className="muted">{p.tasks.length} tarefas</span>}/><div className="table">
   <div className="tableRow tableHeader"><span>Tarefa</span><span>Complexidade</span><span>Estado</span><span>Chave</span></div>
   {p.tasks.length===0?<EmptyState>Nenhuma tarefa registrada.</EmptyState>:p.tasks.map(t=><div className="tableRow" key={t.id}><strong>{t.title}</strong><StatusPill status={t.complexity}/><StatusPill status={t.status}/><span className="muted mono">{t.externalKey||t.id.slice(0,8)}</span></div>)}
  </div></section>
  <section className="section"><SectionHeader title="Equipe de execução" action={teamPlan?<span className="muted">plano v{teamPlan.version} · {teamPlan.profilesSelected} perfil{teamPlan.profilesSelected===1?"":"is"} · pico {teamPlan.plannedWorkerPeak} worker{teamPlan.plannedWorkerPeak===1?"":"s"}</span>:undefined}/>
   {!teamPlan?<EmptyState>A equipe será definida automaticamente quando o planejamento de engenharia for concluído.</EmptyState>:<div className="stack">
    <div className="grid compact">
     <MetricCard label="Perfis selecionados" value={teamPlan.profilesSelected} note="menor conjunto que cobre o plano"/>
     <MetricCard label="Pico de workers" value={teamPlan.plannedWorkerPeak} note="paralelismo máximo planejado"/>
     <MetricCard label="Ondas" value={teamPlan.waves.length} note="dependências e conflitos de escopo"/>
     <MetricCard label="Estado do plano" value={teamPlan.status==="ready"?"Pronto":"Bloqueado"} note={"gerado em "+new Date(teamPlan.createdAt).toLocaleString("pt-BR")}/>
    </div>
    <div className="threeCol">
     {teamPlan.selectedAgents.map(agent=><div className="card denseStack" key={agent.agent_key}>
      <div className="panelHeading"><strong>{agent.role}</strong><StatusPill status={agent.execution_ready?"active":"blocked"} label={agent.execution_ready?agent.workers_planned+" worker"+(agent.workers_planned===1?"":"s"):"lane pendente"}/></div>
      <div className="muted mono">{agent.agent_key}</div>
      <div><span className="detailLabel">Tarefas</span><div className="badgeLine">{agent.task_keys.map(key=><code key={key}>{key}</code>)}</div></div>
      <div><span className="detailLabel">Por que foi escolhido</span><ul>{agent.reasons.map((reason,i)=><li key={i}>{reason}</li>)}</ul></div>
      <div className="muted">capacidade máxima: {agent.max_concurrency}</div>
     </div>)}
    </div>
    {teamPlan.waves.length?<div className="card"><span className="detailLabel">Ondas de execução</span><div className="timeline">{teamPlan.waves.map(wave=><div className="timelineItem" key={wave.wave}><div className="badgeLine"><StatusPill status="policy" label={"Onda "+wave.wave}/><strong>{wave.parallel_workers} worker{wave.parallel_workers===1?"":"s"} em paralelo</strong></div><div className="badgeLine">{wave.task_keys.map(key=><code key={key}>{key}</code>)}</div></div>)}</div></div>:null}
    {teamPlan.advisorySpecialistLanes.length?<div className="card"><span className="detailLabel">Especialistas recomendados para fases independentes</span><p className="muted">Estas participações foram identificadas pela política, mas permanecem fail-closed até existir uma lane própria sem escrita para review/QA/operações.</p><div className="valueList">{teamPlan.advisorySpecialistLanes.map(item=><div className="valueRow" key={item.role}><strong>{item.role}</strong><span className="muted">{item.reasons.join(" · ")}</span></div>)}</div></div>:null}
    {teamPlan.blockers.length?<div className="card"><span className="detailLabel">Bloqueios do plano</span><ul>{teamPlan.blockers.map((item,i)=><li key={i}><strong>{item.code}</strong>{item.task_key?" · "+item.task_key:""}{item.dependency?" · dependência "+item.dependency:""}</li>)}</ul></div>:null}
    {teamPlan.excludedAgents.length?<div className="card"><span className="detailLabel">Perfis não usados neste trabalho</span><div className="valueList">{teamPlan.excludedAgents.map(item=><div className="valueRow" key={item.agent_key}><strong>{item.role}</strong><span className="muted">{item.reason}</span></div>)}</div></div>:null}
   </div>}
  </section>
  <section className="section"><SectionHeader title="Linha do tempo operacional" action={<span className="muted">{ops.timeline.length} eventos de evidência</span>}/>
   {ops.timeline.length===0?<EmptyState>Ainda não há evidências operacionais para este projeto.</EmptyState>:<div className="card"><div className="timeline">{ops.timeline.slice(0,40).map(item=><div className="timelineItem" key={item.id}><div className="badgeLine"><StatusPill status={item.kind}/><strong>{item.title}</strong>{item.status?<StatusPill status={item.status}/>:null}</div><div className="timelineMeta"><span>{new Date(item.at).toLocaleString("pt-BR")}</span>{item.detail?<span>{item.detail}</span>:null}{item.cost!=null?<span>custo {item.cost}</span>:null}{item.ref?<code>{item.ref}</code>:null}</div></div>)}</div></div>}
  </section>
   </div>
  </details>
 </>;
}