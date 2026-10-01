"use client";

import type {ReactNode} from "react";
import {useFormStatus} from "react-dom";

export function GateDecisionPending({children}:{children:ReactNode}){
 const {pending}=useFormStatus();
 return <fieldset className="gatePendingFieldset" disabled={pending} aria-busy={pending}>
  {pending?<div className="gatePendingStatus" role="status" aria-live="polite">Processando decisão...</div>:null}
  {children}
 </fieldset>;
}
