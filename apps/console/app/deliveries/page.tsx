import Link from "next/link";
import {deliveryLanes,getDeliveryBoard,type DeliveryCard} from "../../lib/delivery-board";
import {PageHeader} from "../ui";

export const dynamic="force-dynamic";

function DeliveryCardView({item}:{item:DeliveryCard}){
 return <article className="deliveryCard">
  <div className="deliveryCardOverline"><span>{item.projectName}</span><span className={"deliveryStatus "+item.lane}>{item.statusLabel}</span></div>
  <h3>{item.title}</h3>
  {item.latestActivity?<p className="deliveryLatest">Última atividade: {item.latestActivity}</p>:null}
  <p className="deliveryCardMeta">{item.taskCount} {item.taskCount===1?"tarefa vinculada":"tarefas vinculadas"} · atualização {new Date(item.updatedAt).toLocaleDateString("pt-BR")}</p>
  <div className="deliveryCardActions">
   {item.needsHuman?<Link prefetch={false} className="deliveryActionLink" href="/gates">Revisar decisão →</Link>
    :<Link prefetch={false} className="deliveryActionLink" href={"/projects/"+item.projectKey}>Abrir produto →</Link>}
   {item.latestRunId?<Link prefetch={false} className="deliverySecondaryLink" href={"/runs/"+item.latestRunId}>Ver execução</Link>:null}
  </div>
 </article>;
}

export default async function Deliveries({searchParams}:{searchParams:Promise<{project?:string;view?:string}>}){
 const query=await searchParams;
 const selected=typeof query.project==="string"&&/^[a-z0-9][a-z0-9-]{0,63}$/.test(query.project)?query.project:"";
 const board=await getDeliveryBoard();
 const knownProject=board.projects.some(p=>p.key===selected);
 const projectKey=knownProject?selected:"";
 const scoped=projectKey?board.cards.filter(c=>c.projectKey===projectKey):board.cards;
 const showTechnical=query.view==="all";
 const technicalCount=scoped.filter(c=>c.internalRoutine).length;
 const cards=showTechnical?scoped:scoped.filter(c=>!c.internalRoutine);
 const viewSuffix=showTechnical?"?view=all":"";
 const projectViewSuffix=showTechnical?"&view=all":"";
 const counts=Object.fromEntries(deliveryLanes.map(l=>[l.key,cards.filter(c=>c.lane===l.key).length]));
 return <>
  <PageHeader eyebrow="Entregas" title="Quadro de trabalho"
   subtitle="Acompanhe pedidos e pacotes de trabalho de cada produto. A Factory atualiza os estados; você só decide quando houver uma pendência real."
   actions={<Link prefetch={false} className="primary linkButton" href="/projects">Solicitar uma melhoria</Link>}/>
  <section className="deliveryIntro" aria-label="Como usar o quadro">
   <div><strong>Como usar</strong><p>Escolha um cartão para ver seu produto e as execuções. Você não precisa mover cartões: eles refletem os registros verificados do Control Plane.</p></div>
   <Link prefetch={false} href="/gates">Ver decisões que dependem de mim →</Link>
  </section>

  <nav className="deliveryFilters" aria-label="Filtrar entregas por produto">
   <Link prefetch={false} className={!projectKey?"deliveryFilter active":"deliveryFilter"} aria-current={!projectKey?"page":undefined} href={"/deliveries"+viewSuffix}>Todos os produtos</Link>
   {board.projects.map(p=><Link prefetch={false} className={projectKey===p.key?"deliveryFilter active":"deliveryFilter"}
     aria-current={projectKey===p.key?"page":undefined} key={p.key} href={"/deliveries?project="+encodeURIComponent(p.key)+projectViewSuffix}>{p.name}</Link>)}
  </nav>

  <div className="deliveryBoardHeading">
   <p>{cards.length} {cards.length===1?"pacote de trabalho":"pacotes de trabalho"} no quadro · consulta {new Date(board.readAt).toLocaleString("pt-BR")}</p>
   {technicalCount>0?<Link prefetch={false} className="deliveryTechnicalToggle"
     href={showTechnical?("/deliveries"+(projectKey?"?project="+encodeURIComponent(projectKey):"")):
       ("/deliveries?view=all"+(projectKey?"&project="+encodeURIComponent(projectKey):""))}>
     {showTechnical?"Ocultar rotinas internas":technicalCount+" rotinas internas ocultas · Mostrar"}
    </Link>:<span>Estados registrados; não é execução em tempo real.</span>}
  </div>
  <section className="deliveryBoard" aria-label="Quadro Kanban de entregas">
   {deliveryLanes.map(lane=>{
    const items=cards.filter(c=>c.lane===lane.key);
    return <div className={"deliveryLane lane-"+lane.key} key={lane.key}>
     <div className="deliveryLaneHeading">
      <div><h2>{lane.label}</h2><small>{lane.hint}</small></div><strong aria-label={items.length+" pacotes"}>{counts[lane.key]}</strong>
     </div>
     <div className="deliveryLaneCards">
      {items.length===0?<p className="deliveryLaneEmpty">Nenhum trabalho nesta etapa.</p>:<>
       {items.slice(0,8).map(item=><DeliveryCardView item={item} key={item.id}/>)}
       {items.length>8?<details className="deliveryMore">
        <summary>Mostrar mais {items.length-8} {items.length-8===1?"pacote":"pacotes"}</summary>
        {items.slice(8).map(item=><DeliveryCardView item={item} key={item.id}/>)}
       </details>:null}
      </>}
     </div>
    </div>;
   })}
  </section>
  <p className="deliveryDisclaimer">Importante: “Encerrado” significa que tarefas foram concluídas ou canceladas no Control Plane; não comprova aprovação de qualidade, merge, publicação nem certificação do produto. Itens bloqueados não são automaticamente ações humanas.</p>
 </>;
}
