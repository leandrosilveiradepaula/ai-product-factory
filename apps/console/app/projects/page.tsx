import Link from "next/link";
import {cookies} from "next/headers";
import {getDashboard} from "../../lib/control-plane";
import {ActionLink,EmptyState,humanizeStatus,PageHeader,StatusPill} from "../ui";

const macroStages=[
 {label:"Entender",members:["discovery","specification"]},
 {label:"Planejar",members:["planning"]},
 {label:"Construir",members:["implementation","review"]},
 {label:"Validar",members:["validation","preview"]},
 {label:"Liberar",members:["human_gate","release","operations"]},
];
function macroIndex(stage:string){return macroStages.findIndex(item=>item.members.includes(stage))}
function macroLabel(stage:string){return macroStages.find(item=>item.members.includes(stage))?.label||humanizeStatus(stage)}

const notices:Record<string,string>={
 oauth_invalid:"A autorização do Supabase expirou ou não corresponde ao fluxo iniciado. Volte ao projeto e inicie a conexão novamente.",
 project_missing:"O projeto associado à autorização do Supabase não foi encontrado.",
};

export default async function Projects({searchParams}:{searchParams:Promise<{supabase?:string;github_app?:string;setup_action?:string}>}){
 const query=await searchParams;
 const installReturned=query.github_app==="installed"||query.setup_action==="install"||query.setup_action==="update";
 const jar=installReturned?await cookies():null;
 const rawInstallProject=jar?.get("factory_github_app_install_project")?.value||"";
 const installProject=/^[a-z0-9][a-z0-9-]{0,63}$/.test(rawInstallProject)?rawInstallProject:null;
 const d=await getDashboard();const notice=query.supabase?notices[query.supabase]:undefined;
 const installPending=installReturned&&installProject&&d.projects.some(p=>p.key===installProject);
 return <>
  <PageHeader eyebrow="Área de trabalho" title="Seus projetos" subtitle="Acesse cada produto para ver a etapa registrada, a próxima ação e as evidências. Estar em uma etapa não significa que seus testes foram aprovados." actions={<ActionLink href="/projects/new" variant="primary">Novo projeto</ActionLink>}/>
  {notice?<div className="card noticeCard danger" role="status"><StatusPill status="failed"/><span>{notice}</span></div>:null}
  {installPending?<div className="card noticeCard" role="status">
   <span>Instalação da GitHub App iniciada para {installProject}. Confira as permissões concedidas no GitHub e confirme a verificação; retornar a esta tela não comprova acesso.</span>
   <form method="POST" action="/api/integrations/github-app/verify">
    <input type="hidden" name="project" value={installProject}/>
    <input type="hidden" name="return_to" value="gates"/>
    <button type="submit" className="primary">Verificar acesso da GitHub App</button>
   </form>
  </div>:null}
  <div className="projectCards">
   {d.projects.length===0?<div className="homeEmptyProject"><EmptyState>Nenhum projeto cadastrado. Inicie um produto ou importe um repositório existente.</EmptyState><ActionLink href="/projects/new" variant="primary">Criar primeiro projeto</ActionLink></div>
   :d.projects.map(p=>{
    const current=macroIndex(p.stage);
    return <Link className="card projectCard" href={"/projects/"+p.key} key={p.key}>
     <div className="cardTop"><div><h2 className="cardTitle">{p.name}</h2><p className="cardMeta mono">{p.key}</p></div><StatusPill status={p.status}/></div>
     <div className="projectStageLabel"><span>Etapa registrada</span><strong>{macroLabel(p.stage)}</strong></div>
     <div className="projectMiniRail" role="img" aria-label={current>=0?`Etapa ${current+1} de 5: ${macroLabel(p.stage)}. Indicador de posição, não de prontidão.`:"Etapa ainda não classificada; nenhuma prontidão inferida."}>
      {macroStages.map((step,i)=><span key={step.label} className={i===current?"projectMiniStep current":i<current?"projectMiniStep done":"projectMiniStep"}>{step.label}</span>)}
     </div>
     <div className="projectCardFooter"><span className="muted">Atualizado em {new Date(p.updatedAt).toLocaleString("pt-BR")}</span><strong className="cardAction">Abrir acompanhamento →</strong></div>
    </Link>;
   })}
  </div>
 </>;
}