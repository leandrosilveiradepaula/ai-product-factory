import {notFound} from "next/navigation";
import {getRunDetail} from "../../../lib/control-plane";
import {EmptyState,humanizeStatus,PageHeader,SectionHeader,StatusPill} from "../../ui";

const stages=["discovery","specification","planning","implementation","review","validation","preview","human_gate","release","operations"];
const labels=["Descoberta","Especificação","Plano","Implementação","Revisão","Testes","Prévia","Gate humano","Liberação","Operação"];

export default async function RunDetailPage({params}:{params:Promise<{id:string}>}){
 const {id}=await params;const r=await getRunDetail(id);if(!r)notFound();
 const current=Math.max(0,stages.indexOf(r.projectStage));
 const cost=r.toolUsage.reduce((sum,x)=>sum+(x.cost||0),0);
 const units=r.toolUsage.reduce((sum,x)=>sum+(x.units||0),0);
 return <>
  <PageHeader eyebrow="Execução do pipeline" title={r.taskTitle} subtitle={r.projectName+" · "+r.id} actions={<><StatusPill status={r.route||"unrouted"}/><StatusPill status={r.status}/></>}/>
  <div className="runStageRail" aria-label="Etapas da execução">
   {labels.map((label,index)=><div className={index<current?"runStage done":index===current?"runStage current":"runStage"} key={label}><span className="runStageDot">{index<current?"✓":index+1}</span><strong>{label}</strong><small>{index===current?"atual":index<current?"concluída":"aguardando"}</small></div>)}
  </div>
  <div className="runDetailGrid">
   <section className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Executor e contexto</strong><StatusPill status={r.route||"unrouted"}/></div>
     <div className="runExecutorHero">
      <div><span className="detailLabel">Rota arbitrada</span><h3>{humanizeStatus(r.route||"unrouted")}</h3><p className="muted">A rota registrada no Control Plane é a fonte de verdade para esta execução.</p></div>
      <div className="runScore"><span>Estado</span><strong>{humanizeStatus(r.status)}</strong></div>
     </div>
     <div className="detailGrid">
      <div className="detailItem"><span className="detailLabel">Etapa</span><strong>{humanizeStatus(r.projectStage)}</strong></div>
      <div className="detailItem"><span className="detailLabel">Complexidade</span><strong>{humanizeStatus(r.taskComplexity)}</strong></div>
      <div className="detailItem"><span className="detailLabel">Branch</span><code>{r.branchName||"—"}</code></div>
      <div className="detailItem"><span className="detailLabel">Commit candidato</span><code>{r.candidateCommit||"—"}</code></div>
     </div>
     {r.lastError?<div className="errorText runError">{r.lastError}</div>:null}
    </div>

    <div className="card">
     <SectionHeader title="Artefatos e verificação"/>
     <div className="verificationGrid">
      <div><span className="detailLabel">Avaliações</span><strong>{r.evaluations.length}</strong><small>evidências</small></div>
      <div><span className="detailLabel">Implantações</span><strong>{r.deployments.length}</strong><small>registros</small></div>
      <div><span className="detailLabel">Ferramentas</span><strong>{r.toolUsage.length}</strong><small>{units} unidades</small></div>
      <div><span className="detailLabel">Custo conhecido</span><strong>{cost.toFixed(4)}</strong><small>ledger</small></div>
     </div>
     <div className="twoCol runEvidenceCols">
      <div className="compactList">{r.evaluations.length===0?<span className="muted">Nenhuma avaliação.</span>:r.evaluations.map(x=><div className="compactRow" key={x.id}><span><strong>{x.type}</strong><br/><span className="muted">{x.baselineRef||"sem baseline"}</span></span><StatusPill status={x.status} label={humanizeStatus(x.status)+(x.score==null?"":" · "+x.score)}/></div>)}</div>
      <div className="compactList">{r.deployments.length===0?<span className="muted">Nenhuma implantação.</span>:r.deployments.map(x=><div className="compactRow" key={x.id}><span><strong>{humanizeStatus(x.environment)}</strong><br/><code>{x.deploymentRef||"sem referência"}</code></span><StatusPill status={x.status}/></div>)}</div>
     </div>
    </div>

    {r.gates.length?<div className="card runGateCard"><div className="panelHeading"><strong>Aprovação humana</strong><StatusPill status={r.gates[0].status}/></div>{r.gates.map(g=><div className="compactRow" key={g.id}><span><strong>{humanizeStatus(g.type)}</strong><br/><span className="muted">{Array.isArray(g.reasons)?g.reasons.join(", "):String(g.reasons||"")}</span></span><span className="mono">{g.id.slice(0,8)}</span></div>)}</div>:null}
   </section>

   <aside className="denseStack">
    <div className="card runTimelineCard">
     <SectionHeader title="Linha do tempo da execução" action={<span className="muted">{r.audit.length} eventos</span>}/>
     {r.audit.length===0?<EmptyState>Nenhum evento de auditoria.</EmptyState>:<div className="timeline">{r.audit.map(x=><div className="timelineItem" key={x.id}><strong>{x.eventType}</strong><div className="timelineMeta"><span>{new Date(x.createdAt).toLocaleString("pt-BR")}</span><span>{x.actorType}{x.actorRef?" · "+x.actorRef:""}</span></div></div>)}</div>}
    </div>
    <div className="card">
     <div className="panelHeading"><strong>Recursos e custo</strong><StatusPill status={r.lastError?"attention":"healthy"} label={r.lastError?"atenção":"dentro da política"}/></div>
     <div className="compactList">
      <div className="compactRow"><span className="muted">Tentativas</span><strong>{r.attemptCount}</strong></div>
      <div className="compactRow"><span className="muted">Lease owner</span><span>{r.leaseOwner||"—"}</span></div>
      <div className="compactRow"><span className="muted">Expiração</span><span>{r.leaseExpiresAt?new Date(r.leaseExpiresAt).toLocaleString("pt-BR"):"—"}</span></div>
      <div className="compactRow"><span className="muted">Custo conhecido</span><strong>{cost.toFixed(4)}</strong></div>
     </div>
     <div className="resourceList">{r.toolUsage.map(x=><div className="resourceRow" key={x.id}><div><strong>{x.family}</strong><span>{x.operation||"operação"}</span></div><div><strong>{x.cost==null?"—":x.cost.toFixed(4)}</strong><span>{x.units==null?"":x.units+" un."}</span></div></div>)}</div>
    </div>
    <div className="logPanel">run.id = {r.id}<br/>candidate = {r.candidateCommit||"none"}<br/>route = {r.route||"unrouted"}<br/>status = {r.status}</div>
   </aside>
  </div>
 </>;
}
