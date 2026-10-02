"use client";

import {useEffect,useState} from "react";

export function GateActionErrorBanner({message}:{message:string}){
 const [visible,setVisible]=useState(true);

 useEffect(()=>{
  const url=new URL(window.location.href);
  if(!url.searchParams.has("error"))return;
  url.searchParams.delete("error");
  const next=url.pathname+(url.searchParams.toString()?"?"+url.searchParams.toString():"")+url.hash;
  window.history.replaceState(window.history.state,"",next);
 },[]);

 if(!visible)return null;
 return <div className="card" role="alert" aria-live="assertive">
  <div className="panelHeading">
   <strong>Não foi possível concluir a ação.</strong>
   <button type="button" className="linkButton" onClick={()=>setVisible(false)} aria-label="Fechar aviso">Fechar</button>
  </div>
  <div className="errorText">{message}</div>
  <div className="muted">O gate continua pendente e nenhuma etapa seguinte foi liberada.</div>
 </div>;
}
