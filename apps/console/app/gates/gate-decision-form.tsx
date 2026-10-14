"use client";

import type {ReactNode} from "react";
import {useFormStatus} from "react-dom";

export function GateDecisionPending({children,pendingMessage="Processando decisão e conferindo o resultado. Não envie novamente."}:{children:ReactNode;pendingMessage?:string}){
 const {pending}=useFormStatus();
 return <fieldset className="gatePendingFieldset" disabled={pending} aria-busy={pending}>
  {pending?<div className="gateBusyStatus" role="status" aria-live="polite" aria-atomic="true"><span className="gateBusySpinner" aria-hidden="true"/><span><strong>Operação em andamento</strong><span>{pendingMessage}</span></span></div>:null}
  {children}
 </fieldset>;
}
