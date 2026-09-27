"use server";
import {redirect} from "next/navigation";
import {normalizeIntake,parseReferenceLines,validateIntake,type ProjectIntake,type ReportedStage} from "../../../lib/intake";
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
 const encoded=Buffer.from(JSON.stringify(clean)).toString("base64url");redirect(`/projects/new/review?intake=${encoded}`);
}