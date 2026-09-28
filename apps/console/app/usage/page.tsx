import {getUsageOverview} from "../../lib/control-plane";
import {EmptyState,MetricCard,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Usage(){
 const u=await getUsageOverview();
 return <>
  <PageHeader eyebrow="Observabilidade" title="Modelos e uso" subtitle="Ledger de ferramentas, custo conhecido e uso real de Codex. Custo pago desconhecido permanece fail-closed."/>
  <div className="grid compact">
   <MetricCard label="Custo conhecido" value={u.knownCost.toFixed(4)}/>
   <MetricCard label="Eventos de ferramentas" value={u.toolEvents}/>
   <MetricCard label="Invocações do Codex" value={u.codexInvocations}/>
   <MetricCard label="Custo pago desconhecido" value={u.unknownPaidCostEvents} note={u.unknownPaidCostEvents?"a execução deve bloquear":"sem pendências"}/>
  </div>
  <section className="section"><SectionHeader title="Uso por família de ferramenta"/><div className="table"><div className="tableRow tableHeader"><span>Família</span><span>Eventos</span><span>Custo conhecido</span><span>Participação</span></div>{u.byFamily.length===0?<EmptyState>Nenhum uso registrado.</EmptyState>:u.byFamily.map(x=><div className="tableRow" key={x.family}><strong>{x.family}</strong><span>{x.events}</span><span>{x.knownCost.toFixed(4)}</span><span className="muted">{u.toolEvents?Math.round((x.events/u.toolEvents)*100):0}%</span></div>)}</div></section>
  <section className="section"><div className="card"><div className="badgeLine"><StatusPill status="healthy" label="Determinístico primeiro"/><StatusPill status="pending" label="Modelo principal bloqueado por gate"/><StatusPill status="pending" label="Codex WIF bloqueado por gate"/></div><p className="muted" style={{marginBottom:0}}>A Factory só usa providers pagos quando enablement, credencial oficial, budget total e reserva por run estiverem válidos.</p></div></section>
 </>;
}