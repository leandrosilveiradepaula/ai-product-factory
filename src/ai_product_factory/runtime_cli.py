from __future__ import annotations
import argparse,json,os,socket
from decimal import Decimal, InvalidOperation
from .model_executor import ModelExecutor
from .metered_provider import MeteredPrimaryProvider
from .openai_provider import OpenAIResponsesProvider
from .product_stage_executor import ProductStageExecutor
from .runtime_auth import AuthKind,RuntimeAuthResolver
from .runtime_worker import RuntimeWorker
from .supabase_runtime_queue import SupabaseRuntimeQueue
from .supabase_backlog_dispatch import SupabaseBacklogDispatch
from .direct_run_queue import SupabaseDirectRunQueue
from .codex_run_queue import SupabaseCodexRunQueue
from .routed_execution_epoch import assert_routed_epoch
from .codex_cli_producer import CodexCLIProducer
from .codex_usage import SupabaseCodexUsageRecorder
from .implementation_producer import ModelImplementationProducer
from .execution_worker import DirectExecutionWorker,ImplementationBlocked
from .change_set_store import SupabaseChangeSetStore
from .change_set_worker import ChangeSetBuilderWorker
from .change_set_integrator import ChangeSetIntegrator
from .github_rest import GitHubRestAdapter
from .autonomous_github import AutonomousGitHubLoop,GitHubWorkSession
from .issue_materializer import GitHubIssueMaterializer
from .supabase_issue_binding import SupabaseIssueBindingStore
from .supabase_delivery_store import SupabaseDeliveryStore
from .primary_cost_config import SupabasePrimaryCostPolicyReader, require_primary_cost_capacity
from .integration_readiness import github_alerts_readiness,github_vercel_preview_readiness,vercel_preview_readiness,verified_preview_readiness
from .operational_alerts import OPERATIONAL_ALERT_CODES,evaluate_operational_alerts
from .supabase_operational_health import SupabaseOperationalHealthReader
from .supabase_scheduler_liveness import SupabaseSchedulerLivenessReader,evaluate_scheduler_liveness
from .github_scheduler_health import GithubNativeScheduledRunReader,evaluate_native_scheduler_health
from .supabase_backlog_inventory import SupabaseBacklogInventoryReader
from .github_alert_adapter import GitHubIssueAlertAdapter
from .ci_followup_queue import SupabaseCIFollowupQueue
from .release_followup_queue import SupabaseReleaseFollowupQueue
from .preview_followup_queue import SupabasePreviewFollowupQueue
from .project_preview_config import resolve_project_vercel_preview_config
from .preview_policy import evaluate_preview_applicability
from .preview_base_guard import verify_preview_base_compatibility
from .nonproduction_preview_merge import verify_nonproduction_preview_merge
from .vercel_preview import VercelPreviewAdapter,VercelPreviewConfig
from .github_vercel_preview import GitHubVercelPreviewAdapter,config_from_env as github_vercel_config_from_env
from .command_browser_evidence import CommandBrowserEvidenceAdapter,CommandBrowserEvidenceConfig
from .supabase_deployment import DurablePreviewAdapter,SupabaseDeploymentEvidenceStore
from .browser_evidence_store import BrowserEvidenceRecorder
from .preview_flow import PreviewDeferred,VerifiedPreviewCoordinator
from .deployment import DeploymentRequest
from .release_policy import ReleaseEnvironment
from .agent_scheduler import SupabaseAgentScheduler
from .adaptive_agent_scheduler import SupabaseAdaptiveConcurrencyController
from .evidence import EvidenceBundle
from .review_gate import EvalResult,evaluate_quality_gate
from .specialist_lane_queue import SupabaseSpecialistLaneQueue
from .specialist_lanes import evaluate_specialist_lane
from .traceability_store import SupabaseTraceabilityStore
from .release_intelligence import build_release_assessment,load_default_release_policy
from .release_policy_store import SupabaseReleasePolicyStore
from .provenance_replay import SupabaseProvenanceStore
from .schedule_probe import SupabaseScheduleProbe
from .bounded_continuation import drain_deterministic_lane, drain_waiting_followups
from .product_worker_readiness import record_product_worker_readiness
from .delivery_metrics import SupabaseDeliveryMetricsReader
from .project_release_reconciliation import SupabaseProjectReleaseReconciler
from .project_github_access import SupabaseProjectGitHubAccessStore
from .github_capability_preflight import run_project_github_preflight

def require_primary_runtime_enabled()->None:
 if os.getenv("FACTORY_PRIMARY_MODEL_ENABLED")!="true":raise PermissionError("primary model execution is disabled")

def require_paid_runtime_budget(*, health_reader=None, policy_reader=None)->None:
 # Fail closed: never use stale GitHub workflow environment ceilings.
 require_primary_cost_capacity(policy_reader=policy_reader,health_reader=health_reader)

def require_codex_runtime_enabled()->None:
 """Validate one official Codex auth mode without performing a paid request.

 A partial WIF configuration always wins over and disables token fallback.
 """
 if os.getenv("FACTORY_CODEX_ENABLED")!="true":
  raise PermissionError("Codex execution is disabled")
 if not os.getenv("FACTORY_GITHUB_TOKEN","").strip():
  raise PermissionError("Codex runtime configuration is incomplete: FACTORY_GITHUB_TOKEN")
 wif=("OPENAI_FEDERATION_RULE_ID","OPENAI_WIF_AUDIENCE","OPENAI_IDENTITY_TOKEN_FILE")
 configured=[name for name in wif if os.getenv(name,"").strip()]
 if configured:
  missing=[name for name in wif if not os.getenv(name,"").strip()]
  if missing:
   raise PermissionError("Codex WIF configuration is incomplete: "+", ".join(missing))
  if not os.path.isfile(os.environ["OPENAI_IDENTITY_TOKEN_FILE"]):
   raise PermissionError("Codex identity token file does not exist")
 elif not os.getenv("CODEX_ACCESS_TOKEN","").strip():
  raise PermissionError("Codex runtime requires official WIF or CODEX_ACCESS_TOKEN")


def build_handler():
 require_primary_runtime_enabled()
 auth=RuntimeAuthResolver().resolve_primary_api()
 if auth.kind in {AuthKind.OPENAI_API_KEY,AuthKind.OPENAI_API_WIF}:
  profiles=SupabaseAgentScheduler().profiles()
  return ProductStageExecutor(ModelExecutor(primary=MeteredPrimaryProvider(OpenAIResponsesProvider())),team_profiles=profiles)
 raise RuntimeError(f"No supported primary-model runtime auth is configured (resolved: {auth.kind.value})")

def run_recovery_once(max_attempts:int=3)->dict:
 queue=SupabaseRuntimeQueue()
 runs=queue.recover_expired(max_attempts)
 decisions=queue.resume_resolved_decisions()
 descendants=queue.reconcile_terminal_descendants()
 scheduler=SupabaseAgentScheduler()
 agents=scheduler.recover_expired()
 # Recovery never creates new agent assignments: the legacy global RPC can
 # silently choose an unready Direct run or a Codex manual handoff. The
 # readiness-gated dispatcher schedules eligible Direct runs separately.
 agent_retry={"attempted":0,"assigned":0,"no_eligible_slot":False,
              "deferred_to_readiness_gated_dispatch":True}
 specialist_lanes=SupabaseSpecialistLaneQueue().recover_expired(max_attempts)
 change_sets=SupabaseChangeSetStore().recover_expired(max_attempts)
 return {"runs":runs,"decisions":decisions,"descendants":descendants,"agents":agents,"agent_retry":agent_retry,"specialist_lanes":specialist_lanes,"change_sets":change_sets}

def run_product_once(worker_id:str)->dict:
 try:
  require_primary_runtime_enabled()
  require_paid_runtime_budget()
  handler=build_handler()
 except (RuntimeError,PermissionError) as exc:return {"claimed":False,"status":"blocked","error":str(exc)}
 result=RuntimeWorker(queue=SupabaseRuntimeQueue(),handler=handler,worker_id=worker_id).run_once()
 return {"claimed":result is not None,"status":result.status.value if result else None,"error":result.error if result else None}

def _select_assigned_route_run(scheduler:SupabaseAgentScheduler,route:str,
                                agent_key:str|None=None)->tuple[str,str]|None:
 # Pure read of already-assigned work; never reserve the next unscoped run.
 if route not in {"direct","codex"}:raise ValueError("invalid worker route")
 matrix=scheduler.work_matrix(12)
 items=matrix.get(route)
 if not isinstance(items,list):raise RuntimeError("invalid route work matrix")
 for row in items:
  if not isinstance(row,dict):raise RuntimeError("invalid assigned work item")
  row_run=row.get("run_id")
  row_agent=row.get("agent_key")
  if not isinstance(row_run,str) or not row_run.strip() or not isinstance(row_agent,str) or not row_agent.strip():
   raise RuntimeError("assigned work item lacks durable run and agent")
  if agent_key is None or row_agent==agent_key:
   return row_run,row_agent
 return None

def _routed_checkpoint(item,worker_id):
 assert_routed_epoch(getattr(item,'project_id',None),getattr(item,'execution_generation',0),item.run_id,worker_id)

class _CheckpointedProducer:
 def __init__(self,producer,checkpoint):
  self._producer=producer;self._checkpoint=checkpoint
 def produce(self,item):
  self._checkpoint()
  return self._producer.produce(item)

class _CheckpointedGitHub:
 def __init__(self,adapter,checkpoint):
  self._adapter=adapter;self._checkpoint=checkpoint
 def __getattr__(self,name):
  attr=getattr(self._adapter,name)
  if not callable(attr):return attr
  if name in ('commit_files','create_issue','create_pull_request','create_branch','create_branch_at_sha','ensure_branch_at_sha','update_file','open_pull_request','dispatch_workflow','create_ref','update_ref','post_comment','create_review','close_issue'):
   def guarded(*args,**kwargs):
    self._checkpoint()
    return attr(*args,**kwargs)
   return guarded
  return attr

def _release_routed_run(scheduler,item,worker_id,status):
 # Completed runs require a still-valid capability; revoked workers must not report success.
 if status=="completed":
  _routed_checkpoint(item,worker_id)
 scheduler.release(item.run_id,status)

def run_direct_once(worker_id:str,agent_key:str|None=None,run_id:str|None=None)->dict:
 try:
  require_primary_runtime_enabled()
  auth=RuntimeAuthResolver().resolve_primary_api()
  if auth.kind not in {AuthKind.OPENAI_API_KEY,AuthKind.OPENAI_API_WIF}:raise RuntimeError(f"No supported primary-model runtime auth is configured (resolved: {auth.kind.value})")
  require_paid_runtime_budget()
 except (RuntimeError,PermissionError) as exc:return {"claimed":False,"status":"blocked","error":str(exc)}
 scheduler=SupabaseAgentScheduler()
 if run_id is None:
  selected=_select_assigned_route_run(scheduler,"direct",agent_key)
  if selected is None:return {"claimed":False,"status":"empty"}
  run_id,agent_key=selected
 elif not agent_key:
  raise ValueError("agent_key is required when run_id is explicit")
 scheduler.require_route_tools(agent_key,"direct")
 item=SupabaseDirectRunQueue().claim_next(worker_id,agent_key,run_id)
 if item is None:return {"claimed":False,"status":"empty"}
 try:
  _routed_checkpoint(item,worker_id)
  checkpoint=lambda:_routed_checkpoint(item,worker_id)
  if item.repository!=os.getenv("GITHUB_REPOSITORY","").strip():
   SupabaseProjectGitHubAccessStore().require_capabilities(item.project_key,("contents_write","issues_write","pull_requests_write"))
  producer=ModelImplementationProducer(ModelExecutor(primary=MeteredPrimaryProvider(OpenAIResponsesProvider())))
  producer=_CheckpointedProducer(producer,checkpoint)
  github=_CheckpointedGitHub(GitHubRestAdapter(repository=item.repository),checkpoint)
  if getattr(item,"change_set_id",None):
   try:
    result=ChangeSetBuilderWorker(github=github,store=SupabaseChangeSetStore(),producer=producer,execution_route="direct").execute(item)
   except ImplementationBlocked as exc:
    _release_routed_run(scheduler,item,worker_id,"blocked")
    return {"claimed":True,"status":"blocked","run_id":item.run_id,"error":str(exc)}
   _release_routed_run(scheduler,item,worker_id,"completed")
   return {"claimed":True,"status":"work_unit_completed","run_id":item.run_id,"change_set_id":result.change_set_id,"output_commit":result.output_commit}
  loop=AutonomousGitHubLoop(github,SupabaseDeliveryStore())
  materializer=GitHubIssueMaterializer(github=github,binding=SupabaseIssueBindingStore())
  session=DirectExecutionWorker(loop=loop,producer=producer,issue_materializer=materializer).execute(item)
  if session.pull_request is None:raise RuntimeError("GitHub delivery did not open a pull request")
 except Exception:
  _release_routed_run(scheduler,item,worker_id,"blocked")
  raise
 _release_routed_run(scheduler,item,worker_id,"completed")
 return {"claimed":True,"status":"pr_open","run_id":item.run_id,"pr_number":session.pull_request.number}

def run_codex_once(worker_id:str,agent_key:str|None=None,run_id:str|None=None)->dict:
 try:
  require_codex_runtime_enabled()
 except (RuntimeError,PermissionError) as exc:return {"claimed":False,"status":"blocked","error":str(exc)}
 scheduler=SupabaseAgentScheduler()
 if run_id is None:
  selected=_select_assigned_route_run(scheduler,"codex",agent_key)
  if selected is None:return {"claimed":False,"status":"empty"}
  run_id,agent_key=selected
 elif not agent_key:
  raise ValueError("agent_key is required when run_id is explicit")
 scheduler.require_route_tools(agent_key,"codex")
 item=SupabaseCodexRunQueue().claim_next(worker_id,agent_key,run_id)
 if item is None:return {"claimed":False,"status":"empty"}
 try:
  _routed_checkpoint(item,worker_id)
  checkpoint=lambda:_routed_checkpoint(item,worker_id)
  if item.repository!=os.getenv("GITHUB_REPOSITORY","").strip():
   SupabaseProjectGitHubAccessStore().require_capabilities(item.project_key,("contents_write","issues_write","pull_requests_write"))
  usage=SupabaseCodexUsageRecorder()
  producer=CodexCLIProducer(on_invoke=lambda:usage.record_invocation(run_id=item.run_id,reported_usage={"status":"started","policy_level":item.codex_level}))
  producer=_CheckpointedProducer(producer,checkpoint)
  github=_CheckpointedGitHub(GitHubRestAdapter(repository=item.repository),checkpoint)
  if getattr(item,"change_set_id",None):
   result=ChangeSetBuilderWorker(github=github,store=SupabaseChangeSetStore(),producer=producer,execution_route="codex").execute(item)
   _release_routed_run(scheduler,item,worker_id,"completed")
   return {"claimed":True,"status":"work_unit_completed","run_id":item.run_id,"change_set_id":result.change_set_id,"output_commit":result.output_commit}
  store=SupabaseDeliveryStore()
  loop=AutonomousGitHubLoop(github,store)
  materializer=GitHubIssueMaterializer(github=github,binding=SupabaseIssueBindingStore())
  session=DirectExecutionWorker(loop=loop,producer=producer,issue_materializer=materializer).execute(item)
  if session.pull_request is None:raise RuntimeError("GitHub delivery did not open a pull request")
 except Exception:
  _release_routed_run(scheduler,item,worker_id,"blocked")
  raise
 _release_routed_run(scheduler,item,worker_id,"completed")
 return {"claimed":True,"status":"pr_open","run_id":item.run_id,"pr_number":session.pull_request.number}

class _CheckpointedIntegrationStore:
 """Fence integration metadata mutations after pause/stop, not just GitHub writes."""
 _mutations=frozenset(("complete_integration","mark_repair_wave_integrated","prepare_release"))
 def __init__(self,store,checkpoint):
  self._store=store;self._checkpoint=checkpoint
 def __getattr__(self,name):
  attr=getattr(self._store,name)
  if name not in self._mutations or not callable(attr):return attr
  def guarded(*args,**kwargs):
   self._checkpoint()
   return attr(*args,**kwargs)
  return guarded

def run_change_set_integration_once(worker_id:str)->dict:
 store=SupabaseChangeSetStore()
 # Code merged before its production SQL migration must not claim a lease or
 # create GitHub commits. The DB readiness probe also rejects legacy write grants.
 store.require_epoch_mutation_ready()
 item=store.claim_integration(worker_id)
 if item is None:return {"claimed":False,"status":"empty"}
 checkpoint=lambda:store.assert_integration_epoch(item,worker_id)
 checkpoint()
 github=_CheckpointedGitHub(GitHubRestAdapter(repository=item.repository),checkpoint)
 result=ChangeSetIntegrator(github=github,store=_CheckpointedIntegrationStore(store,checkpoint)).integrate(item)
 ci_dispatched=False
 if result.pull_request and item.repository==os.getenv("GITHUB_REPOSITORY","").strip():
  github.dispatch_workflow("validate.yml",ref=item.integration_branch)
  ci_dispatched=True
 return {"claimed":True,"status":result.status,"change_set_id":result.change_set_id,"wave":result.wave,"candidate_commit":result.candidate_commit,"pr_number":result.pull_request.number if result.pull_request else None,"ci_dispatched":ci_dispatched}

def run_health_once()->dict:
 auth=RuntimeAuthResolver().resolve()
 vercel=vercel_preview_readiness();github_vercel=github_vercel_preview_readiness();alerts=github_alerts_readiness()
 codex_missing=[name for name in ("OPENAI_FEDERATION_RULE_ID","OPENAI_WIF_AUDIENCE","OPENAI_IDENTITY_TOKEN_FILE","FACTORY_GITHUB_TOKEN") if not os.getenv(name,"").strip()]
 policy_ready=False
 if os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
  try:
   SupabasePrimaryCostPolicyReader().read()
   policy_ready=True
  except (RuntimeError,ValueError):
   policy_ready=False
 return {"status":"healthy","control_plane_configured":bool(os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY"))),"primary_auth":auth.kind.value,"primary_enabled":os.getenv("FACTORY_PRIMARY_MODEL_ENABLED")=="true","budget_configured":policy_ready,"reservation_configured":policy_ready,"codex":{"enabled":os.getenv("FACTORY_CODEX_ENABLED")=="true","configured":not codex_missing,"ready":os.getenv("FACTORY_CODEX_ENABLED")=="true" and not codex_missing and os.path.isfile(os.getenv("OPENAI_IDENTITY_TOKEN_FILE","")),"missing":codex_missing},"vercel_preview_api":{"enabled":vercel.enabled,"configured":vercel.configured,"ready":vercel.ready,"missing":list(vercel.missing)},"vercel_preview_github":{"enabled":github_vercel.enabled,"configured":github_vercel.configured,"ready":github_vercel.ready,"missing":list(github_vercel.missing)},"github_alerts":{"enabled":alerts.enabled,"configured":alerts.configured,"ready":alerts.ready,"missing":list(alerts.missing)}}

def reconcile_ci_candidate_once(*,expected_run_id:str,expected_pr_number:int,allowed_paths:tuple[str,...]=(".github/workflows/crm-validation.yml",))->dict:
 """Explicit operator-invoked reconciliation; never run on a normal CI poll.

 Requires an exact run/PR, same-repository branch, clean fast-forward and an
 allowlisted change set. No release or merge action is performed.
 """
 import re
 item=SupabaseCIFollowupQueue().next_pending(allow_unreconciled_receipt=True)
 if item is None or item.run_id!=expected_run_id or item.pr_number!=expected_pr_number:
  raise RuntimeError("requested candidate is not the next durable CI item")
 if not item.change_set_id:
  raise RuntimeError("only change-set candidates support atomic reconciliation")
 github=GitHubRestAdapter(repository=item.repository)
 pr=github.get_pull_request(item.pr_number)
 if (pr.merged or pr.state!="open" or pr.head_ref!=item.branch
     or pr.head_repository!=item.repository or not pr.base_ref):
  raise RuntimeError("GitHub PR identity or open state mismatch")
 old=item.candidate_commit
 new=pr.head_sha
 if not re.fullmatch(r"[0-9a-f]{40}",old) or not re.fullmatch(r"[0-9a-f]{40}",new) or old==new:
  raise RuntimeError("candidate SHA drift is not a valid update")
 comparison=github.compare_commits(old,new)
 changed=comparison.get("files")
 if (comparison.get("status")!="ahead" or comparison.get("behind_by")!=0
     or not isinstance(comparison.get("ahead_by"),int) or comparison["ahead_by"]<1
     or not isinstance(changed,list) or not changed
     or len(changed)>300 or any(path not in allowed_paths for path in changed)):
  raise RuntimeError("GitHub candidate ancestry or changed-path policy rejected")
 if github.get_branch_sha(item.branch)!=new:
  raise RuntimeError("candidate branch moved during reconciliation")
 evidence={"old_sha":old,"new_sha":new,"pr_number":str(item.pr_number),
           "compare_status":"ahead","ahead_by":str(comparison["ahead_by"]),
           "changed_files":changed,"branch":item.branch,"repository":item.repository}
 return SupabaseDeliveryStore().reconcile_change_set_ci_candidate(
  change_set_id=item.change_set_id,run_id=item.run_id,pr_number=item.pr_number,
  previous_commit=old,new_commit=new,verified_evidence=evidence)


def run_ci_once(*,exclude_run_ids:tuple[str,...]=())->dict:
 queue=SupabaseCIFollowupQueue()
 item=queue.next_pending(exclude_run_ids=exclude_run_ids) if exclude_run_ids else queue.next_pending()
 if item is None:return {"claimed":False,"status":"empty"}
 github=GitHubRestAdapter(repository=item.repository)
 pr=github.get_pull_request(item.pr_number)
 if pr.head_sha!=item.candidate_commit:
  # Never adopt a changed PR head implicitly: the release candidate, durable
  # create_pr receipt, and change-set metadata must be reconciled atomically.
  # Emit an actionable diagnostic without mutating any release or CI state.
  return {"claimed":False,"status":"candidate_drift_blocked",
   "run_id":item.run_id,"pr_number":item.pr_number,
   "change_set_id":getattr(item,"change_set_id",None),
   "recorded_candidate_commit":item.candidate_commit,
   "observed_pr_head":pr.head_sha,
   "requires":"atomic_candidate_reconciliation"}
 store=SupabaseDeliveryStore()
 # A human may merge an exact PR before CI/Preview/quality gates pass. This
 # must never be interpreted as successful CI or a production release.
 if getattr(pr,"merged",False):
  merge_sha=str(getattr(pr,"merge_commit_sha",None) or "")
  if not merge_sha:raise RuntimeError("merged PR has no verifiable merge SHA")
  result=store.block_early_merged_ci_candidate(
   run_id=item.run_id,repository=item.repository,pr_number=item.pr_number,
   candidate_commit=item.candidate_commit,merge_sha=merge_sha,
  )
  return {"claimed":True,"status":"merged_before_readiness_blocked",
   "run_id":item.run_id,"pr_number":item.pr_number,"merge_sha":merge_sha,
   "change_set_id":result.get("change_set_id"),"idempotent":bool(result.get("idempotent"))}
 issue=github.get_issue(item.issue_number)
 loop=AutonomousGitHubLoop(github,store)
 session=GitHubWorkSession(issue,item.branch,item.run_id,"","",pr)
 decision=loop.evaluate(session,human_gate_required=item.human_gate_required)
 status=decision.action.value
 if (
  decision.action.value=="wait_ci"
  and item.repository==os.getenv("GITHUB_REPOSITORY","").strip()
  and getattr(github,"last_ci_evidence_present",None) is False
 ):
  github.dispatch_workflow("validate.yml",ref=item.branch)
  store.record_tool_usage(
   run_id=item.run_id,tool_family="github",operation="dispatch_ci",
   metadata={"pr":item.pr_number,"head_sha":item.candidate_commit,"workflow":"validate.yml","ref":item.branch},
  )
  store.record_audit_event(
   run_id=item.run_id,event_type="ci.same_repo_dispatched",
   payload={"pr":item.pr_number,"candidate_commit":item.candidate_commit,"workflow":"validate.yml","ref":item.branch},
   actor_ref="ci-followup",
  )
  return {"claimed":True,"status":"ci_triggered","run_id":item.run_id,"pr_number":item.pr_number,"ci_state":decision.ci_state.value}
 if decision.action.value=="preview_ready":
  quality=evaluate_quality_gate(evals=(EvalResult("github_ci",True,required=True),))
  if not quality.passed:raise RuntimeError("quality gate did not pass after successful CI")
  store.record_evaluation(run_id=item.run_id,eval_type="quality_gate",status="success",baseline_ref=item.candidate_commit,result={"passed":True,"reasons":list(quality.reasons),"source":"github_ci"})
  store.record_audit_event(run_id=item.run_id,event_type="quality_gate.passed",payload={"candidate_commit":item.candidate_commit,"reasons":list(quality.reasons)},actor_ref="ci-followup")
  ci_evidence_source=getattr(github,"last_ci_evidence_source",None)
  if ci_evidence_source not in {"github_checks","github_actions_statuses"}:
   ci_evidence_source="github_checks"
  SupabaseTraceabilityStore().record_delivery_evidence(
   run_id=item.run_id,evidence_type="github_ci",status="passed",evidence_ref=item.candidate_commit,
   metadata={"source":ci_evidence_source,"pr_number":item.pr_number}
  )
  routed=SupabaseSpecialistLaneQueue().enqueue(item.run_id)
  status=str(routed.get("status") or "specialist_review_pending")
 return {"claimed":True,"status":status,"run_id":item.run_id,"pr_number":item.pr_number,"ci_state":decision.ci_state.value}

def run_specialist_once(role:str,worker_id:str)->dict:
 queue=SupabaseSpecialistLaneQueue()
 item=queue.claim(role,worker_id)
 if item is None:return {"claimed":False,"status":"empty","role":role}
 github=GitHubRestAdapter(repository=item.repository)
 result=evaluate_specialist_lane(item,github)
 completed=queue.complete(item,status=result.status,findings=list(result.findings),evidence=result.evidence)
 SupabaseTraceabilityStore().record_delivery_evidence(
  run_id=item.run_id,evidence_type=role,status=result.status,evidence_ref=item.candidate_commit,
  metadata={"source":"specialist_lane","role":role,"job_id":item.job_id,"findings_count":len(result.findings)}
 )
 return {"claimed":True,"role":role,"job_id":item.job_id,"run_id":item.run_id,"status":result.status,
  "run_status":completed.get("run_status"),"findings":list(result.findings),
  "repair":completed.get("repair"),"repair_recheck":completed.get("repair_recheck")}

def _assess_release_policy(*,run_id:str,candidate_commit:str,changed_files:tuple[str,...],risk:dict)->tuple[object,dict]:
 policy_store=SupabaseReleasePolicyStore()
 facts=policy_store.facts(run_id)
 health=SupabaseOperationalHealthReader().read()
 assessment=build_release_assessment(
  policy=load_default_release_policy(),
  candidate_commit=candidate_commit,
  changed_files=changed_files,
  risk=risk,
  facts=facts,
  unknown_paid_cost=health.unknown_cost_events>0,
  known_cost=health.known_cost,
 )
 recorded=policy_store.record(run_id=run_id,assessment=assessment)
 return assessment,recorded

def _require_current_preview_base(github:GitHubRestAdapter,pr)->dict:
 # A moved preview base is rejected unless every new byte has already been
 # present and tested at the exact candidate HEAD, with bounded Git evidence.
 return verify_preview_base_compatibility(github,pr)

def run_preview_probe_once()->dict:
 item=SupabasePreviewFollowupQueue().next_pending()
 if item is None:return {"claimed":False,"status":"empty","preview_required":False}
 github=GitHubRestAdapter(repository=item.repository)
 pr=github.get_pull_request(item.pr_number)
 if getattr(pr,"state","open")!="open" or getattr(pr,"merged",False):
  if getattr(pr,"merged",False):
   return {"claimed":False,"status":"merged_pr_requires_release_observation",
    "run_id":item.run_id,"pr_number":item.pr_number,"preview_required":False}
  if pr.head_sha!=item.candidate_commit:
   raise RuntimeError("closed PR head does not match durable candidate")
  return {"claimed":True,"status":"reconcile_closed_pr","run_id":item.run_id,
   "pr_number":item.pr_number,"preview_required":False}
 if pr.head_sha!=item.candidate_commit:raise RuntimeError("GitHub PR head no longer matches preview candidate")
 base_evidence=_require_current_preview_base(github,pr)
 changed_files=github.get_pull_request_files(item.pr_number)
 applicability=evaluate_preview_applicability(manifest=item.manifest,changed_files=changed_files)
 if not applicability.required:
  return {"claimed":True,"status":"ready","run_id":item.run_id,"preview_required":False,"reason":applicability.reason}
 try:
  project_cfg=resolve_project_vercel_preview_config(repository=item.repository,manifest=item.manifest)
 except ValueError as exc:
  return {"claimed":True,"status":"blocked","run_id":item.run_id,"preview_required":True,"error":str(exc)}
 return {"claimed":True,"status":"ready","run_id":item.run_id,"preview_required":True,"preview_mode":project_cfg.mode}

def run_preview_once()->dict:
 item=SupabasePreviewFollowupQueue().next_pending()
 if item is None:return {"claimed":False,"status":"empty"}
 github=GitHubRestAdapter(repository=item.repository)
 pr=github.get_pull_request(item.pr_number)
 if getattr(pr,"state","open")!="open" or getattr(pr,"merged",False):
  if getattr(pr,"merged",False):
   return {"claimed":False,"status":"merged_pr_requires_release_observation",
    "run_id":item.run_id,"pr_number":item.pr_number}
  if pr.head_sha!=item.candidate_commit:
   raise RuntimeError("closed PR head does not match durable candidate")
  result=SupabaseDeliveryStore().reconcile_closed_preview_candidate(
   item.run_id,candidate_commit=item.candidate_commit,
   pr_number=item.pr_number,github_state="closed",github_merged=False)
  return {"claimed":True,"status":"superseded","run_id":item.run_id,
   "pr_number":item.pr_number,"change_set_status":result["change_set_status"],
   "idempotent":result.get("idempotent",False)}
 issue=github.get_issue(item.issue_number)
 if pr.head_sha!=item.candidate_commit:raise RuntimeError("GitHub PR head no longer matches preview candidate")
 base_evidence=_require_current_preview_base(github,pr)
 changed_files=github.get_pull_request_files(item.pr_number)
 applicability=evaluate_preview_applicability(manifest=item.manifest,changed_files=changed_files)
 store=SupabaseDeliveryStore()
 if base_evidence:
  store.record_audit_event(
   run_id=item.run_id,event_type="preview.compatible_base_advance",
   payload=base_evidence,actor_ref="preview-followup",
  )
 loop=AutonomousGitHubLoop(github,store)
 session=GitHubWorkSession(issue,item.branch,item.run_id,"","",pr)
 if not applicability.required:
  assessment,recorded=_assess_release_policy(
   run_id=item.run_id,candidate_commit=item.candidate_commit,changed_files=changed_files,
   risk=getattr(item,"risk",{}) or {},
  )
  if assessment.decision.blocked:
   return {"claimed":True,"status":"release_policy_blocked","run_id":item.run_id,"pr_number":item.pr_number,
    "preview_required":False,"reason":applicability.reason,"policy_reasons":list(assessment.decision.reasons)}
  refreshed_pr=github.get_pull_request(item.pr_number)
  if (getattr(refreshed_pr,"merged",False)
      or getattr(refreshed_pr,"state","open")!="open"
      or refreshed_pr.head_sha!=item.candidate_commit):
   raise RuntimeError("GitHub PR identity changed before non-Preview release readiness")
  _require_current_preview_base(github,refreshed_pr)
  status=loop.finalize_preview_not_required(session,reason=applicability.reason,changed_files=changed_files)
  return {"claimed":True,"status":status,"run_id":item.run_id,"pr_number":item.pr_number,
   "preview_required":False,"reason":applicability.reason,"release_report_id":recorded.get("report_id")}
 try:
  project_cfg=resolve_project_vercel_preview_config(repository=item.repository,manifest=item.manifest)
 except ValueError as exc:
  return {"claimed":False,"status":"blocked","run_id":item.run_id,"error":str(exc)}
 readiness=verified_preview_readiness(project_cfg.mode)
 if not readiness.ready:return {"claimed":False,"status":"blocked","run_id":item.run_id,"missing":list(readiness.missing),"preview_mode":project_cfg.mode}
 if project_cfg.mode=="github":
  provider=GitHubVercelPreviewAdapter(github_vercel_config_from_env(item.repository,pull_request_number=item.pr_number))
 else:
  vercel_cfg=VercelPreviewConfig(token=os.environ["VERCEL_TOKEN"],team_id=project_cfg.team_id or "",project_name=project_cfg.project_name or "",github_org=project_cfg.github_org,github_repo=project_cfg.github_repo)
  provider=VercelPreviewAdapter(vercel_cfg)
 deployment=DurablePreviewAdapter(provider,SupabaseDeploymentEvidenceStore(),run_id=item.run_id)
 browser=CommandBrowserEvidenceAdapter(CommandBrowserEvidenceConfig.from_env())
 request=DeploymentRequest(item.project_key,ReleaseEnvironment.PREVIEW,item.candidate_commit,EvidenceBundle(item.candidate_commit,item.candidate_commit,"success",metadata={"quality_gate_passed":True,"source":"durable_quality_gate"}))
 try:
  verified=VerifiedPreviewCoordinator().execute(run_id=item.run_id,request=request,deployment_adapter=deployment,browser_adapter=browser,evidence_recorder=BrowserEvidenceRecorder(store))
 except PreviewDeferred as exc:
  store.record_resource_limit_signal(
   provider="vercel",resource_key="team",metric_key="deployments_daily",
   quality="provider_blocked",source="preview-runtime-signal",unit="deployments",window_key="rolling_24h",
   metadata={"repository":item.repository,"candidate_commit":item.candidate_commit,"deployment_ref":exc.deployment.deployment_ref},
  )
  store.record_audit_event(
   run_id=item.run_id,event_type="preview.deferred",
   payload={"candidate_commit":item.candidate_commit,"status":exc.deployment.status,"deployment_ref":exc.deployment.deployment_ref,"retry_after_hours":24},
   actor_ref="preview-followup",
  )
  return {"claimed":True,"status":exc.deployment.status,"run_id":item.run_id,"pr_number":item.pr_number,
   "preview_required":True,"deployment_ref":exc.deployment.deployment_ref,"retry_after_hours":24}
 except ValueError as exc:
  if str(exc)=="preview requires successful browser/e2e evidence":
   store.fail_preview(item.run_id,candidate_commit=item.candidate_commit,reason=str(exc))
  raise
 # A successful browser check does not authorize release if the PR or
 # its base moved while the deployment was being verified.
 refreshed_pr=github.get_pull_request(item.pr_number)
 if (getattr(refreshed_pr,"merged",False)
     or getattr(refreshed_pr,"state","open")!="open"
     or refreshed_pr.head_sha!=item.candidate_commit):
  raise RuntimeError("GitHub PR identity changed during verified Preview")
 _require_current_preview_base(github,refreshed_pr)
 store.record_resource_limit_signal(
  provider="vercel",resource_key="team",metric_key="deployments_daily",
  quality="unknown",source="preview-runtime-recovered",unit="deployments",window_key="rolling_24h",
  metadata={"repository":item.repository,"candidate_commit":item.candidate_commit,"deployment_ref":verified.deployment.deployment_ref},
 )
 trace=SupabaseTraceabilityStore()
 trace.record_delivery_evidence(
  run_id=item.run_id,evidence_type="preview",status="passed",evidence_ref=verified.deployment.deployment_ref,
  metadata={"candidate_commit":item.candidate_commit}
 )
 trace.record_delivery_evidence(
  run_id=item.run_id,evidence_type="browser_evidence",status="passed",evidence_ref=verified.deployment.deployment_ref,
  metadata={"candidate_commit":item.candidate_commit}
 )
 assessment,recorded=_assess_release_policy(
  run_id=item.run_id,candidate_commit=item.candidate_commit,changed_files=changed_files,
  risk=getattr(item,"risk",{}) or {},
 )
 if assessment.decision.blocked:
  return {"claimed":True,"status":"release_policy_blocked","run_id":item.run_id,"pr_number":item.pr_number,
   "preview_required":True,"preview_url":verified.deployment.preview_url,"deployment_ref":verified.deployment.deployment_ref,
   "policy_reasons":list(assessment.decision.reasons)}
 status=loop.finalize_verified_preview(session,verified)
 return {"claimed":True,"status":status,"run_id":item.run_id,"pr_number":item.pr_number,
  "preview_required":True,"preview_url":verified.deployment.preview_url,"deployment_ref":verified.deployment.deployment_ref,
  "release_report_id":recorded.get("report_id")}

def run_release_once(*,exclude_run_ids:tuple[str,...]=())->dict:
 queue=SupabaseReleaseFollowupQueue()
 item=queue.next_pending(exclude_run_ids=exclude_run_ids) if exclude_run_ids else queue.next_pending()
 if item is None:return {"claimed":False,"status":"empty"}
 github=GitHubRestAdapter(repository=item.repository)
 pr=github.get_pull_request(item.pr_number)
 if pr.head_sha!=item.candidate_commit:raise RuntimeError("GitHub PR head no longer matches verified release candidate")
 if str(getattr(pr,"base_ref",None) or "").startswith("preview/"):
  if item.merge_sha or item.release_source!="delivery":
   raise RuntimeError("nonproduction merge cannot use a production Console release receipt")
  # The runtime may OBSERVE a nonproduction merge performed elsewhere.
  # It must never merge, mark human_release, or promote production.
  if not getattr(pr,"merged",False):
   return {"claimed":True,"status":"awaiting_nonproduction_merge",
    "run_id":item.run_id,"pr_number":item.pr_number}
  receipt=verify_nonproduction_preview_merge(github,item,pr)
  if receipt is None:
   return {"claimed":True,"status":"wait_preview_merge_deployment",
    "run_id":item.run_id,"pr_number":item.pr_number}
  # Prevent TOCTOU: re-read the same PR identity after external status reads.
  checked=github.get_pull_request(item.pr_number)
  if (not checked.merged or checked.head_sha!=item.candidate_commit
      or checked.merge_commit_sha!=receipt["merge_sha"]
      or checked.base_ref!=receipt["base_ref"]
      or checked.head_ref!=item.branch
      or checked.head_repository!=item.repository):
   raise RuntimeError("nonproduction PR identity changed during observation")
  store=SupabaseDeliveryStore()
  postmerge=store.find_verified_nonproduction_browser_snapshot(
   project_id=item.project_id,repository=item.repository,merge_sha=receipt["merge_sha"])
  if postmerge is None:
   return {"claimed":True,"status":"wait_postmerge_browser_evidence",
    "run_id":item.run_id,"pr_number":item.pr_number}
  receipt={**receipt,
   "postmerge_browser_snapshot_id":postmerge["snapshot_id"],
   "postmerge_preview_url":postmerge["preview_url"],
   "verifier_run_id":str(postmerge["verifier_run_id"])}
  final_pr=github.get_pull_request(item.pr_number)
  if (not final_pr.merged or final_pr.merge_commit_sha!=receipt["merge_sha"]
      or final_pr.head_sha!=item.candidate_commit
      or final_pr.base_ref!=receipt["base_ref"]):
   raise RuntimeError("nonproduction PR identity changed after browser receipt")
  result=store.observe_nonproduction_preview_merge(
   run_id=item.run_id,pr_number=item.pr_number,candidate_commit=item.candidate_commit,
   merge_sha=receipt["merge_sha"],base_ref=receipt["base_ref"],
   verified_evidence=receipt)
  return {"claimed":True,"status":"integrated_nonproduction",
   "run_id":item.run_id,"pr_number":item.pr_number,
   "merge_sha":receipt["merge_sha"],
   "release_completed":False,"integration":result}
 if getattr(pr,"base_ref",None) not in (None,"main"):
  return {"claimed":True,"status":"nonproduction_candidate_not_released","run_id":item.run_id,"pr_number":item.pr_number}
 store=SupabaseDeliveryStore()
 if item.merge_sha:
  if not pr.merged or not pr.merge_commit_sha:
   raise RuntimeError("released Console report points to a pull request that is not merged")
  if pr.merge_commit_sha!=item.merge_sha:
   raise RuntimeError("GitHub merge SHA does not match durable Console release report")
  merged=store.finalize_console_human_release(
   item.run_id,candidate_commit=item.candidate_commit,merge_sha=item.merge_sha,
  )
  if item.issue_number is not None:
   github.close_issue(item.issue_number)
  merge_sha=item.merge_sha
 else:
  if item.issue_number is None:
   raise RuntimeError("legacy release followup requires GitHub issue binding")
  issue=github.get_issue(item.issue_number)
  loop=AutonomousGitHubLoop(github,store)
  session=GitHubWorkSession(issue,item.branch,item.run_id,"","",pr)
  merge_sha=loop.observe_manual_merge(session)
  if merge_sha is None:return {"claimed":True,"status":"awaiting_release","run_id":item.run_id,"pr_number":item.pr_number}
  merged={"status":"merged","idempotent":False}
 SupabaseTraceabilityStore().record_delivery_evidence(
  run_id=item.run_id,evidence_type="human_release",status="passed",evidence_ref=merge_sha,
  metadata={"source":"observed_manual_merge","pr_number":item.pr_number}
 )
 SupabaseReleasePolicyStore().mark_released(item.run_id,merge_sha)
 project_state=SupabaseProjectReleaseReconciler().reconcile(
  project_id=item.project_id,run_id=item.run_id,merge_sha=merge_sha
 )
 change_set=SupabaseChangeSetStore().finalize_released_run(item.run_id,merge_sha)
 SupabaseAgentScheduler().release_scopes(item.run_id)
 return {"claimed":True,"status":"merged","run_id":item.run_id,"pr_number":item.pr_number,"merge_sha":merge_sha,"change_set":change_set,"project_state":project_state,"run":merged}

def run_bounded_deterministic_lane(mode:str,worker_id:str,max_items:int,role:str|None=None)->dict:
 # No new reservations or paid model calls: delegates to existing guarded workers.
 if mode=="ci":
  return drain_waiting_followups(lambda ignored:run_ci_once(exclude_run_ids=ignored),max_items=max_items)
 if mode=="release":
  return drain_waiting_followups(lambda ignored:run_release_once(exclude_run_ids=ignored),max_items=max_items)
 if mode=="change-set-integration":
  callback=lambda:run_change_set_integration_once(worker_id);key="change_set_id"
 elif mode=="specialist":
  if role not in {"security","qa","operations"}:raise ValueError("valid specialist role required")
  callback=lambda:run_specialist_once(role,worker_id);key="job_id"
 else:raise ValueError("batch not permitted for this lane")
 return drain_deterministic_lane(callback,max_items=max_items,identity=key)

def run_retry_once(source_run_id:str,reason:str)->dict:
 if not source_run_id.strip():raise ValueError("source run id is required")
 if not reason.strip():raise ValueError("retry reason is required")
 return SupabaseRuntimeQueue().retry_failed_run(source_run_id,reason)

def run_replan_once(source_run_id:str)->dict:
 if not source_run_id.strip():raise ValueError("source run id is required")
 profiles=SupabaseAgentScheduler().profiles()
 return SupabaseRuntimeQueue().rebuild_team_plan(source_run_id,profiles)

def run_replay_once(source_run_id:str,mode:str="offline")->dict:
 if not source_run_id.strip():raise ValueError("source run id is required")
 replay=SupabaseProvenanceStore().create_replay(source_run_id,mode)
 return {
  "status":replay.status,"replay_id":replay.replay_id,"source_run_id":replay.source_run_id,
  "mode":replay.mode,"effect":replay.effect,"model_calls_allowed":replay.model_calls_allowed,
  "snapshot_hash":replay.snapshot_hash,
 }

def run_alerts_once()->dict:
 readiness=github_alerts_readiness()
 if not readiness.ready:return {"status":"blocked","published":0,"resolved":0,"missing":list(readiness.missing)}
 policy=SupabasePrimaryCostPolicyReader().read()
 health=SupabaseOperationalHealthReader().read(budget=policy.budget_usd)
 liveness=SupabaseSchedulerLivenessReader().read()
 repository=os.environ["FACTORY_ALERTS_GITHUB_REPOSITORY"]
 github=GitHubRestAdapter(repository=repository)
 # Native heartbeat telemetry proves delivery, not successful workflow completion.
 # A read-only GitHub API failure is itself a warning; never silently resolve
 # the pipeline issue or prevent other alerts from being reconciled.
 try:
  native=GithubNativeScheduledRunReader(github).read()
  pipeline_alerts=evaluate_native_scheduler_health(native)
 except (RuntimeError, ValueError, OSError):
  from .operational_alerts import OperationalAlert
  pipeline_alerts=(OperationalAlert(
   "scheduler_pipeline","warning",
   "Native GitHub Actions workflow results could not be verified"
  ),)
 alerts=(*evaluate_operational_alerts(health),*evaluate_scheduler_liveness(liveness),*pipeline_alerts)
 adapter=GitHubIssueAlertAdapter(github)
 results=adapter.publish_many(alerts)
 resolved=adapter.resolve_inactive(active_codes={alert.code for alert in alerts},known_codes=OPERATIONAL_ALERT_CODES)
 return {
  "status":"ok",
  "published":sum(1 for result in results if result.created),
  "resolved":len(resolved),
  "alerts":[{"code":result.code,"created":result.created,"issue_number":result.issue_number} for result in results],
  "resolutions":[{"code":result.code,"issue_number":result.issue_number} for result in resolved],
 }

def require_dispatch_claim_readiness()->None:
 # The protected product-stage job authenticated Primary and exposes only a
 # bounded readiness signal, not API secrets, to the dispatcher.
 require_primary_runtime_enabled()
 if os.getenv("FACTORY_DISPATCH_PRIMARY_READY")!="true":
  raise PermissionError("dispatcher has no verified primary-auth readiness")
 # Ledger is checked before claiming; the Direct worker repeats its own check.
 require_paid_runtime_budget()

def allowed_dispatch_routes()->tuple[str,...]:
 # The Direct route may claim ONLY when authenticated in the protected job
 # and the real paid ledger permits it. Never pass model keys to dispatcher.
 enabled=[]
 try:
  require_dispatch_claim_readiness()
 except (RuntimeError,PermissionError,ValueError,InvalidOperation):
  pass
 else:
  enabled.append("direct")
 # Automatic Codex is intentionally ineligible without a separate WIF/token
 # preflight. Only the existing no-model manual handoff can be selected.
 # Until automatic/manual Codex claims are isolated in the Control Plane,
 # a protected auth-ready boolean alone is NOT sufficient to claim work.
 if (os.getenv("FACTORY_CODEX_ENABLED")=="true"
     and os.getenv("FACTORY_DISPATCH_CODEX_READY")=="true"
     and os.getenv("FACTORY_CODEX_COST_APPROVED")=="true"):
  enabled.append("codex")
 elif (os.getenv("FACTORY_CODEX_ENABLED")!="true"
       and os.getenv("FACTORY_CODEX_MANUAL_FALLBACK_ENABLED")=="true"
       and os.getenv("FACTORY_DISPATCH_MANUAL_CODEX_READY")=="true"):
  enabled.append("codex")
 return tuple(enabled)

def run_dispatch_once(project_key:str|None=None,max_items:int=6)->dict:
 allowed_routes=allowed_dispatch_routes()
 if not allowed_routes:
  return {"claimed":False,"status":"blocked_executor_readiness",
   "routed":[],"scheduling":{"attempted":0,"assigned":0,"no_eligible_slot":False},
   "matrix":{"direct":[],"codex":[]}}
 dispatch=SupabaseBacklogDispatch();scheduler=SupabaseAgentScheduler();routed=[]
 codex_mode="automatic" if os.getenv("FACTORY_CODEX_ENABLED")=="true" else ("manual" if "codex" in allowed_routes else None)
 scheduling={"attempted":0,"assigned":0,"no_eligible_slot":False}
 for _ in range(max(1,min(max_items,32))):
  decision=(dispatch.dispatch_next(project_key,allowed_routes=allowed_routes,codex_mode=codex_mode)
    if project_key else dispatch.dispatch_next_any(allowed_routes=allowed_routes,codex_mode=codex_mode))
  if decision is None:break
  if not isinstance(decision.run_id,str) or not decision.run_id.strip():
   raise RuntimeError("atomic dispatcher did not return a durable run ID")
  routed.append({"route":decision.execution.route.value,"run_id":decision.run_id,
   "human_gate_required":decision.execution.human_gate_required,
   "codex_level":decision.execution.codex.level})
  if decision.execution.route.value=="codex":
   if codex_mode=="manual":continue
   if codex_mode!="automatic":raise RuntimeError("Codex route requires explicit mode")
   if decision.execution.human_gate_required:continue
   scheduling["attempted"]+=1
   assignment=scheduler.schedule_eligible_codex(run_id=decision.run_id,project_key=project_key)
   if assignment is None:
    scheduling["no_eligible_slot"]=True
    break
   scheduling["assigned"]+=1
   continue
  if decision.execution.route.value!="direct":
   raise RuntimeError("unsupported dispatch execution route")
  if decision.execution.human_gate_required:
   # Atomic claim is awaiting_human: no agent reservation before approval.
   continue
  scheduling["attempted"]+=1
  try:
   assignment=scheduler.schedule_eligible_direct(
     run_id=decision.run_id,project_key=project_key)
  except RuntimeError as exc:
   if "no eligible agent slot" not in str(exc):raise
   scheduling["no_eligible_slot"]=True
   break
  if assignment is None:
   scheduling["no_eligible_slot"]=True
   break
  scheduling["assigned"]+=1
 if codex_mode=="automatic" and "codex" in allowed_routes and not scheduling["no_eligible_slot"]:
  for _ in range(max(1,min(max_items,32))):
   assignment=scheduler.schedule_eligible_codex(project_key=project_key)
   if assignment is None:break
   scheduling["attempted"]+=1
   scheduling["assigned"]+=1
 # Resume Direct runs that became eligible after human approval or freed slots.
 # Never do this for Codex or without approved Primary/real budget readiness.
 resumed_direct=0
 if "direct" in allowed_routes and not scheduling["no_eligible_slot"]:
  for _ in range(max(1,min(max_items,32))):
   try:
    assignment=scheduler.schedule_eligible_direct(project_key=project_key)
   except RuntimeError as exc:
    if "no eligible agent slot" not in str(exc):raise
    scheduling["no_eligible_slot"]=True
    break
   if assignment is None:break
   scheduling["attempted"]+=1
   scheduling["assigned"]+=1
   resumed_direct+=1
 matrix=SupabaseAdaptiveConcurrencyController().work_matrix(max_items)
 out={"claimed":bool(routed),"status":"routed" if routed else ("scheduled_existing" if resumed_direct else "empty"),"routed":routed,"scheduling":scheduling,"resumed_direct":resumed_direct,"matrix":matrix}
 if routed:
  out.update(routed[0])
 return out


def run_project_control_settlement()->dict:
    """Settle only already-quiescent projects; never change a running project."""
    from .project_control_settlement import SupabaseProjectControlSettlement
    return SupabaseProjectControlSettlement().settle_pending()

from .project_control_wake_outbox import ControlWakeOutbox

def main()->int:
 p=argparse.ArgumentParser(prog="factory-runtime");p.add_argument("--worker-id",default=f"worker-{socket.gethostname()}");p.add_argument("--agent-key");p.add_argument("--run-id");p.add_argument("--mode",choices=("product","product-readiness-evidence","dispatch","agent-matrix","direct","codex","change-set-integration","recovery","project-control-settle","project-control-wake","health","alerts","ci","specialist","release","preview","preview-probe","schedule-probe","backlog-audit","github-preflight","delivery-metrics","replay","replan","retry","reconcile-ci-candidate"),default="product");p.add_argument("--project-key");p.add_argument("--source-run-id");p.add_argument("--pr-number",type=int);p.add_argument("--retry-reason");p.add_argument("--replay-mode",choices=("offline","shadow"),default="offline");p.add_argument("--specialist-role",choices=("security","qa","operations"));p.add_argument("--max-items",type=int,default=6);p.add_argument("--batch-items",type=int,default=1);p.add_argument("--max-attempts",type=int,default=3)
 args=p.parse_args()
 if args.mode=="reconcile-ci-candidate":
  if not args.source_run_id or not args.pr_number:raise ValueError("--source-run-id and --pr-number required")
  out=reconcile_ci_candidate_once(expected_run_id=args.source_run_id,expected_pr_number=args.pr_number)
 elif args.mode=="health":out=run_health_once()
 elif args.mode=="product-readiness-evidence":out=record_product_worker_readiness()
 elif args.mode=="github-preflight":out=run_project_github_preflight(args.project_key)
 elif args.mode=="schedule-probe":out=SupabaseScheduleProbe().probe()
 elif args.mode=="backlog-audit":out=SupabaseBacklogInventoryReader().read()
 elif args.mode=="delivery-metrics":
  if not args.source_run_id:raise ValueError("--source-run-id is required for delivery-metrics mode")
  out=SupabaseDeliveryMetricsReader().read(args.source_run_id).as_json()
 elif args.mode=="replay":
  if not args.source_run_id:raise ValueError("--source-run-id is required for replay mode")
  out=run_replay_once(args.source_run_id,args.replay_mode)
 elif args.mode=="replan":
  if not args.source_run_id:raise ValueError("--source-run-id is required for replan mode")
  out=run_replan_once(args.source_run_id)
 elif args.mode=="retry":
  if not args.source_run_id:raise ValueError("--source-run-id is required for retry mode")
  if not args.retry_reason:raise ValueError("--retry-reason is required for retry mode")
  out=run_retry_once(args.source_run_id,args.retry_reason)
 elif args.mode=="agent-matrix":out=SupabaseAgentScheduler().work_matrix(args.max_items)
 elif args.mode=="preview-probe":out=run_preview_probe_once()
 elif args.mode=="preview":out=run_preview_once()
 elif args.mode=="release":out=run_bounded_deterministic_lane("release",args.worker_id,args.batch_items)
 elif args.mode=="ci":out=run_bounded_deterministic_lane("ci",args.worker_id,args.batch_items)
 elif args.mode=="specialist":
  if not args.specialist_role:raise ValueError("--specialist-role is required for specialist mode")
  out=run_bounded_deterministic_lane("specialist",args.worker_id,args.batch_items,args.specialist_role)
 elif args.mode=="alerts":out=run_alerts_once()
 elif args.mode=="recovery":out=run_recovery_once(args.max_attempts)
 elif args.mode=="project-control-settle":out=run_project_control_settlement()
 elif args.mode=="project-control-wake":out=ControlWakeOutbox().observe_one(owner=args.worker_id)
 elif args.mode=="direct":out=run_direct_once(args.worker_id,args.agent_key,args.run_id)
 elif args.mode=="codex":out=run_codex_once(args.worker_id,args.agent_key,args.run_id)
 elif args.mode=="change-set-integration":out=run_bounded_deterministic_lane("change-set-integration",args.worker_id,args.batch_items)
 elif args.mode=="dispatch":out=run_dispatch_once(args.project_key,args.max_items)
 else:out=run_product_once(args.worker_id)
 print(json.dumps(out));return 0 if not out.get("error") else 2
if __name__=="__main__":raise SystemExit(main())
