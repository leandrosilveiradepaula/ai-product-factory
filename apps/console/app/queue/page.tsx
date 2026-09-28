import Link from "next/link";
import {getWorkQueue} from "../../lib/control-plane";
import {ActionLink,EmptyState,PageHeader,StatusPill} from "../ui";

export default async function Queue(){
 const items=await getWorkQueue();
 const high=items.filter(x=>x.complexity==="high").length;
 const waitingHuman=items.filter(x=>x.status.includes("human")||x.status.includes("release")).length;
 return <>
  <PageHeader eyebrow="Fila de trabalho" title="Fila de trabalho" subtitle="Trabalho executável aguardando distribuição, execução ou autoridade humana." actions={<ActionLink href="/projects/new" variant="primary">+ Novo projeto</ActionLink>}/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Total na fila</span><strong>{items.length}</strong></div>
   <div className="operationalStat"><span>Alta complexidade</span><strong>{high}</strong></div>
   <div className="operationalStat"><span>Aguardando humano</span><strong>{waitingHuman}</strong></div>
   <div className="operationalStat"><span>Roteamento</span><strong>automático</strong></div>
  </div>
  <div className="table">
   <div className="tableRow tableHeader"><span>Tarefa / Projeto</span><span>Complexidade</span><span>Estado</span><span>Atualizada em</span></div>
   {items.length===0?<EmptyState>Fila vazia. Nenhum trabalho pendente.</EmptyState>:items.map(x=><div className="tableRow" key={x.id}>
    <div><strong>{x.title}</strong><div><Link className="muted" href={"/projects/"+x.projectKey}>{x.projectName}</Link></div></div>
    <StatusPill status={x.complexity}/><StatusPill status={x.status}/><span className="muted">{new Date(x.updatedAt).toLocaleString("pt-BR")}</span>
   </div>)}
  </div>
  <section className="section"><div className="logPanel">queue.policy = deterministic_first<br/>queue.codex = selective<br/>queue.production = human_gate</div></section>
 </>;
}