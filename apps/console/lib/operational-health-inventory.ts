/** Fail-closed REST reader for the Console. Read-only; never dispatches work. */
export type OperationalRow=Record<string,unknown>&{id:unknown;created_at:unknown};
export type OperationalIdKind="uuid"|"bigint";
const PAGE_SIZE=200;
const MAX_PAGES=20;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const BIGINT=/^[1-9][0-9]*$/;
const TZ=/(?:Z|[+-][0-9]{2}:[0-9]{2})$/i;

function verifiedId(value:unknown,kind:OperationalIdKind):string{
 if(kind==="uuid"){
  if(typeof value!=="string"||!UUID.test(value))throw new Error("Inventário operacional contém UUID inválido.");
  return value.toLowerCase();
 }
 if(typeof value==="number"){
  if(!Number.isSafeInteger(value)||value<=0)throw new Error("ID BIGINT de custo não representável.");
  return String(value);
 }
 if(typeof value!=="string"||!BIGINT.test(value))throw new Error("ID BIGINT de custo inválido.");
 return value;
}
function verifiedTime(value:unknown):number{
 if(typeof value!=="string"||!TZ.test(value))throw new Error("Inventário operacional sem timezone verificável.");
 const time=Date.parse(value);
 if(!Number.isFinite(time))throw new Error("Inventário operacional com horário inválido.");
 return time;
}
function greater(a:string,b:string,kind:OperationalIdKind):boolean{
 return kind==="bigint"?BigInt(a)>BigInt(b):a>b;
}
export async function readCompleteOperationalRows(args:{
 url:string;headers:Record<string,string>;table:"factory_runs"|"factory_tool_usage";
 select:string;idKind:OperationalIdKind;transport?:typeof fetch;
}):Promise<OperationalRow[]>{
 const fetcher=args.transport||fetch;
 const result:OperationalRow[]=[];
 const seen=new Set<string>();
 let prevTime:number|null=null,prevId:string|null=null;
 for(let page=0;page<MAX_PAGES;page++){
  const endpoint=args.url.replace(/\/$/,"")+"/rest/v1/"+args.table+
   "?select="+args.select+"&order=created_at.desc,id.desc&limit="+PAGE_SIZE+"&offset="+page*PAGE_SIZE;
  const response=await fetcher(endpoint,{headers:args.headers,cache:"no-store"});
  if(!response.ok)throw new Error("Inventário operacional indisponível ("+args.table+" HTTP "+response.status+").");
  const parsed:unknown=await response.json();
  if(!Array.isArray(parsed)||parsed.length>PAGE_SIZE||!parsed.every(x=>x!==null&&typeof x==="object"&&!Array.isArray(x)))
   throw new Error("Inventário operacional retornou página inválida ("+args.table+").");
  const rows=parsed as OperationalRow[];
  for(const row of rows){
   const id=verifiedId(row.id,args.idKind),at=verifiedTime(row.created_at);
   if(seen.has(id))throw new Error("Inventário operacional repetiu ID ("+args.table+").");
   if(prevTime!==null&&(at>prevTime||(at===prevTime&&prevId!==null&&greater(id,prevId,args.idKind))))
    throw new Error("Inventário operacional perdeu ordenação ("+args.table+").");
   seen.add(id);prevTime=at;prevId=id;result.push(row);
  }
  if(rows.length<PAGE_SIZE)return result;
 }
 // A full last page cannot prove exhaustion. Never show truncated healthy counts.
 throw new Error("Inventário operacional excede limite verificado de 4.000 ("+args.table+").");
}
export function parseRecordedCost(value:unknown):number|null{
 if(value===null)return null;
 if(typeof value!=="number"&&typeof value!=="string")throw new Error("Custo operacional inválido.");
 if(typeof value==="string"&&!/^(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$/.test(value))
  throw new Error("Custo operacional não numérico.");
 const amount=Number(value);
 if(!Number.isFinite(amount)||amount<0)throw new Error("Custo operacional fora do limite.");
 return amount;
}
export function summarizeOperationalHealth(
 runs:OperationalRow[],usage:OperationalRow[],failedTasks:Map<string,string>,now:number
){
 if(!Number.isFinite(now))throw new Error("Relógio operacional inválido.");
 const incidents:{id:string;status:string;route:string|null;attempts:number;error:string|null;leaseExpiresAt:string|null;createdAt:string}[]=[];
 let expiredLeases=0,deadLetterRuns=0,failedRuns=0,queuedRuns=0,knownCost=0,unknownCostEvents=0;
 for(const row of runs){
  const id=verifiedId(row.id,"uuid"),status=row.status,taskId=row.task_id;
  if(typeof status!=="string"||!status||typeof taskId!=="string"||!UUID.test(taskId))
   throw new Error("Run sem status ou tarefa confiável.");
  const error=row.last_error==null?null:String(row.last_error);
  const expires=row.lease_expires_at==null?null:verifiedTime(row.lease_expires_at);
  const expired=(status==="running"||status==="implementing")&&expires!==null&&expires<now;
  const failed=status==="failed"&&failedTasks.get(taskId)==="failed";
  const dead=failed&&!!error&&error.toLowerCase().includes("maximum attempts");
  if(expired)expiredLeases++;
  if(failed)failedRuns++;
  if(dead)deadLetterRuns++;
  if(status==="created"||status==="queued")queuedRuns++;
  if(expired||failed){
   const attempts=Number(row.attempt_count??0);
   if(!Number.isSafeInteger(attempts)||attempts<0)throw new Error("Run com tentativas inválidas.");
   incidents.push({id,status,route:row.execution_route==null?null:String(row.execution_route),
    attempts,error,leaseExpiresAt:row.lease_expires_at==null?null:String(row.lease_expires_at),
    createdAt:String(row.created_at)});
  }
 }
 const paid=new Set(["model","openai","llm","paid_provider"]);
 for(const row of usage){
  const amount=parseRecordedCost(row.estimated_cost);
  const family=String(row.tool_family||"").toLowerCase();
  if(!family)throw new Error("Uso operacional sem família.");
  if(amount===null){if(paid.has(family))unknownCostEvents++;}
  else{
   knownCost+=amount;
   if(!Number.isFinite(knownCost))throw new Error("Total de custos sem limite confiável.");
  }
 }
 return {expiredLeases,deadLetterRuns,failedRuns,queuedRuns,knownCost,unknownCostEvents,incidents};
}
