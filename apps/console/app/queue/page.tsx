import Link from "next/link";
import {getWorkQueue} from "../../lib/control-plane";
import {ActionLink,EmptyState,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Queue(){
 const items=await getWorkQueue();
 const high=items.filter(x=>x.complexity==="high").length;
 const waitingHuman=items.filter(x=>x.status.includes("human")||x.status.includes("release")).length;
 const executing=items.filter(x=>["running","implementing"].includes(x.status)).length;
 const queued=items.filter(x=>["queued","queued_execution","dispatching"].includes(x.status)).length;
 return <>
  <PageHeader eyebrow="Backlog ativo · despacho autônomo" title="Fila de trabalho" subtitle="Priorização, despacho e estado operacional do backlog executável da Factory." actions={<ActionLink href="/projects/new" variant="primary">+ Novo trabalho</ActionLink>}/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Total na fila</span><strong>{items.length}</strong><small>backlog carregado</small></div>
   <div className="operationalStat"><span>Em execução</span><strong>{executing}</strong><small>workers ativos</small></div>
   <div className="operationalStat warning"><span>Aguardando humano</span><strong>{waitingHuman}</strong><small>bloqueio por autoridade</small></div>
   <div className="operationalStat"><span>Alta complexidade</span><strong>{high}</strong><small>candidatas a rota seletiva</small></div>
  </div>

  <section className="section">
   <SectionHeader title="Backlog operacional" action={<span className="muted">{queued} aguardando despacho</span>}/>
   <div className="table queueTable">
    <div className="tableRow tableHeader"><span>Tarefa / Projeto</span><span>Complexidade</span><span>Estado</span><span>Chave</span><span>Atualizada</span></div>
    {items.length===0?<EmptyState>Fila vazia. Nenhum trabalho pendente.</EmptyState>:items.map(x=><div className="tableRow" key={x.id}>
     <div><strong>{x.title}</strong><div><Link className="muted" href={"/projects/"+x.projectKey}>{x.projectName}</Link></div></div>
     <StatusPill status={x.complexity}/>
     <StatusPill status={x.status}/>
     <code>{x.externalKey||x.id.slice(0,8)}</code>
     <span className="muted">{new Date(x.updatedAt).toLocaleString("pt-BR")}</span>
    </div>)}
   </div>
  </section>

  <div className="overviewGrid section">
   <div className="card">
    <div className="panelHeading"><strong>Status de execução</strong><StatusPill status="active" label="política ativa"/></div>
    <div className="compactList">
     <div className="compactRow"><span>Ferramenta determinística</span><span className="muted">preferida</span></div>
     <div className="compactRow"><span>Executor direto</span><span className="muted">padrão com IA</span></div>
     <div className="compactRow"><span>Codex</span><span className="muted">somente quando justificado</span></div>
     <div className="compactRow"><span>Produção</span><span className="muted">gate humano</span></div>
    </div>
   </div>
   <div className="logPanel">queue.total = {items.length}<br/>queue.waiting = {queued}<br/>queue.running = {executing}<br/>queue.human_gate = {waitingHuman}</div>
  </div>
 </>;
}
