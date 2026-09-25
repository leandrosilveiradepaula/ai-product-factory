from __future__ import annotations
import argparse,json,socket
from .model_executor import ModelExecutor
from .openai_provider import OpenAIResponsesProvider
from .product_stage_executor import ProductStageExecutor
from .runtime_auth import AuthKind,RuntimeAuthResolver
from .runtime_worker import RuntimeWorker
from .supabase_runtime_queue import SupabaseRuntimeQueue
from .supabase_backlog_dispatch import SupabaseBacklogDispatch

def build_handler():
 auth=RuntimeAuthResolver().resolve()
 if auth.kind == AuthKind.OPENAI_API_KEY:
  return ProductStageExecutor(ModelExecutor(primary=OpenAIResponsesProvider()))
 raise RuntimeError(f"No supported primary-model runtime auth is configured (resolved: {auth.kind.value})")

def run_product_once(worker_id:str)->dict:
 try:handler=build_handler()
 except RuntimeError as exc:return {"claimed":False,"status":"blocked","error":str(exc)}
 result=RuntimeWorker(queue=SupabaseRuntimeQueue(),handler=handler,worker_id=worker_id).run_once()
 return {"claimed":result is not None,"status":result.status.value if result else None,"error":result.error if result else None}

def run_dispatch_once(project_key:str)->dict:
 decision=SupabaseBacklogDispatch().dispatch_next(project_key)
 if decision is None:return {"claimed":False,"status":"empty"}
 return {"claimed":True,"status":"routed","route":decision.execution.route.value,"human_gate_required":decision.execution.human_gate_required,"codex_level":decision.execution.codex.level}

def main()->int:
 p=argparse.ArgumentParser(prog="factory-runtime");p.add_argument("--worker-id",default=f"worker-{socket.gethostname()}");p.add_argument("--mode",choices=("product","dispatch"),default="product");p.add_argument("--project-key")
 args=p.parse_args()
 if args.mode=="dispatch":
  if not args.project_key:p.error("--project-key is required for dispatch mode")
  out=run_dispatch_once(args.project_key)
 else:out=run_product_once(args.worker_id)
 print(json.dumps(out));return 0 if not out.get("error") else 2
if __name__=="__main__":raise SystemExit(main())
