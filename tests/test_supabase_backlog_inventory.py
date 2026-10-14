import json
import unittest
from pathlib import Path
from unittest.mock import patch
from ai_product_factory.supabase_backlog_inventory import SupabaseBacklogInventoryReader

ROOT=Path(__file__).resolve().parents[1]
P="00000000-0000-0000-0000-000000000001"
Q="00000000-0000-0000-0000-000000000002"
T="00000000-0000-0000-0000-000000000010"
PARENT="00000000-0000-0000-0000-000000000011"
UNIT="00000000-0000-0000-0000-000000000020"

class Response:
    def __init__(self, data): self.data=data
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.data).encode()

def inventory():
    return SupabaseBacklogInventoryReader(url="https://mock.supabase.co",secret_key="sb_secret_test")

class Tests(unittest.TestCase):
    def setUp(self):
        self.projects=[{"id":P,"project_key":"crm-infodive","is_active":True}]
        self.task={"id":T,"project_id":P,"parent_task_id":PARENT,"status":"queued"}

    def test_empty_backlog_has_no_parent_unit_reads(self):
        with patch("urllib.request.urlopen",side_effect=[Response(self.projects),Response([])]) as call:
            value=inventory().read()
        self.assertEqual(value["queued_tasks"],0)
        self.assertTrue(value["read_only"])
        self.assertEqual(call.call_count,2)

    def test_historical_queued_child_with_completed_unit_is_not_active(self):
        parent=[{"id":PARENT,"project_id":P,"status":"completed"}]
        units=[{"id":UNIT,"task_id":T,"status":"completed"}]
        with patch("urllib.request.urlopen",side_effect=[
            Response(self.projects),Response([self.task]),Response(parent),Response(units)
        ]) as calls:
            result=inventory().read()
        self.assertEqual(result["queued_tasks"],1)
        self.assertEqual(result["active_work_units"],0)
        self.assertEqual(result["historical_children_without_active_units"],1)
        self.assertTrue(all(c.args[0].get_method()=="GET" for c in calls.call_args_list))

    def test_active_unit_is_reported_without_claiming_runnability(self):
        task={**self.task,"parent_task_id":None}
        with patch("urllib.request.urlopen",side_effect=[
            Response(self.projects),Response([task]),
            Response([{"id":UNIT,"task_id":T,"status":"queued"}])
        ]):
            result=inventory().read()
        self.assertEqual(result["with_active_units"],1)
        self.assertEqual(result["active_work_units"],1)
        self.assertIn("do not establish",result["disclaimer"])

    def test_unmaterialized_root_is_not_classified_historical(self):
        task={**self.task,"parent_task_id":None}
        with patch("urllib.request.urlopen",side_effect=[
            Response(self.projects),Response([task]),Response([])
        ]):
            result=inventory().read()
        self.assertEqual(result["other_queued_without_active_units"],1)
        self.assertEqual(result["historical_children_without_active_units"],0)

    def test_missing_parent_fails_closed(self):
        with patch("urllib.request.urlopen",side_effect=[
            Response(self.projects),Response([self.task]),Response([])
        ]):
            with self.assertRaisesRegex(RuntimeError,"parent task unavailable"):
                inventory().read()

    def test_cross_project_parent_fails_closed(self):
        projects=[*self.projects,{"id":Q,"project_key":"factory","is_active":True}]
        with patch("urllib.request.urlopen",side_effect=[
            Response(projects),Response([self.task]),
            Response([{"id":PARENT,"project_id":Q,"status":"completed"}]),Response([])
        ]):
            with self.assertRaisesRegex(RuntimeError,"cross-project"):
                inventory().read()

    def test_overflow_refuses_partial_report(self):
        tasks=[{"id":f"00000000-0000-0000-0000-{n:012d}","project_id":P,
                "parent_task_id":None,"status":"queued"} for n in range(101)]
        with patch("urllib.request.urlopen",side_effect=[
            Response(self.projects),Response(tasks)
        ]) as calls:
            with self.assertRaisesRegex(RuntimeError,"100-row boundary"):
                inventory().read()
        self.assertEqual(calls.call_count,2)

    def test_duplicate_task_fails_closed(self):
        task={**self.task,"parent_task_id":None}
        with patch("urllib.request.urlopen",side_effect=[
            Response(self.projects),Response([task,task])
        ]):
            with self.assertRaisesRegex(RuntimeError,"inconsistent queued"):
                inventory().read()

    def test_scheduler_probe_diagnostic_remains_read_only(self):
        workflow=(ROOT/".github/workflows/autonomous-runner.yml").read_text()
        self.assertIn("Diagnose historical queued backlog without dispatch",workflow)
        self.assertIn("steps.probe.outputs.work_detected == 'false'",workflow)
        self.assertIn("runtime_cli --mode backlog-audit",workflow)

    def test_cli_mode_is_independent_of_dispatch(self):
        cli=(ROOT/"src/ai_product_factory/runtime_cli.py").read_text()
        self.assertIn('"backlog-audit"',cli)
        self.assertIn("SupabaseBacklogInventoryReader().read()",cli)

if __name__=="__main__":unittest.main()
