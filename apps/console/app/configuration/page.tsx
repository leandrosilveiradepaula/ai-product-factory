import {getConsoleConfiguration} from "../../lib/control-plane";
import {ActionLink,MetricCard,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Configuration(){
 const c=await getConsoleConfiguration();
 return <>
  <PageHeader eyebrow="Sistema" title="Configuração" subtitle="Configuração operacional visível do Painel de Controle. Segredos e tokens nunca são expostos no Console."/>
  <div className="grid compact">
   <MetricCard label="Painel de Controle" value={c.controlPlaneConfigured?"Pronto":"Ausente"} note="credenciais somente no servidor"/>
   <MetricCard label="Projetos" value={c.projects.length}/>
   <MetricCard label="Ativação de modelos" value="Externa" note="gerenciada pelo ambiente de execução"/>
   <MetricCard label="Segredos" value="Somente servidor" note="nunca exibidos no Console"/>
  </div>
  <section className="section"><SectionHeader title="Manifestos dos projetos" action={<ActionLink href="/admin/operators">Operadores</ActionLink>}/><div className="stack">{c.projects.map(p=><article className="card" key={p.key}><div className="cardTop"><div><h3 className="cardTitle">{p.name}</h3><p className="cardMeta mono">{p.repository||p.key}</p></div><div className="badgeLine"><StatusPill status={p.kind}/><StatusPill status={p.stage} tone="accent"/></div></div><details style={{marginTop:14}}><summary className="muted">Manifesto</summary><pre className="jsonBlock">{JSON.stringify(p.manifest,null,2)}</pre></details></article>)}</div></section>
 </>;
}