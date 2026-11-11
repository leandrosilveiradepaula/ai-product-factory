"use client";

import {useEffect} from "react";

export default function ConsoleError({reset}:{error:Error & {digest?:string};reset:()=>void}){
 useEffect(()=>{
  // Keep diagnostics server-side. The UI must not render provider responses,
  // stack traces, tokens, or operator data after a failed route render.
  console.error("console_route_render_failed");
 },[]);
 return <div className="card consoleRouteError" role="alert" aria-live="assertive" aria-atomic="true">
  <h1>Não foi possível carregar esta tela</h1>
  <p className="muted">Nenhuma ação foi confirmada. Tente carregar novamente; se o problema continuar, use o estado operacional para investigar.</p>
  <button type="button" className="primary" onClick={reset}>Tentar novamente</button>
 </div>;
}
