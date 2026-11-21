"use client";
import {useRef} from "react";
import {useFormStatus} from "react-dom";
type ProjectCommand="start"|"pause"|"resume"|"stop"|"restart";

// Prevent SSR randomness and enforce one human-confirmed onSubmit path for all inputs.
export function ProjectControlForm({command,label,version,projectKey,action,recovery=false}:{
  command:ProjectCommand;label:string;version:number;projectKey:string;
  action:(formData:FormData)=>void|Promise<void>;recovery?:boolean;
}){
  const commandId=useRef<HTMLInputElement>(null);
  const destructive=command==="stop";
  const needsConfirmation=command==="start"||destructive||command==="restart";
  return <form action={action} onSubmit={event=>{
    if(needsConfirmation&&!window.confirm(command==="start"
      ?"Iniciar o desenvolvimento deste projeto? A Factory poderá enfileirar tarefas e executar ações autorizadas pelos gates existentes."
      :command==="stop"
      ?"Parar este projeto? Nenhuma tarefa nova será assumida. Trabalhos já assumidos poderão concluir com segurança; a fila e o histórico serão preservados."
      :recovery
      ?"Solicitar à Factory a recuperação do trabalho interrompido? O trabalho concluído será preservado e os gates de execução continuarão obrigatórios."
      :"Reiniciar este projeto? Uma nova geração de execução será autorizada, mantendo as tarefas pendentes e os gates existentes.")){
      event.preventDefault();
      return;
    }
    if(!commandId.current){event.preventDefault();return;}
    // Stable idempotency identity for retries, generated only after confirmation.
    if(!commandId.current.value)commandId.current.value=crypto.randomUUID();
  }}>
    <input type="hidden" name="project_key" value={projectKey}/>
    <input type="hidden" name="command" value={command}/>
    <input type="hidden" name="version" value={version}/>
    <input ref={commandId} type="hidden" name="command_id" defaultValue=""/>
    <ProjectControlSubmit command={command} label={label}/>
  </form>;
}
function ProjectControlSubmit({command,label}:{command:ProjectCommand;label:string}){
  const {pending}=useFormStatus();
  return <button type="submit" className={command==="stop"?"danger":"primary"}
    disabled={pending} aria-disabled={pending} aria-busy={pending}>
    {pending?"Registrando comando...":label}
  </button>;
}
