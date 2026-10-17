"use client";
import {useFormStatus} from "react-dom";

export function ProjectControlSubmit({command,label}:{command:string;label:string}){
 const {pending}=useFormStatus();
 const destructive=command==="stop"||command==="restart";
 return <button type="submit" className={destructive?"danger":"primary"}
  disabled={pending} aria-disabled={pending} aria-busy={pending}
  onClick={event=>{
   if(destructive&&!window.confirm(command==="stop"
    ?"Parar este projeto? Os trabalhos serão interrompidos com segurança, sem excluir os dados."
    :"Reiniciar este projeto em um novo ciclo? Será necessária nova autorização de execução.")){
      event.preventDefault();
   }
  }}>{pending?"Registrando comando...":label}</button>;
}
