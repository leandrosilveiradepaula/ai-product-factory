import Link from "next/link";
import type {ProductSituation} from "../lib/product-status";
import {operatorStageLabel} from "../lib/operator-home";
function latestRunLabel(status:string):string{
 switch(status){
  case "completed":return "Execução técnica concluída";
  case "integrated":return "Trabalho integrado (publicação não verificada)";
  case "merged":return "Integração registrada (publicação não verificada)";
  case "preview_ready":return "Prévia registrada; evidência deve ser conferida";
  case "failed":return "Falha registrada";
  case "failed_gate":return "Verificação bloqueada";
  case "blocked":return "Execução bloqueada";
  case "repair_pending":return "Recuperação pendente";
  case "cancelled":case "canceled":return "Execução cancelada";
  default:return "Último estado registrado: "+status.replaceAll("_"," ");
 }
}
export function ProductSituationCard({item,showOpen=true}:{item:ProductSituation;showOpen?:boolean}){
 return <article className={"productSituationCard state-"+item.state}>
  <div className="productSituationTop">
   <div><h3><Link prefetch={false} href={"/projects/"+encodeURIComponent(item.key)}>{item.name}</Link></h3><span>Etapa registrada: {operatorStageLabel(item.stage)} · {item.controlState==="running"?"Projeto habilitado":item.controlState==="stopped"?"Projeto parado":item.controlState==="paused"?"Projeto pausado":"Controle: "+item.controlState}</span></div>
   <strong className={"productSituationStatus "+item.state}>{item.headline}</strong>
  </div>
  <div className="productSituationContent">
   <div className="productSituationNow"><span>O QUE ESTÁ ACONTECENDO</span><p>{item.explanation}</p></div>
   <div className="productSituationRequest"><span>ÚLTIMA SOLICITAÇÃO REGISTRADA NO CONSOLE</span><p>{item.lastRequest||"Nenhuma solicitação recente localizada neste canal. Pedidos pelo GitHub podem existir separadamente."}</p></div>
   <div className="productSituationLast"><span>ÚLTIMA TENTATIVA</span>
    {item.lastRun?<p><strong>{latestRunLabel(item.lastRun.status)}</strong> · {new Date(item.lastRun.at).toLocaleString("pt-BR")}. <Link prefetch={false} href={"/runs/"+item.lastRun.id}>Ver evidência</Link></p>:<p>Nenhuma execução vinculada a este produto.</p>}
   </div>
  </div>
  <div className="productSituationNext">
   <div><span>PRÓXIMO PASSO · {item.nextOwner}</span><p>{item.nextLabel}</p></div>
   <Link prefetch={false} className="productSituationButton" href={item.nextHref}>{item.nextLabel} <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg></Link>
   {showOpen?<Link prefetch={false} className="productSituationSecondary" href={"/projects/"+encodeURIComponent(item.key)}>Abrir acompanhamento</Link>:null}
  </div>
 </article>;
}
