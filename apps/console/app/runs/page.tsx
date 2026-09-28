import Link from "next/link";
import {getOperationsHealth,getRuns} from "../../lib/control-plane";
import {ActionLink,EmptyState,MetricCard,PageHeader,SectionHeader,StatusPill} from "../ui";

function leaseText(value:string|null){if(!value)return "—";const d=new Date(value);return Number.isNaN(d.getTime())?value:d.toLocaleString("pt-BR")}

export default async function Runs(){
 const [runs,health]=await Promise.all([getRuns(),getOperationsHealth()]);
 return <>
  <PageHeader eyebrow="Execução" title="Execuções" subtitle="Execuções, leases, tentativas, commits candidatos e incidentes do Control Plane." actions={<ActionLink href="/queue">Abrir fila de trabalho</ActionLink>}/>
  <div className="kpiStrip">
   <MetricCard compact label="Carregadas" value={runs.length}/>
   <MetricCard compact label="Na fila" value={health.queuedRuns}/>
   <MetricCard compact label="Com falha" value={health.failedRuns}/>
   <MetricCard compact label="Lease expirado" value={health.expiredLeases}/>
   <MetricCard compact label="Fila de erro" value={health.deadLetterRuns}/>
   <MetricCard compact label="Custo conhecido" value={health.knownCost.toFixed(4)}/>
  </div>
  {health.incidents.length?<section className="section"><SectionHeader title="Requer atenção" action={<StatusPill status="attention" label={health.incidents.length}/>}/><div className="stack">{health.incidents.map(i=><Link className="card projectCard" href={"/runs/"+i.id} key={i.id}><div className="cardTop"><strong>{i.id.slice(0,8)} · {i.status}</strong><StatusPill status={i.route||"unrouted"}/></div><p className="muted">tentativas {i.attempts} · lease {leaseText(i.leaseExpiresAt)}</p>{i.error?<div className="errorText">{i.error}</div>:null}</Link>)}</div></section>:null}
  <section className="section"><SectionHeader title="Histórico de execuções" action={<span className="muted">{runs.length} registros</span>}/><div className="table"><div className="runHeader"><span>Tarefa</span><span>Rota / estado</span><span>Tentativas / lease</span><span>Commit / erro</span></div>{runs.length===0?<EmptyState>Nenhuma execução registrada.</EmptyState>:runs.map(r=><Link href={"/runs/"+r.id} className="runRow" key={r.id}><div><strong>{r.taskTitle}</strong><div className="muted mono">{r.id.slice(0,12)}</div></div><div><StatusPill status={r.route||"unrouted"}/><div style={{marginTop:7}}><StatusPill status={r.status}/></div></div><div><strong>{r.attemptCount}</strong><div className="muted">{r.leaseOwner||"sem lease"}</div><small className="muted">{leaseText(r.leaseExpiresAt)}</small></div><div><span className="muted mono">{r.candidateCommit?r.candidateCommit.slice(0,12):"—"}</span>{r.lastError?<div className="errorText">{r.lastError}</div>:null}</div></Link>)}</div></section>
 </>;
}