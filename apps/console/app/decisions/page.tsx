import {getHumanGates} from "../../lib/control-plane";

function reasonText(value:unknown){if(Array.isArray(value))return value.join(", ");if(value&&typeof value==="object")return JSON.stringify(value);return value?String(value):"Sem motivo adicional";}

export default async function Decisions(){
 const gates=await getHumanGates();
 const pending=gates.filter(g=>g.status==="pending");
 return <><div className="eyebrow">Human gates</div><h1 className="title">Decisões</h1><p className="muted">A Factory só interrompe você quando uma decisão realmente exige autoridade humana.</p><div className="grid"><div className="card"><span className="muted">Pendentes</span><div className="metric">{pending.length}</div></div><div className="card"><span className="muted">Histórico carregado</span><div className="metric">{gates.length}</div></div></div><section className="section">{gates.length===0?<div className="card"><span className="status"><i className="dot"/>Nenhuma decisão registrada</span></div>:gates.map(g=><article className="card" key={g.id}><div className="heading"><div><span className="pill">{g.type}</span><h2>{g.status==="pending"?"Decisão necessária":"Gate resolvido"}</h2></div><span className="status"><i className={`dot ${g.status==="pending"?"warn":""}`}/>{g.status}</span></div><p className="muted">{reasonText(g.reasons)}</p><small className="muted">Run {g.runId.slice(0,8)} · {new Date(g.requestedAt).toLocaleString("pt-BR")}</small></article>)}</section></>
}