import {getUsageOverview} from "../../lib/control-plane";
import {EmptyState,MetricCard,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Usage(){
 const u=await getUsageOverview();
 return <>
  <PageHeader eyebrow="Observability" title="Models & Usage" subtitle="Ledger de ferramentas, custo conhecido e uso real de Codex. Custo pago desconhecido permanece fail-closed."/>
  <div className="grid compact">
   <MetricCard label="Known cost" value={u.knownCost.toFixed(4)}/>
   <MetricCard label="Tool events" value={u.toolEvents}/>
   <MetricCard label="Codex invocations" value={u.codexInvocations}/>
   <MetricCard label="Unknown paid cost" value={u.unknownPaidCostEvents} note={u.unknownPaidCostEvents?"execution must block":"clean"}/>
  </div>
  <section className="section"><SectionHeader title="Usage by tool family"/><div className="table"><div className="tableRow tableHeader"><span>Family</span><span>Events</span><span>Known cost</span><span>Share</span></div>{u.byFamily.length===0?<EmptyState>No usage recorded.</EmptyState>:u.byFamily.map(x=><div className="tableRow" key={x.family}><strong>{x.family}</strong><span>{x.events}</span><span>{x.knownCost.toFixed(4)}</span><span className="muted">{u.toolEvents?Math.round((x.events/u.toolEvents)*100):0}%</span></div>)}</div></section>
  <section className="section"><div className="card"><div className="badgeLine"><StatusPill status="healthy" label="Deterministic first"/><StatusPill status="pending" label="Primary model gated"/><StatusPill status="pending" label="Codex WIF gated"/></div><p className="muted" style={{marginBottom:0}}>A Factory só usa providers pagos quando enablement, credencial oficial, budget total e reserva por run estiverem válidos.</p></div></section>
 </>;
}