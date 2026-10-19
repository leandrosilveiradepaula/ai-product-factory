"""Observe project control wakes; GitHub acceptance and runner observation differ."""
import json
import re
import urllib.error
import urllib.request

from .supabase_server import resolve_supabase_server_config


class ControlWakeOutbox:
    def __init__(self, *, url=None, service_role_key=None):
        cfg = resolve_supabase_server_config(url=url, service_role_key=service_role_key)
        self.url = cfg.url.rstrip("/")
        self.headers = cfg.headers

    def rpc(self, name, payload):
        req = urllib.request.Request(
            self.url + "/rest/v1/rpc/" + name,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={**self.headers, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("control wake RPC unavailable") from exc
        result = json.loads(raw) if raw else None
        if result is not None and not isinstance(result, dict):
            raise RuntimeError("invalid control wake RPC result")
        return result

    def observe_batch(self, *, owner, limit=16):
        if not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{3,128}", owner):
            raise ValueError("invalid control wake observer")
        if type(limit) is not int or not 1 <= limit <= 32:
            raise ValueError("invalid control wake batch size")
        ack = self.rpc("factory_observe_project_control_wakes", {"p_owner": owner, "p_limit": limit})
        if not isinstance(ack, dict) or type(ack.get("observed")) is not int or type(ack.get("suppressed")) is not int:
            raise RuntimeError("invalid wake observer receipt")
        a, b = ack["observed"], ack["suppressed"]
        if a < 0 or b < 0 or a + b > limit:
            raise RuntimeError("out-of-bounds wake observer receipt")
        return {"status": "observed" if a else "suppressed" if b else "empty",
                "observed": a > 0, "observed_count": a, "suppressed_count": b}

    def observe_one(self, *, owner):
        result = self.observe_batch(owner=owner, limit=1)
        return {"status": result["status"], "observed": result["observed"]}
