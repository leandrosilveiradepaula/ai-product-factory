import Link from "next/link";
import {notFound} from "next/navigation";
import {getDeliveryBoard,type DeliveryLane} from "../../../lib/delivery-board";
import {PageHeader} from "../../ui";

export const dynamic="force-dynamic";

function stageText(lane:DeliveryLane){
 switch(lane){
  case "received":return {heading:"Pedido registrado",body:"A Factory registrou este pacote, mas não há execução comprovada. Você não precisa escolher agente ou mover o cartão."};
  case "working":return {heading:"A Factory está cuidando deste trabalho",body:"Existe atividade de execução registrada. Isso não assegura que um worker esteja ativo neste exato momento."};
  case "validating":return {heading:"Trabalho em validação",body:"A execução chegou a testes, revisão ou prévia. Aguarde evidência completa antes de aprovar publicação."};
  case "waiting_human":return {heading:"Sua decisão é necessária",body:"A Factory encontrou um gate acionável. Revise o motivo e as evidências na área de Decisões antes de responder."};
  case "blocked":return {heading:"Há um bloqueio técnico",body:"O trabalho não está pronto. A Factory registrou falha ou bloqueio, mas isso não significa que você precise autorizar qualquer ação."};
  case "closed":return {heading:"Este pacote foi encerrado",body:"As tarefas foram concluídas ou canceladas no Control Plane. Isso não comprova que uma versão tenha sido publicada em produção."};
 }
}
function taskState(status:string){
 if(["completed","integrated","merged","work_unit_completed"].includes(status))return "Trabalho técnico concluído";
 if(["cancelled","canceled"].includes(status))return "Cancelado";
 if(["blocked","failed","failed_gate","repair_pending"].includes(status))return "Bloqueado";
 if(["running","implementing","processing"].includes(status))return "Em execução";
 if(["preview_ready","ci_pending","review_ready"].includes(status))return "Em validação";
 return "Estado registrado: "+status.replaceAll("_"," ");
}

export default async function DeliveryDetails({params}:{params:Promise<{id:string}>}){
 const {id}=await params;
 if(!/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(id))notFound();
 const board=await getDeliveryBoard();
 const item=board.cards.find(card=>card.id===id);
 if(!item)notFound();
 const stage=stageText(item.lane);
 return <>
  <PageHeader eyebrow="Entrega" title={item.title}
   subtitle={"Produto: "+item.projectName+" · "+item.taskCount+" "+(item.taskCount===1?"tarefa vinculada":"tarefas vinculadas")}
   actions={<Link prefetch={false} href="/deliveries" className="secondary linkButton">Voltar ao quadro</Link>}/>

  <section className="deliveryDetailHero" aria-label="Próximo passo desta entrega">
   <span className={"deliveryStatus "+item.lane}>{item.statusLabel}</span>
   <h2>{stage.heading}</h2>
   <p>{stage.body}</p>
   <div className="deliveryDetailActions">
    {item.needsHuman?<Link prefetch={false} className="primary linkButton" href="/gates">Revisar decisão</Link>
     :item.latestRunId?<Link prefetch={false} className="primary linkButton" href={"/runs/"+item.latestRunId}>Acompanhar execução</Link>
     :<Link prefetch={false} className="primary linkButton" href={"/projects/"+item.projectKey}>Abrir produto</Link>}
    <Link prefetch={false} className="secondary linkButton" href={"/projects/"+item.projectKey+"/request"}>Solicitar melhoria ou ajuste</Link>
    <Link prefetch={false} className="secondary linkButton" href={"/projects/"+item.projectKey}>Ver produto</Link>
   </div>
  </section>

  <section className="deliveryDetailNext" aria-labelledby="delivery-detail-review">
   <h2 id="delivery-detail-review">Revisão e publicação</h2>
   <p>Esta página acompanha o trabalho técnico. Ela não autoriza merge nem afirma que existe Preview válido para esta entrega. Antes de publicar, verifique a prévia vinculada ao SHA, os testes e a aprovação humana correspondente.</p>
   <div className="deliveryDetailActions">
    <Link prefetch={false} href="/deployments">Ver implantações e prévias →</Link>
    <Link prefetch={false} href="/gates">Consultar decisões →</Link>
   </div>
  </section>

  <details className="deliveryDetailTasks">
   <summary>Etapas e evidências técnicas ({item.tasks.length})</summary>
   <div className="deliveryDetailSteps">
    {item.tasks.map(task=><div className="deliveryDetailStep" key={task.id}>
      <div><strong>{task.title}</strong><small>{taskState(task.status)} · {new Date(task.updatedAt).toLocaleString("pt-BR")}</small></div>
      {task.latestRunId?<Link prefetch={false} href={"/runs/"+task.latestRunId}>Ver execução</Link>:<span>Sem execução associada</span>}
    </div>)}
   </div>
  </details>
 </>;
}
