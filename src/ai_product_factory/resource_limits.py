from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class ResourceLimit:
 provider:str
 resource_key:str
 metric_key:str
 used:Decimal|None
 limit:Decimal|None
 unit:str="count"
 quality:str="unknown"
 source:str="unknown"
 window_key:str|None=None
 resets_at:str|None=None

 @property
 def percent(self)->Decimal|None:
  if self.used is None or self.limit is None or self.limit<=0:return None
  return (self.used/self.limit)*Decimal("100")

 @property
 def status(self)->str:
  if self.quality=="provider_blocked":return "blocked"
  p=self.percent
  if p is None:return "unknown"
  if p>=100:return "blocked"
  if p>=90:return "critical"
  if p>=70:return "attention"
  return "normal"

def summarize_limit(item:ResourceLimit)->dict:
 return {"provider":item.provider,"resource_key":item.resource_key,"metric_key":item.metric_key,
  "used":None if item.used is None else str(item.used),"limit":None if item.limit is None else str(item.limit),
  "percent":None if item.percent is None else float(item.percent.quantize(Decimal("0.1"))),
  "unit":item.unit,"quality":item.quality,"source":item.source,"window_key":item.window_key,
  "resets_at":item.resets_at,"status":item.status}
