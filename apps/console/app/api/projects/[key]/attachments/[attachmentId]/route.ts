import {NextResponse} from "next/server";
import {requireConsoleOperator} from "../../../../../../lib/auth-server";
import {getSupabaseServerConfig} from "../../../../../../lib/supabase-server";
import {MAX_PROJECT_FILE_BYTES,PROJECT_FILE_BUCKET} from "../../../../../../lib/attachments";

function downloadName(value:string){
 return value.replace(/[\r\n"]/g,"_").replace(/[^\x20-\x7E]/g,"_").slice(0,180)||"anexo";
}

export async function GET(_request:Request,{params}:{params:Promise<{key:string;attachmentId:string}>}){
 await requireConsoleOperator();
 const {key,attachmentId}=await params;
 if(!/^[a-z0-9][a-z0-9-]{0,63}$/.test(key)||!/^[0-9a-f-]{36}$/i.test(attachmentId))return NextResponse.json({error:"Anexo inválido."},{status:400});
 const cfg=getSupabaseServerConfig();if(!cfg)return NextResponse.json({error:"Control Plane indisponível."},{status:503});
 const projectResponse=await fetch(cfg.url+"/rest/v1/factory_projects?select=id&project_key=eq."+encodeURIComponent(key)+"&is_active=eq.true&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!projectResponse.ok)return NextResponse.json({error:"Não foi possível validar o projeto."},{status:502});
 const projects=await projectResponse.json();const projectId=projects[0]?.id;
 if(!projectId)return NextResponse.json({error:"Projeto não encontrado."},{status:404});
 const metadataResponse=await fetch(cfg.url+"/rest/v1/factory_project_attachments?select=id,storage_bucket,storage_path,original_name,mime_type,size_bytes&project_id=eq."+encodeURIComponent(String(projectId))+"&id=eq."+encodeURIComponent(attachmentId)+"&finalized_at=not.is.null&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!metadataResponse.ok)return NextResponse.json({error:"Não foi possível validar o anexo."},{status:502});
 const rows=await metadataResponse.json();const file=rows[0];
 if(!file||file.storage_bucket!==PROJECT_FILE_BUCKET)return NextResponse.json({error:"Anexo não encontrado."},{status:404});
 const size=Number(file.size_bytes||0);if(size<=0||size>MAX_PROJECT_FILE_BYTES)return NextResponse.json({error:"Tamanho de anexo inválido."},{status:422});
 const objectResponse=await fetch(cfg.url+"/storage/v1/object/"+encodeURIComponent(file.storage_bucket)+"/"+String(file.storage_path).split("/").map(encodeURIComponent).join("/"),{headers:cfg.headers,cache:"no-store"});
 if(!objectResponse.ok)return NextResponse.json({error:"Não foi possível baixar o anexo."},{status:objectResponse.status===404?404:502});
 const body=await objectResponse.arrayBuffer();
 if(body.byteLength!==size)return NextResponse.json({error:"O anexo armazenado não corresponde aos metadados registrados."},{status:502});
 return new Response(body,{status:200,headers:{
  "Content-Type":String(file.mime_type||"application/octet-stream"),
  "Content-Length":String(body.byteLength),
  "Content-Disposition":'attachment; filename="'+downloadName(String(file.original_name||"anexo"))+'"',
  "Cache-Control":"private, no-store",
  "X-Content-Type-Options":"nosniff",
 }});
}
