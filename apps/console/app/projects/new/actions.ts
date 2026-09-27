"use server";
import {randomUUID} from "node:crypto";
import {redirect} from "next/navigation";
import {normalizeIntake,parseReferenceLines,validateIntake,type ProjectIntake,type ReportedStage} from "../../../lib/intake";
import {uploadProjectDraftFile} from "../../../lib/attachments";
export type IntakeState={errors:Record<string,string>;message?:string};
export async function submitIntake(_prev:IntakeState,formData:FormData):Promise<IntakeState>{
 const mode=formData.get("mode")==="existing"?"existing":"greenfield";
 const input:ProjectIntake={
  mode,
  name:String(formData.get("name")||""),
  summary:String(formData.get("summary")||""),
  repository:String(formData.get("repository")||""),
  users:String(formData.get("users")||""),
  mustHave:String(formData.get("mustHave")||""),
  integrations:String(formData.get("integrations")||""),
  references:parseReferenceLines(String(formData.get("references")||"")),
  reportedStage:(String(formData.get("reportedStage")||"unknown") as ReportedStage),
  knownPending:String(formData.get("knownPending")||""),
  constraints:String(formData.get("constraints")||"")
 };
 const clean=normalizeIntake(input);const validation=validateIntake(clean);if(!validation.ok)return{errors:validation.errors};
 const draftId=randomUUID();const files=formData.getAll("attachments").filter((x):x is File=>x instanceof File&&x.size>0);
 if(files.length>10)return{errors:{attachments:"Envie no máximo 10 arquivos por projeto."}};
 try{for(const file of files)await uploadProjectDraftFile(draftId,file)}catch(error){return{errors:{attachments:error instanceof Error?error.message:"Não foi possível enviar os anexos."}}}
 const encoded=Buffer.from(JSON.stringify({...clean,draftId,attachmentCount:files.length})).toString("base64url");redirect(`/projects/new/review?intake=${encoded}`);
}