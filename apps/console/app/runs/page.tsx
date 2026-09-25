import {getRuns} from "../../lib/control-plane";

export default async function Runs(){
 const runs=await getRuns();
 return <><div className="eyebrow">Execution</div><h1 className="title">Execuções</h1><p className="muted">Runs, rotas de execução e candidatos produzidos pela Factory.</p><section className="section"><div className="row muted"><span>Tarefa</span><span>Rota</span><span>Status</span><span>Commit</span></div>{runs.length===0?<div className="card">Nenhuma execução registrada.</div>:runs.map(r=><div className="row" key={r.id}><div><strong>{r.taskTitle}</strong><div className="muted">{r.id.slice(0,8)}</div></div><span className="pill">{r.route||"—"}</span><span className="status"><i className={`dot ${r.status==="failed"?"warn":""}`}/>{r.status}</span><span className="muted">{r.candidateCommit?r.candidateCommit.slice(0,10):"—"}</span></div>)}</section></>
}