import {getSupabaseServerConfig} from "./supabase-server";
import {requestIntakeWorkerWake} from "./intake-worker-wake";
import {inspectFactoryWakeAppInstallation} from "./github-app";

const keyPattern=/^[a-z0-9][a-z0-9-]{0,63}$/;
export type RecoveryResult={status:"requested"|"failed"|"unconfigured"|"cooldown"|"not_eligible"|"unavailable";integration:string};

export async function recoverPendingProjectWake(projectKey:string,actorId:string):Promise<RecoveryResult>{
 if(!keyPattern.test(projectKey)||!actorId)return {status:"not_eligible",integration:"unknown"};
 const cfg=getSupabaseServerConfig();
 if(!cfg)return {status:"unavailable",integration:"unknown"};
 const integration=await inspectFactoryWakeAppInstallation();
 const lookup=await fetch(cfg.url+"/rest/v1/factory_projects?select=id&project_key=eq."+encodeURIComponent(projectKey)+"&is_active=eq.true&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!lookup.ok)throw new Error("Unable to verify project");
 const projects=await lookup.json();
 if(projects.length!==1)return {status:"not_eligible",integration};
 const id=String(projects[0].id);
 const tasks=await fetch(cfg.url+"/rest/v1/factory_tasks?select=id,external_key,status&project_id=eq."+encodeURIComponent(id)+"&external_key=in.(product-bootstrap-v1,project-reconciliation-v1)&status=eq.queued&limit=2",{headers:cfg.headers,cache:"no-store"});
 if(!tasks.ok)throw new Error("Unable to verify bootstrap task");
 const rows=await tasks.json();
 if(rows.length!==1)return {status:"not_eligible",integration};
 const taskId=String(rows[0].id);
 const run=await fetch(cfg.url+"/rest/v1/factory_runs?select=id,status,attempt_count,started_at&task_id=eq."+encodeURIComponent(taskId)+"&status=eq.created&order=created_at.asc&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!run.ok)throw new Error("Unable to verify initial run");
 const runs=await run.json();
 if(runs.length!==1||runs[0].started_at!=null||Number(runs[0].attempt_count)!==0)return {status:"not_eligible",integration};
 const runId=String(runs[0].id);
 // A distributed durable throttle: any previously attempted wake in the last
 // 15 minutes blocks repeated requests. Concurrent requests can still race;
 // endpoint is intentionally limited to authenticated admins, not automated polling.
 const since=new Date(Date.now()-15*60*1000).toISOString();
 const prior=await fetch(cfg.url+"/rest/v1/factory_audit_events?select=event_type,payload&run_id=eq."+encodeURIComponent(runId)+"&event_type=eq.project.bootstrap.wake_attempted&created_at=gte."+encodeURIComponent(since)+"&order=created_at.desc&limit=1",{headers:cfg.headers,cache:"no-store"});
 if(!prior.ok)throw new Error("Unable to check recovery cooldown");
 const recent=(await prior.json())[0];
 // Only a successful dispatch warrants cooldown; failed/unconfigured attempts may retry.
 if(recent?.payload?.status==="requested")return {status:"cooldown",integration};
 const auditBody={project_id:id,run_id:runId,task_id:taskId,actor_type:"operator",actor_ref:"console-admin",event_type:"project.bootstrap.recovery_requested",payload:{source:"admin_recovery",operator_ref:actorId}};
 const audit=await fetch(cfg.url+"/rest/v1/factory_audit_events",{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json",Prefer:"return=minimal"},body:JSON.stringify(auditBody),cache:"no-store"});
 if(!audit.ok)throw new Error("Cannot persist recovery request");
 const status=await requestIntakeWorkerWake();
 const result=await fetch(cfg.url+"/rest/v1/factory_audit_events",{method:"POST",headers:{...cfg.headers,"Content-Type":"application/json",Prefer:"return=minimal"},body:JSON.stringify({project_id:id,run_id:runId,task_id:taskId,actor_type:"system",actor_ref:"console-recovery",event_type:"project.bootstrap.wake_attempted",payload:{status,source:"admin_recovery"}}),cache:"no-store"});
 if(!result.ok)console.warn("recovery_wake_audit_failed",{status:result.status});
 return {status,integration};
}
