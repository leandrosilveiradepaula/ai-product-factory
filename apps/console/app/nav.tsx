"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import type {ReactNode} from "react";

type IconName="overview"|"projects"|"runs"|"queue"|"gates"|"evals"|"deployments"|"usage"|"audit"|"configuration"|"operators";

function Icon({name}:{name:IconName}){
 const common={fill:"none",stroke:"currentColor",strokeWidth:1.7,strokeLinecap:"round" as const,strokeLinejoin:"round" as const};
 let body:ReactNode;
 switch(name){
  case "overview": body=<><rect x="3.5" y="3.5" width="7" height="7" rx="1"/><rect x="13.5" y="3.5" width="7" height="7" rx="1"/><rect x="3.5" y="13.5" width="7" height="7" rx="1"/><rect x="13.5" y="13.5" width="7" height="7" rx="1"/></>;break;
  case "projects": body=<><path d="M3.5 7.5h6l1.8 2h9.2v9.5a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19z"/><path d="M3.5 7.5V5A1.5 1.5 0 0 1 5 3.5h4.5l1.8 2H19a1.5 1.5 0 0 1 1.5 1.5v2.5"/></>;break;
  case "runs": body=<><circle cx="12" cy="12" r="8.5"/><path d="m10 8.5 5.5 3.5-5.5 3.5z"/></>;break;
  case "queue": body=<><path d="M6 6.5h14M6 12h14M6 17.5h14"/><circle cx="3.5" cy="6.5" r=".7" fill="currentColor" stroke="none"/><circle cx="3.5" cy="12" r=".7" fill="currentColor" stroke="none"/><circle cx="3.5" cy="17.5" r=".7" fill="currentColor" stroke="none"/></>;break;
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

const groups=[
 {label:"Operações",items:[
  {href:"/",label:"Visão geral",icon:"overview" as IconName},
  {href:"/projects",label:"Projetos",icon:"projects" as IconName},
  {href:"/runs",label:"Execuções",icon:"runs" as IconName},
  {href:"/queue",label:"Fila de trabalho",icon:"queue" as IconName},
  {href:"/gates",label:"Aprovações humanas",icon:"gates" as IconName},
 ]},
 {label:"Qualidade e liberação",items:[
  {href:"/evals",label:"Avaliações e testes",icon:"evals" as IconName},
  {href:"/deployments",label:"Implantações",icon:"deployments" as IconName},
 ]},
 {label:"Governança e observação",items:[
  {href:"/usage",label:"Modelos e uso",icon:"usage" as IconName},
  {href:"/audit",label:"Log de auditoria",icon:"audit" as IconName},
  {href:"/configuration",label:"Configuração",icon:"configuration" as IconName},
  {href:"/admin/operators",label:"Operadores",icon:"operators" as IconName},
 ]},
];

function active(pathname:string,href:string){
 if(href==="/")return pathname==="/";
 return pathname===href||pathname.startsWith(href+"/");
}

export function ConsoleNav(){
 const pathname=usePathname();
 return <nav className="sidebarNav">
  {groups.map(group=><div className="navGroup" key={group.label}>
   <div className="navGroupLabel">{group.label}</div>
   <div className="navGroupItems">
    {group.items.map(item=><Link className={active(pathname,item.href)?"navItem active":"navItem"} href={item.href} key={item.href}>
     <span className="navIcon"><Icon name={item.icon}/></span>
     <span>{item.label}</span>
    </Link>)}
   </div>
  </div>)}
 </nav>;
}
