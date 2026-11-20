"""Local-only Product Stage warmup before any durable claim.

The socket has no timeout; SIGALRM limits the overall warmup process.
This never alters workers, queues, model policy or git repositories.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_product_factory.private_model_warmup import WarmupBlocked, warmup_if_pending


@contextmanager
def bounded_process(seconds: int):
    def expire(signum, frame):
        raise TimeoutError("cold-start watchdog expired")
    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def save_receipt(path: Path, result: dict) -> None:
    if not path.parent.is_dir() or path.is_symlink():
        raise OSError("receipt path unavailable")
    fd, tmp = tempfile.mkstemp(prefix=".ibm-warm-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(prog="factory-infodive-cold-start")
    parser.add_argument("--when-product-pending", required=True,
                        action="store_true")
    parser.add_argument("--max-wait-seconds", type=int, default=1800)
    parser.add_argument("--receipt",
                        default="/var/lib/ai-product-factory/ibm-warmup-latest.json")
    args = parser.parse_args(argv)
    if not 60 <= args.max_wait_seconds <= 3600:
        parser.error("max-wait-seconds out of range")
    try:
        with bounded_process(args.max_wait_seconds):
            data = warmup_if_pending(os.environ)
    except Exception as exc:
        reason = (
            "model cold-start watchdog expired" if isinstance(exc, TimeoutError)
            else str(exc) if isinstance(exc, WarmupBlocked)
            else "model warmup unavailable"
        )
        data = {"schema": "factory-ibm-vps-warmup-v1",
                "status": "blocked", "reason": reason,
                "model_invoked": None, "run_claimed": False}
    data["recorded_at"] = datetime.now(timezone.utc).isoformat()
    try:
        save_receipt(Path(args.receipt), data)
    except Exception:
        print(json.dumps({"status": "blocked",
                          "reason": "warmup receipt not durable"}))
        return 2
    print(json.dumps(data, sort_keys=True))
    return 0 if data["status"] in ("idle", "warmed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
