"use client";

import {useFormStatus} from "react-dom";
import {ConfirmSubmit} from "../confirm-submit";

function GateDecisionButtons(){
 const {pending}=useFormStatus();
 return <div className="gateActionBar" aria-live="polite" aria-busy={pending}>
  <ConfirmSubmit className="danger" name="resolution" value="rejected" disabled={pending} confirmMessage="Rejeitar este gate e interromper esta continuação da Factory?">{pending?"Processando decisão...":"Rejeitar / interromper"}</ConfirmSubmit>
  <ConfirmSubmit className="primary" name="resolution" value="approved" disabled={pending} confirmMessage="Confirmar esta aprovação humana? A Factory poderá continuar a partir deste gate, respeitando os próximos gates aplicáveis.">{pending?"Processando decisão...":"Assinar e aprovar"}</ConfirmSubmit>
 </div>;
}

export function GateDecisionForm({gateId,action}:{gateId:string;action:(formData:FormData)=>Promise<void>}){
 return <form action={action} className="gateForm">
  <input type="hidden" name="gate_id" value={gateId}/>
  <input name="note" placeholder="Observação opcional da decisão"/>
  <GateDecisionButtons/>
 </form>;
}
