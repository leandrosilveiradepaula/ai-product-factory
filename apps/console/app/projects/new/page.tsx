import {IntakeForm,type IntakeFormInitial} from "./intake-form";
import {PageHeader} from "../../ui";

function decode(raw:string|undefined):IntakeFormInitial|undefined{
 if(!raw)return undefined;
 try{return JSON.parse(Buffer.from(raw,"base64url").toString("utf8")) as IntakeFormInitial}catch{return undefined}
}

export default async function NewProject({searchParams}:{searchParams:Promise<{intake?:string}>}){
 const p=await searchParams;const initial=decode(p.intake);
 return <>
  <PageHeader eyebrow="Novo projeto" title="Iniciar ou importar projeto" subtitle="Comece uma ideia nova ou traga um projeto em andamento. A Factory inicia Descoberta ou reconcilia o estado real antes de continuar."/>
  <div className="gettingStarted" aria-label="Etapas para iniciar um projeto">
   <div className="guideStep current"><span className="guideStepNumber">1</span><strong>Descreva o projeto</strong><p>Escolha novo produto ou projeto em andamento e conte o resultado que você quer alcançar.</p></div>
   <div className="guideStep"><span className="guideStepNumber">2</span><strong>Revise o briefing</strong><p>A Factory mostra um resumo antes de criar qualquer ciclo de trabalho.</p></div>
   <div className="guideStep"><span className="guideStepNumber">3</span><strong>Acompanhe a execução</strong><p>Depois de iniciar, você acompanha o projeto e age apenas quando existir uma decisão necessária.</p></div>
  </div>
  <div className="flowIntro"><strong>Comece pelo resultado, não pela tecnologia.</strong><p>Você não precisa decidir stack, modelo, agente ou sequência técnica. Essas decisões pertencem à Factory, dentro dos gates configurados.</p></div>
  <IntakeForm initial={initial}/>
 </>;
}
