import {redirect} from "next/navigation";
import {notFound} from "next/navigation";
import {enqueueProjectContinuation,getProjectDetail} from "../../../../lib/control-plane";
import {ActionLink,Button,PageHeader,StatusPill} from "../../../ui";

async function submit(formData:FormData){
 "use server";
 const projectKey=String(formData.get("project_key")||"").trim();
 const request=String(formData.get("request")||"").trim();
 if(!projectKey)throw new Error("Projeto inválido.");
 await enqueueProjectContinuation(projectKey,request);
 redirect("/projects/"+encodeURIComponent(projectKey));
}

export default async function ProjectRequest({params}:{params:Promise<{key:string}>}){
 const {key}=await params;
 const project=await getProjectDetail(key);
 if(!project)notFound();
 const activeTasks=project.tasks.filter(task=>!["completed","cancelled","failed","merged"].includes(task.status));
 if(activeTasks.length){
  return <>
   <PageHeader eyebrow="Novo pedido" title={project.name} subtitle="A Factory não abre dois ciclos concorrentes no mesmo projeto." actions={<ActionLink href={"/projects/"+key}>Voltar ao projeto</ActionLink>}/>
   <div className="card denseStack" style={{maxWidth:760}}>
    <div className="badgeLine"><StatusPill status="blocked" label="Trabalho já em andamento"/></div>
    <p style={{margin:0}}>Conclua ou resolva o ciclo atual antes de iniciar outro pedido. Isso evita branches, decisões e evidências concorrentes no mesmo projeto.</p>
    <div className="compactList">
     {activeTasks.slice(0,6).map(task=><div className="compactRow" key={task.id}><strong>{task.title}</strong><StatusPill status={task.status}/></div>)}
    </div>
   </div>
  </>;
 }
 return <>
  <PageHeader eyebrow="Novo pedido" title={"Continuar "+project.name} subtitle="Descreva o resultado que você quer. A Factory reconcilia o estado atual, identifica as lacunas e cria somente o trabalho necessário." actions={<ActionLink href={"/projects/"+key}>Cancelar</ActionLink>}/>
  <form action={submit} className="form card" style={{maxWidth:820}}>
   <input type="hidden" name="project_key" value={key}/>
   <label>O que você quer mudar ou continuar?
    <textarea name="request" rows={10} autoFocus required maxLength={6000} placeholder="Ex.: corrigir o fluxo de proposta em dólar, preservar as regras atuais e validar a mudança ponta a ponta pela Factory."/>
   </label>
   <p className="muted">Não precisa escolher agente, stack ou modelo. A Factory registra este pedido no contexto durável do projeto e inicia a reconciliação/planejamento adequado. Produção continua sob gate humano.</p>
   <div className="actions"><Button variant="primary">Iniciar novo ciclo</Button></div>
  </form>
 </>;
}
