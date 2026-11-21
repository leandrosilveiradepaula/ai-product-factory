/** Pure, read-only presentation rules for the Factory operator experience.
 * Never authorizes a gate, starts a worker or claims product readiness. */
export type OperatorAttention={
 kind:"gate"|"access"|"clear";
 count:number;
 humanGateCount:number;
 accessCount:number;
 title:string;
 description:string;
 label:string;
};
type HumanGate={status:string;actionable:boolean;projectName:string|null};
type InstallAction={projectName:string;projectKey:string};

export function summarizeOperatorAttention(
 gates:readonly HumanGate[],
 installations:readonly InstallAction[],
 githubAppConfigured:boolean,
):OperatorAttention{
 const pending=gates.filter(g=>g.status==="pending"&&g.actionable);
 const access=githubAppConfigured?installations:[];
 const count=pending.length+access.length;
 if(pending.length){
  return{kind:"gate",count,humanGateCount:pending.length,accessCount:access.length,
   title:pending.length===1?"Uma decisão precisa de você":pending.length+" decisões precisam de você",
   description:(pending[0].projectName?"Projeto: "+pending[0].projectName+". ":"")+
    "Revise o motivo e as evidências antes de aprovar ou rejeitar. A Factory nunca publica sem o gate humano correspondente.",
   label:"Revisar decisão"};
 }
 if(access.length){
  return{kind:"access",count,humanGateCount:0,accessCount:access.length,
   title:access.length===1?"Um projeto precisa de acesso ao GitHub":access.length+" projetos precisam de acesso ao GitHub",
   description:"Projeto: "+access[0].projectName+". É uma pendência de integração, não uma aprovação de publicação. Avalie a necessidade antes de conceder acesso.",
   label:"Entender pendência"};
 }
 return{kind:"clear",count:0,humanGateCount:0,accessCount:0,
  title:"Nenhuma decisão sua está pendente",
  description:"Você pode criar, melhorar ou acompanhar produtos. Isso não significa que todas as execuções ou serviços estejam saudáveis.",
  label:""};
}

export function operatorStageLabel(stage:string):string{
 switch(stage){
  case "discovery":case "specification":return "Entendendo o pedido";
  case "planning":return "Planejando";
  case "implementation":case "review":return "Construção e revisão";
  case "validation":case "preview":return "Testes e prévia";
  case "human_gate":case "release":return "Revisão e publicação";
  case "operations":return "Operação";
  default:return "Etapa não classificada";
 }
}
