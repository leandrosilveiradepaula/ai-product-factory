"""B2 regression: same immutable source tree may have multiple successful PR scans.

A forced branch rewrite produced two npm successes for one exact tree. Use
ONLY the unique successful job linked to the merge commit's second parent.
Ambiguous, forged or unmerged sources remain rejected.
"""
from __future__ import annotations

import copy
import unittest

from ai_product_factory.independent_security_evidence import (
    _scan_run, REPO, WORKFLOWS, SecurityEvidenceBlocked,
)

ROOT="/repos/"+REPO
TREE="e"*40
MAIN="a"*40
PR="b"*40
STALE="c"*40
FIRST="d"*40
KIND="npm"
WORKFLOW_ID, NAME, JOB, _, _, STEPS=WORKFLOWS[KIND]
LISTING=ROOT+f"/actions/workflows/{WORKFLOW_ID}/runs?event=pull_request&status=success&per_page=100"


def run(run_id,sha):
    return {"id":run_id,"name":NAME,"event":"pull_request",
            "status":"completed","conclusion":"success",
            "run_attempt":1,"head_sha":sha}


def fixture():
    merged={
        "tree":{"sha":TREE},
        "parents":[{"sha":FIRST},{"sha":PR}],
    }
    jobs={
        101:{"total_count":1,"jobs":[{
            "name":JOB,"run_id":101,"head_sha":PR,
            "status":"completed","conclusion":"success",
            "steps":[{"name":s,"status":"completed","conclusion":"success"} for s in STEPS]}]},
        102:{"total_count":1,"jobs":[{
            "name":JOB,"run_id":102,"head_sha":STALE,
            "status":"completed","conclusion":"success",
            "steps":[{"name":s,"status":"completed","conclusion":"success"} for s in STEPS]}]},
    }
    return {
        LISTING:{"workflow_runs":[run(102,STALE),run(101,PR)]},
        ROOT+"/git/commits/"+PR:{"tree":{"sha":TREE}},
        ROOT+"/git/commits/"+STALE:{"tree":{"sha":TREE}},
        ROOT+"/git/commits/"+MAIN:merged,
        ROOT+"/git/trees/"+TREE+"?recursive=1":{
            "truncated":False,
            "tree":[{"type":"blob","path":f"file{i}","sha":f"{i+1:040x}"} for i in range(100)],
        },
        ROOT+"/actions/runs/101/jobs?per_page=100":jobs[101],
        ROOT+"/actions/runs/102/jobs?per_page=100":jobs[102],
    }


def evaluate(data):
    return _scan_run(lambda path:data[path], ROOT, KIND, TREE, MAIN)


class MergeSourceSelectionTests(unittest.TestCase):
    def test_merge_second_parent_selects_exactly_one_successful_source(self):
        selection,rid=evaluate(fixture())
        self.assertEqual(rid,101)
        self.assertEqual(selection["head_sha"],PR)

    def test_unmerged_successful_scan_can_never_win(self):
        data=fixture()
        data[ROOT+"/git/commits/"+MAIN]["parents"]=[{"sha":FIRST},{"sha":"f"*40}]
        with self.assertRaises(SecurityEvidenceBlocked):
            evaluate(data)

    def test_missing_or_fake_merge_parent_blocks_duplicate_scans(self):
        for parents in (
            None,[],[{"sha":PR}],[{"sha":FIRST},{"sha":FIRST}],
            [{"sha":FIRST},{"sha":"oops"}],
            [{"sha":FIRST},{"sha":PR},{"sha":STALE}],
        ):
            data=fixture()
            if parents is None:
                data[ROOT+"/git/commits/"+MAIN].pop("parents")
            else:
                data[ROOT+"/git/commits/"+MAIN]["parents"]=parents
            with self.subTest(parents=parents),self.assertRaises(SecurityEvidenceBlocked):
                evaluate(data)

    def test_duplicate_success_on_the_same_merged_sha_is_not_accepted(self):
        data=fixture()
        data[LISTING]["workflow_runs"][0]["head_sha"]=PR
        with self.assertRaises(SecurityEvidenceBlocked):
            evaluate(data)

    def test_one_success_without_a_merge_parent_remains_valid(self):
        data=fixture()
        del data[ROOT+"/git/commits/"+MAIN]["parents"]
        data[LISTING]["workflow_runs"]=[run(101,PR)]
        selection,rid=evaluate(data)
        self.assertEqual(rid,101)

    def test_broken_merge_parent_job_never_becomes_a_security_certificate(self):
        data=fixture()
        data[ROOT+"/actions/runs/101/jobs?per_page=100"]["jobs"][0]["steps"][0]["conclusion"]="failure"
        with self.assertRaises(SecurityEvidenceBlocked):
            evaluate(data)


if __name__ == "__main__":
    unittest.main()
