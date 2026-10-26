import type {ButtonHTMLAttributes,ReactNode} from "react";
import Link from "next/link";

export type StatusTone="success"|"warning"|"danger"|"accent"|"";

// Never infer success by substring. "inactive" contains "active",
// "unhealthy" contains "healthy", and "not_ready" contains "ready".
// All three used to render green in operational Console surfaces.
const successStatuses=new Set([
  "passed","success","succeeded","complete","completed","merged",
  "released","ready","verified","healthy","active","approved","integrated",
]);
const dangerStatuses=new Set([
  "failed","failure","blocked","rejected","error","dead_letter","unhealthy",
  "ci_failed","budget_exhausted","credit_balance_exhausted","critical",
]);
const warningStatuses=new Set([
  "warning","attention","pending","queued","awaiting","awaiting_human",
  "awaiting_release","review_ready","not_assessed","not_reported",
  "not_ready","not_verified","not_released","unverified",
  "provider_reported_ready","provider_status_success_unverified",
  "degraded","stalled_ci","unknown","unavailable","paused",
]);
const neutralStatuses=new Set([
  "inactive","not_applicable","disabled","skipped","stopped","draft",
  "created","cancelled","canceled","inventory_only",
]);
const accentStatuses=new Set([
  "running","implementing","preview","preview_ready","planning","review",
  "in_progress","processing","dispatching","discovery","specification",
  "validation","routing","preparing_codex_manual",
]);
const negativeTokens=new Set([
  "failed","failure","blocked","rejected","error","exhausted",
  "invalid","denied","unhealthy",
]);
const uncertainTokens=new Set([
  "warning","attention","pending","queued","awaiting","unknown",
  "unverified","missing","not","degraded","unavailable","stalled",
]);
function canonicalStatus(status:string){
  return status.trim().toLowerCase().replace(/[\s.:/-]+/g,"_");
}

export function statusTone(status:string):StatusTone{
  const value=canonicalStatus(status);
  if(!/^[a-z0-9_]+$/.test(value)||neutralStatuses.has(value))return "";
  const tokens=value.split("_");
  // Contradictory compounds must never turn green: "failed_but_ready",
  // "provider_status_success_unverified" and "not_verified" are not PASS.
  if(dangerStatuses.has(value)||tokens.some(token=>negativeTokens.has(token)))return "danger";
  if(warningStatuses.has(value)||tokens.some(token=>uncertainTokens.has(token)))return "warning";
  if(successStatuses.has(value))return "success";
  if(accentStatuses.has(value))return "accent";
  // Unknown provider and future states are neutral, not silently successful.
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

const statusLabels:Record<string,string>={
  active:"ativo",inactive:"inativo",healthy:"saudável",attention:"atenção",unknown:"desconhecido",
  failed:"falhou",failure:"falha",blocked:"bloqueado",rejected:"rejeitado",error:"erro",dead_letter:"fila de erro",
  awaiting:"aguardando",pending:"pendente",queued:"na fila",warning:"aviso",
  passed:"aprovado",success:"sucesso",succeeded:"concluído",complete:"concluído",completed:"concluído",
  merged:"mesclado",released:"liberado",ready:"pronto",verified:"verificado",
  running:"em execução",implementing:"implementando",planning:"planejamento",review:"revisão",
  discovery:"descoberta",specification:"especificação",implementation:"implementação",validation:"testes / avaliações",
  preview:"prévia",human_gate:"aprovação humana",release:"liberação",operations:"operação",
  created:"criado",dispatching:"distribuindo",queued_execution:"aguardando execução",
  awaiting_human:"aguardando decisão humana",awaiting_release:"aguardando liberação",approved:"aprovado",cancelled:"cancelado",canceled:"cancelado",ci_pending:"CI pendente",ci_failed:"CI com falha",preview_ready:"prévia pronta",preparing_codex_manual:"preparando Codex manual",awaiting_codex_manual:"aguardando Codex manual",
  direct:"direto",unrouted:"sem rota",operator:"operador",system:"sistema",human:"humano",run:"execução",tool:"ferramenta",evaluation:"avaliação",deployment:"implantação",gate:"aprovação",audit:"auditoria",decision:"decisão",invoked:"invocado","not invoked":"não invocado",production:"produção",
  greenfield:"novo produto",existing:"projeto em andamento",low:"baixa",medium:"média",high:"alta",
  policy:"política",codex:"Codex",
  not_ready:"não pronto",not_verified:"não verificado",unverified:"não verificado",
  unhealthy:"não saudável",not_released:"não liberado",not_assessed:"não avaliado",
  not_reported:"não informado",not_applicable:"não aplicável",
  provider_reported_ready:"informação do provedor sem verificação",
  provider_status_success_unverified:"sucesso do provedor não verificado",
  budget_exhausted:"orçamento esgotado",credit_balance_exhausted:"créditos esgotados",
  ci_failed:"CI reprovada",stalled_ci:"CI sem progresso",unknown_cost:"custo desconhecido",
  expired_lease:"lease vencida",degraded:"degradado",unavailable:"indisponível",
  paused:"pausado",stopped:"parado",disabled:"desabilitado",skipped:"ignorado",
  integrated:"integrado",review_ready:"revisão pendente"
};

export function humanizeStatus(status:string){
  const key=canonicalStatus(status);
  return statusLabels[key]??status.replaceAll("_"," ");
}

export function StatusPill({status,label,tone}:{status:string;label?:ReactNode;tone?:StatusTone}){
  const inferred=statusTone(status);
  // Caller styling must not turn an uncertain/failed status into a green badge.
  const resolved=inferred==="danger"||inferred==="warning"
    ? inferred : tone==="success"&&inferred!=="success" ? inferred : tone??inferred;
  const stateLabel=humanizeStatus(status);
  // A custom visible label can otherwise mask the underlying state for
  // screen readers. Preserve that state in the accessible name.
  const spokenLabel=(typeof label==="string"||typeof label==="number")&&String(label)!==stateLabel
    ? stateLabel+": "+String(label) : undefined;
  return <span className={resolved?"pill "+resolved:"pill"} aria-label={spokenLabel}>
    {label??stateLabel}
  </span>;
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
