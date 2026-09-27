import Link from "next/link";
import {getWorkQueue} from "../../lib/control-plane";
function tone(status:string){return status==="awaiting_human"?"warning":status.includes("fail")?"danger":status==="running"||status==="implementing"?"accent":""}
export default async function Queue(){
 const items=await getWorkQueue();
 return <><div className="pageHeader"><div><div className="eyebrow">Execution</div><h1 className="title">Work Queue</h1><p className="subtitle">Backlog executável e trabalho atualmente aguardando dispatch, execução ou autoridade humana.</p></div><Link className="primary linkButton" href="/projects/new">+ New Work</Link></div>
 <div className="table"><div className="tableRow tableHeader"><span>Task / Project</span><span>Complexity</span><span>Status</span><span>Updated</span></div>{items.length===0?<div className="emptyState">Fila vazia. Nenhum trabalho pendente.</div>:items.map(x=><div className="tableRow" key={x.id}><div><strong>{x.title}</strong><div><Link className="muted" href={`/projects/${x.projectKey}`}>{x.projectName}</Link></div></div><span className="pill">{x.complexity}</span><span className={`pill ${tone(x.status)}`}>{x.status}</span><span className="muted">{new Date(x.updatedAt).toLocaleString("pt-BR")}</span></div>)}</div></>;
}