from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

OPERATIONAL_ALERT_CODES=("dead_letter","expired_lease","failed_runs","unknown_cost","budget_exhausted")

@dataclass(frozen=True)
class OperationalHealth:
 expired_leases:int=0
 dead_letter_runs:int=0
 failed_runs:int=0
 unknown_cost_events:int=0
 known_cost:Decimal=Decimal("0")
 budget:Decimal|None=None

@dataclass(frozen=True)
class OperationalAlert:
 code:str
 severity:str
 message:str

def evaluate_operational_alerts(health:OperationalHealth)->tuple[OperationalAlert,...]:
 alerts:list[OperationalAlert]=[]
 if health.dead_letter_runs>0:alerts.append(OperationalAlert("dead_letter","critical",f"{health.dead_letter_runs} run(s) exhausted retry attempts"))
 if health.expired_leases>0:alerts.append(OperationalAlert("expired_lease","warning",f"{health.expired_leases} worker lease(s) expired"))
 if health.failed_runs>0:alerts.append(OperationalAlert("failed_runs","warning",f"{health.failed_runs} run(s) are failed"))
 if health.unknown_cost_events>0:alerts.append(OperationalAlert("unknown_cost","warning",f"{health.unknown_cost_events} usage event(s) have unknown cost"))
 if health.budget is not None and health.known_cost>=health.budget:alerts.append(OperationalAlert("budget_exhausted","critical","known spend reached or exceeded the configured budget"))
 return tuple(alerts)
