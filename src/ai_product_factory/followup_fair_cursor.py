"""Server-side advisory fairness cursor backed by existing append-only audit events.

This does not reserve or authorize a task, call a model, or claim a lease.
The authenticated Control Plane remains authoritative for all worker effects.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .supabase_server import resolve_supabase_server_config


class SupabaseFollowupFairCursor:
    def __init__(self, *, url: str | None = None, secret_key: str | None = None,
                 service_role_key: str | None = None) -> None:
        config = resolve_supabase_server_config(
            url=url, secret_key=secret_key, service_role_key=service_role_key)
        self.url = config.url
        self.headers = config.headers

    @staticmethod
    def _lane(lane: str) -> None:
        if lane not in {"ci", "release"}:
            raise ValueError("unsupported follow-up cursor lane")

    @staticmethod
    def _offset(value: int) -> None:
        if type(value) is not int or not 0 <= value <= 1000000 or value % 8:
            raise ValueError("invalid bounded follow-up cursor position")

    def read_offset(self, lane: str) -> int:
        self._lane(lane)
        path = ("factory_audit_events?select=id,payload"
                "&event_type=eq.followup.fair_scan_reserved"
                "&actor_ref=eq." + lane + "-followup&order=id.desc&limit=1")
        request = urllib.request.Request(
            self.url + "/rest/v1/" + path, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                rows = json.loads(response.read().decode())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError("follow-up cursor unavailable") from exc
        if not isinstance(rows, list) or len(rows) > 1:
            raise RuntimeError("invalid durable follow-up cursor response")
        if not rows:
            return 0
        row = rows[0]
        if (not isinstance(row, dict) or type(row.get("id")) is not int
            or row["id"] < 1 or not isinstance(row.get("payload"), dict)):
            raise RuntimeError("invalid durable follow-up cursor row")
        data = row["payload"]
        if data.get("version") != 1 or data.get("lane") != lane:
            raise RuntimeError("unexpected durable follow-up cursor format")
        offset = data.get("next_offset")
        try:
            self._offset(offset)
        except ValueError:
            raise RuntimeError("invalid durable follow-up cursor position") from None
        return offset

    def reserve_next(self, lane: str, next_offset: int) -> None:
        self._lane(lane)
        self._offset(next_offset)
        event = {
            "actor_type": "system", "actor_ref": lane + "-followup",
            "event_type": "followup.fair_scan_reserved",
            "payload": {"version": 1, "lane": lane,
                        "next_offset": next_offset},
        }
        request = urllib.request.Request(
            self.url + "/rest/v1/factory_audit_events",
            headers={**self.headers, "Content-Type": "application/json",
                     "Prefer": "return=minimal"},
            method="POST", data=json.dumps(event).encode())
        try:
            with urllib.request.urlopen(request, timeout=30):
                pass
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("follow-up cursor reservation failed") from exc
