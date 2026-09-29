import json
import unittest
from unittest.mock import patch

from ai_product_factory.agent_scheduler import AgentProfile
from ai_product_factory.model_executor import ModelExecutor,ModelResult,ModelRole
from ai_product_factory.product_stage_executor import ProductStageExecutor
from ai_product_factory.runtime_worker import StageEvidence,WorkItem
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue


class Provider:
    def __init__(self):
        self.requests=[]
    def execute(self,request):
        self.requests.append(request)
        return ModelResult(
            ModelRole.PRIMARY,
            json.dumps({
                "tasks":[{
                    "task_key":"ui",
                    "title":"Build UI",
                    "required_capabilities":["ui"],
                    "scope_keys":["apps/console"],
                    "depends_on":[],
                }]
            }),
            provider_ref="ref-plan",
            usage={"input_tokens":10},
        )


class Response:
    def __init__(self,data):
        self.data=data
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self):
        return json.dumps(self.data).encode() if self.data is not None else b""


class ExecutionTeamRuntimeTests(unittest.TestCase):
    def test_planning_derives_team_plan_without_extra_model_call(self):
        provider=Provider()
        ui=AgentProfile(
            agent_key="ui",
            role="ui",
            capabilities=("ui","ux"),
            allowed_tools=("github_write","model_primary"),
            model_policy={"preferred":"primary"},
            max_concurrency=2,
            cost_budget_usd=0.75,
            is_active=True,
        )
        handler=ProductStageExecutor(ModelExecutor(primary=provider),team_profiles=(ui,))
        item=WorkItem("r","t","p","demo",("planning",),{"summary":"build x"})
        out=handler.execute(item,"planning")
        self.assertEqual(out["_team_plan"]["status"],"ready")
        self.assertEqual(out["_team_plan"]["selected_agents"][0]["agent_key"],"ui")
        self.assertEqual(len(provider.requests),1)

    def test_planning_stage_persists_versioned_team_plan_rpc(self):
        queue=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        output={
            "tasks":[],
            "_team_plan":{
                "version":1,
                "status":"ready",
                "profiles_selected":0,
                "planned_worker_peak":0,
                "blockers":[],
            },
        }
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            queue.record_stage(item,StageEvidence("planning","completed",output))
        urls=[entry.args[0].full_url for entry in call.call_args_list]
        self.assertEqual(len(urls),4)
        self.assertTrue(urls[0].endswith("/rest/v1/rpc/factory_record_runtime_stage"))
        self.assertTrue(urls[1].endswith("/rest/v1/rpc/factory_persist_product_stage"))
        self.assertTrue(urls[2].endswith("/rest/v1/rpc/factory_record_project_brain_snapshot"))
        self.assertTrue(urls[3].endswith("/rest/v1/rpc/factory_record_execution_team_plan"))


if __name__=="__main__":
    unittest.main()
