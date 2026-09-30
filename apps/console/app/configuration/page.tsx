import {getConsoleConfiguration} from "../../lib/control-plane";
import {ActionLink,PageHeader,SectionHeader,StatusPill} from "../ui";

function previewLabel(manifest:Record<string,unknown>){
 const preview=manifest.preview;
 if(!preview||typeof preview!=="object")return "política não informada";
 const mode=(preview as Record<string,unknown>).mode;
 return typeof mode==="string"?mode:"configurado";
}

export default async function Configuration(){
 const c=await getConsoleConfiguration();
 return <>
  <PageHeader eyebrow="Governança · políticas e circuit breakers" title="Configuração" subtitle="Estado operacional visível do Console. Segredos, tokens e credenciais privilegiadas nunca são renderizados." actions={<ActionLink href="/admin/operators">Operadores</ActionLink>}/>
  <nav className="configTabs" aria-label="Seções de configuração">
   <a className="active" href="#governanca">Governança</a>
   <a href="#modelos">Modelos</a>
   <a href="#execucao">Execução</a>
   <a href="#preview">Preview</a>
   <a href="#seguranca">Segurança</a>
  </nav>
  <div className="overviewGrid">
   <section className="denseStack">
    <div className="card" id="modelos">
     <div className="panelHeading"><strong>Política de provedores</strong><StatusPill status={c.controlPlaneConfigured?"healthy":"blocked"} label={c.controlPlaneConfigured?"Control Plane pronto":"Control Plane ausente"}/></div>
     <div className="configRows">
      <div><span>Primary model</span><strong>API key explícita</strong><small>execução paga limitada por budget e ledger</small></div>
      <div><span>Codex</span><strong>desligado</strong><small>auth automática ainda depende de gate externo</small></div>
      <div><span>Cross-repo</span><strong>credencial explícita</strong><small>falha fechada sem credencial cross-repo explícita</small></div>
      <div><span>Release</span><strong>humano</strong><small>nenhuma capacidade de auto-merge</small></div>
     </div>
    </div>

    <div className="card" id="execucao">
     <SectionHeader title="Manifestos dos projetos" action={<span className="muted">{c.projects.length} projetos</span>}/>
     <div className="denseStack">{c.projects.map(p=><article className="detailItem" key={p.key}>
      <div className="cardTop"><div><strong>{p.name}</strong><div className="muted mono">{p.repository||p.key}</div></div><div className="badgeLine"><StatusPill status={p.kind}/><StatusPill status={p.stage} tone="accent"/></div></div>
      <details className="manifestDetails"><summary className="muted">Manifesto</summary><pre className="jsonBlock">{JSON.stringify(p.manifest,null,2)}</pre></details>
     </article>)}</div>
    </div>

    <div className="card" id="preview">
     <div className="panelHeading"><strong>Política de Preview</strong><StatusPill status="active" label="fail-closed"/></div>
     <p className="muted">Preview só é obrigatório quando a política do projeto e os paths alterados o exigem. Quando não for aplicável, a Factory registra a não aplicabilidade como evidência durável.</p>
     <div className="compactList">
      {c.projects.map(p=><div className="compactRow" key={p.key}><span>{p.name}</span><span className="muted">{previewLabel(p.manifest)}</span></div>)}
     </div>
    </div>
   </section>

   <aside className="denseStack">
    <div className="card" id="governanca">
     <div className="panelHeading"><strong>Invariantes</strong><StatusPill status="active" label="enforced"/></div>
     <div className="compactList">
      <div className="compactRow"><span>Auto-merge</span><span className="muted">proibido</span></div>
      <div className="compactRow"><span>Preview sem política</span><span className="muted">fail-closed</span></div>
      <div className="compactRow"><span>Custo pago desconhecido</span><span className="muted">bloqueia</span></div>
      <div className="compactRow"><span>Benchmark de 63 perguntas</span><span className="muted">adiado</span></div>
      <div className="compactRow"><span>RLS público</span><span className="muted">sem policies permissivas</span></div>
     </div>
    </div>
    <div className="card" id="seguranca">
     <div className="panelHeading"><strong>Hardening administrativo</strong></div>
     <p className="muted">Leaked Password Protection permanece uma ação administrativa externa. O Console não amplia permissões nem altera Auth por conta própria.</p>
    </div>
    <div className="logPanel">config.control_plane = {c.controlPlaneConfigured?"ready":"missing"}<br/>config.projects = {c.projects.length}<br/>release.auto_merge = false<br/>preview.default = fail_closed</div>
   </aside>
  </div>
 </>;
}
