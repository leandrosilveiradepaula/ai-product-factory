import Link from "next/link";
import {getWorkQueue} from "../../lib/control-plane";
import {ActionLink,EmptyState,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Queue(){
 const items=await getWorkQueue();
 const operational=items.filter(x=>!x.requiresReconciliation);
 const needsReview=items.filter(x=>x.requiresReconciliation);
 const waitingHuman=operational.filter(x=>x.status.includes("human")||x.status.includes("release")).length;
 const executing=operational.filter(x=>["running","implementing"].includes(x.status)).length;
 const queued=operational.filter(x=>["queued","queued_execution","dispatching"].includes(x.status)).length;
 const high=operational.filter(x=>x.complexity==="high").length;
 return <>
  <PageHeader eyebrow="Diagnóstico · trabalho automático" title="Fila de trabalho" subtitle="Acompanhe trabalho operacional e tarefas antigas que precisam de reconciliação. Estar na fila não significa autorização de execução." actions={<ActionLink href="/projects/new" variant="primary">+ Novo projeto</ActionLink>}/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Trabalho operacional</span><strong>{operational.length}</strong><small>itens que ainda exigem verificação dos gates</small></div>
   <div className="operationalStat"><span>Em execução</span><strong>{executing}</strong><small>estado registrado, não prova worker ativo</small></div>
   <div className="operationalStat warning"><span>Aguardando humano</span><strong>{waitingHuman}</strong><small>autoridade de decisão</small></div>
   <div className="operationalStat warning"><span>Para conciliar</span><strong>{needsReview.length}</strong><small>filhos de tarefas-pai encerradas</small></div>
  </div>

  <section className="section">
   <SectionHeader title="Backlog operacional" action={<span className="muted">{queued} marcados para despacho · {high} de alta complexidade</span>}/>
   <div className="table queueTable">
    <div className="tableRow tableHeader"><span>Tarefa / Projeto</span><span>Complexidade</span><span>Estado</span><span>Chave</span><span>Atualizada</span></div>
    {operational.length===0?<EmptyState>Nenhum trabalho operacional identificado neste inventário. Verifique também os itens para conciliar abaixo.</EmptyState>:operational.map(x=><div className="tableRow" key={x.id}>
     <div><strong>{x.title}</strong><div><Link className="muted" href={"/projects/"+x.projectKey}>{x.projectName}</Link></div></div>
     <StatusPill status={x.complexity}/>
     <StatusPill status={x.status}/>
     <code>{x.externalKey||x.id.slice(0,8)}</code>
     <span className="muted">{new Date(x.updatedAt).toLocaleString("pt-BR")}</span>
    </div>)}
   </div>
  </section>

  {needsReview.length>0?<section className="section">
   <SectionHeader title="Tarefas que exigem reconciliação" action={<span className="muted">{needsReview.length} registros preservados</span>}/>
   <p className="muted">Estas tarefas continuam registradas como pendentes, mas seus pais foram encerrados. Um pai concluído não comprova que o filho foi implementado nem autoriza executá-lo novamente. A Factory deve reconciliar Work Units, dependências, runs e gates antes de decidir o próximo passo. Esta área é apenas leitura.</p>
   <div className="table queueTable">
    <div className="tableRow tableHeader"><span>Tarefa / Projeto</span><span>Complexidade</span><span>Estado</span><span>Chave</span><span>Atualizada</span></div>
    {needsReview.map(x=><div className="tableRow" key={x.id}>
     <div><strong>{x.title}</strong><div><Link className="muted" href={"/projects/"+x.projectKey}>{x.projectName}</Link></div><small className="muted">Pai: {x.parentStatus||"desconhecido"} · reconciliação necessária</small></div>
     <StatusPill status={x.complexity}/>
     <StatusPill status={x.status}/>
     <code>{x.externalKey||x.id.slice(0,8)}</code>
     <span className="muted">{new Date(x.updatedAt).toLocaleString("pt-BR")}</span>
    </div>)}
   </div>
  </section>:null}

  <div className="overviewGrid section">
   <div className="card">
    <div className="panelHeading"><strong>Como a Factory escolhe a execução</strong><StatusPill status="active" label="política ativa"/></div>
    <div className="compactList">
     <div className="compactRow"><span>Ferramenta determinística</span><span className="muted">preferida</span></div>
     <div className="compactRow"><span>Executor direto</span><span className="muted">padrão com IA</span></div>
     <div className="compactRow"><span>Codex</span><span className="muted">somente quando justificado</span></div>
     <div className="compactRow"><span>Produção</span><span className="muted">gate humano</span></div>
    </div>
   </div>
   <div className="logPanel">queue.operational = {operational.length}<br/>queue.reconciliation = {needsReview.length}<br/>queue.queued_status = {queued}<br/>queue.running_status = {executing}<br/>queue.human_gate = {waitingHuman}</div>
  </div>
 </>;
}
