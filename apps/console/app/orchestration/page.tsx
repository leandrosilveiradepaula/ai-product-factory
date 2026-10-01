import Link from "next/link";
import {getOrchestrationOverview} from "../../lib/control-plane";
import {EmptyState,MetricCard,PageHeader,SectionHeader,StatusPill} from "../ui";

function incidentNext(status:string){
 const map:Record<string,string>={
  triage:"Classificar evidências e iniciar investigação.",
  investigating:"Coletar evidências antes de propor correção.",
  evidence:"Escolher reparo mínimo ou validação direcionada.",
  repair:"Concluir reparo e executar validação direcionada.",
  targeted_validation:"Passar pelos gates completos.",
  full_gates:"Validar todos os gates antes de resolver.",
  blocked:"Resolver o bloqueio registrado e retomar a investigação.",
 };
 return map[status]||"Aguardar próxima transição registrada.";
}
function repairNext(status:string){
 if(status==="queued")return "Development executará o reparo no scope atribuído.";
 if(status==="running")return "Aguardar integração do reparo.";
 if(status==="integrated")return "Security/QA revalidará o candidato integrado.";
 if(status==="blocked"||status==="exhausted")return "Intervenção necessária: o reparo automático não pode continuar.";
 return "Aguardar próxima evidência.";
}
function releaseNext(status:string){
 return status==="ready_for_human_release"?"Aguardando merge humano de produção.":"Resolver blockers factuais antes do release.";
}

export default async function Orchestration(){
 const data=await getOrchestrationOverview();
 const urgent=data.incidents.filter(x=>x.severity==="P0"||x.severity==="P1");
 const blockedReleases=data.releases.filter(x=>x.status==="blocked");
 const ready=data.releases.filter(x=>x.status==="ready_for_human_release");
 return <>
  <PageHeader eyebrow="Orquestração adaptativa" title="Operação da Factory"
   subtitle="Visão técnica do motor da Factory: prioridades, incidentes, ciclos de reparo, reexecuções de análise e prontidão para liberação."/>
  <div className="grid compact">
   <MetricCard label="Projetos no portfólio" value={data.projects.length} note={data.projects.filter(x=>x.paused).length+" pausados"}/>
   <MetricCard label="Incidentes ativos" value={data.incidents.length} note={urgent.length+" P0/P1"}/>
   <MetricCard label="Repairs ativos" value={data.repairs.length} note="máximo de 3 ciclos por origem"/>
   <MetricCard label="Prontos para humano" value={ready.length} note={blockedReleases.length+" releases bloqueados"}/>
  </div>

  <section className="section">
   <SectionHeader title="Portfólio e prioridade" action={<span className="muted">novos trabalhos respeitam esta ordem</span>}/>
   {data.projects.length===0?<EmptyState>Nenhum projeto ativo.</EmptyState>:<div className="table">
    <div className="tableRow tableHeader"><span>Projeto</span><span>Prioridade</span><span>Prazo / impacto</span><span>Capacidade</span></div>
    {data.projects.map(p=><Link href={"/projects/"+p.projectKey} className="tableRow" key={p.projectId}>
     <div><strong>{p.projectName}</strong><div className="muted mono">{p.projectKey}</div></div>
     <div><StatusPill status={p.paused?"blocked":p.priority} label={p.paused?"Pausado":p.priority}/></div>
     <span>{p.deadline?new Date(p.deadline).toLocaleString("pt-BR"):"sem prazo"} · impacto {p.customerImpact}/5</span>
     <span>até {p.maxActiveWorkers} workers</span>
    </Link>)}
   </div>}
  </section>

  <section className="section">
   <SectionHeader title="Incidentes ativos" action={<span className="muted">P0 faz preempção suave apenas de novos trabalhos</span>}/>
   {data.incidents.length===0?<EmptyState>Nenhum incidente ativo.</EmptyState>:<div className="stack">
    {data.incidents.map(i=><div className="card" key={i.id}>
     <div className="cardTop"><div className="badgeLine"><StatusPill status={i.severity}/><StatusPill status={i.status}/><strong>{i.title}</strong></div><Link href={"/projects/"+i.projectKey} className="muted">Abrir {i.projectName} →</Link></div>
     <p>{i.summary}</p>
     <div className="twoCol"><div><span className="detailLabel">Por que está aqui</span><p className="muted">Incidente {i.severity} em {i.status}.</p></div><div><span className="detailLabel">Próxima ação</span><p>{incidentNext(i.status)}</p></div></div>
    </div>)}
   </div>}
  </section>

  <section className="section">
   <SectionHeader title="Ciclos automáticos de reparo" action={<span className="muted">Security/QA continuam independentes</span>}/>
   {data.repairs.length===0?<EmptyState>Nenhum reparo automático ativo.</EmptyState>:<div className="table">
    <div className="tableRow tableHeader"><span>Projeto / origem</span><span>Ciclo</span><span>Estado</span><span>Próxima ação</span></div>
    {data.repairs.map(r=><div className="tableRow" key={r.id}>
     <div><Link href={"/projects/"+r.projectKey}><strong>{r.projectName}</strong></Link><div className="muted">{r.sourceRole} → {r.ownerAgentKey}</div></div>
     <span>{r.cycle}/{r.maxCycles}</span>
     <StatusPill status={r.status}/>
     <span>{repairNext(r.status)}</span>
    </div>)}
   </div>}
  </section>

  <section className="section">
   <SectionHeader title="Prontidão de release" action={<span className="muted">fatos, não score subjetivo</span>}/>
   {data.releases.length===0?<EmptyState>Nenhum candidato aguardando release.</EmptyState>:<div className="stack">
    {data.releases.map(r=><div className="card" key={r.id}>
     <div className="cardTop"><div><strong>{r.projectName}</strong><div className="muted mono">{r.candidateCommit.slice(0,12)}</div></div><StatusPill status={r.status}/></div>
     <div className="twoCol"><div><span className="detailLabel">Estado factual</span><p>{releaseNext(r.status)}</p></div><div><span className="detailLabel">Rollback</span><p>{r.rollback?.verified===true?"evidência verificada":r.rollback?.required===true?"ainda requerido":"não requerido pelo relatório"}</p></div></div>
     <div className="badgeLine"><Link href={"/runs/"+r.runId}>Abrir execução</Link><Link href={"/projects/"+r.projectKey}>Abrir projeto</Link></div>
    </div>)}
   </div>}
  </section>

  <section className="section">
   <SectionHeader title="Reanálise e aprendizado" action={<span className="muted">sempre zero-effect</span>}/>
   <div className="twoCol">
    <div className="card"><span className="detailLabel">Replay / Shadow recentes</span>
     {data.replays.length===0?<p className="muted">Nenhum replay registrado.</p>:<div className="valueList">{data.replays.slice(0,10).map(r=><div className="valueRow" key={r.id}><div><strong>{r.mode}</strong><div><Link href={"/runs/"+r.sourceRunId} className="muted mono">abrir execução {r.sourceRunId.slice(0,8)} →</Link></div></div><span>{r.effect} · modelo {r.modelCallsAllowed?"permitido":"desativado"}</span></div>)}</div>}
    </div>
    <div className="card"><span className="detailLabel">Propostas de melhoria</span>
     {data.proposals.length===0?<p className="muted">Nenhuma proposta pendente.</p>:<div className="valueList">{data.proposals.slice(0,10).map(p=><div className="valueRow" key={p.id}><strong>{p.proposalKey}</strong><span>{p.requiresSourceControl?"via source control":"sem source control"} · {p.autoApply?"auto":"não autoaplica"}</span></div>)}</div>}
    </div>
   </div>
  </section>
 </>;
}
