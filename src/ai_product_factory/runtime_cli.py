from __future__ import annotations
import argparse,json,os,socket
from decimal import Decimal
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
from .codex_cli_producer import CodexCLIProducer
from .codex_usage import SupabaseCodexUsageRecorder
from .implementation_producer import ModelImplementationProducer
from .execution_worker import DirectExecutionWorker
from .github_rest import GitHubRestAdapter
from .autonomous_github import AutonomousGitHubLoop,GitHubWorkSession
from .issue_materializer import GitHubIssueMaterializer
from .supabase_issue_binding import SupabaseIssueBindingStore
from .supabase_delivery_store import SupabaseDeliveryStore
from .cost_policy import require_cost_ceiling
from .integration_readiness import github_alerts_readiness,github_vercel_preview_readiness,vercel_preview_readiness,verified_preview_readiness
from .operational_alerts import evaluate_operational_alerts
from .supabase_operational_health import SupabaseOperationalHealthReader
from .github_alert_adapter import GitHubIssueAlertAdapter
from .ci_followup_queue import SupabaseCIFollowupQueue
from .release_followup_queue import SupabaseReleaseFollowupQueue
from .preview_followup_queue import SupabasePreviewFollowupQueue
from .project_preview_config import resolve_project_vercel_preview_config
from .preview_policy import evaluate_preview_applicability
from .vercel_preview import VercelPreviewAdapter,VercelPreviewConfig
from .github_vercel_preview import GitHubVercelPreviewAdapter,config_from_env as github_vercel_config_from_env
from .command_browser_evidence import CommandBrowserEvidenceAdapter,CommandBrowserEvidenceConfig
from .supabase_deployment import DurablePreviewAdapter,SupabaseDeploymentEvidenceStore
from .browser_evidence_store import BrowserEvidenceRecorder
from .preview_flow import VerifiedPreviewCoordinator
from .deployment import DeploymentRequest
from .release_policy import ReleaseEnvironment
from .evidence import EvidenceBundle
from .review_gate import EvalResult,evaluate_quality_gate

def require_primary_runtime_enabled()->None:
 if os.getenv("FACTORY_PRIMARY_MODEL_ENABLED")!="true":raise PermissionError("primary model execution is disabled")

def require_paid_runtime_budget(*, health_reader=None)->None:
 budget_raw=os.getenv("FACTORY_MODEL_BUDGET_USD")
 reserve_raw=os.getenv("FACTORY_MODEL_RESERVE_USD")
 budget=Decimal(budget_raw) if budget_raw else None
 reserve=Decimal(reserve_raw) if reserve_raw else None
 if budget is None or reserve is None:
  require_cost_ceiling(budget=budget,known_spend=Decimal("0"),reserved_cost=reserve,strict=True)
  return
 reader=health_reader or SupabaseOperationalHealthReader()
 health=reader.read(budget=budget)
 if health.unknown_cost_events>0:
  raise PermissionError("paid usage ledger contains unknown-cost events")
 require_cost_ceiling(budget=budget,known_spend=health.known_cost,reserved_cost=reserve,strict=True)

def require_codex_runtime_enabled()->None:
 if os.getenv("FACTORY_CODEX_ENABLED")!="true":raise PermissionError("Codex execution is disabled")
 missing=[name for name in ("OPENAI_FEDERATION_RULE_ID","OPENAI_WIF_AUDIENCE","OPENAI_IDENTITY_TOKEN_FILE","FACTORY_GITHUB_TOKEN") if not os.getenv(name,"").strip()]
 if missing:raise PermissionError("Codex runtime configuration is incomplete: "+", ".join(missing))
 if not os.path.isfile(os.environ["OPENAI_IDENTITY_TOKEN_FILE"]):raise PermissionError("Codex identity token file does not exist")

def build_handler():
 require_primary_runtime_enabled()
 auth=RuntimeAuthResolver().resolve()
 if auth.kind == AuthKind.OPENAI_API_KEY:
  return ProductStageExecutor(ModelExecutor(primary=MeteredPrimaryProvider(OpenAIResponsesProvider())))
 raise RuntimeError(f"No supported primary-model runtime auth is configured (resolved: {auth.kind.value})")

def run_recovery_once(max_attempts:int=3)->dict:
 return SupabaseRuntimeQueue().recover_expired(max_attempts)

def run_product_once(worker_id:str)->dict:
 try:
  require_primary_runtime_enabled()
  require_paid_runtime_budget()
  handler=build_handler()
 except (RuntimeError,PermissionError) as exc:return {"claimed":False,"status":"blocked","error":str(exc)}
 result=RuntimeWorker(queue=SupabaseRuntimeQueue(),handler=handler,worker_id=worker_id).run_once()
 return {"claimed":result is not None,"status":result.status.value if result else None,"error":result.error if result else None}

def run_direct_once(worker_id:str)->dict:
 try:
  require_primary_runtime_enabled()
  auth=RuntimeAuthResolver().resolve()
  if auth.kind != AuthKind.OPENAI_API_KEY:raise RuntimeError(f"No supported primary-model runtime auth is configured (resolved: {auth.kind.value})")
  require_paid_runtime_budget()
 except (RuntimeError,PermissionError) as exc:return {"claimed":False,"status":"blocked","error":str(exc)}
 item=SupabaseDirectRunQueue().claim_next(worker_id)
 if item is None:return {"claimed":False,"status":"empty"}
 producer=ModelImplementationProducer(ModelExecutor(primary=MeteredPrimaryProvider(OpenAIResponsesProvider())))
 github=GitHubRestAdapter(repository=item.repository)
 loop=AutonomousGitHubLoop(github,SupabaseDeliveryStore())
 materializer=GitHubIssueMaterializer(github=github,binding=SupabaseIssueBindingStore())
 session=DirectExecutionWorker(loop=loop,producer=producer,issue_materializer=materializer).execute(item)
 if session.pull_request is None:raise RuntimeError("GitHub delivery did not open a pull request")
 return {"claimed":True,"status":"pr_open","run_id":item.run_id,"pr_number":session.pull_request.number}

def run_codex_once(worker_id:str)->dict:
 try:
  require_codex_runtime_enabled()
 except (RuntimeError,PermissionError) as exc:return {"claimed":False,"status":"blocked","error":str(exc)}
 item=SupabaseCodexRunQueue().claim_next(worker_id)
 if item is None:return {"claimed":False,"status":"empty"}
 usage=SupabaseCodexUsageRecorder()
 producer=CodexCLIProducer(on_invoke=lambda:usage.record_invocation(run_id=item.run_id,reported_usage={"status":"started","policy_level":item.codex_level}))
 github=GitHubRestAdapter(repository=item.repository)
 store=SupabaseDeliveryStore()
 loop=AutonomousGitHubLoop(github,store)
 materializer=GitHubIssueMaterializer(github=github,binding=SupabaseIssueBindingStore())
 session=DirectExecutionWorker(loop=loop,producer=producer,issue_materializer=materializer).execute(item)
 if session.pull_request is None:raise RuntimeError("GitHub delivery did not open a pull request")
 return {"claimed":True,"status":"pr_open","run_id":item.run_id,"pr_number":session.pull_request.number}

def run_health_once()->dict:
 auth=RuntimeAuthResolver().resolve()
 vercel=vercel_preview_readiness();github_vercel=github_vercel_preview_readiness();alerts=github_alerts_readiness()
 codex_missing=[name for name in ("OPENAI_FEDERATION_RULE_ID","OPENAI_WIF_AUDIENCE","OPENAI_IDENTITY_TOKEN_FILE","FACTORY_GITHUB_TOKEN") if not os.getenv(name,"").strip()]
 return {"status":"healthy","control_plane_configured":bool(os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY"))),"primary_auth":auth.kind.value,"primary_enabled":os.getenv("FACTORY_PRIMARY_MODEL_ENABLED")=="true","budget_configured":bool(os.getenv("FACTORY_MODEL_BUDGET_USD")),"reservation_configured":bool(os.getenv("FACTORY_MODEL_RESERVE_USD")),"codex":{"enabled":os.getenv("FACTORY_CODEX_ENABLED")=="true","configured":not codex_missing,"ready":os.getenv("FACTORY_CODEX_ENABLED")=="true" and not codex_missing and os.path.isfile(os.getenv("OPENAI_IDENTITY_TOKEN_FILE","")),"missing":codex_missing},"vercel_preview_api":{"enabled":vercel.enabled,"configured":vercel.configured,"ready":vercel.ready,"missing":list(vercel.missing)},"vercel_preview_github":{"enabled":github_vercel.enabled,"configured":github_vercel.configured,"ready":github_vercel.ready,"missing":list(github_vercel.missing)},"github_alerts":{"enabled":alerts.enabled,"configured":alerts.configured,"ready":alerts.ready,"missing":list(alerts.missing)}}

def run_ci_once()->dict:
 item=SupabaseCIFollowupQueue().next_pending()
 if item is None:return {"claimed":False,"status":"empty"}
 github=GitHubRestAdapter(repository=item.repository)
 issue=github.get_issue(item.issue_number)
 pr=github.get_pull_request(item.pr_number)
 if pr.head_sha!=item.candidate_commit:raise RuntimeError("GitHub PR head no longer matches durable candidate commit")
 store=SupabaseDeliveryStore()
 loop=AutonomousGitHubLoop(github,store)
 session=GitHubWorkSession(issue,item.branch,item.run_id,"","",pr)
 decision=loop.evaluate(session,human_gate_required=item.human_gate_required)
 if decision.action.value=="preview_ready":
  quality=evaluate_quality_gate(evals=(EvalResult("github_ci",True,required=True),))
  if not quality.passed:raise RuntimeError("quality gate did not pass after successful CI")
  store.record_evaluation(run_id=item.run_id,eval_type="quality_gate",status="success",baseline_ref=item.candidate_commit,result={"passed":True,"reasons":list(quality.reasons),"source":"github_ci"})
  store.record_audit_event(run_id=item.run_id,event_type="quality_gate.passed",payload={"candidate_commit":item.candidate_commit,"reasons":list(quality.reasons)},actor_ref="ci-followup")
 return {"claimed":True,"status":decision.action.value,"run_id":item.run_id,"pr_number":item.pr_number,"ci_state":decision.ci_state.value}

def run_preview_probe_once()->dict:
 item=SupabasePreviewFollowupQueue().next_pending()
 if item is None:return {"claimed":False,"status":"empty","preview_required":False}
 github=GitHubRestAdapter(repository=item.repository)
 pr=github.get_pull_request(item.pr_number)
 if pr.head_sha!=item.candidate_commit:raise RuntimeError("GitHub PR head no longer matches preview candidate")
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
 issue=github.get_issue(item.issue_number)
 pr=github.get_pull_request(item.pr_number)
 if pr.head_sha!=item.candidate_commit:raise RuntimeError("GitHub PR head no longer matches preview candidate")
 changed_files=github.get_pull_request_files(item.pr_number)
 applicability=evaluate_preview_applicability(manifest=item.manifest,changed_files=changed_files)
 store=SupabaseDeliveryStore()
 loop=AutonomousGitHubLoop(github,store)
 session=GitHubWorkSession(issue,item.branch,item.run_id,"","",pr)
 if not applicability.required:
  status=loop.finalize_preview_not_required(session,reason=applicability.reason,changed_files=changed_files)
  return {"claimed":True,"status":status,"run_id":item.run_id,"pr_number":item.pr_number,"preview_required":False,"reason":applicability.reason}
 try:
  project_cfg=resolve_project_vercel_preview_config(repository=item.repository,manifest=item.manifest)
 except ValueError as exc:
  return {"claimed":False,"status":"blocked","run_id":item.run_id,"error":str(exc)}
 readiness=verified_preview_readiness(project_cfg.mode)
 if not readiness.ready:return {"claimed":False,"status":"blocked","run_id":item.run_id,"missing":list(readiness.missing),"preview_mode":project_cfg.mode}
 if project_cfg.mode=="github":
  provider=GitHubVercelPreviewAdapter(github_vercel_config_from_env(item.repository))
 else:
  vercel_cfg=VercelPreviewConfig(token=os.environ["VERCEL_TOKEN"],team_id=project_cfg.team_id or "",project_name=project_cfg.project_name or "",github_org=project_cfg.github_org,github_repo=project_cfg.github_repo)
  provider=VercelPreviewAdapter(vercel_cfg)
 deployment=DurablePreviewAdapter(provider,SupabaseDeploymentEvidenceStore(),run_id=item.run_id)
 browser=CommandBrowserEvidenceAdapter(CommandBrowserEvidenceConfig.from_env())
 request=DeploymentRequest(item.project_key,ReleaseEnvironment.PREVIEW,item.candidate_commit,EvidenceBundle(item.candidate_commit,item.candidate_commit,"success",metadata={"quality_gate_passed":True,"source":"durable_quality_gate"}))
 verified=VerifiedPreviewCoordinator().execute(run_id=item.run_id,request=request,deployment_adapter=deployment,browser_adapter=browser,evidence_recorder=BrowserEvidenceRecorder(store))
 status=loop.finalize_verified_preview(session,verified)
 return {"claimed":True,"status":status,"run_id":item.run_id,"pr_number":item.pr_number,"preview_required":True,"preview_url":verified.deployment.preview_url,"deployment_ref":verified.deployment.deployment_ref}

def run_release_once()->dict:
 item=SupabaseReleaseFollowupQueue().next_pending()
 if item is None:return {"claimed":False,"status":"empty"}
 github=GitHubRestAdapter(repository=item.repository)
 issue=github.get_issue(item.issue_number)
 pr=github.get_pull_request(item.pr_number)
 if pr.head_sha!=item.candidate_commit:raise RuntimeError("GitHub PR head no longer matches verified release candidate")
 store=SupabaseDeliveryStore()
 loop=AutonomousGitHubLoop(github,store)
 session=GitHubWorkSession(issue,item.branch,item.run_id,"","",pr)
 merge_sha=loop.observe_manual_merge(session)
 if merge_sha is None:return {"claimed":True,"status":"awaiting_release","run_id":item.run_id,"pr_number":item.pr_number}
 return {"claimed":True,"status":"merged","run_id":item.run_id,"pr_number":item.pr_number,"merge_sha":merge_sha}

def run_alerts_once()->dict:
 readiness=github_alerts_readiness()
 if not readiness.ready:return {"status":"blocked","published":0,"missing":list(readiness.missing)}
 budget_raw=os.getenv("FACTORY_MODEL_BUDGET_USD")
 budget=Decimal(budget_raw) if budget_raw else None
 health=SupabaseOperationalHealthReader().read(budget=budget)
 alerts=evaluate_operational_alerts(health)
 if not alerts:return {"status":"ok","published":0,"alerts":[]}
 repository=os.environ["FACTORY_ALERTS_GITHUB_REPOSITORY"]
 results=GitHubIssueAlertAdapter(GitHubRestAdapter(repository=repository)).publish_many(alerts)
 return {"status":"ok","published":sum(1 for result in results if result.created),"alerts":[{"code":result.code,"created":result.created,"issue_number":result.issue_number} for result in results]}

def run_dispatch_once(project_key:str|None=None)->dict:
 dispatch=SupabaseBacklogDispatch()
 decision=dispatch.dispatch_next(project_key) if project_key else dispatch.dispatch_next_any()
 if decision is None:return {"claimed":False,"status":"empty"}
 return {"claimed":True,"status":"routed","route":decision.execution.route.value,"human_gate_required":decision.execution.human_gate_required,"codex_level":decision.execution.codex.level}

def main()->int:
 p=argparse.ArgumentParser(prog="factory-runtime");p.add_argument("--worker-id",default=f"worker-{socket.gethostname()}");p.add_argument("--mode",choices=("product","dispatch","direct","codex","recovery","health","alerts","ci","release","preview","preview-probe"),default="product");p.add_argument("--project-key");p.add_argument("--max-attempts",type=int,default=3)
 args=p.parse_args()
 if args.mode=="health":out=run_health_once()
 elif args.mode=="preview-probe":out=run_preview_probe_once()
 elif args.mode=="preview":out=run_preview_once()
 elif args.mode=="release":out=run_release_once()
 elif args.mode=="ci":out=run_ci_once()
 elif args.mode=="alerts":out=run_alerts_once()
 elif args.mode=="recovery":out=run_recovery_once(args.max_attempts)
 elif args.mode=="direct":out=run_direct_once(args.worker_id)
 elif args.mode=="codex":out=run_codex_once(args.worker_id)
 elif args.mode=="dispatch":out=run_dispatch_once(args.project_key)
 else:out=run_product_once(args.worker_id)
 print(json.dumps(out));return 0 if not out.get("error") else 2
if __name__=="__main__":raise SystemExit(main())
