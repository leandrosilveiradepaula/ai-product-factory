"use client";

import {useFormStatus} from "react-dom";

/** Feedback tied to the real server-action transition, not to a guessed timeout. */
export function ContinuationSubmit(){
 const {pending}=useFormStatus();
 return <div className="continuationSubmit">
  <button type="submit" className="primary" disabled={pending}
   aria-disabled={pending} aria-busy={pending}>
   {pending?<><span className="continuationSubmitSpinner" aria-hidden="true"/>Registrando pedido...</>:"Iniciar novo ciclo"}
  </button>
  <p className="muted continuationSubmitFeedback" role="status" aria-live="polite" aria-atomic="true">
   {pending
    ?"Salvando o pedido e confirmando o acionamento. Não clique novamente; você será direcionado ao projeto."
    :"Ao confirmar, a Factory registra uma solicitação. O trabalho só começa quando um worker assume a execução."}
  </p>
 </div>;
}
