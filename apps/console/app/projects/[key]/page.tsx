import {notFound} from "next/navigation";
import {getProjectDetail,getProjectOperations} from "../../../lib/control-plane";
import {ActionLink,EmptyState,MetricCard,PageHeader,SectionHeader,StatusPill} from "../../ui";

const stages=["discovery","specification","planning","implementation","review","validation","preview","human_gate","release","operations"];
const stageLabels=["Discovery","Spec","Plano","Build","Review","Testes / Evals","Preview","Aprovação","Release","Operação"];
function progress(stage:string){const i=stages.indexOf(stage);return i<0?0:Math.round(((i+1)/stages.length)*100)}

export default async function Project({params}:{params:Promise<{key:string}>}){
 const {key}=await params;const p=await getProjectDetail(key);if(!p)notFound();const ops=await getProjectOperations(p.id);const activeTasks=p.tasks.filter(t=>!["completed","cancelled"].includes(t.status));
 return <>
  <PageHeader eyebrow="Project Detail" title={p.name} subtitle={p.repository||p.key} actions={<><StatusPill status={p.stage} tone="accent"/><ActionLink href="/queue">Work Queue</ActionLink></>}/>
  <div className="lifecycleRail" aria-label="Ciclo do produto"><span className="lifecycleIdea done">Ideia</span>{stageLabels.map((label,i)=><span key={label} className={i<stages.indexOf(p.stage)?"done":i===stages.indexOf(p.stage)?"current":""}>{label}</span>)}</div>
  <div className="grid compact">
   <MetricCard label="Lifecycle" value={progress(p.stage)+"%"} note={<div className="progressTrack"><div className="progressFill" style={{width:progress(p.stage)+"%"}}/></div>}/>
   <MetricCard label="Open tasks" value={activeTasks.length} note={p.tasks.length+" total"}/>
   <MetricCard label="Known cost" value={ops.estimatedCost.toFixed(4)} note={ops.usageUnits+" usage units"}/>
   <MetricCard label="Evidence" value={ops.evaluations+ops.deployments} note={ops.evaluations+" evals · "+ops.deployments+" deploys"}/>
  </div>
  <section className="section"><SectionHeader title="Backlog" action={<span className="muted">{p.tasks.length} tasks</span>}/><div className="table">
   <div className="tableRow tableHeader"><span>Task</span><span>Complexity</span><span>Status</span><span>Key</span></div>
   {p.tasks.length===0?<EmptyState>Nenhuma tarefa registrada.</EmptyState>:p.tasks.map(t=><div className="tableRow" key={t.id}><strong>{t.title}</strong><StatusPill status={t.complexity}/><StatusPill status={t.status}/><span className="muted mono">{t.externalKey||t.id.slice(0,8)}</span></div>)}
  </div></section>
  <section className="section"><SectionHeader title="Operational timeline" action={<span className="muted">{ops.timeline.length} evidence events</span>}/>
   {ops.timeline.length===0?<EmptyState>Ainda não há evidências operacionais para este projeto.</EmptyState>:<div className="card"><div className="timeline">{ops.timeline.slice(0,40).map(item=><div className="timelineItem" key={item.id}><div className="badgeLine"><StatusPill status={item.kind}/><strong>{item.title}</strong>{item.status?<StatusPill status={item.status}/>:null}</div><div className="timelineMeta"><span>{new Date(item.at).toLocaleString("pt-BR")}</span>{item.detail?<span>{item.detail}</span>:null}{item.cost!=null?<span>cost {item.cost}</span>:null}{item.ref?<code>{item.ref}</code>:null}</div></div>)}</div></div>}
  </section>
 </>;
}