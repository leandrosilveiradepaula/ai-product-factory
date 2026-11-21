import type {ProductSituation} from "./product-status";

/** Read-only owner summary. It NEVER invents a recovery, release, worker or gate.
 * Technical error remediation is not a human approval.
 */
export type OwnerProductSummary={
 tone:"blocked"|"doing"|"human"|"quiet"|"paused"|"delivered";
 headline:string;reason:string;
 delivery:string;activity:string;
 nextTitle:string;nextDetail:string;
 yourAction:string;yourDetail:string;
 actionHref:string|null;actionLabel:string|null;
};
export function summarizeOwnerProduct(item:ProductSituation):OwnerProductSummary{
 const base="/projects/"+encodeURIComponent(item.key);
 const hasProof=item.proof?.productReady===true;
 const delivery=hasProof?"Uso funcional avaliado para a versão registrada":
   item.proof?.hasHumanMerge?"Código integrado; uso funcional ainda não comprovado":
   "Ainda sem entrega funcional comprovada";
 const activity=item.confirmedRunning>0&&item.state==="executing"?
   "Execução iniciada e lease vigente":
   item.state==="queued"?"Na fila; execução ainda não iniciada":
   item.state==="verifying"?"Em verificação; sem worker ativo comprovado":
   "Nenhuma execução ativa comprovada";
 const noUser="Nenhuma decisão sua pendente neste produto.";
 const output=(tone:OwnerProductSummary["tone"],headline:string,reason:string,
  nextTitle:string,nextDetail:string,yourAction:string,yourDetail:string,
  actionHref:string|null=null,actionLabel:string|null=null):OwnerProductSummary=>
  ({tone,headline,reason,delivery,activity,nextTitle,nextDetail,yourAction,yourDetail,actionHref,actionLabel});
 if(item.state==="decision")return output("human","A Factory precisa da sua decisão",
  "Um gate acionável foi registrado para este produto. O trabalho sujeito a esse gate não pode prosseguir sem sua escolha.",
  "Aguardar a decisão registrada","Confira motivo, impacto e evidências antes de aprovar.",
  "Revisar decisão","É uma intervenção real: não se trata de falha técnica.", "/gates","Abrir decisão");
 if(item.state==="stopped"||item.state==="paused"||item.controlState==="draft")
  return output("paused",item.controlState==="draft"?"Produto ainda não iniciado":"Execução do produto desabilitada",
   "O controle do projeto não permite novos trabalhos. O histórico não é apagado.",
   item.controlState==="draft"?"Iniciar desenvolvimento quando desejar":"Retomar o projeto quando desejar",
   "Um comando de início ou retomada não prova que o worker já executou.",
   "Início ou retomada opcional","Só você decide reativar o controle; isto não aprova produção.",
   base+"#project-control",item.controlState==="draft"?"Ver opção de iniciar":"Ver controle");
 if(item.state==="investigate"){
  const blocker=item.blocker;
  const repair=item.latestRepair;
  const repairBlocked=repair?.status==="blocked"&&
   (!item.lastRun||Date.parse(repair.updatedAt)>=Date.parse(item.lastRun.at));
  const reason=blocker?.why||"A última tentativa foi interrompida; a tarefa permanece sem conclusão.";
  const repairNote=repairBlocked?
   " A tentativa de reparo "+repair.cycle+" de "+repair.maxCycles+" também está bloqueada. Nenhuma retomada foi confirmada.":"";
  return output("blocked","O trabalho parou em uma falha técnica",reason+repairNote,
   blocker?.code==="source_context"?"Verificar o contexto do repositório e retomar o reparo":
   blocker?.code==="database_migration"?"Revisar a migration e revalidar a correção":
   blocker?.code==="provider_budget"?"Verificar disponibilidade e orçamento do provedor":
   "Investigar a falha e preparar uma retomada segura",
   (blocker?.resolution||"Resolver a causa antes de tentar executar novamente.")+
   " Este é trabalho necessário, não uma execução agendada.",
   "Nenhuma aprovação solicitada",noUser);
 }
 if(item.state==="executing")return output("doing","A Factory está trabalhando",
  item.currentWork?"Atividade: "+item.currentWork:"Há execução iniciada com lease válido.",
  "Concluir e verificar o trabalho atual",
  "Uma conclusão técnica ainda precisará das evidências de entrega aplicáveis.",
  "Nenhuma ação agora",noUser);
 if(item.state==="queued")return output("quiet","Há trabalho na fila",
  "O pedido foi registrado, mas nenhum worker ativo foi comprovado.",
  "Iniciar processamento da tarefa","A Factory precisa assumir a execução antes de relatar avanço.",
  "Nenhuma ação agora",noUser);
 if(item.state==="verifying")return output("doing","A entrega está em verificação",
  "Existe trabalho em validação; não há confirmação automática de publicação.",
  "Comprovar testes e ambiente","A Factory deve registrar o resultado e os critérios de saída.",
  "Nenhuma ação agora",noUser);
 if(item.state==="unknown")return output("quiet","Execução ainda não verificada",
  "O Control Plane não demonstrou que este projeto está apto a executar novas tarefas.",
  "Reconciliar o controle e a origem","Não é seguro supor avanço nem solicitar um merge.",
  "Nenhuma aprovação solicitada",noUser);
 if(hasProof)return output("delivered","Entrega avaliada na versão registrada",
  "Há evidência de prontidão vinculada ao commit de avaliação. Mudanças posteriores exigem nova verificação.",
  "Operar e acompanhar qualidade","Não há execução ativa comprovada nesta consulta.",
  "Nenhuma decisão agora",noUser);
 if(item.unclosedTasks>0)return output("quiet","Há tarefas abertas, mas ninguém está executando",
  "Há registros de trabalho inacabado e nenhuma execução com lease vigente.",
  "Reconciliar e retomar o trabalho pendente",
  "A Factory deve confirmar a possibilidade de retomada sem repetir uma tarefa terminal.",
  "Nenhuma aprovação solicitada",noUser);
 if(item.projectKind==="greenfield"&&item.databaseEvidence?.state!=="verified")
  return output("quiet","O produto ainda não pode ser considerado entregue",
   "A entrega funcional não foi comprovada e o banco da aplicação não foi verificado no inventário.",
   "Comprovar o ambiente e o fluxo principal",
   "Verificar banco existente, autenticação, fluxo completo e Preview; nenhuma execução foi iniciada nesta consulta.",
   "Nenhuma decisão agora",noUser);
 return output("quiet","O uso do produto ainda não foi comprovado",
  "Nenhuma execução está ativa. O código ou o cadastro por si só não comprovam produto pronto.",
  "Revisar requisitos e evidências funcionais",
  "A Factory precisa registrar o próximo trabalho verificável; ainda não há execução ativa.",
  "Nenhuma decisão agora",noUser);
}
