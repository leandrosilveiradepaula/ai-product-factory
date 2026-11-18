/** Owner-facing financial gate. Never infer it from the control.state.
 * Only a blocker audit tied to the CURRENT pending run can identify the cause.
 * Always reconcile with the live paid-cost policy; stale audits do not persist
 * as a current shortage when the policy has already changed.
 */
import type {ProjectDetail} from "./control-plane";
import type {PrimaryCostPolicyView} from "./primary-cost-policy";

export type OwnerFinancialBlocker={
 kind:"exhausted"|"unverified";
 title:string;
 description:string;
 detail:string;
 actionLabel:string;
 href:string;
};

const money=(n:number)=>new Intl.NumberFormat("pt-BR",{
 style:"currency",currency:"USD",minimumFractionDigits:2,maximumFractionDigits:2,
}).format(n);

export function ownerFinancialBlocker(
 detail:Pick<ProjectDetail,"pendingRun"|"wakeEvidence">|null,
 policy:PrimaryCostPolicyView|null
):OwnerFinancialBlocker|null{
 const pending=detail?.pendingRun;
 if(!pending||!["created","queued"].includes(pending.status)||
    detail?.wakeEvidence?.blockerCode!=="budget_exhausted"||
    typeof detail.wakeEvidence.blockedAt!=="string"||
    !Number.isFinite(Date.parse(detail.wakeEvidence.blockedAt))||
    !Number.isFinite(Date.parse(pending.createdAt))||
    Date.parse(detail.wakeEvidence.blockedAt)<Date.parse(pending.createdAt))return null;

 const common={href:"/configuration",actionLabel:"Revisar orçamento"};
 if(policy===null||policy.knownSpendUsd===null||
    policy.unknownPaidCostEvents===null||
    policy.unknownPaidCostEvents>0){
   return{...common,kind:"unverified",
     title:"Execução bloqueada — verificar orçamento",
     description:"O worker recusou a execução por limite financeiro, mas o saldo atual não pôde ser confirmado.",
     detail:"O pedido continua na fila. Confira a política e o consumo antes de autorizar novos custos."};
 }
 const {budgetUsd,reserveUsd,knownSpendUsd}=policy;
 if(![budgetUsd,reserveUsd,knownSpendUsd].every(
    n=>typeof n==="number"&&Number.isFinite(n)&&n>=0))return{
    ...common,kind:"unverified",title:"Orçamento não verificável",
    description:"A última tentativa foi impedida por limite financeiro.",
    detail:"Os valores atuais não foram validados. Não libere uso pago."};
 if(knownSpendUsd+reserveUsd<=budgetUsd+0.0000001)return null;
 const available=Math.max(0,budgetUsd-knownSpendUsd);
 return{...common,kind:"exhausted",title:"Parado por limite financeiro",
   description:"O orçamento interno não cobre a reserva necessária para continuar.",
   detail:"Teto "+money(budgetUsd)+" · consumido "+money(knownSpendUsd)+
     " · disponível "+money(available)+" · reserva exigida "+money(reserveUsd)+
     ". A tarefa já está na fila. Não é necessário reiniciar novamente."};
}
