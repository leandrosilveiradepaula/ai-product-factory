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
  <PageHeader eyebrow="Aprovações humanas" title="Aprovações humanas" subtitle="Decisões que interrompem a automação por risco de produção, dados, acesso, custo ou requisito material."/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Pendentes</span><strong>{pending.length}</strong></div>
   <div className="operationalStat"><span>Resolvidas</span><strong>{resolved}</strong></div>
   <div className="operationalStat"><span>Política</span><strong>fail-closed</strong></div>
   <div className="operationalStat"><span>Produção</span><strong>humana</strong></div>
  </div>
  <div className="overviewGrid">
   <section className="denseStack">
    {gates.length===0?<EmptyState><span className="status"><i className="statusDot"/>Nenhuma aprovação humana registrada.</span></EmptyState>:gates.map(g=><article className="card" key={g.id}>
     <div className="cardTop">
      <div className="badgeLine"><StatusPill status={g.type}/><StatusPill status={g.status}/></div>
      <span className="muted mono">{g.runId.slice(0,8)}</span>
     </div>
     <div style={{marginTop:10}}><strong>{g.status==="pending"?"Decisão necessária":"Aprovação resolvida"}</strong><p className="muted" style={{margin:"5px 0 0"}}>{reasonText(g.reasons)}</p></div>
     <div className="timelineMeta"><span>{new Date(g.requestedAt).toLocaleString("pt-BR")}</span></div>
     {g.status==="pending"?<form action={resolveGate} className="gateForm">
      <input type="hidden" name="gate_id" value={g.id}/>
      <input name="note" placeholder="Observação opcional da decisão"/>
      <div className="actions"><button className="danger" name="resolution" value="rejected">Rejeitar</button><button className="primary" name="resolution" value="approved">Aprovar</button></div>
     </form>:null}
    </article>)}
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Regra de autoridade</strong><StatusPill status="active" label="vigente"/></div>
     <div className="compactList">
      <div className="compactRow"><span className="muted">Preview verificado</span><span>não autoriza merge</span></div>
      <div className="compactRow"><span className="muted">Produção</span><span>merge humano</span></div>
      <div className="compactRow"><span className="muted">Dados destrutivos</span><span>aprovação</span></div>
      <div className="compactRow"><span className="muted">Ampliação de acesso</span><span>aprovação</span></div>
      <div className="compactRow"><span className="muted">Mudança material</span><span>aprovação</span></div>
     </div>
    </div>
    <div className="logPanel">gate.policy = durable<br/>gate.default = fail_closed<br/>release.merge = human_only</div>
   </aside>
  </div>
 </>;
}