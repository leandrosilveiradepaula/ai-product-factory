"""Pre-persistence monotonicity check, independent of the post-write alarm."""
from __future__ import annotations

from typing import Callable
from urllib.parse import quote

from ai_product_factory.product_readiness import REQUIRED_COVERAGE_BY_DOMAIN

EXPECTED={(domain,key) for domain,keys in REQUIRED_COVERAGE_BY_DOMAIN.items() for key in keys}


class ReadinessPrewriteRegression(RuntimeError):
    pass


def _statuses(report: object) -> dict:
    criteria=report.get("criteria") if isinstance(report,dict) else None
    if not isinstance(criteria,dict) or set(criteria)!=set(REQUIRED_COVERAGE_BY_DOMAIN):
        raise ReadinessPrewriteRegression("readiness_guard_criteria_invalid")
    values={}
    for domain,keys in REQUIRED_COVERAGE_BY_DOMAIN.items():
        cells=criteria.get(domain)
        if not isinstance(cells,dict) or set(cells)!=set(keys):
            raise ReadinessPrewriteRegression("readiness_guard_cells_invalid")
        for key in keys:
            row=cells[key]
            status=row.get("status") if isinstance(row,dict) else None
            if status not in ("passed","partial","missing","failed","external_gate"):
                raise ReadinessPrewriteRegression("readiness_guard_status_invalid")
            values[(domain,key)]=status
    if len(values)!=19 or set(values)!=EXPECTED:
        raise ReadinessPrewriteRegression("readiness_guard_inventory_invalid")
    return values


def require_monotonic_before_write(*, repository: str, assessed_commit: str,
                                   new_report: dict, get: Callable[[str],object]) -> None:
    if repository!="leandrosilveiradepaula/ai-product-factory" or len(assessed_commit)!=40 or any(ch not in "0123456789abcdef" for ch in assessed_commit):
        raise ReadinessPrewriteRegression("readiness_guard_identity_invalid")
    new=_statuses(new_report)
    path=("factory_product_readiness_certifications?select=repository,assessed_commit,state,report"
          "&repository=eq."+quote(repository,safe="")+
          "&state=eq.persisted&order=created_at.desc&limit=2")
    rows=get(path)
    if not isinstance(rows,list) or len(rows)>2 or any(
        not isinstance(r,dict) or r.get("repository")!=repository
        or r.get("state")!="persisted" for r in rows
    ):
        raise ReadinessPrewriteRegression("readiness_guard_history_invalid")
    for old in rows:
        previous=_statuses(old.get("report"))
        lost=sorted((domain,key) for (domain,key),status in previous.items()
                    if status=="passed" and new[(domain,key)]!="passed")
        if lost:
            raise ReadinessPrewriteRegression("readiness_guard_regression_blocked")
