from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote

from .supabase_server import resolve_supabase_server_config
from .post_release_readiness import summarize_released_product

_UUID=re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
_SHA=re.compile(r"^[0-9a-f]{40}$")
_PAGE=16
_MAX_PAGES=32


class ReleaseReconciliationRejected(RuntimeError):
    """SQL PT409: exact durable evidence requires operator reconciliation."""


class LegacyCapabilityUnavailable(RuntimeError):
    """The optional, versioned legacy-repair migration is not activated."""


class SupabaseProjectReleaseReconciler:
    """An observed human release is reconciled exactly once, atomically.

    The versioned RPC must exist; never fall back to PATCH+POST+POST. Production
    merges stay human-only and this adapter neither dispatches nor merges.
    """

    def __init__(self,*,url:str|None=None,secret_key:str|None=None,service_role_key:str|None=None)->None:
        cfg=resolve_supabase_server_config(url=url,secret_key=secret_key,service_role_key=service_role_key)
        self.url=cfg.url
        self.headers=cfg.headers

    def _request(self,method:str,path:str,payload:dict|None=None):
        if method not in {"GET","POST"} or (method=="POST" and not path.startswith("rpc/")):
            raise ValueError("release reconciler only allows read-only GET or RPC")
        body=None if payload is None else json.dumps(payload).encode()
        headers=self.headers if payload is None else {**self.headers,"Content-Type":"application/json"}
        req=urllib.request.Request(f"{self.url}/rest/v1/{path}",data=body,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                raw=response.read().decode()
        except urllib.error.HTTPError as exc:
            if (exc.code==404
                and path=="rpc/factory_pending_legacy_release_readiness_v1"):
                raise LegacyCapabilityUnavailable("legacy release migration not applied") from exc
            if exc.code==409:
                raise ReleaseReconciliationRejected("human release reconciliation rejected") from exc
            raise RuntimeError("release reconciliation Control Plane unavailable") from exc
        except (urllib.error.URLError,TimeoutError) as exc:
            raise RuntimeError("release reconciliation Control Plane unavailable") from exc
        return None if not raw else json.loads(raw)

    def require_atomic_capability(self)->None:
        """Read-only migration check before changing an observed human release.

        Without the new RPC an old mark-released call could persist 'merged'
        without an outbox, losing the opportunity for deterministic recovery.
        """
        value=self._request("POST","rpc/factory_pending_release_reconciliations_v1",{
            "p_after_event_id":0,"p_limit":1,
        })
        if not isinstance(value,list) or len(value)>1 or any(
            not isinstance(row,dict) for row in value
        ):
            raise RuntimeError("atomic release recovery capability unavailable")

    def reconcile(self,*,project_id:str,run_id:str,merge_sha:str,legacy:bool=False)->dict:
        if type(legacy) is not bool:
            raise ValueError("invalid legacy reconciliation mode")
        if (not isinstance(project_id,str) or not _UUID.fullmatch(project_id)
            or not isinstance(run_id,str) or not _UUID.fullmatch(run_id)
            or not isinstance(merge_sha,str) or not _SHA.fullmatch(merge_sha)):
            raise ValueError("invalid exact human-release identity")
        rows=self._request(
            "GET","factory_release_reports?"
            "select=project_id,run_id,status,candidate_commit,report"
            f"&project_id=eq.{quote(project_id,safe='')}"
            f"&run_id=eq.{quote(run_id,safe='')}&limit=2"
        )
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):
            raise RuntimeError("exact released report unavailable")
        summary=summarize_released_product(
            project_id=project_id,run_id=run_id,
            merge_sha=merge_sha,report_rows=rows,
        )
        if summary["report_verified"] is not True or summary["ready"] is not False:
            raise RuntimeError("release evidence is not verified for reconciliation")
        # Never fall back to REST split writes or use the normal RPC for a
        # historical catch-up: the wrapper locks the CURRENT release and
        # records an explicit correction audit in the same transaction.
        rpc=("rpc/factory_reconcile_latest_legacy_release_v1" if legacy
             else "rpc/factory_reconcile_observed_release_v1")
        receipt=self._request("POST",rpc,{
            "p_project_id":project_id,"p_run_id":run_id,"p_merge_sha":merge_sha,
            "p_release_report":rows[0]["report"],"p_followup":summary,
        })
        if (not isinstance(receipt,dict)
            or receipt.get("project_id")!=project_id
            or receipt.get("run_id")!=run_id
            or receipt.get("merge_sha")!=merge_sha
            or receipt.get("lifecycle_stage")!="operations"
            or receipt.get("product_ready") is not False
            or type(receipt.get("idempotent")) is not bool
            or type(receipt.get("snapshot_written")) is not bool
            or type(receipt.get("audit_written")) is not bool
            or type(receipt.get("change_set_updated")) is not bool
            or receipt.get("change_set_status") not in {"completed","not_change_set"}
            or type(receipt.get("pending_domains")) is not int
            or receipt["pending_domains"]!=len(summary["pending_domains"])):
            raise RuntimeError("inconsistent atomic release reconciliation receipt")
        if legacy and (receipt.get("legacy_backfill") is not True
                       or type(receipt.get("backfill_audit_written")) is not bool):
            raise RuntimeError("invalid atomic legacy repair receipt")
        return receipt

    def _defer_manual_review(self,event_id:int)->None:
        receipt=self._request("POST","rpc/factory_defer_release_reconciliation_v1",{
            "p_event_id":event_id,
        })
        if (not isinstance(receipt,dict) or receipt.get("event_id")!=event_id
            or receipt.get("status")!="needs_review"
            or type(receipt.get("idempotent")) is not bool):
            raise RuntimeError("inconsistent durable release review receipt")

    def settle_pending(self,*,max_items:int=32)->dict:
        if type(max_items) is not int or not 1<=max_items<=128:
            raise ValueError("invalid bounded release settlement")
        scanned=0
        reconciled=0
        idempotent=0
        failed=[]
        cursor=0
        exhausted=False
        for page in range(_MAX_PAGES):
            rows=self._request("POST","rpc/factory_pending_release_reconciliations_v1",{
                "p_after_event_id":cursor,"p_limit":_PAGE,
            })
            if (not isinstance(rows,list) or len(rows)>_PAGE
                or any(not isinstance(row,dict) for row in rows)):
                raise RuntimeError("invalid pending human release scan")
            if not rows:
                exhausted=True
                break
            for row in rows:
                event_id=row.get("event_id")
                if type(event_id) is not int or event_id<=cursor:
                    raise RuntimeError("invalid release keyset cursor")
                cursor=event_id
                scanned+=1
                # This loop only completes already-observed releases. A broken
                # release is isolated so another project's receipt still lands.
                try:
                    result=self.reconcile(
                        project_id=row.get("project_id"),
                        run_id=row.get("run_id"),
                        merge_sha=row.get("merge_sha"),
                    )
                except (RuntimeError,ValueError) as exc:
                    # Only a proven identity/provenance violation is parked;
                    # outages and unknown failures remain retryable. Parking
                    # is a service-role-only audit effect, never a release.
                    permanent=(isinstance(exc,(ReleaseReconciliationRejected,ValueError))
                      or str(exc) in (
                        "exact released report unavailable",
                        "release evidence is not verified for reconciliation",
                      ))
                    if permanent:
                        self._defer_manual_review(event_id)
                    failed.append({"event_id":event_id,
                                   "reason":("release_reconciliation_needs_review" if permanent
                                             else "release_reconciliation_retryable")})
                else:
                    if result["idempotent"]:
                        idempotent+=1
                    else:
                        reconciled+=1
                if scanned>=max_items:
                    return {"status":"partial" if failed else "bounded",
                            "scanned":scanned,"reconciled":reconciled,
                            "idempotent":idempotent,"needs_review":failed,
                            "truncated":True}
            if len(rows)<_PAGE:
                exhausted=True
                break
        return {"status":"partial" if failed else "complete",
                "scanned":scanned,"reconciled":reconciled,
                "idempotent":idempotent,"needs_review":failed,
                "truncated":not exhausted}

    def _defer_legacy_review(self,*,project_id:str,run_id:str,merge_sha:str)->None:
        receipt=self._request("POST","rpc/factory_defer_legacy_release_readiness_v1",{
            "p_project_id":project_id,"p_run_id":run_id,"p_merge_sha":merge_sha,
        })
        if (not isinstance(receipt,dict)
            or receipt.get("project_id")!=project_id
            or receipt.get("run_id")!=run_id
            or receipt.get("merge_sha")!=merge_sha
            or receipt.get("status")!="needs_review"
            or type(receipt.get("idempotent")) is not bool):
            raise RuntimeError("invalid durable legacy review receipt")

    def repair_legacy_readiness(self,*,max_items:int=4)->dict:
        """Bounded repair of CURRENT historical human releases, never replay.

        Separate from the normal release outbox: old split-REST code already
        emitted an audit marker, which would suppress ordinary outbox recovery.
        The service-role SQL selector verifies current release, proof of human
        merge, Pause/Stop, six-domain gaps and fair keyset paging BEFORE any RPC.
        Absent migration fails closed and produces an explicit blocked status.
        """
        if type(max_items) is not int or not 1<=max_items<=32:
            raise ValueError("invalid legacy release repair bound")
        scanned=repaired=idempotent=0
        issues=[]
        cursor=None
        exhausted=False
        for page in range(_MAX_PAGES):
            try:
                rows=self._request("POST","rpc/factory_pending_legacy_release_readiness_v1",{
                    "p_after_project_id":cursor,"p_limit":_PAGE,
                })
            except LegacyCapabilityUnavailable:
                return {"status":"blocked_migration_not_applied",
                        "scanned":0,"repaired":0,"idempotent":0,
                        "needs_review":[],"truncated":False}
            if (not isinstance(rows,list) or len(rows)>_PAGE
                or any(not isinstance(row,dict) for row in rows)):
                raise RuntimeError("invalid bounded legacy readiness selection")
            if not rows:
                exhausted=True
                break
            # Reject an untrusted page before writing even one project's state.
            inspected=cursor
            for row in rows:
                pid=row.get("project_id")
                run=row.get("run_id")
                sha=row.get("merge_sha")
                if (not isinstance(pid,str) or not _UUID.fullmatch(pid)
                    or inspected is not None and pid<=inspected
                    or not isinstance(run,str) or not _UUID.fullmatch(run)
                    or not isinstance(sha,str) or not _SHA.fullmatch(sha)):
                    raise RuntimeError("invalid legacy release keyset identity")
                inspected=pid
            for row in rows:
                pid=row["project_id"]
                run=row["run_id"]
                sha=row["merge_sha"]
                cursor=pid
                scanned+=1
                try:
                    result=self.reconcile(
                        project_id=pid,run_id=run,merge_sha=sha,legacy=True)
                except (RuntimeError,ValueError) as exc:
                    permanent=(isinstance(exc,(ReleaseReconciliationRejected,ValueError))
                        or str(exc) in (
                            "exact released report unavailable",
                            "release evidence is not verified for reconciliation"))
                    if permanent:
                        self._defer_legacy_review(project_id=pid,run_id=run,merge_sha=sha)
                    issues.append({"project_id":pid,
                        "reason":("legacy_release_needs_review" if permanent
                                  else "legacy_release_retryable")})
                else:
                    if result["idempotent"]:
                        idempotent+=1
                    else:
                        repaired+=1
                if scanned>=max_items:
                    return {"status":"partial" if issues else "bounded",
                        "scanned":scanned,"repaired":repaired,"idempotent":idempotent,
                        "needs_review":issues,"truncated":True}
            if len(rows)<_PAGE:
                exhausted=True
                break
        return {"status":"partial" if issues else "complete",
            "scanned":scanned,"repaired":repaired,"idempotent":idempotent,
            "needs_review":issues,"truncated":not exhausted}
