import unittest
from unittest.mock import MagicMock

from ai_product_factory.runtime_worker import StageEvidence,WorkItem
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue


class ChangeSetRuntimeTests(unittest.TestCase):
    def test_ready_team_plan_materializes_change_set(self):
        queue=SupabaseRuntimeQueue.__new__(SupabaseRuntimeQueue)
        queue._rpc=MagicMock(side_effect=[
            None,
            None,
            {"requirements":0,"linked":0,"unlinked":0},
            {"snapshot_id":"brain","version":1,"status":"current"},
            {"id":"team-plan","status":"ready"},
            {"change_set_id":"cs","builder_work_units":2,"status":"planned"},
            {"id":"dod","version":1,"check_count":2},
        ])
        item=WorkItem("run","task","project","demo",(),{})
        output={"_team_plan":{"status":"ready","profiles_selected":2,"planned_worker_peak":2}}
        queue.record_stage(item,StageEvidence("planning","completed",output))
        names=[call.args[0] for call in queue._rpc.call_args_list]
        self.assertEqual(names,[
            "factory_record_runtime_stage",
            "factory_persist_product_stage",
            "factory_record_requirement_trace",
            "factory_record_project_brain_snapshot",
            "factory_record_execution_team_plan",
            "factory_materialize_change_set",
            "factory_record_definition_of_done",
        ])
        self.assertEqual(queue._rpc.call_args_list[5].args[1],{"p_team_plan_id":"team-plan"})

    def test_blocked_team_plan_does_not_materialize_change_set(self):
        queue=SupabaseRuntimeQueue.__new__(SupabaseRuntimeQueue)
        queue._rpc=MagicMock(side_effect=[
            None,None,{"requirements":0,"linked":0,"unlinked":0},
            {"snapshot_id":"brain","version":1,"status":"current"},
            {"id":"team-plan","status":"blocked"},
            {"id":"dod","version":1,"check_count":2},
        ])
        item=WorkItem("run","task","project","demo",(),{})
        queue.record_stage(item,StageEvidence("planning","completed",{"_team_plan":{"status":"blocked"}}))
        names=[call.args[0] for call in queue._rpc.call_args_list]
        self.assertNotIn("factory_materialize_change_set",names)


if __name__=="__main__":
    unittest.main()
