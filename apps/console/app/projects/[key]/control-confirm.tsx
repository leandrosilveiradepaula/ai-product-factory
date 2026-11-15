"use client";
import {useRef} from "react";
import {useFormStatus} from "react-dom";

export function ProjectControlSubmit({command,label}:{command:string;label:string}){
 const {pending}=useFormStatus();
 const commandId=useRef<HTMLInputElement>(null);
 const destructive=command==="stop";
 const needsConfirmation=destructive||command==="start"||command==="restart";
 return <><input ref={commandId} type="hidden" name="command_id" defaultValue=""/><button type="submit" className={destructive?"danger":"primary"}
  disabled={pending} aria-disabled={pending} aria-busy={pending}
  onClick={event=>{
   if(needsConfirmation&&!window.confirm(command==="start"
    ?"Iniciar o desenvolvimento deste projeto? A Factory poderá enfileirar tarefas e executar ações autorizadas pelos gates existentes."
    :command==="stop"
    ?"Parar este projeto? Nenhuma tarefa nova será assumida. Trabalhos já assumidos poderão concluir com segurança; a fila e o histórico serão preservados."
    :"Reiniciar este projeto? Uma nova geração de execução será autorizada, mantendo as tarefas pendentes e os gates existentes.")){
      event.preventDefault();
      return;
   }
   // The unique idempotency key is generated after human confirmation.
   // It remains stable if the browser repeats the same pending submit.
   if(commandId.current&&!commandId.current.value)
      commandId.current.value=crypto.randomUUID();
  }}>{pending?"Registrando comando...":label}</button></>;
}
