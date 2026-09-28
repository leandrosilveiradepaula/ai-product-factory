import {redirect} from "next/navigation";
import type {ProjectIntake} from "../../../../lib/intake";
import {finalizeProjectDraftFiles} from "../../../../lib/attachments";
import {createProjectIntake,enqueueProjectBootstrap} from "../../../../lib/control-plane";
import {ActionLink,Button,PageHeader} from "../../../ui";

type ReviewIntake=ProjectIntake&{draftId?:string;attachmentCount?:number};
function decode(raw:string|undefined):ReviewIntake|null{if(!raw)return null;try{return JSON.parse(Buffer.from(raw,"base64url").toString("utf8"))}catch{return null}}
async function start(formData:FormData){"use server";const intake=decode(String(formData.get("intake")||""));if(!intake)throw new Error("Intake inválido");const result=await createProjectIntake(intake);if(intake.draftId)await finalizeProjectDraftFiles(intake.draftId,result.projectId);await enqueueProjectBootstrap(result.projectKey);redirect("/projects/"+result.projectKey)}

export default async function Review({searchParams}:{searchParams:Promise<{intake?:string}>}){
 const p=await searchParams;const intake=decode(p.intake);
 if(!intake)return <><PageHeader eyebrow="Novo trabalho" title="Intake inválido" subtitle="O conteúdo de intake não pôde ser validado."/><ActionLink href="/projects/new">Voltar</ActionLink></>;
 return <>
  <PageHeader eyebrow="Revisar intake" title={intake.name} subtitle={intake.mode==="existing"?"A Factory vai registrar o briefing e iniciar uma reconciliação antes de decidir de onde continuar.":"Ao iniciar, a Factory persiste o produto, cria o bootstrap e abre o estágio de descoberta no Painel de Controle."}/>
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
   <div className="section"><span className="detailLabel">Referências</span>{intake.references?.length?<div className="stack">{intake.references.map((ref,i)=><div className="badgeLine" key={ref.value+i}><span className="pill accent">{ref.kind}</span><code>{ref.value}</code></div>)}</div>:<p className="muted">Not informed</p>}</div>
   <div className="intakeReviewNote"><strong>O que acontece ao iniciar</strong><p className="muted">{intake.mode==="existing"?"A Factory registra este briefing, reconcilia as evidências disponíveis do projeto e cria somente o trabalho que falta. O estágio informado é uma pista, não uma verdade presumida.":"A Factory registra este pedido como fonte do projeto, cria o bootstrap e entra em Discovery. Decisões técnicas comuns seguem autonomamente; dúvidas que mudem materialmente o produto devem voltar como decisão humana."}</p></div>
  </div>
  <div className="actions"><ActionLink href="/projects/new">Editar</ActionLink><form action={start}><input type="hidden" name="intake" value={p.intake}/><Button variant="primary">{intake.mode==="existing"?"Importar e reconciliar":"Iniciar Discovery"}</Button></form></div>
 </>;
}