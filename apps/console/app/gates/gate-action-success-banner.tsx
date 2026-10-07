"use client";

import {useEffect,useState} from "react";

export function GateActionSuccessBanner({message}:{message:string}){
 const [visible,setVisible]=useState(true);

 useEffect(()=>{
  const url=new URL(window.location.href);
  if(!url.searchParams.has("success"))return;
  url.searchParams.delete("success");
  const next=url.pathname+(url.searchParams.toString()?"?"+url.searchParams.toString():"")+url.hash;
  window.history.replaceState(window.history.state,"",next);
 },[]);

 if(!visible)return null;
 return <div className="card gateSuccessBanner" role="status" aria-live="polite">
  <div className="panelHeading">
   <strong>Ação concluída.</strong>
   <button type="button" className="linkButton" onClick={()=>setVisible(false)} aria-label="Fechar aviso">Fechar</button>
  </div>
  <div>{message}</div>
 </div>;
}
