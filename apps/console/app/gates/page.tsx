import {revalidatePath} from "next/cache";
import {getHumanGates,resolveHumanGate} from "../../lib/control-plane";

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
  <div className="pageHeader"><div><div className="eyebrow">Human Authority</div><h1 className="title">Human Gates</h1><p className="subtitle">A Factory só interrompe quando produção, dados, acesso, custo recorrente ou requisito material exigem autoridade humana.</p></div></div>
  <div className="grid compact"><div className="card metricCard"><span className="metricLabel">Pending</span><div className="metric">{pending.length}</div></div><div className="card metricCard"><span className="metricLabel">History</span><div className="metric">{gates.length}</div></div><div className="card metricCard"><span className="metricLabel">Policy</span><div className="metric">Fail closed</div></div><div className="card metricCard"><span className="metricLabel">Production</span><div className="metric">Human</div></div></div>
  <section className="section"><div className="stack">{gates.length===0?<div className="emptyState"><span className="status"><i className="statusDot"/>No human gates recorded.</span></div>:gates.map(g=><article className="card" key={g.id}><div className="cardTop"><div><span className="pill">{g.type}</span><h2 style={{margin:"10px 0 5px",fontSize:15}}>{g.status==="pending"?"Decision required":"Gate resolved"}</h2><p className="muted" style={{margin:0}}>{reasonText(g.reasons)}</p></div><span className={g.status==="pending"?"pill warning":"pill success"}>{g.status}</span></div><div className="timelineMeta"><span>run {g.runId.slice(0,8)}</span><span>{new Date(g.requestedAt).toLocaleString("pt-BR")}</span></div>{g.status==="pending"?<form action={resolveGate} className="gateForm"><input type="hidden" name="gate_id" value={g.id}/><input name="note" placeholder="Optional decision note"/><div className="actions"><button className="primary" name="resolution" value="approved">Approve</button><button className="danger" name="resolution" value="rejected">Reject</button></div></form>:null}</article>)}</div></section>
 </>;
}