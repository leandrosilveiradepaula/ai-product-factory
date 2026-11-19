"""Execute real runtime wiring under offline mocks; never call providers."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai_product_factory import runtime_cli

class GenericIBMRuntimeIntegrationTests(unittest.TestCase):
    @patch.dict(os.environ, {"FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud","GITHUB_ACTIONS":"false"})
    def test_product_stage_uses_private_primary_under_existing_stage_handler(self):
        executor=object()
        profiles=(object(),)
        with patch.object(runtime_cli,"require_primary_runtime_enabled"), \
             patch.object(runtime_cli,"require_primary_provider_ready") as ready, \
             patch.object(runtime_cli,"SupabaseAgentScheduler") as agents, \
             patch.object(runtime_cli,"build_primary_model_executor",return_value=executor), \
             patch.object(runtime_cli,"ProductStageExecutor") as handler:
            agents.return_value.profiles.return_value=profiles
            result=runtime_cli.build_handler()
            self.assertIs(result,handler.return_value)
            handler.assert_called_once_with(executor,team_profiles=profiles)
            ready.assert_called_once_with()

    @patch.dict(os.environ, {"FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud","GITHUB_ACTIONS":"false"})
    def test_wrong_agent_provider_blocks_before_direct_claim(self):
        profile=SimpleNamespace(model_policy={"provider":"openai","enabled":True})
        with patch.object(runtime_cli,"require_primary_runtime_enabled"), \
             patch.object(runtime_cli,"require_primary_provider_ready"), \
             patch.object(runtime_cli,"require_paid_runtime_budget"), \
             patch.object(runtime_cli,"SupabaseAgentScheduler") as scheduler, \
             patch.object(runtime_cli,"SupabaseDirectRunQueue") as queue:
            scheduler.return_value.require_route_tools.return_value=profile
            outcome=runtime_cli.run_direct_once("worker-1",agent_key="development",
                                                run_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
            self.assertEqual(outcome["status"],"blocked")
            self.assertFalse(outcome["claimed"])
            queue.assert_not_called()

    @patch.dict(os.environ, {"FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud","GITHUB_ACTIONS":"false"})
    def test_explicit_private_direct_assignment_can_check_empty_queue_no_model(self):
        profile=SimpleNamespace(model_policy={"provider":"infodive_ibm_cloud","enabled":True})
        with patch.object(runtime_cli,"require_primary_runtime_enabled"), \
             patch.object(runtime_cli,"require_primary_provider_ready"), \
             patch.object(runtime_cli,"require_paid_runtime_budget"), \
             patch.object(runtime_cli,"SupabaseAgentScheduler") as scheduler, \
             patch.object(runtime_cli,"SupabaseDirectRunQueue") as queue, \
             patch.object(runtime_cli,"build_primary_model_executor") as build:
            scheduler.return_value.require_route_tools.return_value=profile
            queue.return_value.claim_next.return_value=None
            outcome=runtime_cli.run_direct_once("worker-1",agent_key="development",
                                                run_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
            self.assertEqual(outcome,{"claimed":False,"status":"empty"})
            build.assert_not_called()
            queue.return_value.claim_next.assert_called_once_with(
                "worker-1","development","bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

if __name__ == "__main__":
    unittest.main()
