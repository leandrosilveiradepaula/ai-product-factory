import Link from "next/link";
import {getEvaluations} from "../../lib/control-plane";
import {EmptyState,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Evals(){
 const rows=await getEvaluations();
 const passed=rows.filter(x=>["passed","success"].includes(x.status)).length;
 const failed=rows.filter(x=>x.status==="failed").length;
 const scored=rows.filter(x=>x.score!=null);
 const avg=scored.length?scored.reduce((s,x)=>s+(x.score||0),0)/scored.length:null;
 return <>
  <PageHeader eyebrow="Qualidade · evidências automáticas" title="Avaliações e testes" subtitle="Resultados de testes e avaliações usados pela Factory para decidir se um candidato pode avançar. Consulte principalmente quando houver uma falha." actions={<StatusPill status={failed?"attention":"healthy"} label={failed?"falhas detectadas":"quality gate limpo"}/>}/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Avaliações</span><strong>{rows.length}</strong><small>registros duráveis</small></div>
   <div className="operationalStat"><span>Aprovadas</span><strong>{passed}</strong><small>evidências verdes</small></div>
   <div className="operationalStat danger"><span>Falharam</span><strong>{failed}</strong><small>bloqueiam avanço</small></div>
   <div className="operationalStat"><span>Pontuação média</span><strong>{avg==null?"—":avg.toFixed(2)}</strong><small>{scored.length} com score</small></div>
  </div>

  <div className="overviewGrid">
   <section>
    <SectionHeader title="Suítes e resultados" action={<span className="muted">{rows.length} registros</span>}/>
    <div className="table evalTable">
     <div className="tableRow tableHeader"><span>Avaliação / Tarefa</span><span>Projeto</span><span>Estado</span><span>Score</span><span>Criada</span></div>
     {rows.length===0?<EmptyState>Ainda não há evidências de avaliação.</EmptyState>:rows.map(x=><div className="tableRow" key={x.id}>
      <div><strong>{x.type}</strong><div><Link className="muted" href={"/runs/"+x.runId}>{x.taskTitle}</Link></div></div>
      <Link href={"/projects/"+x.projectKey}>{x.projectName}</Link>
      <StatusPill status={x.status}/>
      <span>{x.score==null?"—":x.score}</span>
      <span className="muted">{new Date(x.createdAt).toLocaleString("pt-BR")}</span>
     </div>)}
    </div>
   </section>

   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Como interpretar</strong><StatusPill status={failed?"attention":"healthy"} label={failed?"atenção":"sem regressão crítica"}/></div>
     <div className="compactList">
      <div className="compactRow"><span className="muted">Mesmo commit candidato</span><span>obrigatório</span></div>
      <div className="compactRow"><span className="muted">Falha de avaliação</span><span>bloqueia</span></div>
      <div className="compactRow"><span className="muted">Preview</span><span>exige evidência</span></div>
      <div className="compactRow"><span className="muted">Produção</span><span>continua humana</span></div>
     </div>
    </div>
    <div className="logPanel">quality.total = {rows.length}<br/>quality.passed = {passed}<br/>quality.failed = {failed}<br/>quality.avg_score = {avg==null?"none":avg.toFixed(4)}</div>
   </aside>
  </div>
 </>;
}
