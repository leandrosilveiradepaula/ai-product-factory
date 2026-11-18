import type {ProductSituation,ProductState} from "./product-status";

/* A product journey is a guide to the next phase, not a certification of
 * completed phases. Always derive it from Control Plane lifecycle_stage and
 * observed execution state; never infer from task counts or percentages. */
export const PRODUCT_PHASES=[
 {key:"understand",label:"Entender",goal:"Reunir o pedido, as necessidades e a especificação.",exit:"Requisitos e escopo registrados para planejar."},
 {key:"plan",label:"Planejar",goal:"Organizar o plano, as entregas e as dependências.",exit:"Plano e tarefas definidos para iniciar o desenvolvimento."},
 {key:"build",label:"Construir",goal:"Implementar a solução e revisar as mudanças.",exit:"Código implementado e revisado para iniciar os testes."},
 {key:"validate",label:"Testar",goal:"Executar testes, avaliações e verificar a prévia quando exigida.",exit:"Evidências de qualidade e prévia verificadas, quando aplicáveis."},
 {key:"release",label:"Publicar",goal:"Solicitar a decisão humana e acompanhar a publicação autorizada.",exit:"Aprovação humana, merge e publicação comprovados."},
 {key:"operate",label:"Operar",goal:"Acompanhar o produto e receber pedidos de evolução.",exit:"Uma nova solicitação pode abrir outro ciclo de desenvolvimento."},
] as const;
export type ProductPhaseKey=typeof PRODUCT_PHASES[number]["key"];
const STAGE_TO_PHASE:Record<string,ProductPhaseKey>={
 discovery:"understand",specification:"understand",
 planning:"plan",
 implementation:"build",review:"build",
 validation:"validate",preview:"validate",
 human_gate:"release",release:"release",
 operations:"operate",
};
const STAGE_SUBTITLE:Record<string,string>={
 discovery:"Descoberta",specification:"Especificação",
 planning:"Plano técnico",
 implementation:"Implementação",review:"Revisão",
 validation:"Testes",preview:"Prévia",
 human_gate:"Aprovação humana",release:"Liberação",
 operations:"Acompanhamento",
};
type PathMark="anterior"|"atual"|"proxima"|"futura"|"desconhecida";
export type JourneyPhaseView={key:ProductPhaseKey;label:string;position:number;mark:PathMark};
export type JourneyAction={
 owner:"Você"|"Factory"|"Equipe técnica"|"Nenhuma ação necessária";
 title:string;description:string;label:string;href:string;humanRequired:boolean;
};
export type ProductJourney={
 phaseIndex:number;phaseLabel:string;substage:string;phasePurpose:string;
 nextPhaseLabel:string;conditionToAdvance:string;action:JourneyAction;
 phaseSteps:JourneyPhaseView[];phaseKnown:boolean;
};
const path=(p:ProductSituation)=>"/projects/"+encodeURIComponent(p.key);
function action(owner:JourneyAction["owner"],title:string,description:string,label:string,href:string,humanRequired=false):JourneyAction{
 return{owner,title,description,label,href,humanRequired};
}
export function describeNextAction(item:ProductSituation,phaseIndex:number):JourneyAction{
 const detail=path(item);
 // Only an actionable human gate produces a mandatory user action.
 if(item.state==="decision")
  return action("Você","Há uma decisão aguardando você","A Factory só pode seguir após sua decisão registrada. Confira o que será liberado e as evidências antes de aprovar.","Revisar decisão","/gates",true);
 if(item.state==="stopped"||item.state==="paused")
  return action("Nenhuma ação necessária",item.state==="stopped"?"Projeto parado":"Projeto pausado","O caminho está preservado, mas a Factory não pode avançar enquanto o controle impedir novas execuções. Retomar é opcional, não uma pendência obrigatória.","Ver situação e controle",detail+"#project-control");
 if(item.state==="unknown"||phaseIndex<0)
  return action("Equipe técnica","É preciso confirmar o estado do produto","O sistema não conseguiu comprovar a fase ou o controle. Nenhuma próxima fase será apresentada como iniciada.","Consultar situação",detail);
 if(item.state==="investigate")
  return action("Equipe técnica","Resolver a tentativa interrompida","Há trabalho sem conclusão comprovada e uma falha ou bloqueio registrado. Nenhuma aprovação sua foi solicitada; primeiro é preciso investigar e corrigir.","Ver o bloqueio",item.nextHref);
 if(item.state==="executing")
  return action("Factory","A Factory está trabalhando","Existe uma execução iniciada com lease vigente. A próxima fase depende de concluir e verificar o trabalho desta etapa.","Acompanhar trabalho",item.nextHref);
 if(item.state==="verifying")
  return action("Factory","Verificar o resultado","A fase tem validação registrada, mas ainda é necessário confirmar os testes e as evidências aplicáveis.","Ver validação",item.nextHref);
 if(item.state==="queued")
  return action("Factory","Aguardar a execução do pedido","O trabalho foi enfileirado; ainda não há prova de que um worker tenha começado.","Ver trabalho na fila",item.nextHref);
 if(item.unclosedTasks>0)
  return action("Equipe técnica","Retomar o trabalho pendente","Há tarefas registradas sem conclusão, mas nenhum worker em execução comprovada. É necessário investigar ou retomar o processamento; não há decisão sua registrada.","Ver tarefas pendentes","/deliveries?project="+encodeURIComponent(item.key));
 if(phaseIndex===4)
  return action("Equipe técnica","Conferir a publicação antes de avançar","A fase de liberação está registrada, mas não há decisão humana acionável nem execução ativa confirmada. É necessário reconciliar as evidências antes de qualquer release.","Ver implantações","/deployments");
 if(phaseIndex===PRODUCT_PHASES.length-1)
  return action("Nenhuma ação necessária","Produto na fase de operação","A etapa registrada é Operação, sem trabalho ativo comprovado. Se você quiser uma melhoria, abra um novo pedido; publicação anterior não foi certificada por esta tela.","Solicitar melhoria",detail+"/request");
 if(!item.lastRequest)
  return action("Você","Descrever o que quer construir","O projeto está habilitado, mas não há pedido recente registrado neste canal nem execução ativa. Envie a demanda para a Factory poder organizar o próximo trabalho.","Descrever pedido",detail+"/request");
 return action("Equipe técnica","Confirmar a continuidade da fase","O pedido está registrado, mas nenhum trabalho ativo foi comprovado. É necessário reconciliar as tarefas antes de declarar que o projeto avançou.","Ver pedidos e execução",detail+"#latest-request");
}
export function describeProductJourney(item:ProductSituation):ProductJourney{
 const phaseKey=STAGE_TO_PHASE[item.stage];
 const phaseIndex=phaseKey?PRODUCT_PHASES.findIndex(p=>p.key===phaseKey):-1;
 const phase=phaseIndex>=0?PRODUCT_PHASES[phaseIndex]:null;
 const next=phaseIndex>=0&&phaseIndex<PRODUCT_PHASES.length-1?PRODUCT_PHASES[phaseIndex+1]:null;
 const phaseSteps:JourneyPhaseView[]=PRODUCT_PHASES.map((p,i):JourneyPhaseView=>({
  key:p.key,label:p.label,position:i+1,
  mark:phaseIndex<0?"desconhecida":i<phaseIndex?"anterior":i===phaseIndex?"atual":i===phaseIndex+1?"proxima":"futura",
 }));
 return{
  phaseIndex,phaseKnown:phaseIndex>=0,
  phaseLabel:phase?.label||"Não identificada",
  substage:STAGE_SUBTITLE[item.stage]||"Sem informação",
  phasePurpose:phase?.goal||"A Factory não conseguiu identificar com segurança a fase registrada.",
  nextPhaseLabel:next?.label||(phaseIndex===PRODUCT_PHASES.length-1?"Novo ciclo, quando solicitado":"A confirmar"),
  conditionToAdvance:phase?.exit||"O estado da jornada precisa ser verificado pelo operador técnico.",
  phaseSteps,action:describeNextAction(item,phaseIndex),
 };
}
