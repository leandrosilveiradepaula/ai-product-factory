import {getConsoleConfiguration} from "../../lib/control-plane";
import {ActionLink,MetricCard,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Configuration(){
 const c=await getConsoleConfiguration();
 return <>
  <PageHeader eyebrow="System" title="Configuration" subtitle="Configuração operacional visível do Control Plane. Segredos e tokens nunca são expostos no Console."/>
  <div className="grid compact">
   <MetricCard label="Control Plane" value={c.controlPlaneConfigured?"Ready":"Missing"} note="server-side credentials"/>
   <MetricCard label="Projects" value={c.projects.length}/>
   <MetricCard label="Model activation" value="External" note="managed by runtime environment"/>
   <MetricCard label="Secrets" value="Server only" note="never rendered by Console"/>
  </div>
  <section className="section"><SectionHeader title="Project manifests" action={<ActionLink href="/admin/operators">Operators</ActionLink>}/><div className="stack">{c.projects.map(p=><article className="card" key={p.key}><div className="cardTop"><div><h3 className="cardTitle">{p.name}</h3><p className="cardMeta mono">{p.repository||p.key}</p></div><div className="badgeLine"><StatusPill status={p.kind}/><StatusPill status={p.stage} tone="accent"/></div></div><details style={{marginTop:14}}><summary className="muted">Manifest</summary><pre className="jsonBlock">{JSON.stringify(p.manifest,null,2)}</pre></details></article>)}</div></section>
 </>;
}