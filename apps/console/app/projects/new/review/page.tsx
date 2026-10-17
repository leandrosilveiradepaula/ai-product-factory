import {redirect} from "next/navigation";
import {normalizeIntake,validateIntake,type ProjectIntake} from "../../../../lib/intake";
import {countProjectDraftFiles} from "../../../../lib/attachments";
import {createProjectIntakeAndBootstrap} from "../../../../lib/control-plane";
import {ActionLink,PageHeader} from "../../../ui";
import {SubmitProjectButton} from "./submit-button";

type ReviewIntake=ProjectIntake&{draftId?:string;attachmentCount?:number};
function decode(raw:string|undefined):ReviewIntake|null{if(!raw)return null;try{return JSON.parse(Buffer.from(raw,"base64url").toString("utf8"))}catch{return null}}
async function start(formData:FormData){"use server";const intake=decode(String(formData.get("intake")||""));if(!intake)throw new Error("Intake inválido");const clean=normalizeIntake({mode:intake.mode,name:intake.name,summary:intake.summary,repository:intake.repository,users:intake.users,mustHave:intake.mustHave,integrations:intake.integrations,references:intake.references,reportedStage:intake.reportedStage,knownPending:intake.knownPending,constraints:intake.constraints});const validation=validateIntake(clean);if(!validation.ok)throw new Error("Intake inválido");if(!intake.draftId)throw new Error("Identificador do rascunho ausente.");const expectedCount=await countProjectDraftFiles(intake.draftId);if(expectedCount>10)throw new Error("Excesso de anexos.");const result=await createProjectIntakeAndBootstrap(clean,intake.draftId,expectedCount);redirect("/projects/"+result.projectKey)}

export default async function Review({searchParams}:{searchParams:Promise<{intake?:string}>}){
 const p=await searchParams;const intake=decode(p.intake);
 if(!intake)return <><PageHeader eyebrow="Novo projeto" title="Entrada inválida" subtitle="O conteúdo da entrada não pôde ser validado."/><ActionLink href="/projects/new">Voltar</ActionLink></>;
 return <>
  <PageHeader eyebrow="Revisar entrada" title={intake.name} subtitle={intake.mode==="existing"?"A Factory registra o briefing como rascunho e aguarda seu comando Iniciar.":"Ao cadastrar, a Factory salva o projeto sem iniciar a execução. Você decide quando começar."}/>
  <div className="intakeSteps" aria-label="Etapas para iniciar um projeto">
   <span className="done">1. Descrever</span>
   <span className="current" aria-current="step">2. Revisar</span>
   <span>3. Acompanhar</span>
  </div>
  <p className="intakeIntro">Confirme o briefing antes de registrar o projeto. Você ainda pode editar sem iniciar qualquer execução.</p>
  <div className="card" style={{maxWidth:860}}>
   <div className="detailGrid">
    <div className="detailItem"><span className="detailLabel">Modo</span><strong>{intake.mode==="greenfield"?"Novo produto":"Projeto em andamento"}</strong></div>
    <div className="detailItem"><span className="detailLabel">Repositório</span><strong>{intake.repository||"Será criado depois"}</strong></div>
   </div>
   <div className="section"><span className="detailLabel">Objetivo</span><p>{intake.summary}</p></div>
   <div className="twoCol">
    <div><span className="detailLabel">Usuários</span><p className="muted">{intake.users||"Não informado"}</p></div>
    <div><span className="detailLabel">Obrigatório</span><p className="muted">{intake.mustHave||"Não informado"}</p></div>
   </div>
   <div><span className="detailLabel">Integrações conhecidas</span><p className="muted">{intake.integrations||"Não informado"}</p></div>
   {intake.mode==="existing"?<><div className="detailGrid section"><div className="detailItem"><span className="detailLabel">Estágio informado</span><strong>{intake.reportedStage||"não informado"}</strong></div><div className="detailItem"><span className="detailLabel">Pendências conhecidas</span><strong>{intake.knownPending||"Não informadas"}</strong></div></div><div className="section"><span className="detailLabel">Restrições a preservar</span><p className="muted">{intake.constraints||"Não informadas"}</p></div></>:null}
   <div className="section"><span className="detailLabel">Anexos privados</span><p className="muted">{intake.attachmentCount?intake.attachmentCount+" arquivo(s) armazenado(s) e aguardando vínculo ao projeto.":"Nenhum anexo."}</p></div>
   <div className="section"><span className="detailLabel">Referências</span>{intake.references?.filter(ref=>/^https:\/\//i.test(ref.value)).length?<div className="stack">{intake.references.filter(ref=>/^https:\/\//i.test(ref.value)).map((ref,i)=><div className="badgeLine" key={ref.value+i}><span className="pill accent">{ref.kind}</span><a href={ref.value} target="_blank" rel="noreferrer">{ref.value}</a></div>)}</div>:<p className="muted">Não informado</p>}</div>
   <div className="intakeReviewNote"><strong>O que acontece ao cadastrar</strong><p className="muted">{intake.mode==="existing"?"A Factory salva o briefing e os anexos. A reconciliação só começa quando você clicar em Iniciar. O estágio informado é uma pista, não uma verdade presumida.":"A Factory salva seu projeto como rascunho. A Descoberta só começa quando você clicar em Iniciar. Decisões técnicas comuns seguem autonomamente; dúvidas que mudem materialmente o produto devem voltar como decisão humana."}</p></div>
  </div>
  <div className="actions"><ActionLink href={"/projects/new?intake="+encodeURIComponent(p.intake||"")}>Editar</ActionLink><form action={start}><input type="hidden" name="intake" value={p.intake}/><SubmitProjectButton existing={intake.mode==="existing"}/></form></div>
 </>;
}