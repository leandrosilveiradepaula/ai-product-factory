"use client";

import {useEffect,useState} from "react";

export function GateActionSuccessBanner({migrationName,alreadyApplied}:{migrationName:string;alreadyApplied:boolean}){
 const [visible,setVisible]=useState(true);
 useEffect(()=>{
  const url=new URL(window.location.href);
  if(!url.searchParams.has("migration_result"))return;
  url.searchParams.delete("migration_result");
  const next=url.pathname+(url.searchParams.toString()?"?"+url.searchParams.toString():"")+url.hash;
  window.history.replaceState(window.history.state,"",next);
 },[]);
 if(!visible)return null;
 return <div className="card noticeCard success gateSuccessNotice" role="status" aria-live="polite">
  <div className="gateSuccessMark" aria-hidden="true">✓</div>
  <div className="gateSuccessCopy">
   <strong>{alreadyApplied?"Migration já aplicada, estado confirmado.":"Migration aplicada e confirmada no Supabase."}</strong>
   <span>{migrationName} · evidência de auditoria e gate resolvido verificados no Control Plane.</span>
  </div>
  <button type="button" className="linkButton" onClick={()=>setVisible(false)} aria-label="Fechar confirmação">Fechar</button>
 </div>;
}
