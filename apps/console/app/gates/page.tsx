import Link from "next/link";
import {revalidatePath} from "next/cache";
import {redirect} from "next/navigation";
import {getHumanGates,resolveHumanGate} from "../../lib/control-plane";
import {mergeReadyReleaseFromConsole} from "../../lib/release-operator";
import {applyPendingMigrationFromConsole} from "../../lib/migration-operator";
import {EmptyState,PageHeader,StatusPill} from "../ui";
import {GateDecisionPending} from "./gate-decision-form";
import {GateActionErrorBanner} from "./gate-action-error-banner";
import {ConfirmSubmit} from "../confirm-submit";

function reasonText(value:unknown){
 if(Array.isArray(value))return value.join(", ");
 if(value&&typeof value==="object")return JSON.stringify(value);
 return value?String(value):"Sem motivo adicional";
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
 const resolution=String(formData.get("resolution")||"");
 const note=String(formData.get("note")||"").trim();
 if(!gateId||!["approved","rejected"].includes(resolution))throw new Error("Resolução de aprovação inválida");
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
export default async function Gates({searchParams}:{searchParams:Promise<{error?:string}>}){
 const params=await searchParams;
 const actionError=typeof params.error==="string"?params.error.slice(0,360):null;
 const gates=await getHumanGates();const pending=gates.filter(g=>g.status==="pending");const resolved=gates.length-pending.length;
 return <>
  {actionError?<GateActionErrorBanner message={actionError}/>:null}
  <PageHeader eyebrow="Sua caixa de entrada de decisões" title="Decisões que precisam de você" subtitle="Se esta tela estiver vazia, você não precisa fazer nada. A Factory só para aqui quando produção, dados, acesso, custo ou uma mudança importante exigem sua decisão." actions={<StatusPill status={pending.length?"attention":"healthy"} label={pending.length?pending.length+" críticas pendentes":"nenhuma pendência"}/>}/>
  <div className="operationalStrip">
   <div className="operationalStat warning"><span>Aguardando sua decisão</span><strong>{pending.length}</strong><small>ação humana</small></div>
   <div className="operationalStat"><span>Resolvidas</span><strong>{resolved}</strong><small>histórico durável</small></div>
   <div className="operationalStat"><span>Política</span><strong>fail-closed</strong><small>sem bypass</small></div>
   <div className="operationalStat"><span>Produção</span><strong>humana</strong><small>merge nunca automático</small></div>
  </div>
  <div className="gateLayout">
   <section className="denseStack">
    {gates.length===0?<EmptyState><span className="status"><i className="statusDot"/>Nenhuma aprovação humana registrada.</span></EmptyState>:gates.map(g=><article className={g.status==="pending"?"card gateCard pending":"card gateCard"} key={g.id}>
     <div className="gateBanner"><div className="badgeLine"><StatusPill status={g.status}/><StatusPill status={g.type}/></div><span className="muted mono">GATE · {g.id.slice(0,12)}</span></div>
     <div className="gateContent">
      <div><span className="detailLabel">Motivo</span><h3>{g.source==="release_report"?"Merge humano necessário":g.status==="pending"?"Decisão humana necessária":"Gate resolvido"}</h3><p className="muted">{reasonText(g.reasons)}</p>{g.candidateCommit?<div className="muted mono">candidate · {g.candidateCommit.slice(0,12)}</div>:null}</div>
      <div className="gateMeta"><div><span className="detailLabel">Projeto / tarefa</span><strong>{g.projectName||"Contexto histórico indisponível"}</strong>{g.taskTitle?<div className="muted">{g.taskTitle}</div>:null}{g.projectKey?<div><Link href={"/projects/"+g.projectKey}>Abrir projeto →</Link></div>:null}</div><div><span className="detailLabel">Execução</span><Link className="mono" href={"/runs/"+g.runId}>Abrir {g.runId.slice(0,12)} →</Link><div className="muted">solicitado em {new Date(g.requestedAt).toLocaleString("pt-BR")}</div>{g.source==="release_report"&&g.actionUrl?<div><a href={g.actionUrl} target="_blank" rel="noreferrer">{g.actionLabel||"Abrir PR no GitHub"} →</a></div>:null}</div></div>
     </div>
     {g.status==="pending"&&g.source==="human_gate"&&g.requestedAction==="register_github_app"?<div className="gateForm"><GateDecisionPending><div className="gatePendingStatus" role="status">A Factory precisa do teu consentimento no GitHub para registrar a App. O gate só será concluído depois que o callback do GitHub for validado e a configuração server-side for persistida.</div><div className="gateActionBar"><form action={resolveGate}><input type="hidden" name="gate_id" value={g.id}/><ConfirmSubmit className="danger" name="resolution" value="rejected" confirmMessage="Rejeitar o registro da GitHub App e manter o acesso cross-repo bloqueado?">Rejeitar / manter bloqueado</ConfirmSubmit></form><a className="primary linkButton" href={"/api/integrations/github-app/register?gate="+encodeURIComponent(g.id)}>Registrar GitHub App</a></div></GateDecisionPending></div>:g.status==="pending"&&g.source==="human_gate"&&g.requestedAction==="apply_control_plane_migration"?<div className="gateForm">{g.canApplyMigration&&g.candidateCommit?<form action={applyMigration}><input type="hidden" name="gate_id" value={g.id}/><input type="hidden" name="candidate_commit" value={g.candidateCommit}/><GateDecisionPending><div className="gatePendingStatus" role="status">Migration versionada pronta. O Console vai revalidar PR, SHA, checks e arquivo exato antes de aplicar no Supabase.</div><div className="muted mono">{g.migrationFile||g.migrationName}</div><div className="gateActionBar"><ConfirmSubmit className="danger" name="resolution" value="rejected" formAction={resolveGate} confirmMessage="Rejeitar esta migration e interromper esta continuação da Factory?">Rejeitar / interromper</ConfirmSubmit><ConfirmSubmit className="primary" confirmMessage={`Aplicar ${g.migrationName||"esta migration"} no Supabase de produção a partir do commit ${g.candidateCommit.slice(0,12)}? Esta ação altera o banco de produção.`}>Aplicar migration em produção</ConfirmSubmit></div></GateDecisionPending></form>:<GateDecisionPending><div className="gatePendingStatus" role="status">{g.migrationBlocker||"Aplicação de migration pelo Console ainda não disponível."}</div><form action={resolveGate}><input type="hidden" name="gate_id" value={g.id}/><div className="gateActionBar"><ConfirmSubmit className="danger" name="resolution" value="rejected" confirmMessage="Rejeitar esta migration e interromper esta continuação da Factory?">Rejeitar / interromper</ConfirmSubmit></div></form></GateDecisionPending>}</div>:g.status==="pending"&&g.source==="human_gate"?<form action={resolveGate} className="gateForm"><input type="hidden" name="gate_id" value={g.id}/><GateDecisionPending><input name="note" placeholder="Observação opcional da decisão"/><div className="gateActionBar"><ConfirmSubmit className="danger" name="resolution" value="rejected" confirmMessage="Rejeitar este gate e interromper esta continuação da Factory?">Rejeitar / interromper</ConfirmSubmit><ConfirmSubmit className="primary" name="resolution" value="approved" confirmMessage="Confirmar esta aprovação humana? A Factory poderá continuar a partir deste gate, respeitando os próximos gates aplicáveis.">Assinar e aprovar</ConfirmSubmit></div></GateDecisionPending></form>:g.status==="pending"&&g.source==="release_report"?<div className="gateForm">{g.canMergeInConsole&&g.candidateCommit?<form action={mergeRelease}><input type="hidden" name="run_id" value={g.runId}/><input type="hidden" name="candidate_commit" value={g.candidateCommit}/><GateDecisionPending><div className="gatePendingStatus" role="status">Release validado. O merge só acontece após esta ação humana explícita e será revalidado contra o SHA exato.</div><div className="gateActionBar"><ConfirmSubmit className="primary" confirmMessage={`Fazer merge do PR #${g.prNumber||"?"} em produção no commit ${g.candidateCommit.slice(0,12)}? Esta ação altera main e não será executada automaticamente.`}>Fazer merge em produção</ConfirmSubmit></div></GateDecisionPending></form>:<><div className="gatePendingStatus" role="status">{g.mergeBlocker||"Merge pelo Console ainda não disponível."}</div>{g.actionUrl?<div className="gateActionBar"><a href={g.actionUrl} target="_blank" rel="noreferrer">{g.actionLabel||"Abrir PR no GitHub"} →</a></div>:null}</>}</div>:null}
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
