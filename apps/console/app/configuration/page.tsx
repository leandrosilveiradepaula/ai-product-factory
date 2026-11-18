import {getConsoleConfiguration} from "../../lib/control-plane";
import {getPrimaryCostPolicyView} from "../../lib/primary-cost-policy";
import {PrimaryCostPolicyPanel} from "./cost-policy-panel";
import {requireConsoleOperator} from "../../lib/auth-server";
import {ActionLink,PageHeader,StatusPill} from "../ui";

function previewLabel(manifest:unknown){
 if(!manifest||typeof manifest!=="object")return "Não informada";
 const preview=(manifest as Record<string,unknown>).preview;
 if(!preview||typeof preview!=="object")return "Não informada";
 const record=preview as Record<string,unknown>;
 if(record.required===false)return "Não aplicável";
 const mode=record.mode;
 return typeof mode==="string"?mode:"Configuração registrada";
}

export default async function Configuration({searchParams}:{
 searchParams:Promise<{cost_policy?:string}>
}){
 const [c,operator,policy,params]=await Promise.all([
  getConsoleConfiguration(),requireConsoleOperator(),getPrimaryCostPolicyView(),searchParams,
 ]);
 return <>
  <PageHeader eyebrow="Administração" title="Configurações"
   subtitle="Controle os limites financeiros da Factory. As demais opções técnicas ficam organizadas abaixo, sem atrapalhar a operação."
   actions={operator.role==="admin"
    ?<ActionLink href="/admin/operators">Operadores</ActionLink>
    :<StatusPill status="active" label="Perfil operador"/>}/>
  <section className="configurationFocus" aria-label="Orçamento da Factory">
   <PrimaryCostPolicyPanel policy={policy} admin={operator.role==="admin"}
    feedback={params?.cost_policy}/>
  </section>

  <section className="configurationBeyond" aria-labelledby="configuration-advanced-title">
   <div className="configurationBeyondHeader">
    <h2 id="configuration-advanced-title">Outras configurações</h2>
    <p>Políticas de funcionamento, segurança e informações técnicas. Não são necessárias para ajustar o orçamento.</p>
   </div>

   <details className="configurationDisclosure" id="politicas-avancadas">
    <summary><span><strong>Funcionamento e segurança</strong>
     <small>Modelos, permissões, release e proteções da Factory</small></span></summary>
    <div className="overviewGrid configOverviewGrid configurationAdvancedGrid">
     <div className="card" id="modelos">
      <div className="panelHeading"><strong>Provedores e execução</strong>
       <StatusPill status={c.controlPlaneConfigured?"healthy":"blocked"}
        label={c.controlPlaneConfigured?"Control Plane conectado":"Control Plane indisponível"}/></div>
      <div className="configRows">
       <div><span>Modelo principal</span><strong>API key explícita</strong>
        <small>Uso pago sujeito a orçamento, quota e ledger reais</small></div>
       <div><span>Codex</span><strong>Sem ativação automática</strong>
        <small>Autenticação independente da API principal</small></div>
       <div><span>Acesso entre repositórios</span><strong>Credencial específica</strong>
        <small>Falha fechada sem permissão cross-repo</small></div>
       <div><span>Publicação</span><strong>Aprovação humana</strong>
        <small>A Factory não faz merge automático em produção</small></div>
      </div>
     </div>
     <div className="card" id="governanca">
      <div className="panelHeading"><strong>Proteções obrigatórias</strong>
       <StatusPill status="active" label="Ativas"/></div>
      <div className="compactList">
       <div className="compactRow"><span>Merge em produção</span><strong>Humano</strong></div>
       <div className="compactRow"><span>Preview sem política</span><strong>Bloqueado</strong></div>
       <div className="compactRow"><span>Custo pago desconhecido</span><strong>Bloqueado</strong></div>
       <div className="compactRow"><span>Benchmark de 63 perguntas</span><strong>Adiado</strong></div>
       <div className="compactRow"><span>RLS público</span><strong>Sem políticas permissivas</strong></div>
      </div>
     </div>
     <div className="card" id="seguranca">
      <div className="panelHeading"><strong>Hardening administrativo</strong></div>
      <p className="muted">Leaked Password Protection é uma pendência administrativa externa.
       O Console não amplia permissões de Auth automaticamente.</p>
     </div>
    </div>
   </details>

   <details className="configurationDisclosure" id="politicas-de-preview">
    <summary><span><strong>Preview dos produtos</strong>
     <small>Confira a política de cada projeto sem alterar o desenvolvimento</small></span></summary>
    <div className="card" id="preview">
     <p className="configurationExplanation">Um Preview só é obrigatório se a política do projeto e os caminhos modificados o exigirem.
      Quando não aplicável, a Factory registra evidência durável da dispensa.</p>
     <div className="configurationProjectList">
      {c.projects.map(p=><div className="configurationProjectRow" key={p.key}>
       <strong>{p.name}</strong><span>{previewLabel(p.manifest)}</span>
      </div>)}
     </div>
    </div>
   </details>

   <details className="configurationDisclosure" id="dados-tecnicos">
    <summary><span><strong>Dados técnicos e manifestos</strong>
     <small>Diagnóstico para investigação avançada; normalmente não exige ação</small></span></summary>
    <div className="card" id="execucao">
     <div className="panelHeading"><strong>Manifestos dos projetos</strong>
      <span className="muted">{c.projects.length} projetos</span></div>
     <div className="configurationProjectList">
      {c.projects.map(p=><article className="configurationManifest" key={p.key}>
       <div className="configurationProjectRow">
        <strong>{p.name}</strong><span>{p.repository||p.key}</span>
       </div>
       <details className="manifestDetails">
        <summary>Ver manifesto técnico</summary>
        <pre className="jsonBlock">{JSON.stringify(p.manifest,null,2)}</pre>
       </details>
      </article>)}
     </div>
    </div>
    <details className="configurationDiagnostics">
     <summary>Ver diagnóstico do Control Plane</summary>
     <pre className="logPanel">config.control_plane = {c.controlPlaneConfigured?"ready":"missing"}
config.projects = {c.projects.length}
release.auto_merge = false
preview.default = fail_closed</pre>
    </details>
   </details>
  </section>
 </>;
}
