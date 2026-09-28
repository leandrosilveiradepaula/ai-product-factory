import {getConsoleConfiguration} from "../../lib/control-plane";
import {ActionLink,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Configuration(){
 const c=await getConsoleConfiguration();
 return <>
  <PageHeader eyebrow="Configuration · Governance" title="Configuração" subtitle="Configuração operacional visível. Segredos, tokens e credenciais privilegiadas nunca são exibidos no Console." actions={<ActionLink href="/admin/operators">Operadores</ActionLink>}/>
  <div className="operationalStrip">
   <div className="operationalStat"><span>Control Plane</span><strong>{c.controlPlaneConfigured?"pronto":"ausente"}</strong></div>
   <div className="operationalStat"><span>Projetos</span><strong>{c.projects.length}</strong></div>
   <div className="operationalStat"><span>Segredos</span><strong>server-side</strong></div>
   <div className="operationalStat"><span>Produção</span><strong>gate humano</strong></div>
  </div>
  <div className="overviewGrid">
   <section className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Governança</strong><StatusPill status={c.controlPlaneConfigured?"healthy":"blocked"} label={c.controlPlaneConfigured?"configurada":"incompleta"}/></div>
     <div className="detailGrid">
      <div className="detailItem"><span className="detailLabel">Acesso privilegiado</span><strong>somente servidor</strong></div>
      <div className="detailItem"><span className="detailLabel">RLS</span><strong>fail-closed</strong></div>
      <div className="detailItem"><span className="detailLabel">Preview</span><strong>evidência durável</strong></div>
      <div className="detailItem"><span className="detailLabel">Release</span><strong>autoridade humana</strong></div>
     </div>
    </div>
    <div className="card">
     <SectionHeader title="Manifestos dos projetos"/>
     <div className="denseStack">{c.projects.map(p=><article className="detailItem" key={p.key}>
      <div className="cardTop"><div><strong>{p.name}</strong><div className="muted mono">{p.repository||p.key}</div></div><div className="badgeLine"><StatusPill status={p.kind}/><StatusPill status={p.stage} tone="accent"/></div></div>
      <details style={{marginTop:8}}><summary className="muted">Manifesto</summary><pre className="jsonBlock">{JSON.stringify(p.manifest,null,2)}</pre></details>
     </article>)}</div>
    </div>
   </section>
   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Invariantes</strong></div>
     <div className="compactList">
      <div className="compactRow"><span className="muted">Auto-merge</span><span>proibido</span></div>
      <div className="compactRow"><span className="muted">Credencial cross-repo</span><span>explícita</span></div>
      <div className="compactRow"><span className="muted">Custo desconhecido</span><span>bloqueia</span></div>
      <div className="compactRow"><span className="muted">Benchmark 63</span><span>adiado</span></div>
     </div>
    </div>
    <div className="logPanel">config.control_plane = {c.controlPlaneConfigured?"ready":"missing"}<br/>config.projects = {c.projects.length}<br/>release.auto_merge = false</div>
   </aside>
  </div>
 </>;
}