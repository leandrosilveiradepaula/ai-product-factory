from __future__ import annotations

from .models import RiskProfile


def requires_human_gate(risk: RiskProfile) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if risk.production_change:
        reasons.append("mudanca em producao")
    if risk.destructive_data_change:
        reasons.append("risco de perda de dados")
    if risk.expands_sensitive_access:
        reasons.append("ampliacao sensivel de acesso")
    if risk.new_paid_service:
        reasons.append("novo servico pago")
    if risk.material_requirement_change:
        reasons.append("mudanca material de requisito")
    return bool(reasons), tuple(reasons)
