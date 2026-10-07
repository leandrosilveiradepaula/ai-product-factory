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
 const {pending,data}=useFormStatus();
 const rejecting=String(data?.get("resolution")||"")==="rejected";
 const activeLabel=rejecting?"Registrando rejeição...":pendingLabel;
 const activeDetail=rejecting?"Aguarde a confirmação do servidor. Nenhuma etapa seguinte será liberada enquanto isso.":pendingDetail;
 return <fieldset className="gatePendingFieldset" disabled={pending} aria-busy={pending}>
  {pending?<div className="gateBusyPanel" role="status" aria-live="polite">
   <span className="gateBusySpinner" aria-hidden="true"/>
   <div>
    <strong>{activeLabel}</strong>
    <span>{activeDetail}</span>
   </div>
  </div>:null}
  <div className={pending?"gatePendingBody isPending":"gatePendingBody"}>{children}</div>
 </fieldset>;
}
