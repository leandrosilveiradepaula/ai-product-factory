import Link from "next/link";
import {notFound} from "next/navigation";
import {getProjectDetail,getProjectOperations} from "../../../lib/control-plane";

const stages=["discovery","specification","planning","implementation","review","validation","preview","human_gate","release","operations"];
function progress(stage:string){const i=stages.indexOf(stage);return i<0?0:Math.round(((i+1)/stages.length)*100)}
function tone(status:string){return status.includes("fail")?"danger":status==="awaiting_human"?"warning":status==="completed"||status==="merged"?"success":""}

export default async function Project({params}:{params:Promise<{key:string}>}){
 const {key}=await params;const p=await getProjectDetail(key);if(!p)notFound();const ops=await getProjectOperations(p.id);const activeTasks=p.tasks.filter(t=>!["completed","cancelled"].includes(t.status));
 return <>
  <div className="pageHeader"><div><div className="eyebrow">Project Detail</div><h1 className="title">{p.name}</h1><p className="subtitle">{p.repository||p.key}</p></div><div className="toolbar"><span className="pill accent">{p.stage}</span><Link className="secondary linkButton" href="/queue">Work Queue</Link></div></div>
  <div className="grid compact">
   <div className="card metricCard"><span className="metricLabel">Lifecycle</span><div className="metric">{progress(p.stage)}%</div><div className="progressTrack"><div className="progressFill" style={{width:`${progress(p.stage)}%`}}/></div></div>
   <div className="card metricCard"><span className="metricLabel">Open tasks</span><div className="metric">{activeTasks.length}</div><div className="metricNote">{p.tasks.length} total</div></div>
   <div className="card metricCard"><span className="metricLabel">Known cost</span><div className="metric">{ops.estimatedCost.toFixed(4)}</div><div className="metricNote">{ops.usageUnits} usage units</div></div>
   <div className="card metricCard"><span className="metricLabel">Evidence</span><div className="metric">{ops.evaluations+ops.deployments}</div><div className="metricNote">{ops.evaluations} evals · {ops.deployments} deploys</div></div>
  </div>
  <section className="section"><div className="sectionHeader"><h2>Backlog</h2><span className="muted">{p.tasks.length} tasks</span></div><div className="table">
   <div className="tableRow tableHeader"><span>Task</span><span>Complexity</span><span>Status</span><span>Key</span></div>
   {p.tasks.length===0?<div className="emptyState">Nenhuma tarefa registrada.</div>:p.tasks.map(t=><div className="tableRow" key={t.id}><strong>{t.title}</strong><span className="pill">{t.complexity}</span><span className={`pill ${tone(t.status)}`}>{t.status}</span><span className="muted mono">{t.externalKey||t.id.slice(0,8)}</span></div>)}
  </div></section>
  <section className="section"><div className="sectionHeader"><h2>Operational timeline</h2><span className="muted">{ops.timeline.length} evidence events</span></div>
   {ops.timeline.length===0?<div className="emptyState">Ainda não há evidências operacionais para este projeto.</div>:<div className="card"><div className="timeline">{ops.timeline.slice(0,40).map(item=><div className="timelineItem" key={item.id}><div className="badgeLine"><span className="pill">{item.kind}</span><strong>{item.title}</strong>{item.status?<span className={`pill ${tone(item.status)}`}>{item.status}</span>:null}</div><div className="timelineMeta"><span>{new Date(item.at).toLocaleString("pt-BR")}</span>{item.detail?<span>{item.detail}</span>:null}{item.cost!=null?<span>cost {item.cost}</span>:null}{item.ref?<code>{item.ref}</code>:null}</div></div>)}</div></div>}
  </section>
 </>;
}