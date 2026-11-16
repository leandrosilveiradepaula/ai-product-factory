import unittest
from scripts.resume_preview_external_feedback import prepare_recovery,RecoveryBlocked

REPO="owner/real-project"
SHA="a"*40
FACTORY="b"*40
PREVIEW="https://real-project-preview.vercel.app"
RUN="11111111-1111-1111-1111-111111111111"

def make():
    project=[{"id":"project-1","repository":REPO,"is_active":True}]
    cs=[{"id":"cs-1","status":"ci_pending","release_run_id":RUN,
         "candidate_commit":SHA,"integration_branch":"factory/change-set-xyz",
         "metadata":{"integration_release_request":{"pr_number":2,"candidate_commit":SHA}}}]
    runs=[{"id":RUN,"status":"failed","candidate_commit":SHA,
           "branch_name":"factory/change-set-xyz"}]
    pull={"number":2,"state":"open","draft":False,"merged_at":None,
          "head":{"sha":SHA,"ref":"factory/change-set-xyz","repo":{"full_name":REPO}},
          "base":{"ref":"main"}}
    status={"sha":SHA,"statuses":[{"context":"Vercel","state":"success"}]}
    return project,cs,runs,pull,status

class Tests(unittest.TestCase):
    def prove(self,fixture=None):
        project,cs,runs,pull,status=fixture or make()
        def cp(table,params):
            return {"factory_projects":project,"factory_change_sets":cs,"factory_runs":runs}[table]
        def github(repo,path):
            return pull if path.startswith("pulls/") else status
        return prepare_recovery(repository=REPO,candidate_sha=SHA,preview_url=PREVIEW,
                verifier_factory_sha=FACTORY,cp_get=cp,github_get=github)

    def test_real_failed_candidate_can_prepare_status_only_call(self):
        out=self.prove()
        self.assertEqual(out["p_run_id"],RUN)
        self.assertEqual(out["p_pr_number"],2)
        self.assertEqual(out["p_verified_github"]["factory_sha"],FACTORY)
        self.assertIs(out["p_verified_github"]["merged"],False)

    def test_nonfailed_or_missing_change_set_never_replays(self):
        f=list(make());f[1]=[]
        self.assertIsNone(self.prove(f))
        f=list(make());f[2][0]["status"]="completed"
        self.assertIsNone(self.prove(f))

    def test_pr_sha_draft_status_mismatch_block(self):
        for field,val in (("draft",True),("state","closed"),("merged_at","now")):
            f=list(make());f[3]=dict(f[3]);f[3][field]=val
            with self.subTest(field=field),self.assertRaises(RecoveryBlocked):
                self.prove(f)
        f=list(make());f[4]={"sha":SHA,"statuses":[{"context":"Vercel","state":"pending"}]}
        with self.assertRaises(RecoveryBlocked):self.prove(f)

    def test_untrusted_preview_or_cross_repo_mismatch_block(self):
        project,cs,runs,pull,status=make()
        project[0]["repository"]="elsewhere/repo"
        with self.assertRaises(RecoveryBlocked):
            self.prove((project,cs,runs,pull,status))
        with self.assertRaises(RecoveryBlocked):
            prepare_recovery(repository=REPO,candidate_sha=SHA,
                preview_url="https://evil.invalid",verifier_factory_sha=FACTORY,
                cp_get=lambda *x:[],github_get=lambda *x:{})
