import type {
 Project,ProjectDetail,ProjectRecoveryStatus,ProjectStateContext,
 ProjectExecutionControl,ProjectWorkObservation
} from "./control-plane";

export const PRODUCT_PHASES=["Ideia","Plano","Construção","Validação","Publicação","Operação"] as const;
const declaredPositions:Record<string,number>={
 discovery:0,specification:0,planning:1,implementation:2,review:2,
 validation:3,preview:3,human_gate:4,release:4,operations:5
};
type Tone="working"|"blocked"|"waiting"|"decision"|"paused"|"evaluated"|"quiet"|"unknown";
export type ProductExperience={
 tone:Tone;
 label:string;
 headline:string;
 description:string;
 nextTitle:string;
 nextDetail:string;
 userAction:string;
 proof:string;
 execution:string;
 objective:string;
 declaredStage:number|null;
 declaredStageLabel:string;
 repairNote:string|null;
};
export function summarizeProductExperience(data:{
 project:Project;
 detail:ProjectDetail|null;
 context:ProjectStateContext;
 recovery:ProjectRecoveryStatus;
 control:ProjectExecutionControl;
 work:ProjectWorkObservation;
 actionableGates:number;
}):ProductExperience{
 const {project,detail,context,recovery,control,work,actionableGates}=data;
 const declaredStage=Object.hasOwn(declaredPositions,project.stage)?declaredPositions[project.stage]:null;
 const declaredStageLabel=declaredStage===null?"Sem etapa registrada":PRODUCT_PHASES[declaredStage];
 const objective=typeof context.objective==="string"&&context.objective.trim()
  ?context.objective.trim().slice(0,280):"Objetivo não disponível nesta consulta.";
 const evaluated=detail?.productReadiness.ready===true;
 const assessed=detail?.productReadiness.assessedCommit;
 const assessedProof=evaluated?"Prontidão avaliada para o commit "+(assessed?assessed.slice(0,8):"registrado")+
  "; mudanças posteriores não são certificadas.":"Prontidão do produto ainda não comprovada.";
 const releaseProof=detail?.releaseEvidence?.kind==="released"?
  "Release registrado no Control Plane (commit "+detail.releaseEvidence.candidateCommit?.slice(0,8)+
  "); publicação atual e funcionamento não são comprovados por esse registro.":
  detail?.releaseEvidence?.kind==="unavailable"?"Histórico de release não verificável nesta consulta.":null;
 const proof=[releaseProof,assessedProof].filter(Boolean).join(" ");
 const latestFailure=detail?.latestRun?.failureKind??null;
 const execution=work.kind==="running"?"Execução iniciada com lease válido":
  work.kind==="unavailable"?"Execução não verificável nesta consulta":
  work.kind==="recorded"?"Pedido registrado, sem execução ativa comprovada":
  "Nenhuma execução ativa com lease comprovada";
 const repairBlocked=recovery?recovery.status==="blocked":context.snapshot?.sourceStatus?.repair_status==="blocked";
 const repairNote=recovery?.status==="blocked"&&recovery.maxCycles>0?
  "Reparo bloqueado: ciclo "+recovery.cycle+" de "+recovery.maxCycles:null;
 const base={proof,execution,objective,declaredStage,declaredStageLabel,repairNote};
 const output=(tone:Tone,label:string,headline:string,description:string,nextTitle:string,nextDetail:string,userAction:string):ProductExperience=>
  ({...base,tone,label,headline,description,nextTitle,nextDetail,userAction});
 if(!detail)return output("unknown","Dados indisponíveis","Situação do produto não verificada",
  "A origem do projeto não foi encontrada nesta consulta. A Factory precisa reconciliar os dados.",
  "Validar o registro do produto","Nenhuma conclusão ou execução pode ser presumida.","Nenhuma decisão solicitada");
 if(control.state==="unavailable")return output("unknown","Controle indisponível",
  "Estado de execução não verificado","O estado do projeto não pôde ser confirmado pelo Control Plane.",
  "Verificar o controle do projeto","Não é seguro supor que uma execução ou retomada tenha ocorrido.",
  "Nenhuma aprovação solicitada");
 if(actionableGates>0)return output("decision","Sua decisão é necessária","Uma aprovação humana real está pendente",
  "Existe uma decisão registrada para este produto, separada dos problemas técnicos.",
  "Aguardar decisão vinculada às evidências","A revisão deve indicar o impacto e a versão exata.","Revisar na área Decisões");
 if(!detail.active||["draft","paused","pausing","stopped","stopping"].includes(control.state))return output("paused",
  "Não está em execução","Produto parado ou ainda não iniciado",
  "O controle do projeto não permite novos trabalhos. Seu histórico continua preservado.",
  "Retomada depende do controle do projeto","Iniciar ou retomar não significa liberar produção.","Retomar somente quando for sua intenção");
 if(recovery?.status==="recovery_queued"||recovery?.status==="recovery_claimed")
  return output("waiting","Retomada solicitada","Aguardando execução",
   "O pedido foi registrado; nenhum worker ativo foi comprovado.",
   "Assumir a continuação pendente","A Factory deve assumir o trabalho e registrar o resultado.","Nenhuma ação agora");
 if(recovery?.status==="recovery_recovering"&&work.kind!=="running")
  return output("waiting","Retomada sem lease comprovado","Retomada em verificação",
   "Há um registro de execução, mas o lease não foi verificado.",
   "Verificar o worker","Não anunciar execução ativa sem prova.","Nenhuma ação agora");
 if(recovery?.status==="recovery_completed"&&work.kind!=="running")
  return output("quiet","Etapa recuperada","A recuperação terminou",
   "O trabalho de recuperação foi concluído, mas o produto não foi certificado.",
   "Verificar a próxima entrega","Não confundir recuperação com release.","Nenhuma ação agora");
 if(work.kind==="running")return output("working","Execução comprovada","A Factory está executando trabalho",
  "Existe um run iniciado e com lease vigente."+(repairBlocked?" Também há histórico de reparo bloqueado.":""),
  "Concluir a execução e verificar os resultados",
  "Build, testes e Preview continuam exigindo evidências independentes.","Nenhuma ação agora");
 if(latestFailure==="no_actionable_work")
  return output("blocked","Retomada sem trabalho válido","A última retomada falhou sem tarefas acionáveis",
   "Não há execução ativa comprovada. Repetir o mesmo pedido não cria trabalho novo.",
   "Reconciliar o trabalho e o release registrados",
   "A Factory deve conferir a revisão técnica posterior e identificar trabalho genuinamente novo antes de outra tentativa.",
   "Nenhuma nova aprovação solicitada");
 if(recovery?.status==="recovery_blocked")
  return output("blocked","Recuperação bloqueada","A última recuperação não concluiu o trabalho",
   "A continuação ficou bloqueada. O histórico e o release anterior não devem ser reabertos por tentativa cega.",
   "Verificar a falha e o escopo da recuperação",
   "A Factory precisa preparar uma correção com evidência nova; não basta pressionar Reiniciar.",
   "Nenhuma aprovação solicitada");
 if(repairBlocked)return output("blocked","Reparo técnico bloqueado","Há um reparo técnico registrado como bloqueado",
  (repairNote?repairNote+". ":"")+"Não há prova de recuperação em andamento. O bloqueio não é uma aprovação humana.",
  "Resolver a causa e preparar retomada segura",
  "Trabalho técnico da Factory; a existência de uma falha não dispara automaticamente o reparo.","Nenhuma aprovação solicitada");
 if(work.kind==="recorded"||detail.pendingRun)return output("waiting","Pedido registrado","A execução ainda não começou",
  "Há uma solicitação registrada, mas nenhum worker com lease vigente foi observado.",
  "Assumir a execução pendente","A Factory deve assumir o trabalho e registrar o resultado.","Nenhuma ação agora");
 if(work.kind==="unavailable"||recovery?.status==="unavailable")return output("unknown",
  "Verificação indisponível","Não foi possível confirmar a situação",
  "Uma das fontes de execução ou recuperação falhou. Não é seguro tratar ausência de resposta como sucesso.",
  "Restabelecer a verificação de evidências","Nenhum avanço nem certificação deve ser presumido.","Nenhuma aprovação solicitada");
 if(evaluated)return output("evaluated","Avaliação registrada","Existe prontidão avaliada em uma versão",
  "A avaliação está vinculada ao commit registrado; isso não garante a versão atualmente publicada.",
  "Verificar uso e entrega na versão atual","A Factory precisa confirmar ambiente e versão antes de anunciar produto disponível.",
  "Nenhuma decisão agora");
 return output("quiet","Aguardando trabalho comprovado","O produto ainda não tem entrega comprovada",
  "Não existe execução ativa comprovada. A posição administrativa não certifica funcionamento.",
  "Definir e executar a próxima entrega verificável","O próximo run precisa deixar um recibo confiável de trabalho.",
  "Nenhuma aprovação solicitada");
}
