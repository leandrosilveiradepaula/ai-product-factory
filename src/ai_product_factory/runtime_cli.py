from __future__ import annotations
import argparse,json,socket
from .model_executor import ModelExecutor
from .openai_provider import OpenAIResponsesProvider
from .product_stage_executor import ProductStageExecutor
from .runtime_auth import AuthKind,RuntimeAuthResolver
from .runtime_worker import RuntimeWorker
from .supabase_runtime_queue import SupabaseRuntimeQueue

def build_handler():
 auth=RuntimeAuthResolver().resolve()
 if auth.kind == AuthKind.OPENAI_API_KEY:
  return ProductStageExecutor(ModelExecutor(primary=OpenAIResponsesProvider()))
 raise RuntimeError(f"No supported primary-model runtime auth is configured (resolved: {auth.kind.value})")

def main()->int:
 p=argparse.ArgumentParser(prog="factory-runtime");p.add_argument("--worker-id",default=f"worker-{socket.gethostname()}");args=p.parse_args()
 try:handler=build_handler()
 except RuntimeError as exc:
  print(json.dumps({"claimed":False,"status":"blocked","error":str(exc)}));return 2
 result=RuntimeWorker(queue=SupabaseRuntimeQueue(),handler=handler,worker_id=args.worker_id).run_once()
 print(json.dumps({"claimed":result is not None,"status":result.status.value if result else None,"error":result.error if result else None}))
 return 0 if result is None or result.error is None else 1
if __name__=="__main__":raise SystemExit(main())
