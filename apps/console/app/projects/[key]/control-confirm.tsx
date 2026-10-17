"use client";
import {useFormStatus} from "react-dom";

export function ProjectControlSubmit({command,label}:{command:string;label:string}){
 const {pending}=useFormStatus();
 const destructive=command==="stop";
 const needsConfirmation=destructive||command==="start"||command==="restart";
 return <button type="submit" className={destructive?"danger":"primary"}
  disabled={pending} aria-disabled={pending} aria-busy={pending}
  onClick={event=>{
   if(needsConfirmation&&!window.confirm(command==="start"
    ?"Iniciar o desenvolvimento deste projeto? A Factory poderá enfileirar tarefas e executar ações autorizadas pelos gates existentes."
    :command==="stop"
    ?"Parar este projeto? Nenhuma tarefa nova será assumida. Trabalhos já assumidos poderão concluir com segurança; a fila e o histórico serão preservados."
    :"Reiniciar este projeto? Uma nova geração de execução será autorizada, mantendo as tarefas pendentes e os gates existentes.")){
      event.preventDefault();
   }
  }}>{pending?"Registrando comando...":label}</button>;
}
