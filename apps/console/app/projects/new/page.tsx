import {IntakeForm,type IntakeFormInitial} from "./intake-form";
import {PageHeader} from "../../ui";
import {requireConsoleOperator} from "../../../lib/auth-server";

function decode(raw:string|undefined):IntakeFormInitial|undefined{
 if(!raw)return undefined;
 try{return JSON.parse(Buffer.from(raw,"base64url").toString("utf8")) as IntakeFormInitial}catch{return undefined}
}

export default async function NewProject({searchParams}:{searchParams:Promise<{intake?:string}>}){
 // Middleware checks session validity; the allowlist must be verified on this
 // page independently before any intake payload is rendered.
 await requireConsoleOperator();
 const p=await searchParams;const initial=decode(p.intake);
 return <>
  <PageHeader eyebrow="Novo projeto" title="Cadastrar um produto ou conectar projeto" subtitle="Descreva a ideia ou conecte um repositório. O cadastro não inicia automaticamente o trabalho; depois você verá a ação Iniciar projeto, quando aplicável."/>
  <div className="intakeSteps" role="group" aria-label="Etapas para iniciar um projeto">
   <span className="current" aria-current="step">1. Descrever</span>
   <span>2. Revisar</span>
   <span>3. Acompanhar</span>
  </div>
  <p className="intakeIntro">Descreva o resultado desejado. Depois revise o cadastro e abra o projeto para acompanhar seu estado. A Factory só começa a executar após um início autorizado.</p>
  <IntakeForm initial={initial}/>
 </>;
}
