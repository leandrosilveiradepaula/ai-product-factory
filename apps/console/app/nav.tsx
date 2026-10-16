"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import type {ReactNode} from "react";

type IconName="overview"|"projects"|"runs"|"queue"|"agents"|"orchestration"|"gates"|"evals"|"deployments"|"usage"|"audit"|"configuration"|"operators";

function Icon({name}:{name:IconName}){
 const common={fill:"none",stroke:"currentColor",strokeWidth:1.7,strokeLinecap:"round" as const,strokeLinejoin:"round" as const};
 let body:ReactNode;
 switch(name){
  case "overview": body=<><rect x="3.5" y="3.5" width="7" height="7" rx="1"/><rect x="13.5" y="3.5" width="7" height="7" rx="1"/><rect x="3.5" y="13.5" width="7" height="7" rx="1"/><rect x="13.5" y="13.5" width="7" height="7" rx="1"/></>;break;
  case "projects": body=<><path d="M3.5 7.5h6l1.8 2h9.2v9.5a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19z"/><path d="M3.5 7.5V5A1.5 1.5 0 0 1 5 3.5h4.5l1.8 2H19a1.5 1.5 0 0 1 1.5 1.5v2.5"/></>;break;
  case "runs": body=<><circle cx="12" cy="12" r="8.5"/><path d="m10 8.5 5.5 3.5-5.5 3.5z"/></>;break;
  case "queue": body=<><path d="M6 6.5h14M6 12h14M6 17.5h14"/><circle cx="3.5" cy="6.5" r=".7" fill="currentColor" stroke="none"/><circle cx="3.5" cy="12" r=".7" fill="currentColor" stroke="none"/><circle cx="3.5" cy="17.5" r=".7" fill="currentColor" stroke="none"/></>;break;
  case "agents": body=<><circle cx="8" cy="8" r="2.5"/><circle cx="16.5" cy="9" r="2"/><path d="M3.5 19c.5-3.8 2.2-5.7 5-5.7s4.5 1.9 5 5.7M13 18.5c.4-2.8 1.7-4.2 4-4.2 2.1 0 3.3 1.3 3.7 3.8"/></>;break;
  case "orchestration": body=<><circle cx="5" cy="12" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 12h4c3.5 0 3.5-6 6-6M11 12c3.5 0 3.5 6 6 6"/></>;break;
  case "gates": body=<><path d="M12 3.5 20 7v5.5c0 4.2-3.1 6.8-8 8-4.9-1.2-8-3.8-8-8V7z"/><path d="M12 8v5M12 16.5h.01"/></>;break;
  case "evals": body=<><path d="M5 12.5 9.2 17 19 7"/><circle cx="12" cy="12" r="9"/></>;break;
  case "deployments": body=<><path d="M5 19 19 5M10 5h9v9M5 9v10h10"/></>;break;
  case "usage": body=<><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 15v-3M12 15V8M16 15v-5"/></>;break;
  case "audit": body=<><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5l3 2M4.5 4.5 6 6"/></>;break;
  case "configuration": body=<><path d="M4 7h10M18 7h2M4 12h2M10 12h10M4 17h8M16 17h4"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="14" cy="17" r="2"/></>;break;
  case "operators": body=<><circle cx="12" cy="8" r="3.2"/><path d="M5.5 20c.6-4 2.8-6 6.5-6s5.9 2 6.5 6"/><circle cx="12" cy="12" r="9"/></>;break;
 }
 return <svg viewBox="0 0 24 24" aria-hidden {...common}>{body}</svg>;
}

// Three destinations for day-to-day work; all technical routes remain one click away.
const primaryItems=[
 {href:"/",label:"Visão geral",icon:"overview" as IconName},
 {href:"/projects",label:"Projetos",icon:"projects" as IconName},
 {href:"/gates",label:"Aprovações",icon:"gates" as IconName},
];
const advancedGroups=[
 {label:"Acompanhar execução",items:[
  {href:"/runs",label:"Execuções",icon:"runs" as IconName},
  {href:"/queue",label:"Fila de trabalho",icon:"queue" as IconName},
  {href:"/agents",label:"Agentes",icon:"agents" as IconName},
  {href:"/orchestration",label:"Orquestração",icon:"orchestration" as IconName},
 ]},
 {label:"Qualidade e entrega",items:[
  {href:"/evals",label:"Avaliações e testes",icon:"evals" as IconName},
  {href:"/deployments",label:"Implantações",icon:"deployments" as IconName},
 ]},
 {label:"Administração",items:[
  {href:"/usage",label:"Modelos e custos",icon:"usage" as IconName},
  {href:"/audit",label:"Auditoria",icon:"audit" as IconName},
  {href:"/configuration",label:"Configurações",icon:"configuration" as IconName},
  {href:"/admin/operators",label:"Operadores",icon:"operators" as IconName},
 ]},
];
export const primaryDestinations=primaryItems.map(({href})=>href);

function active(pathname:string,href:string){
 if(href==="/")return pathname==="/";
 return pathname===href||pathname.startsWith(href+"/");
}
function NavLink({href,label,icon,pathname,count}:{
 href:string;label:string;icon:IconName;pathname:string;count?:number|null;
}){
 const isActive=active(pathname,href);
 return <Link className={isActive?"navItem active":"navItem"} href={href} aria-current={isActive?"page":undefined}>
  <span className="navIcon"><Icon name={icon}/></span>
  <span className="navItemLabel">{label}</span>
  {href==="/gates"&&count!==null&&count!==undefined&&count>0
   ?<span className="humanAttentionCount" aria-label={`${count} aprovações pendentes`}>{count}</span>
   :null}
 </Link>;
}

export function ConsoleNav({attentionCount=null}:{attentionCount?:number|null}){
 const pathname=usePathname();
 const advancedActive=advancedGroups.some(group=>group.items.some(item=>active(pathname,item.href)));
 return <nav className="sidebarNav" aria-label="Navegação da Factory">
  <div className="navGroup">
   <div className="navGroupLabel">Seu trabalho</div>
   <div className="navGroupItems">
    {primaryItems.map(item=><NavLink key={item.href} {...item} pathname={pathname} count={attentionCount}/>)}
   </div>
  </div>
  <details key={pathname} className="navAdvanced" open={advancedActive}>
   <summary className="navAdvancedToggle">
    <span className="navAdvancedChevron" aria-hidden>⌄</span>
    <span className="navAdvancedTitle">Ferramentas avançadas</span>
    {advancedActive?<span className="navAdvancedCurrent">Você está aqui</span>:null}
   </summary>
   <div className="navAdvancedContent">
    {advancedGroups.map(group=><div className="navGroup" key={group.label}>
     <div className="navGroupLabel">{group.label}</div>
     <div className="navGroupItems">
      {group.items.map(item=><NavLink key={item.href} {...item} pathname={pathname}/>)}
     </div>
    </div>)}
   </div>
  </details>
 </nav>;
}
