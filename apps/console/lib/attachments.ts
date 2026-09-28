import {createHash,randomUUID} from "node:crypto";
import {requireConsoleOperator} from "./auth-server";
import {getSupabaseServerConfig} from "./supabase-server";

export const PROJECT_FILE_BUCKET="factory-project-files";
export const MAX_PROJECT_FILE_BYTES=10*1024*1024;
const allowed=new Set([
 "application/pdf","text/plain","text/markdown","text/csv","application/json",
 "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
 "application/vnd.openxmlformats-officedocument.presentationml.presentation",
 "image/png","image/jpeg","image/webp"
]);

function safeName(value:string){return value.normalize("NFKD").replace(/[^a-zA-Z0-9._-]+/g,"-").replace(/^-+|-+$/g,"").slice(0,120)||"file";}
export function validateProjectFile(file:File){if(!file.size)throw new Error("Arquivo vazio.");if(file.size>MAX_PROJECT_FILE_BYTES)throw new Error("Arquivo excede 10 MB.");if(!allowed.has(file.type))throw new Error("Tipo de arquivo não permitido.");}

export async function uploadProjectDraftFile(draftId:string,file:File){
 const operator=await requireConsoleOperator();const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control plane unavailable");
 validateProjectFile(file);const bytes=Buffer.from(await file.arrayBuffer());const sha256=createHash("sha256").update(bytes).digest("hex");
 const id=randomUUID();const path=`${operator.userId}/${draftId}/${id}-${safeName(file.name)}`;
 const upload=await fetch(`${cfg.url}/storage/v1/object/${PROJECT_FILE_BUCKET}/${path}`,{method:"POST",headers:{...cfg.headers,"Content-Type":file.type,"x-upsert":"false"},body:bytes});
 if(!upload.ok)throw new Error("Não foi possível armazenar o anexo.");
 const metadata=await fetch(`${cfg.url}/rest/v1/factory_project_attachments`,{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json","Prefer":"return=minimal"},body:JSON.stringify({id,draft_id:draftId,operator_user_id:operator.userId,storage_bucket:PROJECT_FILE_BUCKET,storage_path:path,original_name:file.name,mime_type:file.type,size_bytes:file.size,sha256})});
 if(!metadata.ok){await fetch(`${cfg.url}/storage/v1/object/${PROJECT_FILE_BUCKET}/${path}`,{method:"DELETE",headers:cfg.headers});throw new Error("Não foi possível registrar o anexo.");}
 return{id,name:file.name,size:file.size,type:file.type,sha256};
}

export async function finalizeProjectDraftFiles(draftId:string,projectId:string){
 const operator=await requireConsoleOperator();const cfg=getSupabaseServerConfig();if(!cfg)throw new Error("Control plane unavailable");
 const response=await fetch(`${cfg.url}/rest/v1/rpc/factory_finalize_project_attachments`,{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},body:JSON.stringify({p_draft_id:draftId,p_operator_user_id:operator.userId,p_project_id:projectId})});
 if(!response.ok)throw new Error("Não foi possível vincular os anexos ao projeto.");return Number(await response.json());
}
