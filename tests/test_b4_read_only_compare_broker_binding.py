"""Static policy fence for the no-token B4 release compare in Supabase Edge.

These assertions intentionally fail on broadening the existing App mint route
or moving private App credentials into the GitHub Actions certifier.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class B4ReadOnlyAppBrokerBoundaryTests(unittest.TestCase):
    def setUp(self):
        edge=(ROOT/"supabase/functions/factory-runtime-control-plane/index.ts").read_text()
        self.assertIn("async function b4ReadOnlyComparedSource(", edge)
        self.edge=edge
        self.route=edge.split("async function b4ReadOnlyComparedSource(",1)[1].split(
            "\nDeno.serve(",1)[0]
        self.token=edge.split("async function mintGithubInstallationToken(",1)[1].split(
            "\nconst B4_SHA=",1)[0]

    def test_existing_token_mint_restriction_is_untouched(self):
        edge=self.edge
        self.assertIn('const standardTokenEvent=["schedule","workflow_dispatch","issue_comment","push"].includes(eventName);',edge)
        self.assertIn('if(!standardTokenEvent && !trustedConsoleWake)',edge)
        self.assertIn('github_app_token_event_not_allowed',edge)
        self.assertNotIn('["schedule","workflow_dispatch","issue_comment","push","workflow_run"]',edge)
        self.assertIn('if(requestUrl.pathname.endsWith("/github-app/read-only-compare"))',edge)
        self.assertIn('if(requestUrl.pathname.endsWith("/github-app/token"))',edge)
        self.assertLess(edge.index('if(requestUrl.pathname.endsWith("/github-app/read-only-compare"))'),
                        edge.index('if(requestUrl.pathname.endsWith("/github-app/token"))'))

    def test_compare_requires_exact_protected_first_attempt_and_release(self):
        s=self.route
        for required in (
            'String(identity.event_name||"")!=="workflow_run"',
            'String(identity.workflow_ref||"")!==TRUSTED_BACKUP_WORKFLOW_REF',
            'String(identity.run_attempt||"")!=="1"',
            'Object.keys(input).sort().join(",")!=="current,predecessor,repository"',
            'repository.toLowerCase()===EXPECTED.repository.toLowerCase()',
            'projects[0].project_kind!=="greenfield"',
            'projects[0].lifecycle_stage!=="operations"',
            'status=eq.completed',
            'release?.released_by!=="observed_manual_merge"',
            'candidate_commit=eq.',
            'witness?.candidate_commit===predecessor',
            'preview?.status==="browser_verified"',
            'source?.browser_visual_validation==="success"',
            'limits?.production_merge_authorized===false',
        ):
            self.assertIn(required,s)

    def test_credential_restricted_to_read_only_and_never_returns_to_ci(self):
        s=self.route
        self.assertIn('const B4_COMPARE_PERMISSIONS = {contents:"read"};',self.edge)
        self.assertIn('permissions:readOnlyCompare?B4_COMPARE_PERMISSIONS:APP_PERMISSIONS',self.token)
        self.assertIn('}),supabaseUrl,key,true,',s)
        self.assertIn('const accessToken=String(granted.token||"");',s)
        self.assertIn('Authorization:"Bearer "+accessToken',s)
        self.assertIn('return json(200,{\n    status:"ahead"',s)
        self.assertNotIn('return json(200,granted',s)
        self.assertNotIn('return json(200,{token',s)
        self.assertNotIn('token_persisted:false',s)
        self.assertNotIn('console.log',s)
        self.assertNotIn('console.error',s)
        self.assertIn('"https://api.github.com/repos/"+repository+"/compare/"',s)

    def test_return_contains_only_derived_allowlisted_compare_metadata(self):
        s=self.route
        self.assertIn('files:safeFiles,',s)
        self.assertIn('filename:f.filename,status:f.status,',s)
        self.assertIn('compared.total_commits!==ahead',s)
        self.assertIn('files.length>50',s)
        self.assertIn('(ahead as number)>25',s)
        self.assertIn('!name.split("/").some(x=>!x||x==="."||x==="..")',s)
        self.assertIn('["added","modified","removed","renamed"]',s)
        self.assertNotIn('patch:f.patch',s)
        self.assertNotIn('content:f.content',s)
        self.assertNotIn('commit_message',s)


if __name__=="__main__":
    unittest.main()
