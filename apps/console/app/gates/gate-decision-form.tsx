"use client";

import type {ReactNode} from "react";
import {useFormStatus} from "react-dom";

export function GateDecisionPending({
 children,
 pendingLabel="Processando decisão...",
 pendingDetail="Aguarde a confirmação do servidor. Não feche esta página nem clique novamente.",
}:{
 children:ReactNode;
 pendingLabel?:string;
 pendingDetail?:string;
}){
 const {pending}=useFormStatus();
 return <fieldset className="gatePendingFieldset" disabled={pending} aria-busy={pending}>
  {pending?<div className="gateBusyPanel" role="status" aria-live="polite">
   <span className="gateBusySpinner" aria-hidden="true"/>
   <div>
    <strong>{pendingLabel}</strong>
    <span>{pendingDetail}</span>
   </div>
  </div>:null}
  <div className={pending?"gatePendingBody isPending":"gatePendingBody"}>{children}</div>
 </fieldset>;
}
