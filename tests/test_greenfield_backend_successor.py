"""Offline negative tests for exact-SHA greenfield backend recovery preflight."""
from copy import deepcopy
from datetime import datetime,timezone
import unittest

from scripts.resume_greenfield_backend_successor import (
    prepare_successor,PreviewEnvironmentNotReady,
)

OLD="a"*40
NEW="b"*40
RUN="52998a8f-b478-46b3-9529-08bea72034f3"
TASK="11111111-1111-4111-8111-111111111111"
PROJECT="22222222-2222-4222-8222-222222222222"
CS="60dd6b73-3e98-4da0-bc36-4be6d7562f45"
BRANCH="factory/change-set-60dd6b73"
REPO="leandrosilveiradepaula/infodive-service-desk"
URL="https://new-service-desk-preview.vercel.app"
STATUS_URL="https://vercel.com/leandros-projects-102e32ab/infodive-service-desk/CuYdAFK73HVwJKMzRJe9Uc1HXVQi"


def fixture():
    records={
        "factory_runs":[{"id":RUN,"task_id":TASK,"status":"failed",
            "candidate_commit":OLD,"branch_name":BRANCH,
            "metadata":{"change_set_id":CS,"execution_generation":1}}],
        "factory_tasks":[{"id":TASK,"project_id":PROJECT,"status":"failed"}],
        "factory_projects":[{"id":PROJECT,"project_key":"infodive-service-desk",
            "project_kind":"greenfield","is_active":True,"repository":REPO,
            "manifest":{"preview":{"required":True,"provider":"vercel"}}}],
        "factory_change_sets":[{"id":CS,"status":"ci_pending",
            "candidate_commit":OLD,"integration_branch":BRANCH,
            "release_run_id":RUN,"metadata":{
                "integration_release_request":{"branch":BRANCH,"pr_number":10,"candidate_commit":OLD},
                "integration_epoch_receipt":{"candidate_commit":OLD}}}],
        "factory_evaluations":[{"status":"failure","baseline_ref":"https://old.vercel.app",
            "result":{"detail":"http_503: fetch /api/session",
                      "preview_url":"https://old.vercel.app"}}],
        "factory_deployments":[{"status":"success",
            "metadata":{"candidate_commit":OLD,"preview_url":"https://old.vercel.app"}}],
    }
    github={
      "pulls/10":{"number":10,"state":"open","merged_at":None,"draft":False,
        "head":{"sha":NEW,"ref":BRANCH,"repo":{"full_name":REPO}},
        "base":{"ref":"main"}},
      "branch":{"commit":{"sha":NEW}},
      "compare":{"status":"ahead","ahead_by":4,"behind_by":0},
      "runs":{"total_count":1,"workflow_runs":[{
        "id":40420003503,"run_number":11,"run_attempt":1,
        "head_sha":NEW,"path":".github/workflows/service-desk-ci.yml",
        "event":"pull_request","status":"completed","conclusion":"success"}]},
      "status":{"sha":NEW,"statuses":[{
         "context":"Vercel","state":"success","target_url":STATUS_URL}]},
    }
    probe={"kind":"unauthenticated_json_session_probe",
        "url":URL+"/api/session","http_status":"401",
        "content_type":"application/json; charset=utf-8",
        "checked_at":datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return records,github,probe


def run_preflight(records,github,probe,preview_url=URL):
    calls={"probe":0,"cp":0,"github":[]}
    def cp_get(table,params):
        calls["cp"]+=1
        return deepcopy(records.get(table,[]))
    def github_get(repo,path):
        calls["github"].append((repo,path))
        if repo!=REPO: raise AssertionError("unexpected repository")
        if path=="pulls/10":return deepcopy(github["pulls/10"])
        if path.startswith("branches/"):return deepcopy(github["branch"])
        if path.startswith("compare/"):return deepcopy(github["compare"])
        if path.startswith("actions/runs?"):return deepcopy(github["runs"])
        if path.startswith("commits/") and path.endswith("/status"):
            return deepcopy(github["status"])
        raise AssertionError("unexpected GitHub path")
    def session_probe(url):
        calls["probe"]+=1
        if url!=URL:raise AssertionError("unexpected probe destination")
        return deepcopy(probe)
    payload=prepare_successor(run_id=RUN,project_key="infodive-service-desk",
        preview_url=preview_url,cp_get=cp_get,
        github_get=github_get,session_probe=session_probe)
    return payload,calls


class Tests(unittest.TestCase):
    def test_new_sha_exact_evidence_creates_only_an_authorized_request(self):
        p,c=run_preflight(*fixture())
        self.assertEqual(p["p_previous_commit"],OLD)
        self.assertEqual(p["p_new_commit"],NEW)
        self.assertEqual(p["p_pr_number"],10)
        self.assertEqual(p["p_verified_github"]["ci_run_id"],"40420003503")
        self.assertEqual(p["p_verified_github"]["vercel_deployment_id"],
                         "dpl_CuYdAFK73HVwJKMzRJe9Uc1HXVQi")
        self.assertEqual(c["probe"],1)
        self.assertEqual(c["cp"],6)

    def test_all_remote_mismatches_block_before_session_probe(self):
        edits=[
          lambda r,g,p:r["factory_runs"][0].update(status="completed"),
          lambda r,g,p:r["factory_runs"][0].update(candidate_commit=NEW),
          lambda r,g,p:r["factory_tasks"][0].update(status="integrated"),
          lambda r,g,p:r["factory_projects"][0].update(project_kind="existing"),
          lambda r,g,p:r["factory_projects"][0]["manifest"]["preview"].update(required=False),
          lambda r,g,p:r["factory_change_sets"][0].update(candidate_commit=NEW),
          lambda r,g,p:r["factory_change_sets"][0].update(status="completed"),
          lambda r,g,p:r["factory_evaluations"][0]["result"].update(detail="http_500: other route"),
          lambda r,g,p:r["factory_deployments"][0]["metadata"].update(candidate_commit=NEW),
          lambda r,g,p:g["pulls/10"].update(state="closed"),
          lambda r,g,p:g["pulls/10"].update(draft=True),
          lambda r,g,p:g["pulls/10"]["head"].update(sha=OLD),
          lambda r,g,p:g["pulls/10"]["head"]["repo"].update(full_name="attacker/repo"),
          lambda r,g,p:g["branch"]["commit"].update(sha=OLD),
          lambda r,g,p:g["compare"].update(status="diverged"),
          lambda r,g,p:g["compare"].update(behind_by=1),
          lambda r,g,p:g["runs"]["workflow_runs"][0].update(conclusion="failure"),
          lambda r,g,p:g["runs"]["workflow_runs"][0].update(path="untrusted.yml"),
          lambda r,g,p:g["status"]["statuses"][0].update(state="pending"),
          lambda r,g,p:g["status"]["statuses"][0].update(target_url="https://evil.invalid"),
        ]
        for edit in edits:
            records,github,probe=fixture()
            edit(records,github,probe)
            observed={"probe":0}
            def cp_get(table,params):return deepcopy(records.get(table,[]))
            def github_get(repo,path):
                if path=="pulls/10":return github["pulls/10"]
                if path.startswith("branches/"):return github["branch"]
                if path.startswith("compare/"):return github["compare"]
                if path.startswith("actions/runs?"):return github["runs"]
                if path.endswith("/status"):return github["status"]
                raise AssertionError(path)
            def session_probe(url):
                observed["probe"]+=1
                return probe
            with self.subTest(edit=str(edit)),self.assertRaises(PreviewEnvironmentNotReady):
                prepare_successor(run_id=RUN,project_key="infodive-service-desk",
                    preview_url=URL,cp_get=cp_get,github_get=github_get,
                    session_probe=session_probe)
            self.assertEqual(observed["probe"],0)

    def test_backend_http_503_redirect_and_html_never_authorize(self):
        for mutation in ({"http_status":"503"},{"http_status":"302"},
                         {"content_type":"text/html"},{"url":"https://evil.vercel.app/api/session"},
                         {"kind":"fake"}):
            rec,git,probe=fixture()
            probe.update(mutation)
            with self.subTest(mutation=mutation),self.assertRaises(PreviewEnvironmentNotReady):
                run_preflight(rec,git,probe)

    def test_unapproved_environment_url_rejected_without_probing(self):
        for bad in ("http://new-service-desk-preview.vercel.app",
                    "https://new-service-desk-preview.vercel.app.evil.test",
                    "https://new-service-desk-preview.vercel.app/path"):
            with self.subTest(bad=bad),self.assertRaises(PreviewEnvironmentNotReady):
                run_preflight(*fixture(),preview_url=bad)


if __name__ == "__main__":
    unittest.main()
