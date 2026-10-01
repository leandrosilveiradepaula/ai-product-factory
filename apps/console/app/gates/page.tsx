import {revalidatePath} from "next/cache";
import {getHumanGates,resolveHumanGate} from "../../lib/control-plane";
import {EmptyState,PageHeader,StatusPill} from "../ui";

function reasonText(value:unknown){
 if(Array.isArray(value))return value.join(", ");
 if(value&&typeof value==="object")return JSON.stringify(value);
 return value?String(value):"Sem motivo adicional";
}
async function resolveGate(formData:FormData){
 "use server";
 const gateId=String(formData.get("gate_id")||"");
 const resolution=String(formData.get("resolution")||"");
 const note=String(formData.get("note")||"").trim();
 if(!gateId||!["approved","rejected"].includes(resolution))throw new Error("Resolução de aprovação inválida");
 await resolveHumanGate(gateId,resolution as "approved"|"rejected",note||undefined);
 revalidatePath("/gates");revalidatePath("/runs");revalidatePath("/queue");
}
export default async function Gates(){
 const gates=await getHumanGates();const pending=gates.filter(g=>g.status==="pending");const resolved=gates.length-pending.length;
 return <>
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
      <div><span className="detailLabel">Motivo</span><h3>{g.status==="pending"?"Decisão humana necessária":"Gate resolvido"}</h3><p className="muted">{reasonText(g.reasons)}</p></div>
      <div className="gateMeta"><div><span className="detailLabel">Execução</span><strong className="mono">{g.runId.slice(0,12)}</strong></div><div><span className="detailLabel">Solicitado</span><strong>{new Date(g.requestedAt).toLocaleString("pt-BR")}</strong></div></div>
     </div>
     {g.status==="pending"?<form action={resolveGate} className="gateForm"><input type="hidden" name="gate_id" value={g.id}/><input name="note" placeholder="Observação opcional da decisão"/><div className="gateActionBar"><button className="danger" name="resolution" value="rejected">Rejeitar / interromper</button><button className="primary" name="resolution" value="approved">Assinar e aprovar</button></div></form>:null}
    </article>)}
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Quando você será chamado</strong><StatusPill status="active" label="vigente"/></div>
     <p className="muted">A Factory não possui caminho de auto-merge. Preview, CI e avaliações podem preparar a liberação, mas a promoção para produção depende de uma ação humana já realizada.</p>
     <div className="compactList">
      <div className="compactRow"><span>Liberação de produção</span><span className="muted">merge humano</span></div>
      <div className="compactRow"><span>Destruição de dados</span><span className="muted">aprovação</span></div>
      <div className="compactRow"><span>Acesso sensível</span><span className="muted">aprovação</span></div>
      <div className="compactRow"><span>Serviço pago recorrente</span><span className="muted">aprovação</span></div>
      <div className="compactRow"><span>Mudança material</span><span className="muted">aprovação</span></div>
     </div>
    </div>
    <div className="logPanel">gate.policy = durable<br/>gate.default = fail_closed<br/>release.auto_merge = false<br/>release.observer = read_only</div>
   </aside>
  </div>
 </>;
}
