import Link from "next/link";
import {cookies} from "next/headers";
import {redirect} from "next/navigation";
import {getDashboard} from "../../lib/control-plane";
import {ActionLink,EmptyState,humanizeStatus,PageHeader,StatusPill} from "../ui";

const macroStages=[
 {label:"Entender",members:["discovery","specification"]},
 {label:"Planejar",members:["planning"]},
 {label:"Construir",members:["implementation","review"]},
 {label:"Validar",members:["validation","preview"]},
 {label:"Liberar",members:["human_gate","release","operations"]},
];
function macroProgress(stage:string){const i=macroStages.findIndex(item=>item.members.includes(stage));return i<0?10:Math.round(((i+1)/macroStages.length)*100)}
function macroLabel(stage:string){return macroStages.find(item=>item.members.includes(stage))?.label||humanizeStatus(stage)}

const notices:Record<string,string>={
 oauth_invalid:"A autorização do Supabase expirou ou não corresponde ao fluxo iniciado. Volte ao projeto e inicie a conexão novamente.",
 project_missing:"O projeto associado à autorização do Supabase não foi encontrado.",
};

export default async function Projects({searchParams}:{searchParams:Promise<{supabase?:string;github_app?:string}>}){
 const query=await searchParams;
 if(query.github_app==="installed"){
  const jar=await cookies();
  const project=jar.get("factory_github_app_install_project")?.value||"";
  if(/^[a-z0-9][a-z0-9-]{0,63}$/.test(project)){
   redirect("/api/integrations/github-app/verify?project="+encodeURIComponent(project)+"&return_to=gates");
  }
 }
 const d=await getDashboard();const notice=query.supabase?notices[query.supabase]:undefined;
 return <>
  <PageHeader eyebrow="Projetos" title="Portfólio de produtos" subtitle="Produtos novos e projetos existentes conduzidos pela Factory." actions={<ActionLink href="/projects/new" variant="primary">+ Novo projeto</ActionLink>}/>
  {notice?<div className="card noticeCard danger" role="status"><StatusPill status="failed"/><span>{notice}</span></div>:null}
  <div className="projectCards">
   {d.projects.length===0?<EmptyState>Nenhum projeto registrado.</EmptyState>:d.projects.map(p=><Link className="card projectCard" href={"/projects/"+p.key} key={p.key}>
    <div className="cardTop"><div><h2 className="cardTitle">{p.name}</h2><p className="cardMeta mono">{p.key}</p></div><StatusPill status={p.stage} tone="accent"/></div>
    <div className="projectStageLabel"><span>Etapa atual</span><strong>{macroLabel(p.stage)}</strong></div>
    <div className="progressTrack"><div className="progressFill" style={{width:macroProgress(p.stage)+"%"}}/></div>
    <div className="valueRow"><span className="muted">Progresso pelas 5 macroetapas</span><strong>{macroProgress(p.stage)}%</strong></div>
    <div className="projectCardFooter"><div className="badgeLine"><span className="status"><i className="statusDot"/>{humanizeStatus(p.status)}</span><span className="muted">atualizado em {new Date(p.updatedAt).toLocaleString("pt-BR")}</span></div><strong className="cardAction">Abrir projeto →</strong></div>
   </Link>)}
  </div>
 </>;
}