"use client";
import {useRef,useState} from "react";
import type {FormEvent} from "react";

/** Keep the browser's native POST/303 flow while providing immediate feedback.
 * The server remains authoritative for auth, origin, repository and capability checks.
 */
export function RepositoryLinkForm({projectKey}:{projectKey:string}){
 const [submitting,setSubmitting]=useState(false);
 const submitStarted=useRef(false);
 function onSubmit(event:FormEvent<HTMLFormElement>){
  // Synchronous guard: repeated clicks before React commits are ignored.
  if(submitStarted.current){event.preventDefault();return;}
  submitStarted.current=true;
  setSubmitting(true);
 }
 return <form method="POST"
  action={"/api/projects/"+encodeURIComponent(projectKey)+"/link-repository"}
  onSubmit={onSubmit} aria-busy={submitting}>
   <button className="linkButton" type="submit" disabled={submitting}>
    {submitting?"Verificando repositório e permissões…":"3. Verificar e vincular repositório"}
   </button>
   {submitting?<p className="muted" role="status" aria-live="polite">
    Consultando o GitHub e registrando as permissões. Aguarde; não é necessário clicar novamente.
   </p>:null}
  </form>;
}
