from __future__ import annotations
import json
import unittest
from unittest.mock import patch

from ai_product_factory.agent_scheduler import SupabaseAgentScheduler

class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode()

class Tests(unittest.TestCase):
    def scheduler(self):
        return SupabaseAgentScheduler(url="https://example.supabase.co",service_role_key="legacy.jwt.key")

    def test_schedule_next_maps_specialist_assignment(self):
        payload={"assignment_id":"a","agent_id":"g","agent_key":"security","role":"security","max_concurrency":2,
                 "model_policy":{"preferred":"primary"},"allowed_tools":["supabase"],"run_id":"r","task_id":"t"}
        with patch("urllib.request.urlopen",return_value=Response(payload)):
            out=self.scheduler().schedule_next()
        self.assertEqual(out.agent_key,"security")
        self.assertEqual(out.role,"security")
        self.assertEqual(out.allowed_tools,("supabase",))
        self.assertEqual(out.run_id,"r")

    def test_empty_scheduler_is_not_fabricated(self):
        with patch("urllib.request.urlopen",return_value=Response(None)):
            self.assertIsNone(self.scheduler().schedule_next())

    def test_expired_agent_slots_are_recovered(self):
        with patch("urllib.request.urlopen",return_value=Response({"released":2})):
            self.assertEqual(self.scheduler().recover_expired(),{"released":2})

if __name__=="__main__": unittest.main()
