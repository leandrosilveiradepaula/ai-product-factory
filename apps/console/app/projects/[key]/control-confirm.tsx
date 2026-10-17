"use client";
import {useFormStatus} from "react-dom";

export function ProjectControlSubmit({command,label}:{command:string;label:string}){
 const {pending}=useFormStatus();
 const destructive=command==="stop"||command==="restart";
 const needsConfirmation=destructive||command==="start";
 return <button type="submit" className={destructive?"danger":"primary"}
  disabled={pending} aria-disabled={pending} aria-busy={pending}
  onClick={event=>{
   if(needsConfirmation&&!window.confirm(command==="start"
    ?"Iniciar o desenvolvimento deste projeto? A Factory poderá enfileirar tarefas e executar ações autorizadas pelos gates existentes."
    :command==="stop"
    ?"Parar este projeto? Os trabalhos serão interrompidos com segurança, sem excluir os dados."
    :"Reiniciar este projeto em um novo ciclo? Será necessária nova autorização de execução.")){
      event.preventDefault();
   }
  }}>{pending?"Registrando comando...":label}</button>;
}
