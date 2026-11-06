import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/"scripts"/(name+".py")); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
ops=load("audit_certification_operations_preflight"); boundaries=load("audit_mock_release_boundaries")

class CertificationOperationsAndMockBoundaries(unittest.TestCase):
    def test_runbook_preflight_is_bounded_and_non_certifying(self):
        report=ops.audit(ROOT); self.assertTrue(report["all_contract_markers_present"]); self.assertFalse(report["operations_certified"]); self.assertEqual(report["production_writes"],0); self.assertEqual(report["live_scheduler"]["status"],"not_requested")
    def test_missing_required_runbook_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): ops.audit(Path(folder))
    def test_simulation_inventory_cannot_self_promote_release(self):
        report=boundaries.audit(ROOT); self.assertFalse(report["simulation_marker_can_authorize_release"]); self.assertTrue(report["inventory_is_not_pass"]); self.assertFalse(report["functional_completeness_certified"])
    def test_missing_runtime_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): boundaries.audit(Path(folder))
    def test_live_scheduler_observation_is_read_only_and_not_certifying(self):
        sha="a"*40
        def read(path):
            if path.endswith("/git/ref/heads/main"): return {"object":{"sha":sha}}
            return {"workflow_runs":[{"id":7,"event":"schedule","status":"completed","conclusion":"success","head_branch":"main","head_sha":sha}]}
        report=ops.audit(ROOT,repository="owner/repository",github_get=read)
        self.assertEqual(report["live_scheduler"]["status"],"scheduled_runner_observed")
        self.assertEqual(report["environment_queries_executed"],2)
        self.assertFalse(report["operations_certified"])

if __name__=="__main__": unittest.main()
