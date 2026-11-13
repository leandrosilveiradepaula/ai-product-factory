import {getSupabaseServerConfig} from "./supabase-server";
import {requestIntakeWorkerWake} from "./intake-worker-wake";

const UUID=/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const QUEUED_PLANNING_STATES=new Set(["planning_replan_queued","planning_reconciliation_queued"]);
export type PlanningWakeStatus="requested"|"failed"|"unconfigured"|"not_needed";

type PlanningReceipt={
  gate_id:string;
  resolution:"approved";
  resume_task_id:string;
  resume_run_id:string;
  next_state:string;
};

/**
 * A human-approved planning decision atomically persists the continuation run,
 * but does not claim it. Ask GitHub to wake the existing queue immediately,
 * then persist an exact-run receipt for the project's progress screen.
 *
 * No model, paid reservation, run claim, re-Start, release or merge here.
 * GitHub returns only dispatch acceptance; it does NOT prove execution.
 * The scheduled runner remains a recovery path for failed/unconfigured wakes.
 */
export async function wakeApprovedPlanningDecision(
  gateId:string, value:unknown,
):Promise<PlanningWakeStatus>{
  if(!UUID.test(gateId)||!value||typeof value!=="object"||Array.isArray(value))
    throw new Error("Invalid planning continuation receipt");
  const receipt=value as Partial<PlanningReceipt>;
  if(receipt.gate_id!==gateId||receipt.resolution!=="approved"||
     !UUID.test(String(receipt.resume_task_id||""))||
     !UUID.test(String(receipt.resume_run_id||""))||
     !QUEUED_PLANNING_STATES.has(String(receipt.next_state||"")))
    throw new Error("Planning continuation not durably queued");

  const cfg=getSupabaseServerConfig();
  if(!cfg)return "failed";
  let projectId:string;
  try{
    const lookup=await fetch(cfg.url+"/rest/v1/factory_tasks?select=id,project_id"+
      "&id=eq."+encodeURIComponent(receipt.resume_task_id!)+"&limit=2",{
      headers:cfg.headers,cache:"no-store",
    });
    if(!lookup.ok)return "failed";
    const rows=await lookup.json();
    if(!Array.isArray(rows)||rows.length!==1||rows[0]?.id!==receipt.resume_task_id||
       !UUID.test(String(rows[0]?.project_id||"")))return "failed";
    projectId=String(rows[0].project_id);

    // The gate is a product decision, not permission to resume paused projects.
    const control=await fetch(cfg.url+"/rest/v1/factory_project_execution_controls"+
      "?select=project_id,state&project_id=eq."+encodeURIComponent(projectId)+"&limit=2",{
      headers:cfg.headers,cache:"no-store",
    });
    if(!control.ok)return "failed";
    const controls=await control.json();
    if(!Array.isArray(controls)||controls.length!==1||
       controls[0]?.project_id!==projectId)return "failed";
    if(controls[0]?.state!=="running")return "not_needed";

  }catch{
    // A broken read must not make the already-resolved gate appear pending.
    // No dispatch is attempted until the project is verified as running.
    console.warn("planning_decision_wake_preflight_unavailable");
    return "failed";
  }

  let status:Exclude<PlanningWakeStatus,"not_needed">="failed";
  try{
    status=await requestIntakeWorkerWake();
  }catch{
    console.warn("planning_decision_immediate_wake_failed");
  }

  // Persist only bounded status, exact run/task/gate IDs and source.
  // Audit failure does not revert a committed gate or send a second wake.
  try{
    const audit=await fetch(cfg.url+"/rest/v1/factory_audit_events",{
      method:"POST",headers:{...cfg.headers,"Content-Type":"application/json",Prefer:"return=minimal"},
      body:JSON.stringify({
        project_id:projectId,
        task_id:receipt.resume_task_id,
        run_id:receipt.resume_run_id,
        actor_type:"system",
        actor_ref:"console-planning-decision",
        event_type:"project.continuation.wake_attempted",
        payload:{status,source:"planning-decision",gate_id:gateId,execution_state:"running"},
      }),
      cache:"no-store",
    });
    if(!audit.ok)console.warn("planning_decision_wake_audit_failed",{status:audit.status});
  }catch{
    console.warn("planning_decision_wake_audit_failed",{reason:"transport"});
  }
  return status;
}
