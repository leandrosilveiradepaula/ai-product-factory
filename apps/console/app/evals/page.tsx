import Link from "next/link";
import {getEvaluations} from "../../lib/control-plane";
import {EmptyState,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Evals(){
 const rows=await getEvaluations();
 const passed=rows.filter(x=>["passed","success"].includes(x.status)).length;
 const failed=rows.filter(x=>x.status==="failed").length;
 const scored=rows.filter(x=>x.score!=null).length;
 return <>
  <PageHeader eyebrow="Avaliações · Qualidade" title="Avaliações" subtitle="Evidências de qualidade vinculadas a execuções e candidatos específicos."/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Total</span><strong>{rows.length}</strong></div>
   <div className="operationalStat"><span>Aprovadas</span><strong>{passed}</strong></div>
   <div className="operationalStat"><span>Falharam</span><strong>{failed}</strong></div>
   <div className="operationalStat"><span>Com pontuação</span><strong>{scored}</strong></div>
  </div>
  <div className="overviewGrid">
   <section>
    <SectionHeader title="Resultados de avaliação" action={<span className="muted">{rows.length} registros</span>}/>
    <div className="table">
     <div className="tableRow tableHeader"><span>Avaliação / Tarefa</span><span>Projeto</span><span>Estado / Pontuação</span><span>Criada em</span></div>
     {rows.length===0?<EmptyState>Ainda não há evidências de avaliação.</EmptyState>:rows.map(x=><div className="tableRow" key={x.id}>
      <div><strong>{x.type}</strong><div><Link className="muted" href={"/runs/"+x.runId}>{x.taskTitle}</Link></div></div>
      <Link href={"/projects/"+x.projectKey}>{x.projectName}</Link>
      <StatusPill status={x.status} label={x.status+(x.score==null?"":" · "+x.score)}/>
      <span className="muted">{new Date(x.createdAt).toLocaleString("pt-BR")}</span>
     </div>)}
    </div>
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Quality gate</strong><StatusPill status={failed?"attention":"healthy"} label={failed?"atenção":"sem falhas"}/></div>
     <div className="compactList">
      <div className="compactRow"><span className="muted">Evidência por candidato</span><span>obrigatória</span></div>
      <div className="compactRow"><span className="muted">Falha</span><span>bloqueia avanço</span></div>
      <div className="compactRow"><span className="muted">Preview</span><span>mesmo commit</span></div>
      <div className="compactRow"><span className="muted">Produção</span><span>gate humano</span></div>
     </div>
    </div>
    <div className="logPanel">quality.total = {rows.length}<br/>quality.passed = {passed}<br/>quality.failed = {failed}<br/>quality.scored = {scored}</div>
   </aside>
  </div>
 </>;
}