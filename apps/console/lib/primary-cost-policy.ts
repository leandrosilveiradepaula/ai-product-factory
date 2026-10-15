import "server-only";

import {requireConsoleAdmin,requireConsoleOperator} from "./auth-server";
import {getSupabaseServerConfig} from "./supabase-server";
import {readCompleteOperationalRows,parseRecordedCost} from "./operational-health-inventory";

const amount=/^(?:[0-9]+)(?:\.[0-9]{1,4})?$/;
const positive=/^(?:[1-9][0-9]{0,4})(?:\.[0-9]{1,4})?$|^0\.(?:0{0,3}[1-9][0-9]{0,3})$/;

function validAmount(value:unknown):number{
 const text=typeof value==="string"?value:typeof value==="number"?String(value):"";
 if(!amount.test(text))throw new Error("Configuração monetária inválida.");
 const parsed=Number(text);
 if(!Number.isFinite(parsed)||parsed<=0||parsed>100000)throw new Error("Configuração monetária fora do limite.");
 return parsed;
}
export type PrimaryCostPolicyView={
 budgetUsd:number;reserveUsd:number;version:number;updatedAt:string;
 updatedBy:string|null;knownSpendUsd:number|null;unknownPaidCostEvents:number|null;
};
const paidFamilies=new Set(["openai","model","llm","paid_provider"]);

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
  return {...base,knownSpendUsd:spent,unknownPaidCostEvents:unknown};
 }catch{
  // Fail closed in the interface too: never display zero or a green budget
  // based on partial ledger pages or unavailable provider/Control Plane data.
  return {...base,knownSpendUsd:null,unknownPaidCostEvents:null};
 }
}

export type CostPolicyUpdate={
 budgetUsd:string;reserveUsd:string;reason:string;version:number;confirmed:boolean;
};
export async function updatePrimaryCostPolicy(input:CostPolicyUpdate):Promise<void>{
 const operator=await requireConsoleAdmin();
 const cfg=getSupabaseServerConfig();
 if(!cfg)throw new Error("Control Plane indisponível.");
 const valid=(s:string)=>amount.test(s)&&positive.test(s)&&Number.isFinite(Number(s));
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
