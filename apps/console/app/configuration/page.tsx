import {getConsoleConfiguration} from "../../lib/control-plane";
import {ActionLink,PageHeader,SectionHeader,StatusPill} from "../ui";

export default async function Configuration(){
 const c=await getConsoleConfiguration();
 return <>
  <PageHeader eyebrow="Governança · políticas e circuit breakers" title="Configuração" subtitle="Estado operacional visível do Console. Segredos, tokens e credenciais privilegiadas nunca são renderizados." actions={<ActionLink href="/admin/operators">Operadores</ActionLink>}/>
  <div className="configTabs"><span className="active">Governança</span><span>Modelos</span><span>Execução</span><span>Preview</span><span>Segurança</span></div>
  <div className="overviewGrid">
   <section className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Política de provedores</strong><StatusPill status={c.controlPlaneConfigured?"healthy":"blocked"} label={c.controlPlaneConfigured?"Control Plane pronto":"Control Plane ausente"}/></div>
     <div className="configRows">
      <div><span>Primary model</span><strong>API key explícita</strong><small>execução paga limitada por budget e ledger</small></div>
      <div><span>Codex</span><strong>desligado</strong><small>auth automática ainda depende de gate externo</small></div>
      <div><span>Cross-repo</span><strong>credencial explícita</strong><small>falha fechada sem credencial cross-repo explícita</small></div>
      <div><span>Release</span><strong>humano</strong><small>nenhuma capacidade de auto-merge</small></div>
     </div>
    </div>

    <div className="card">
     <SectionHeader title="Manifestos dos projetos" action={<span className="muted">{c.projects.length} projetos</span>}/>
     <div className="denseStack">{c.projects.map(p=><article className="detailItem" key={p.key}>
      <div className="cardTop"><div><strong>{p.name}</strong><div className="muted mono">{p.repository||p.key}</div></div><div className="badgeLine"><StatusPill status={p.kind}/><StatusPill status={p.stage} tone="accent"/></div></div>
      <details className="manifestDetails"><summary className="muted">Manifesto</summary><pre className="jsonBlock">{JSON.stringify(p.manifest,null,2)}</pre></details>
     </article>)}</div>
    </div>
   </section>

   <aside className="denseStack">
    <div className="card">
     <div className="panelHeading"><strong>Invariantes</strong><StatusPill status="active" label="enforced"/></div>
     <div className="compactList">
      <div className="compactRow"><span>Auto-merge</span><span className="muted">proibido</span></div>
      <div className="compactRow"><span>Preview sem política</span><span className="muted">fail-closed</span></div>
      <div className="compactRow"><span>Custo pago desconhecido</span><span className="muted">bloqueia</span></div>
      <div className="compactRow"><span>Benchmark de 63 perguntas</span><span className="muted">adiado</span></div>
      <div className="compactRow"><span>RLS público</span><span className="muted">sem policies permissivas</span></div>
     </div>
    </div>
    <div className="card">
     <div className="panelHeading"><strong>Hardening administrativo</strong></div>
     <p className="muted">Leaked Password Protection permanece uma ação administrativa externa. O Console não amplia permissões nem altera Auth por conta própria.</p>
    </div>
    <div className="logPanel">config.control_plane = {c.controlPlaneConfigured?"ready":"missing"}<br/>config.projects = {c.projects.length}<br/>release.auto_merge = false<br/>preview.default = fail_closed</div>
   </aside>
  </div>
 </>;
}
