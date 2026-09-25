from __future__ import annotations
import argparse,json,socket
from .runtime_worker import DeterministicBootstrapHandler,RuntimeWorker
from .supabase_runtime_queue import SupabaseRuntimeQueue

def main()->int:
 p=argparse.ArgumentParser(prog="factory-runtime");p.add_argument("--worker-id",default=f"worker-{socket.gethostname()}");args=p.parse_args()
 result=RuntimeWorker(queue=SupabaseRuntimeQueue(),handler=DeterministicBootstrapHandler(),worker_id=args.worker_id).run_once()
 print(json.dumps({"claimed":result is not None,"status":result.status.value if result else None,"error":result.error if result else None}))
 return 0 if result is None or result.error is None else 1
if __name__=="__main__":raise SystemExit(main())
