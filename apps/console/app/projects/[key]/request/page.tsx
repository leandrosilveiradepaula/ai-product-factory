import {redirect} from "next/navigation";
import {notFound} from "next/navigation";
import {enqueueProjectContinuation,getProjectDetail} from "../../../../lib/control-plane";
import {cleanupProjectContinuationFiles,uploadProjectContinuationFile} from "../../../../lib/attachments";
import {ActionLink,Button,PageHeader,StatusPill} from "../../../ui";

async function submit(formData:FormData){
 "use server";
 const projectKey=String(formData.get("project_key")||"").trim();
 const request=String(formData.get("request")||"").trim();
 if(!projectKey)throw new Error("Projeto inválido.");
 const project=await getProjectDetail(projectKey);
 if(!project)throw new Error("Projeto ativo não encontrado.");
 const files=formData.getAll("attachments").filter((value):value is File=>value instanceof File&&value.size>0);
 if(files.length>10)throw new Error("Envie no máximo 10 arquivos por pedido.");
 const requestId=String(formData.get("request_id")||"").trim();
 if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId))throw new Error("Identificador do pedido inválido.");
 try{
  for(const file of files)await uploadProjectContinuationFile(project.id,requestId,file);
 }catch(error){
  // No database RPC has run yet, so cleanup is unquestionably safe.
  try{await cleanupProjectContinuationFiles(project.id,requestId)}catch{}
  throw error;
 }
 // After RPC submission, even a 409 can refer to an already committed request_id.
 // Never delete files based on an ambiguous response; a separate verified cleanup
 // policy must handle private orphan uploads without risking legitimate attachments.
 const result=await enqueueProjectContinuation(projectKey,request,files.length,requestId);
 const notice=!result.created?"replayed":result.wakeStatus==="requested"?"requested":result.wakeStatus==="not_needed"?"recorded":"delayed";
 redirect("/projects/"+encodeURIComponent(projectKey)+"?continuation="+notice);
}

export default async function ProjectRequest({params}:{params:Promise<{key:string}>}){
 const {key}=await params;
 const project=await getProjectDetail(key);
 if(!project)notFound();
 return <>
  <PageHeader eyebrow="Novo pedido" title={"Continuar "+project.name} subtitle="Descreva o resultado que você quer. A Factory reconcilia o estado atual, identifica as lacunas e cria somente o trabalho necessário." actions={<ActionLink href={"/projects/"+key}>Cancelar</ActionLink>}/>
  <form action={submit} className="form card" style={{maxWidth:820}} encType="multipart/form-data">
   <input type="hidden" name="project_key" value={key}/>
   <input type="hidden" name="request_id" value={crypto.randomUUID()}/>
   <label>O que você quer mudar ou continuar?
    <textarea name="request" rows={10} autoFocus required maxLength={6000} placeholder="Ex.: corrigir o fluxo de proposta em dólar, preservar as regras atuais e validar a mudança ponta a ponta pela Factory."/>
   </label>
   <div className="intakeAttachments"><strong>Anexos</strong><input name="attachments" type="file" multiple accept=".pdf,.txt,.md,.csv,.json,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.webp"/><span className="muted">Até 10 arquivos, 10 MB cada. PDF, documentos Office, texto/CSV/JSON e imagens. Os arquivos ficam privados e vinculados ao projeto.</span></div>
   <p className="muted">Não precisa escolher agente, stack ou modelo. A Factory não abre dois ciclos concorrentes: o Control Plane verifica isso de forma atômica quando você envia o pedido. A Factory registra este pedido no contexto durável e inicia a reconciliação/planejamento adequado. Produção continua sob gate humano.</p>
   <div className="actions"><Button variant="primary">Iniciar novo ciclo</Button></div>
  </form>
 </>;
}
