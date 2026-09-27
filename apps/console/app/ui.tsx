import type {ButtonHTMLAttributes,ReactNode} from "react";
import Link from "next/link";

export type StatusTone="success"|"warning"|"danger"|"accent"|"";

export function statusTone(status:string):StatusTone{
  const value=status.toLowerCase();
  if(["failed","failure","blocked","rejected","error","dead_letter"].some(token=>value.includes(token)))return "danger";
  if(["awaiting","pending","queued","warning","attention"].some(token=>value.includes(token)))return "warning";
  if(["passed","success","succeeded","complete","completed","merged","released","ready","verified","healthy","active"].some(token=>value.includes(token)))return "success";
  if(["running","implementing","preview","planning","review"].some(token=>value.includes(token)))return "accent";
  return "";
}

export function PageHeader({eyebrow,title,subtitle,actions}:{eyebrow:string;title:string;subtitle:string;actions?:ReactNode}){
  return <div className="pageHeader">
    <div><div className="eyebrow">{eyebrow}</div><h1 className="title">{title}</h1><p className="subtitle">{subtitle}</p></div>
    {actions?<div className="toolbar">{actions}</div>:null}
  </div>;
}

export function MetricCard({label,value,note,compact=false}:{label:string;value:ReactNode;note?:ReactNode;compact?:boolean}){
  return <div className={compact?"card metricCard metricCardCompact":"card metricCard"}>
    <span className="metricLabel">{label}</span>
    <div className="metric">{value}</div>
    {note!=null?<div className="metricNote">{note}</div>:null}
  </div>;
}

export function StatusPill({status,label,tone}:{status:string;label?:ReactNode;tone?:StatusTone}){
  const resolved=tone??statusTone(status);
  return <span className={resolved?"pill "+resolved:"pill"}>{label??status}</span>;
}

export function SectionHeader({title,action}:{title:string;action?:ReactNode}){
  return <div className="sectionHeader"><h2>{title}</h2>{action}</div>;
}

export function EmptyState({children}:{children:ReactNode}){
  return <div className="emptyState">{children}</div>;
}

export function ActionLink({href,children,variant="secondary"}:{href:string;children:ReactNode;variant?:"primary"|"secondary"|"ghostButton"}){
  return <Link className={variant+" linkButton"} href={href}>{children}</Link>;
}

export function Button({variant="secondary",className="",...props}:ButtonHTMLAttributes<HTMLButtonElement>&{variant?:"primary"|"secondary"|"danger"|"ghostButton"}){
  const classes=[variant,className].filter(Boolean).join(" ");
  return <button {...props} className={classes}/>;
}
