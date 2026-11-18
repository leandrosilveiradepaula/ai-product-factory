import {cookies} from "next/headers";
import {getDashboard} from "../../lib/control-plane";
import {getProductSituations} from "../../lib/product-status";
import {ProductSituationCard} from "../product-situation-card";
import {ActionLink,EmptyState,PageHeader,StatusPill} from "../ui";

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
 const [d,pulse]=await Promise.all([getDashboard(),getProductSituations()]);
 const current=pulse.products.filter(p=>!p.isInternalRecord&&p.state!=="stopped"&&p.state!=="paused");
 const inactive=pulse.products.filter(p=>!p.isInternalRecord&&(p.state==="stopped"||p.state==="paused"));
 const technical=pulse.products.filter(p=>p.isInternalRecord);
 const notice=query.supabase?notices[query.supabase]:undefined;
 const installPending=installReturned&&installProject&&d.projects.some(p=>p.key===installProject);
 return <>
  <PageHeader eyebrow="Produtos" title="Escolha o produto que quer acompanhar"
   subtitle="Veja entregas comprovadas, bloqueios e próximos passos. A fase registrada não garante que o produto esteja finalizado." actions={<ActionLink href="/projects/new" variant="primary">Criar produto</ActionLink>}/>
  {notice?<div className="card noticeCard danger" role="status"><StatusPill status="failed"/><span>{notice}</span></div>:null}
  {installPending?<div className="card noticeCard" role="status">
   <span>O GitHub retornou da instalação de {installProject}. Confira as permissões concedidas e verifique o acesso; retornar a esta tela não comprova acesso.</span>
   <form method="POST" action="/api/integrations/github-app/verify">
    <input type="hidden" name="project" value={installProject}/>
    <input type="hidden" name="return_to" value="gates"/>
    <button type="submit" className="primary">Verificar acesso da GitHub App</button>
   </form>
  </div>:null}
  <div className="productSituationList projectSituationList">
   {pulse.products.length===0?
    <div className="homeEmptyProject"><EmptyState>Nenhum produto cadastrado.</EmptyState><ActionLink href="/projects/new" variant="primary">Criar primeiro produto</ActionLink></div>:
    current.map(item=><ProductSituationCard key={item.key} item={item} compact/>)}
  </div>
  {inactive.length>0?<details className="productInactiveDisclosure">
   <summary>Projetos parados ou aposentados ({inactive.length})</summary>
   <div className="productSituationList">{inactive.map(item=><ProductSituationCard key={item.key} item={item} compact/>)}</div>
  </details>:null}
  {technical.length>0?<details className="productInactiveDisclosure">
   <summary>Registros de testes internos ({technical.length})</summary>
   <div className="productSituationList">{technical.map(item=><ProductSituationCard key={item.key} item={item} compact/>)}</div>
  </details>:null}
  <p className="productSituationFootnote">Situação observada em {new Date(pulse.observedAt).toLocaleString("pt-BR")}. Etapas e execuções são registros; publicação em produção exige evidências e aprovação humana próprias.</p>
 </>;
}
