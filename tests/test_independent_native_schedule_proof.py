import unittest
from ai_product_factory.independent_native_schedule_proof import (
    NativeScheduleProofBlocked, select_native_schedule_proof,
)

REPO="owner/project"
ROOT="/repos/"+REPO
TARGET="b"*40
OLDER="a"*40
FILES=frozenset({"src/runner.py","docs/ops.md"})
JOBS=frozenset({"schedule-probe","alerts"})
QUERY=ROOT+"/actions/workflows/autonomous-runner.yml/runs?event=schedule&status=success&branch=main&per_page=50"

def row(run_id,sha):
    return {"id":run_id,"name":"Factory autonomous runner","path":".github/workflows/autonomous-runner.yml",
      "event":"schedule","head_sha":sha,"head_branch":"main","run_attempt":1,
      "status":"completed","conclusion":"success","repository":{"full_name":REPO}}

def tree(sha):
    return {"truncated":False,"tree":[{"path":p,"type":"blob","mode":"100644","sha":sha} for p in sorted(FILES)]}

def fixture():
    good=row(11,TARGET)
    stale=row(10,OLDER)
    return {
       QUERY:{"workflow_runs":[stale,good]},
       ROOT+"/git/ref/heads/main":{"object":{"sha":TARGET}},
       ROOT+"/git/trees/"+TARGET+"?recursive=1":tree("f"*40),
       ROOT+"/git/trees/"+OLDER+"?recursive=1":tree("e"*40),
       ROOT+"/actions/runs/11":good,
       ROOT+"/actions/runs/10":stale,
       ROOT+"/actions/runs/11/jobs?per_page=100":{"jobs":[{"name":n,"run_id":11,"head_sha":TARGET,"status":"completed","conclusion":"success"} for n in JOBS]},
       ROOT+"/actions/runs/10/jobs?per_page=100":{"jobs":[{"name":n,"run_id":10,"head_sha":OLDER,"status":"completed","conclusion":"success"} for n in JOBS]},
       ROOT+"/compare/"+TARGET+"..."+TARGET:{"status":"identical","behind_by":0,"merge_base_commit":{"sha":TARGET}},
       ROOT+"/compare/"+OLDER+"..."+TARGET:{"status":"ahead","behind_by":0,"merge_base_commit":{"sha":OLDER}},
    }

class Tests(unittest.TestCase):
    def prove(self,rows):
       return select_native_schedule_proof(repository=REPO,assessed_commit=TARGET,
            github_get=lambda path: rows[path],source_files=FILES,required_jobs=JOBS)

    def test_old_source_drift_is_skipped_for_real_matching_current_schedule(self):
       out=self.prove(fixture())
       self.assertEqual(out.run_id,11)
       self.assertEqual(out.source_sha,TARGET)

    def test_no_false_pass_if_only_older_changed_code_is_available(self):
       data=fixture();data[QUERY]["workflow_runs"]=data[QUERY]["workflow_runs"][:1]
       with self.assertRaisesRegex(NativeScheduleProofBlocked,"no_matching_native_schedule"):
          self.prove(data)

    def test_no_workflow_dispatch_or_job_failure_can_substitute(self):
       for change in ("dispatch","missing_alert","wrong_repo","bad_compare","wrong_head"):
          data=fixture()
          good=data[QUERY]["workflow_runs"][1]
          if change=="dispatch":good["event"]="workflow_dispatch"
          if change=="missing_alert":data[ROOT+"/actions/runs/11/jobs?per_page=100"]["jobs"].pop()
          if change=="wrong_repo":good["repository"]={"full_name":"attacker/repo"}
          if change=="bad_compare":data[ROOT+"/compare/"+TARGET+"..."+TARGET]["behind_by"]=1
          if change=="wrong_head":data[ROOT+"/git/ref/heads/main"]["object"]["sha"]=OLDER
          with self.subTest(change=change), self.assertRaises(NativeScheduleProofBlocked):
             self.prove(data)

    def test_run_inventory_and_tree_must_be_bounded(self):
       data=fixture();data[QUERY]["workflow_runs"]=[row(i,TARGET) for i in range(1,52)]
       with self.assertRaisesRegex(NativeScheduleProofBlocked,"list_invalid"):
          self.prove(data)
