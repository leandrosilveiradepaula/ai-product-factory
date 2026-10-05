import Link from "next/link";
import {revalidatePath} from "next/cache";
import {redirect} from "next/navigation";
import {getGitHubAppInstallActions,getHumanGates,resolveHumanGate} from "../../lib/control-plane";
import {mergeReadyReleaseFromConsole} from "../../lib/release-operator";
import {applyPendingMigrationFromConsole} from "../../lib/migration-operator";
import {getGitHubAppStatus} from "../../lib/github-app";
import {EmptyState,PageHeader,StatusPill} from "../ui";
import {GateDecisionPending} from "./gate-decision-form";
import {GateActionErrorBanner} from "./gate-action-error-banner";
import {ConfirmSubmit} from "../confirm-submit";

type PlanningReason={question?:unknown;why_needed?:unknown;decision_key?:unknown;decision_kind?:unknown};

function GateReasons({value}:{value:unknown}){
 if(Array.isArray(value)&&value.some(item=>item&&typeof item==="object")){
  return <div className="compactList">
   {value.map((item,index)=>{
    const reason=(item&&typeof item==="object"?item:{}) as PlanningReason;
    const question=reason.question?String(reason.question):"Decisão sem pergunta legível";
    const why=reason.why_needed?String(reason.why_needed):null;
    const key=reason.decision_key?String(reason.decision_key):null;
    const kind=reason.decision_kind?String(reason.decision_kind):null;
    return <div className="compactRow" key={key||String(index)}>
     <div>
      <span className="detailLabel">Decisão {index+1}{kind?" · "+kind:""}</span>
      <strong>{question}</strong>
      {why?<div className="muted">{why}</div>:null}
      {key?<div className="muted mono">chave · {key}</div>:null}
     </div>
    </div>;
   })}
  </div>;
 }
 if(Array.isArray(value))return <div className="compactList">{value.map((item,index)=><div className="compactRow" key={index}><span>{String(item)}</span></div>)}</div>;
 if(value&&typeof value==="object")return <pre className="muted">{JSON.stringify(value,null,2)}</pre>;
 return <p className="muted">{value?String(value):"Sem motivo adicional"}</p>;
}
function safeGateActionError(error:unknown){
 const raw=error instanceof Error?error.message:"Não foi possível concluir a ação humana.";
 return raw
  .replace(/Bearer\s+\S+/gi,"Bearer [redacted]")
  .replace(/(token|secret|api[_-]?key)\s*[=:]\s*\S+/gi,"$1=[redacted]")
  .replace(/\s+/g," ")
  .trim()
  .slice(0,360)||"Não foi possível concluir a ação humana.";
}
function redirectGateError(error:unknown):never{
 redirect("/gates?error="+encodeURIComponent(safeGateActionError(error)));
}
async function resolveGate(formData:FormData){
 "use server";
 const gateId=String(formData.get("gate_id")||"");
 const gateType=String(formData.get("gate_type")||"");
 const resolution=String(formData.get("resolution")||"");
 const note=String(formData.get("note")||"").trim();
 if(!gateId||!["approved","rejected"].includes(resolution))throw new Error("Resolução de aprovação inválida");
 if(gateType==="planning_decision"&&resolution==="approved"&&!note)throw new Error("Responda a decisão de planejamento antes de continuar.");
 try{
  await resolveHumanGate(gateId,resolution as "approved"|"rejected",note||undefined);
 }catch(error){redirectGateError(error);}
 revalidatePath("/gates");revalidatePath("/runs");revalidatePath("/queue");
}
async function mergeRelease(formData:FormData){
 "use server";
 const runId=String(formData.get("run_id")||"");
 const candidate=String(formData.get("candidate_commit")||"");
 if(!runId||!candidate)throw new Error("Release inválido.");
 try{
  await mergeReadyReleaseFromConsole(runId,candidate);
 }catch(error){redirectGateError(error);}
 revalidatePath("/gates");revalidatePath("/runs");revalidatePath("/queue");revalidatePath("/deployments");
}
async function applyMigration(formData:FormData){
 "use server";
 const gateId=String(formData.get("gate_id")||"");
 const candidate=String(formData.get("candidate_commit")||"");
 if(!gateId||!candidate)throw new Error("Migration inválida.");
 try{
  await applyPendingMigrationFromConsole(gateId,candidate);
 }catch(error){redirectGateError(error);}
 revalidatePath("/gates");revalidatePath("/runs");revalidatePath("/queue");revalidatePath("/projects");
}
const githubAppNotices:Record<string,{status:string;message:string}>={
 verified:{status:"success",message:"GitHub App verificada para o projeto. O acesso cross-repo agora usa uma instalação explicitamente autorizada."},
 blocked:{status:"failed",message:"A GitHub App foi instalada, mas ainda faltam capacidades exigidas. O projeto permanece bloqueado até a verificação ficar completa."},
 verification_failed:{status:"failed",message:"A instalação retornou do GitHub, mas a verificação server-side não foi concluída. Nenhum acesso foi assumido como válido."},
 install_project_invalid:{status:"failed",message:"A ação de instalação não corresponde a um projeto cross-repo ativo da Factory."},
 not_registered:{status:"failed",message:"A GitHub App precisa estar registrada antes da instalação em um projeto."},
};

export default async function Gates({searchParams}:{searchParams:Promise<{error?:string;github_app?:string}>}){
 const params=await searchParams;
 const actionError=typeof params.error==="string"?params.error.slice(0,360):null;
 const githubNotice=typeof params.github_app==="string"?githubAppNotices[params.github_app]:undefined;
 const [gates,githubApp,githubInstallActions]=await Promise.all([getHumanGates(),getGitHubAppStatus(),getGitHubAppInstallActions()]);const pending=gates.filter(g=>g.status==="pending"&&g.actionable);const history=gates.filter(g=>g.status!=="pending"||!g.actionable);const orderedGates=[...pending,...history];const githubAppActionPending=!githubApp.configured;const installActions=githubApp.configured?githubInstallActions:[];const pendingCount=pending.length+(githubAppActionPending?1:0)+installActions.length;const resolved=history.length;
 return <>
  {actionError?<GateActionErrorBanner message={actionError}/>:null}
  {githubNotice?<div className={"card noticeCard "+(githubNotice.status==="success"?"success":"danger")} role="status"><StatusPill status={githubNotice.status}/><span>{githubNotice.message}</span></div>:null}
  <PageHeader eyebrow="Sua caixa de entrada de decisões" title="Decisões que precisam de você" subtitle="Se esta tela estiver vazia, você não precisa fazer nada. A Factory só para aqui quando produção, dados, acesso, custo ou uma mudança importante exigem sua decisão." actions={<StatusPill status={pendingCount?"attention":"healthy"} label={pendingCount?pendingCount+" críticas pendentes":"nenhuma pendência"}/>}/>
  <div className="operationalStrip">
   <div className="operationalStat warning"><span>Aguardando sua decisão</span><strong>{pendingCount}</strong><small>ação humana</small></div>
   <div className="operationalStat"><span>Resolvidas</span><strong>{resolved}</strong><small>histórico durável</small></div>
   <div className="operationalStat"><span>Política</span><strong>fail-closed</strong><small>sem bypass</small></div>
   <div className="operationalStat"><span>Produção</span><strong>humana</strong><small>merge nunca automático</small></div>
  </div>
  <div className="gateLayout">
   <section className="denseStack">
    {githubAppActionPending?<article className="card gateCard pending">
     <div className="gateBanner"><div className="badgeLine"><StatusPill status="pending"/><StatusPill status="sensitive_access"/></div><span className="muted mono">AÇÃO · github-app</span></div>
     <div className="gateContent">
      <div><span className="detailLabel">Motivo</span><h3>Registrar GitHub App da Factory</h3><p className="muted">A Factory precisa do teu consentimento no GitHub para criar a identidade da App. O registro armazena os segredos somente no Supabase Vault e não instala a App em nenhum repositório.</p></div>
      <div className="gateMeta"><div><span className="detailLabel">Escopo</span><strong>Acesso sensível</strong><div className="muted">registro da App; instalação e seleção de repositórios continuam separadas</div></div></div>
     </div>
     <div className="gateForm"><GateDecisionPending><div className="gatePendingStatus" role="status">Esta ação só é considerada concluída depois que o GitHub retornar um callback válido e a configuração server-side for persistida.</div><div className="gateActionBar"><a className="primary linkButton" href="/api/integrations/github-app/register?return_to=gates">Registrar GitHub App</a></div></GateDecisionPending></div>
    </article>:null}
    {installActions.map(action=><article className="card gateCard pending" key={"github-app-install-"+action.projectKey}>
     <div className="gateBanner"><div className="badgeLine"><StatusPill status="pending"/><StatusPill status="sensitive_access"/></div><span className="muted mono">AÇÃO · github-app-install</span></div>
     <div className="gateContent">
      <div><span className="detailLabel">Motivo</span><h3>Instalar GitHub App em {action.projectName}</h3><p className="muted">O projeto ainda depende de acesso cross-repo. A instalação exige teu consentimento no GitHub e a Factory só confiará no acesso depois de uma verificação server-side com token temporário.</p></div>
      <div className="gateMeta"><div><span className="detailLabel">Repositório</span><strong>{action.repository}</strong><div className="muted">estado atual: {action.authMode} · {action.status}</div></div></div>
     </div>
     <div className="gateForm"><GateDecisionPending><div className="gatePendingStatus" role="status">No GitHub, seleciona somente o repositório deste projeto. Não amplie para outros repositórios nesta etapa.</div><div className="gateActionBar"><a className="primary linkButton" href={"/api/integrations/github-app/install?project="+encodeURIComponent(action.projectKey)}>Instalar no GitHub</a><a className="linkButton" href={"/api/integrations/github-app/verify?project="+encodeURIComponent(action.projectKey)}>Verificar instalação</a></div></GateDecisionPending></div>
    </article>)}
    {orderedGates.length===0&&!githubAppActionPending&&installActions.length===0?<EmptyState><span className="status"><i className="statusDot"/>Nenhuma aprovação humana registrada.</span></EmptyState>:orderedGates.map(g=><article className={g.status==="pending"&&g.actionable?"card gateCard pending":"card gateCard"} key={g.id}>
     <div className="gateBanner"><div className="badgeLine"><StatusPill status={g.status==="pending"&&!g.actionable?"cancelled":g.status} label={g.status==="pending"&&!g.actionable?"histórico":undefined}/><StatusPill status={g.type}/></div><span className="muted mono">GATE · {g.id.slice(0,12)}</span></div>
     <div className="gateContent">
      <div><span className="detailLabel">Motivo</span><h3>{g.source==="release_report"?"Merge humano necessário":g.status==="pending"&&g.actionable?"Decisão humana necessária":g.status==="pending"?"Gate histórico":"Gate resolvido"}</h3><GateReasons value={g.reasons}/>{g.staleReason?<div className="gatePendingStatus" role="status">{g.staleReason}</div>:null}{g.candidateCommit?<div className="muted mono">candidate · {g.candidateCommit.slice(0,12)}</div>:null}</div>
      <div className="gateMeta"><div><span className="detailLabel">Projeto / tarefa</span><strong>{g.projectName||"Contexto histórico indisponível"}</strong>{g.taskTitle?<div className="muted">{g.taskTitle}</div>:null}{g.projectKey?<div><Link href={"/projects/"+g.projectKey}>Abrir projeto →</Link></div>:null}</div><div><span className="detailLabel">Execução</span><Link className="mono" href={"/runs/"+g.runId}>Abrir {g.runId.slice(0,12)} →</Link><div className="muted">solicitado em {new Date(g.requestedAt).toLocaleString("pt-BR")}</div>{g.source==="release_report"&&g.actionUrl?<div><a href={g.actionUrl} target="_blank" rel="noreferrer">{g.actionLabel||"Abrir PR no GitHub"} →</a></div>:null}</div></div>
     </div>
     {g.status==="pending"&&g.actionable&&g.source==="human_gate"&&g.requestedAction==="register_github_app"?<div className="gateForm"><GateDecisionPending><div className="gatePendingStatus" role="status">A Factory precisa do teu consentimento no GitHub para registrar a App. O gate só será concluído depois que o callback do GitHub for validado e a configuração server-side for persistida.</div><div className="gateActionBar"><form action={resolveGate}><input type="hidden" name="gate_id" value={g.id}/><ConfirmSubmit className="danger" name="resolution" value="rejected" confirmMessage="Rejeitar o registro da GitHub App e manter o acesso cross-repo bloqueado?">Rejeitar / manter bloqueado</ConfirmSubmit></form><a className="primary linkButton" href={"/api/integrations/github-app/register?gate="+encodeURIComponent(g.id)}>Registrar GitHub App</a></div></GateDecisionPending></div>:g.status==="pending"&&g.actionable&&g.source==="human_gate"&&g.requestedAction==="apply_control_plane_migration"?<div className="gateForm">{g.canApplyMigration&&g.candidateCommit?<form action={applyMigration}><input type="hidden" name="gate_id" value={g.id}/><input type="hidden" name="candidate_commit" value={g.candidateCommit}/><GateDecisionPending><div className="gatePendingStatus" role="status">Migration versionada pronta. O Console vai revalidar PR, SHA, checks e arquivo exato antes de aplicar no Supabase.</div><div className="muted mono">{g.migrationFile||g.migrationName}</div><div className="gateActionBar"><ConfirmSubmit className="danger" name="resolution" value="rejected" formAction={resolveGate} confirmMessage="Rejeitar esta migration e interromper esta continuação da Factory?">Rejeitar / interromper</ConfirmSubmit><ConfirmSubmit className="primary" confirmMessage={`Aplicar ${g.migrationName||"esta migration"} no Supabase de produção a partir do commit ${g.candidateCommit.slice(0,12)}? Esta ação altera o banco de produção.`}>Aplicar migration em produção</ConfirmSubmit></div></GateDecisionPending></form>:<GateDecisionPending><div className="gatePendingStatus" role="status">{g.migrationBlocker||"Aplicação de migration pelo Console ainda não disponível."}</div><form action={resolveGate}><input type="hidden" name="gate_id" value={g.id}/><div className="gateActionBar"><ConfirmSubmit className="danger" name="resolution" value="rejected" confirmMessage="Rejeitar esta migration e interromper esta continuação da Factory?">Rejeitar / interromper</ConfirmSubmit></div></form></GateDecisionPending>}</div>:g.status==="pending"&&g.actionable&&g.source==="human_gate"?<form action={resolveGate} className="gateForm"><input type="hidden" name="gate_id" value={g.id}/><input type="hidden" name="gate_type" value={g.type}/><GateDecisionPending>{g.type==="planning_decision"?<><div className="gatePendingStatus" role="status">Responde as decisões acima. A Factory vai registrar tua resposta e refazer a reconciliação antes de criar qualquer backlog executável.</div><textarea name="note" required rows={5} placeholder="Responde cada decisão acima. Ex.: 1) autorizado... 2) manter somente..."/></>:<input name="note" placeholder="Observação opcional da decisão"/>}<div className="gateActionBar"><ConfirmSubmit className="danger" name="resolution" value="rejected" confirmMessage="Rejeitar este gate e interromper esta continuação da Factory?">Rejeitar / interromper</ConfirmSubmit><ConfirmSubmit className="primary" name="resolution" value="approved" confirmMessage={g.type==="planning_decision"?"Registrar esta decisão e permitir que a Factory refaça o planejamento com tua resposta?":"Confirmar esta aprovação humana? A Factory poderá continuar a partir deste gate, respeitando os próximos gates aplicáveis."}>{g.type==="planning_decision"?"Registrar decisão e continuar":"Assinar e aprovar"}</ConfirmSubmit></div></GateDecisionPending></form>:g.status==="pending"&&g.actionable&&g.source==="release_report"?<div className="gateForm">{g.canMergeInConsole&&g.candidateCommit?<form action={mergeRelease}><input type="hidden" name="run_id" value={g.runId}/><input type="hidden" name="candidate_commit" value={g.candidateCommit}/><GateDecisionPending><div className="gatePendingStatus" role="status">Release validado. O merge só acontece após esta ação humana explícita e será revalidado contra o SHA exato.</div><div className="gateActionBar"><ConfirmSubmit className="primary" confirmMessage={`Fazer merge do PR #${g.prNumber||"?"} em produção no commit ${g.candidateCommit.slice(0,12)}? Esta ação altera main e não será executada automaticamente.`}>Fazer merge em produção</ConfirmSubmit></div></GateDecisionPending></form>:<><div className="gatePendingStatus" role="status">{g.mergeBlocker||"Merge pelo Console ainda não disponível."}</div>{g.actionUrl?<div className="gateActionBar"><a href={g.actionUrl} target="_blank" rel="noreferrer">{g.actionLabel||"Abrir PR no GitHub"} →</a></div>:null}</>}</div>:null}
    </article>)}
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Quando você será chamado</strong><StatusPill status="active" label="vigente"/></div>
     <p className="muted">A Factory não possui caminho de auto-merge. Preview, CI e avaliações preparam a liberação; a promoção para produção exige uma ação humana explícita, pelo Console ou pelo GitHub.</p>
     <div className="compactList">
      <div className="compactRow"><span>Liberação de produção</span><span className="muted">merge humano explícito</span></div><div className="compactRow"><span>Migration de produção</span><span className="muted">aplicação humana explícita</span></div>
      <div className="compactRow"><span>Destruição de dados</span><span className="muted">aprovação</span></div>
      <div className="compactRow"><span>Acesso sensível</span><span className="muted">aprovação</span></div>
      <div className="compactRow"><span>Serviço pago recorrente</span><span className="muted">aprovação</span></div>
      <div className="compactRow"><span>Mudança material</span><span className="muted">aprovação</span></div>
     </div>
    </div>
    <div className="logPanel">gate.policy = durable<br/>gate.default = fail_closed<br/>release.auto_merge = false<br/>release.console_human_merge = explicit<br/>migration.console_human_apply = explicit<br/>release.observer = read_only</div>
   </aside>
  </div>
 </>;
}
