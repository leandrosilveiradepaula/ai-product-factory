import Link from "next/link";
import {getDashboard} from "../../lib/control-plane";
import {ActionLink,EmptyState,humanizeStatus,PageHeader,StatusPill} from "../ui";

const stages=["discovery","specification","planning","implementation","review","validation","preview","human_gate","release","operations"];
function progress(stage:string){const i=stages.indexOf(stage);return i<0?8:Math.round(((i+1)/stages.length)*100)}

const notices:Record<string,string>={
 oauth_invalid:"A autorização do Supabase expirou ou não corresponde ao fluxo iniciado. Volte ao projeto e inicie a conexão novamente.",
 project_missing:"O projeto associado à autorização do Supabase não foi encontrado.",
};

export default async function Projects({searchParams}:{searchParams:Promise<{supabase?:string}>}){
 const [d,query]=await Promise.all([getDashboard(),searchParams]);const notice=query.supabase?notices[query.supabase]:undefined;
 return <>
  <PageHeader eyebrow="Projetos" title="Portfólio de produtos" subtitle="Produtos novos e projetos existentes conduzidos pela Factory." actions={<ActionLink href="/projects/new" variant="primary">+ Novo projeto</ActionLink>}/>
  {notice?<div className="card noticeCard danger" role="status"><StatusPill status="failed"/><span>{notice}</span></div>:null}
  <div className="projectCards">
   {d.projects.length===0?<EmptyState>Nenhum projeto registrado.</EmptyState>:d.projects.map(p=><Link className="card projectCard" href={"/projects/"+p.key} key={p.key}>
    <div className="cardTop"><div><h2 className="cardTitle">{p.name}</h2><p className="cardMeta mono">{p.key}</p></div><StatusPill status={p.stage} tone="accent"/></div>
    <div className="progressTrack"><div className="progressFill" style={{width:progress(p.stage)+"%"}}/></div>
    <div className="valueRow"><span className="muted">Progresso do ciclo</span><strong>{progress(p.stage)}%</strong></div>
    <div className="badgeLine"><span className="status"><i className="statusDot"/>{humanizeStatus(p.status)}</span><span className="muted">atualizado em {new Date(p.updatedAt).toLocaleString("pt-BR")}</span></div>
   </Link>)}
  </div>
 </>;
}