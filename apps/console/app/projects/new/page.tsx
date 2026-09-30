import {IntakeForm,type IntakeFormInitial} from "./intake-form";
import {PageHeader} from "../../ui";

function decode(raw:string|undefined):IntakeFormInitial|undefined{
 if(!raw)return undefined;
 try{return JSON.parse(Buffer.from(raw,"base64url").toString("utf8")) as IntakeFormInitial}catch{return undefined}
}

export default async function NewProject({searchParams}:{searchParams:Promise<{intake?:string}>}){
 const p=await searchParams;const initial=decode(p.intake);
 return <>
  <PageHeader eyebrow="Novo trabalho" title="Iniciar ou importar projeto" subtitle="Comece uma ideia nova ou traga um projeto em andamento. A Factory inicia Descoberta ou reconcilia o estado real antes de continuar."/>
  <IntakeForm initial={initial}/>
 </>;
}
