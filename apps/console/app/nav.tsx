"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";

const groups=[
  {label:"Operações",items:[
    {href:"/",label:"Visão geral",icon:"▦"},
    {href:"/projects",label:"Projetos",icon:"▱"},
    {href:"/runs",label:"Execuções",icon:"◉"},
    {href:"/queue",label:"Fila de trabalho",icon:"◇"},
    {href:"/agents",label:"Agentes da Factory",icon:"✦"},
    {href:"/gates",label:"Aprovações humanas",icon:"♢"},
  ]},
  {label:"Qualidade e liberação",items:[
    {href:"/evals",label:"Avaliações e testes",icon:"✣"},
    {href:"/deployments",label:"Implantações",icon:"↗"},
  ]},
  {label:"Governança e observação",items:[
    {href:"/usage",label:"Modelos e uso",icon:"◌"},
    {href:"/audit",label:"Log de auditoria",icon:"◎"},
    {href:"/configuration",label:"Configuração",icon:"☷"},
    {href:"/admin/operators",label:"Operadores",icon:"⚙"},
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
          <span className="navIcon" aria-hidden>{item.icon}</span>
          <span>{item.label}</span>
        </Link>)}
      </div>
    </div>)}
  </nav>;
}
