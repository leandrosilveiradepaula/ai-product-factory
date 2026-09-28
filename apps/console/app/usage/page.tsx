import {getUsageOverview} from "../../lib/control-plane";
import {EmptyState,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Usage(){
 const u=await getUsageOverview();
 const maxEvents=Math.max(1,...u.byFamily.map(x=>x.events));
 return <>
  <PageHeader eyebrow="Telemetria de LLM · governança de custo" title="Modelos e uso" subtitle="Ledger real de ferramentas e provedores. Custos pagos desconhecidos bloqueiam novas chamadas." actions={<StatusPill status={u.unknownPaidCostEvents?"blocked":"healthy"} label={u.unknownPaidCostEvents?"execução paga bloqueada":"budget operacional"}/>}/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Custo conhecido</span><strong>{u.knownCost.toFixed(4)}</strong><small>ledger acumulado</small></div>
   <div className="operationalStat"><span>Eventos</span><strong>{u.toolEvents}</strong><small>ferramentas registradas</small></div>
   <div className="operationalStat"><span>Codex</span><strong>{u.codexInvocations}</strong><small>invocações reais</small></div>
   <div className="operationalStat danger"><span>Custo desconhecido</span><strong>{u.unknownPaidCostEvents}</strong><small>hard stop</small></div>
  </div>

  <div className="overviewGrid">
   <section className="denseStack">
    <div className="card">
     <SectionHeader title="Uso por família de ferramenta"/>
     {u.byFamily.length===0?<EmptyState>Nenhum uso registrado.</EmptyState>:<div className="usageBars">{u.byFamily.map(x=><div className="usageBarRow" key={x.family}><div className="usageBarMeta"><strong>{x.family}</strong><span>{x.events} eventos · {x.knownCost.toFixed(4)}</span></div><div className="usageBarTrack"><div className="usageBarFill" style={{width:Math.max(4,Math.round((x.events/maxEvents)*100))+"%"}}/></div></div>)}</div>}
    </div>
    <div className="table">
     <div className="tableRow tableHeader"><span>Família</span><span>Eventos</span><span>Custo conhecido</span><span>Participação</span></div>
     {u.byFamily.length===0?<EmptyState>Nenhum uso registrado.</EmptyState>:u.byFamily.map(x=><div className="tableRow" key={x.family}><strong>{x.family}</strong><span>{x.events}</span><span>{x.knownCost.toFixed(4)}</span><span className="muted">{u.toolEvents?Math.round((x.events/u.toolEvents)*100):0}%</span></div>)}
    </div>
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Readiness</strong><StatusPill status={u.unknownPaidCostEvents?"blocked":"healthy"} label={u.unknownPaidCostEvents?"bloqueado":"operacional"}/></div>
     <div className="compactList">
      <div className="compactRow"><span>Primary</span><StatusPill status="active" label="API key ativa"/></div>
      <div className="compactRow"><span>Budget Factory</span><span className="muted">US$ 4,00</span></div>
      <div className="compactRow"><span>Reserva por run</span><span className="muted">US$ 0,50</span></div>
      <div className="compactRow"><span>Codex automático</span><StatusPill status="pending" label="desligado"/></div>
     </div>
    </div>
    <div className="card">
     <div className="panelHeading"><strong>Política de custo</strong></div>
     <p className="muted">Toda chamada paga é pré-reservada no ledger. Resultado mensurável substitui a reserva pelo custo real; custo pago não mensurável bloqueia novas execuções.</p>
    </div>
    <div className="logPanel">cost.policy = fail_closed<br/>primary.auth = api_key<br/>codex.auth = pending_external<br/>unknown_paid = {u.unknownPaidCostEvents}</div>
   </aside>
  </div>
 </>;
}
