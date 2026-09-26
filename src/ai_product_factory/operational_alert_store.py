from __future__ import annotations
from .operational_alerts import OperationalAlert

class OperationalAlertRecorder:
 def __init__(self,store)->None:self.store=store
 def record_for_run(self,*,run_id:str,alerts:tuple[OperationalAlert,...])->int:
  count=0
  for alert in alerts:
   self.store.record_audit_event(run_id=run_id,event_type="operations.alert",payload={"code":alert.code,"severity":alert.severity,"message":alert.message},actor_ref="operational-alert-policy")
   count+=1
  return count
