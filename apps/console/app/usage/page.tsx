import {getUsageOverview} from "../../lib/control-plane";
import {EmptyState,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Usage(){
 const u=await getUsageOverview();
 return <>
  <PageHeader eyebrow="Modelos e uso" title="Modelos e uso" subtitle="Ledger de ferramentas, custo conhecido e uso real de Codex. Custo pago desconhecido bloqueia execução."/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Custo conhecido</span><strong>{u.knownCost.toFixed(4)}</strong></div>
   <div className="operationalStat"><span>Eventos</span><strong>{u.toolEvents}</strong></div>
   <div className="operationalStat"><span>Codex</span><strong>{u.codexInvocations}</strong></div>
   <div className="operationalStat"><span>Custo desconhecido</span><strong>{u.unknownPaidCostEvents}</strong></div>
  </div>
  <div className="overviewGrid">
   <section>
    <SectionHeader title="Uso por família de ferramenta"/>
    <div className="table"><div className="tableRow tableHeader"><span>Família</span><span>Eventos</span><span>Custo conhecido</span><span>Participação</span></div>{u.byFamily.length===0?<EmptyState>Nenhum uso registrado.</EmptyState>:u.byFamily.map(x=><div className="tableRow" key={x.family}><strong>{x.family}</strong><span>{x.events}</span><span>{x.knownCost.toFixed(4)}</span><span className="muted">{u.toolEvents?Math.round((x.events/u.toolEvents)*100):0}%</span></div>)}</div>
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Readiness</strong><StatusPill status={u.unknownPaidCostEvents?"blocked":"healthy"} label={u.unknownPaidCostEvents?"bloqueado":"operacional"}/></div>
     <div className="compactList">
      <div className="compactRow"><span className="muted">Primary</span><StatusPill status="active" label="API key ativa"/></div>
      <div className="compactRow"><span className="muted">Budget</span><span>US$ 4,00</span></div>
      <div className="compactRow"><span className="muted">Reserva</span><span>US$ 0,50</span></div>
      <div className="compactRow"><span className="muted">Codex automático</span><StatusPill status="pending" label="desligado"/></div>
     </div>
    </div>
    <div className="logPanel">cost.policy = fail_closed<br/>primary.auth = api_key<br/>codex.auth = pending_external</div>
   </aside>
  </div>
 </>;
}