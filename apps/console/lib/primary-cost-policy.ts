import "server-only";

import {requireConsoleAdmin,requireConsoleOperator} from "./auth-server";
import {getSupabaseServerConfig} from "./supabase-server";
import {readCompleteOperationalRows,parseRecordedCost} from "./operational-health-inventory";

const amount=/^(?:[0-9]+)(?:\.[0-9]{1,4})?$/;

function validAmount(value:unknown):number{
 const text=typeof value==="string"?value:typeof value==="number"?String(value):"";
 if(!amount.test(text))throw new Error("Configuração monetária inválida.");
 const parsed=Number(text);
 if(!Number.isFinite(parsed)||parsed<=0||parsed>100000)throw new Error("Configuração monetária fora do limite.");
 return parsed;
}
export type FinancialPolicyAuditEntry={
  createdAt:string;actorRef:string;reason:string;version:number;
  previousBudgetUsd:number;newBudgetUsd:number;
  previousReserveUsd:number;newReserveUsd:number;
};
export type PrimaryCostPolicyView={
 budgetUsd:number;reserveUsd:number;version:number;updatedAt:string;
 updatedBy:string|null;knownSpendUsd:number|null;unknownPaidCostEvents:number|null;
 history:FinancialPolicyAuditEntry[]|null;
};
const paidFamilies=new Set(["openai","model","llm","paid_provider"]);

/** Display the 20 newest auditable changes; never present an unavailable
 * audit trail as an empty history. No public user or credential exposure. */
async function getPrimaryCostPolicyHistory(
 cfg:NonNullable<ReturnType<typeof getSupabaseServerConfig>>
):Promise<FinancialPolicyAuditEntry[]>{
 const response=await fetch(cfg.url+"/rest/v1/factory_audit_events"
  +"?select=created_at,actor_ref,payload"
  +"&event_type=eq.factory.cost_policy.updated"
  +"&order=created_at.desc&limit=20",{headers:cfg.headers,cache:"no-store"});
 if(!response.ok)throw new Error("Histórico de auditoria indisponível.");
 const payload:unknown=await response.json();
 if(!Array.isArray(payload)||payload.length>20)
  throw new Error("Histórico financeiro inválido.");
 return payload.map((item:unknown)=>{
  if(!item||typeof item!=="object"||Array.isArray(item))
   throw new Error("Evento financeiro inválido.");
  const row=item as Record<string,unknown>;
  const event=row.payload;
  if(!event||typeof event!=="object"||Array.isArray(event))
   throw new Error("Payload de auditoria financeira inválido.");
  const data=event as Record<string,unknown>;
  const version=data.new_version;
  if(typeof row.actor_ref!=="string"||!row.actor_ref||
     typeof row.created_at!=="string"||
     !Number.isFinite(Date.parse(row.created_at))||
     !Number.isSafeInteger(version)||Number(version)<2||
     typeof data.reason!=="string"||data.reason.length<12)
   throw new Error("Proveniência do histórico financeiro inválida.");
  return {
   actorRef:row.actor_ref,createdAt:row.created_at,reason:data.reason,
   version:Number(version),
   previousBudgetUsd:validAmount(data.previous_budget_usd),
   newBudgetUsd:validAmount(data.new_budget_usd),
   previousReserveUsd:validAmount(data.previous_reserve_usd),
   newReserveUsd:validAmount(data.new_reserve_usd),
  };
 });
}

export async function getPrimaryCostPolicyView():Promise<PrimaryCostPolicyView|null>{
 await requireConsoleOperator();
 const cfg=getSupabaseServerConfig();
 if(!cfg)return null;
 const response=await fetch(cfg.url+"/rest/v1/factory_primary_cost_policy"
  +"?select=policy_key,budget_usd,reserve_usd,version,updated_at,updated_by"
  +"&policy_key=eq.primary&limit=2",{headers:cfg.headers,cache:"no-store"});
 // Before the approved migration is applied, render unavailable rather than
 // manufacturing a budget or crashing the full Console.
 if(!response.ok)return null;
 const rows:unknown=await response.json();
 if(!Array.isArray(rows)||rows.length!==1||rows[0]===null||typeof rows[0]!=="object")
  throw new Error("Política financeira ausente ou duplicada.");
 const row=rows[0] as Record<string,unknown>;
 const budget=validAmount(row.budget_usd),reserve=validAmount(row.reserve_usd);
 const version=row.version;
 if(row.policy_key!=="primary"||reserve>budget||typeof version!=="number"
   ||!Number.isSafeInteger(version)||version<1||typeof row.updated_at!=="string")
  throw new Error("Política financeira inconsistente.");
 const base={budgetUsd:budget,reserveUsd:reserve,version,
  updatedAt:row.updated_at,updatedBy:row.updated_by==null?null:String(row.updated_by)};
 let history:FinancialPolicyAuditEntry[]|null=null;
 try{history=await getPrimaryCostPolicyHistory(cfg);}catch{history=null;}
 try{
  const usage=await readCompleteOperationalRows({
   url:cfg.url,headers:cfg.headers,table:"factory_tool_usage",
   select:"id,tool_family,estimated_cost,created_at",idKind:"bigint",
  });
  let spent=0,unknown=0;
  for(const row of usage){
   const family=String(row.tool_family||"").toLowerCase();
   if(!family)throw new Error("Ledger sem família de custo.");
   const cost=parseRecordedCost(row.estimated_cost);
   if(cost===null){if(paidFamilies.has(family))unknown++;}
   else spent+=cost;
  }
  if(!Number.isFinite(spent))throw new Error("Ledger inválido.");
  return {...base,knownSpendUsd:spent,unknownPaidCostEvents:unknown,history};
 }catch{
  // Fail closed in the interface too: never display zero or a green budget
  // based on partial ledger pages or unavailable provider/Control Plane data.
  return {...base,knownSpendUsd:null,unknownPaidCostEvents:null,history};
 }
}

export type CostPolicyUpdate={
 budgetUsd:string;reserveUsd:string;reason:string;version:number;confirmed:boolean;
};
export async function updatePrimaryCostPolicy(input:CostPolicyUpdate):Promise<void>{
 const operator=await requireConsoleAdmin();
 const cfg=getSupabaseServerConfig();
 if(!cfg)throw new Error("Control Plane indisponível.");
 // Same numeric bounds and four-decimal precision as the database
 // (including its 100000.0000 maximum); SQL independently revalidates.
 const valid=(s:string)=>amount.test(s)&&Number.isFinite(Number(s))
  &&Number(s)>=0.0001&&Number(s)<=100000;
 if(!valid(input.budgetUsd)||!valid(input.reserveUsd)||
    Number(input.budgetUsd)>100000||
    Number(input.reserveUsd)>Number(input.budgetUsd)||
    !Number.isSafeInteger(input.version)||input.version<1||
    input.reason.trim().length<12||input.reason.trim().length>300||
    !input.confirmed)throw new Error("Alteração de orçamento inválida.");
 const response=await fetch(cfg.url+"/rest/v1/rpc/factory_update_primary_cost_policy",{
  method:"POST",headers:{...cfg.headers,"Content-Type":"application/json"},
  body:JSON.stringify({
   p_actor_user_id:operator.userId,
   p_expected_version:input.version,
   p_budget_usd:input.budgetUsd,
   p_reserve_usd:input.reserveUsd,
   p_reason:input.reason.trim(),
   p_confirm_paid_limit:true,
  }),cache:"no-store",
 });
 if(!response.ok){
  if(response.status===409)throw new Error("A política foi alterada por outro administrador. Atualize a tela.");
  throw new Error("Não foi possível registrar o orçamento e sua auditoria.");
 }
}
