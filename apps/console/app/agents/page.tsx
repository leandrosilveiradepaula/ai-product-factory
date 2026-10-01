import Link from "next/link";
import {getFactoryAgents} from "../../lib/control-plane";
import {EmptyState,PageHeader,SectionHeader,StatusPill} from "../ui";

const roleLabel:Record<string,string>={
 product:"Produto e planejamento",
 development:"Desenvolvimento",
 ui:"UI/UX",
 security:"Segurança",
 qa:"QA e avaliação",
 operations:"Operações e observabilidade",
};

function policyLabel(policy:Record<string,unknown>){
 const preferred=typeof policy.preferred==="string"?policy.preferred:"não definido";
 const codex=typeof policy.codex==="string"?policy.codex:null;
 const fallback=typeof policy.fallback==="string"?policy.fallback:null;
 return [preferred,fallback?"fallback "+fallback:null,codex?"Codex "+codex:null].filter(Boolean).join(" · ");
}

export default async function Agents(){
 const agents=await getFactoryAgents();
 const active=agents.filter(x=>x.active).length;
 const working=agents.filter(x=>x.activeSlots>0||x.healthStatus==="working").length;
 const activeSlots=agents.reduce((sum,x)=>sum+x.activeSlots,0);
 const totalSlots=agents.reduce((sum,x)=>sum+x.maxConcurrency,0);
 const totalBudget=agents.reduce((sum,x)=>sum+(x.budgetUsd||0),0);
 const knownCost=agents.reduce((sum,x)=>sum+x.knownCostUsd,0);

 return <>
  <PageHeader
   eyebrow="Diagnóstico · especialistas da Factory"
   title="Agentes da Factory"
   subtitle="Mostra os especialistas que a Factory pode acionar automaticamente. Você não precisa escolher agentes manualmente para conduzir um projeto."
   actions={<StatusPill status={working?"running":"healthy"} label={working?working+" especialistas em trabalho":"registry saudável"}/>}
  />

  <div className="operationalStrip">
   <div className="operationalStat"><span>Agentes ativos</span><strong>{active}</strong><small>perfis configuráveis</small></div>
   <div className="operationalStat"><span>Slots ocupados</span><strong>{activeSlots}/{totalSlots}</strong><small>concorrência reservada</small></div>
   <div className="operationalStat"><span>Budget configurado</span><strong>US$ {totalBudget.toFixed(2)}</strong><small>limites por especialista</small></div>
   <div className="operationalStat"><span>Uso conhecido</span><strong>US$ {knownCost.toFixed(4)}</strong><small>runs já atribuídas</small></div>
  </div>

  <section className="section">
   <SectionHeader title="Especialistas registrados" action={<span className="muted">{working} trabalhando agora</span>}/>
   {agents.length===0?<EmptyState>Nenhum agente registrado no Control Plane.</EmptyState>:<div className="threeCol">
    {agents.map(agent=><article className="card denseStack" key={agent.id}>
     <div className="panelHeading">
      <div><strong>{agent.name}</strong><div className="muted">{roleLabel[agent.role]||agent.role}</div></div>
      <StatusPill status={agent.active?agent.healthStatus:"inactive"}/>
     </div>
     <p className="muted" style={{margin:"0 0 2px"}}>{agent.description}</p>
     <div className="compactList">
      <div className="compactRow"><span>Capacidade</span><strong>{agent.activeSlots}/{agent.maxConcurrency} slots</strong></div>
      <div className="compactRow"><span>Budget</span><span className="muted">{agent.budgetUsd==null?"sem limite local":"US$ "+agent.budgetUsd.toFixed(2)}</span></div>
      <div className="compactRow"><span>Uso conhecido</span><span className="muted">US$ {agent.knownCostUsd.toFixed(4)}</span></div>
      <div className="compactRow"><span>Política de modelo</span><span className="muted">{policyLabel(agent.modelPolicy)}</span></div>
     </div>
     <div>
      <div className="eyebrow">Capacidades</div>
      <div className="badgeLine">{agent.capabilities.map(x=><StatusPill key={x} status="policy" label={x}/>)}</div>
     </div>
     <div>
      <div className="eyebrow">Ferramentas permitidas</div>
      <div className="badgeLine">{agent.allowedTools.map(x=><StatusPill key={x} status="tool" label={x}/>)}</div>
     </div>
     {agent.activeScopes.length?<div>
      <div className="eyebrow">Locks de escopo</div>
      <div className="badgeLine">{agent.activeScopes.map(x=><code key={x}>{x}</code>)}</div>
     </div>:null}
    </article>)}
   </div>}
  </section>

  <section className="section">
   <SectionHeader title="Trabalho em andamento" action={<span className="muted">{activeSlots} assignments ativos</span>}/>
   <div className="table agentWorkTable">
    <div className="tableRow tableHeader"><span>Agente</span><span>Tarefa</span><span>Rota</span><span>Estado</span><span>Run</span></div>
    {activeSlots===0?<EmptyState>Nenhum especialista está executando trabalho neste momento.</EmptyState>:agents.flatMap(agent=>agent.activeRuns.map(run=><div className="tableRow" key={agent.id+"-"+run.runId}>
     <div><strong>{agent.name}</strong><div className="muted">{roleLabel[agent.role]||agent.role}</div></div>
     <span>{run.taskTitle}</span>
     <StatusPill status={run.route||"unrouted"}/>
     <StatusPill status={run.status}/>
     <Link href={"/runs/"+run.runId} className="mono">Abrir {run.runId.slice(0,8)} →</Link>
    </div>))}
   </div>
  </section>

  <div className="overviewGrid section">
   <div className="card">
    <div className="panelHeading"><strong>Como a capacidade é distribuída</strong><StatusPill status="active" label="scheduler ativo"/></div>
    <div className="compactList">
     <div className="compactRow"><span>Produto / planejamento</span><span className="muted">discovery, spec e decomposição</span></div>
     <div className="compactRow"><span>Desenvolvimento / UI</span><span className="muted">Primary; Codex somente por política</span></div>
     <div className="compactRow"><span>Segurança / QA / Operações</span><span className="muted">determinístico primeiro</span></div>
     <div className="compactRow"><span>Conflitos</span><span className="muted">locks por projeto e escopo</span></div>
    </div>
   </div>
   <div className="logPanel">agents.active = {active}<br/>agents.working = {working}<br/>slots.used = {activeSlots}<br/>slots.total = {totalSlots}<br/>scheduler.conflict_policy = fail_closed</div>
  </div>
 </>;
}
