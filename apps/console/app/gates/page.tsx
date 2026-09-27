import {revalidatePath} from "next/cache";
import {getHumanGates,resolveHumanGate} from "../../lib/control-plane";
import {EmptyState,MetricCard,PageHeader,StatusPill} from "../ui";

function reasonText(value:unknown){
 if(Array.isArray(value))return value.join(", ");
 if(value&&typeof value==="object")return JSON.stringify(value);
 return value?String(value):"No additional reason";
}
async function resolveGate(formData:FormData){
 "use server";
 const gateId=String(formData.get("gate_id")||"");
 const resolution=String(formData.get("resolution")||"");
 const note=String(formData.get("note")||"").trim();
 if(!gateId||!["approved","rejected"].includes(resolution))throw new Error("Invalid gate resolution");
 await resolveHumanGate(gateId,resolution as "approved"|"rejected",note||undefined);
 revalidatePath("/gates");revalidatePath("/runs");revalidatePath("/queue");
}
export default async function Gates(){
 const gates=await getHumanGates();const pending=gates.filter(g=>g.status==="pending");
 return <>
  <PageHeader eyebrow="Human Authority" title="Human Gates" subtitle="A Factory só interrompe quando produção, dados, acesso, custo recorrente ou requisito material exigem autoridade humana."/>
  <div className="grid compact"><MetricCard label="Pending" value={pending.length}/><MetricCard label="History" value={gates.length}/><MetricCard label="Policy" value="Fail closed"/><MetricCard label="Production" value="Human"/></div>
  <section className="section"><div className="stack">{gates.length===0?<EmptyState><span className="status"><i className="statusDot"/>No human gates recorded.</span></EmptyState>:gates.map(g=><article className="card" key={g.id}><div className="cardTop"><div><StatusPill status={g.type}/><h2 style={{margin:"10px 0 5px",fontSize:15}}>{g.status==="pending"?"Decision required":"Gate resolved"}</h2><p className="muted" style={{margin:0}}>{reasonText(g.reasons)}</p></div><StatusPill status={g.status}/></div><div className="timelineMeta"><span>run {g.runId.slice(0,8)}</span><span>{new Date(g.requestedAt).toLocaleString("pt-BR")}</span></div>{g.status==="pending"?<form action={resolveGate} className="gateForm"><input type="hidden" name="gate_id" value={g.id}/><input name="note" placeholder="Optional decision note"/><div className="actions"><button className="primary" name="resolution" value="approved">Approve</button><button className="danger" name="resolution" value="rejected">Reject</button></div></form>:null}</article>)}</div></section>
 </>;
}