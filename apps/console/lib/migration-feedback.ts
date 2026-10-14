import {requireConsoleOperator} from "./auth-server";
import {getSupabaseServerConfig} from "./supabase-server";

export type VerifiedMigrationOutcome={migrationName:string;alreadyApplied:boolean};
const GATE_ID_RE=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const VALID_EVENTS=new Set(["human_migration.console_apply_succeeded","human_migration.console_already_applied"]);

/**
 * A URL query is only a lookup hint, never evidence of a successful migration.
 * Return a confirmation only for an approved gate plus matching durable audit
 * from the exact run and candidate; failure to read any source fails closed.
 */
export async function getVerifiedMigrationOutcome(gateId:string):Promise<VerifiedMigrationOutcome|null>{
 await requireConsoleOperator();
 if(!GATE_ID_RE.test(gateId))return null;
 const cfg=getSupabaseServerConfig();
 if(!cfg)return null;
 const gateResponse=await fetch(
  cfg.url+"/rest/v1/factory_human_gates?select=id,run_id,status&id=eq."+encodeURIComponent(gateId)+"&limit=1",
  {headers:cfg.headers,cache:"no-store"},
 );
 if(!gateResponse.ok)return null;
 const gates=await gateResponse.json();
 const gate=Array.isArray(gates)?gates[0]:null;
 if(!gate||gate.status!=="approved"||!GATE_ID_RE.test(String(gate.run_id||"")))return null;

 const runResponse=await fetch(
  cfg.url+"/rest/v1/factory_runs?select=id,candidate_commit,metadata&id=eq."+encodeURIComponent(gate.run_id)+"&limit=1",
  {headers:cfg.headers,cache:"no-store"},
 );
 if(!runResponse.ok)return null;
 const runs=await runResponse.json();
 const run=Array.isArray(runs)?runs[0]:null;
 const metadata=run?.metadata;
 if(!run||metadata?.requested_action!=="apply_control_plane_migration")return null;
 const expectedName=metadata?.migration_name;
 const expectedCommit=run.candidate_commit;
 if(typeof expectedName!=="string"||!expectedName||typeof expectedCommit!=="string"||!expectedCommit)return null;

 const auditResponse=await fetch(
  cfg.url+"/rest/v1/factory_audit_events?select=event_type,payload,created_at&run_id=eq."+encodeURIComponent(gate.run_id)+"&event_type=in.(human_migration.console_apply_succeeded,human_migration.console_already_applied)&order=created_at.desc&limit=20",
  {headers:cfg.headers,cache:"no-store"},
 );
 if(!auditResponse.ok)return null;
 const events=await auditResponse.json();
 if(!Array.isArray(events))return null;
 const matching=events.find((event:any)=>
  VALID_EVENTS.has(String(event?.event_type||""))&&
  event?.payload?.candidate_commit===expectedCommit&&
  event?.payload?.migration_name===expectedName
 );
 if(!matching)return null;
 return{migrationName:expectedName.slice(0,120),alreadyApplied:matching.event_type==="human_migration.console_already_applied"};
}
