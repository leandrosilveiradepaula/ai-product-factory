"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";

const groups=[
  {label:"Workspace",items:[
    {href:"/",label:"Overview",icon:"◫"},
    {href:"/projects",label:"Projects",icon:"◆"},
  ]},
  {label:"Execution",items:[
    {href:"/runs",label:"Runs",icon:"▶"},
    {href:"/queue",label:"Work Queue",icon:"≡"},
    {href:"/gates",label:"Human Gates",icon:"◇"},
  ]},
  {label:"Quality",items:[
    {href:"/evals",label:"Evals",icon:"✓"},
    {href:"/deployments",label:"Deployments",icon:"↗"},
  ]},
  {label:"Observability",items:[
    {href:"/usage",label:"Models & Usage",icon:"◎"},
    {href:"/audit",label:"Audit Log",icon:"≣"},
  ]},
  {label:"System",items:[
    {href:"/configuration",label:"Configuration",icon:"⚙"},
    {href:"/admin/operators",label:"Operators",icon:"◉"},
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
