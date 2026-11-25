"""Offline real-shape regression for the Dark Channel merge-source preflight."""
import base64
import copy
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from ai_product_factory.github_rest import GitHubRestAdapter
from ai_product_factory.product_stage_output_contract import NON_ACTIONABLE_PLANNING_EVIDENCE
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue

SHA = "55e8e8d8422ee044eb1112ab678cb0223e987742"
PARENTS = ["c1719129eaa5b2d7ae3f4afffa1bb70a7d502973", "d90e9b68729d82e960f5bc1ee357d924a3823e28"]
TREE = "bcbbf1e55c377a0ac816f91d51b9053eb1e0487e"
PROJECT = "19f0f200-3777-46c6-969a-acf0d3426ff1"
JOURNEY = "c43e7781-7cb9-49fd-8459-cc358880df0a"
REQUEST = "0b6ab27d-11eb-acf6-1392-50857d8d854c"
RUN = "13fc575b-af98-4eb3-a5b8-01dce69ec8af"
ORIGIN = "1ed3c5d1-fc2a-4bab-a4a9-12f53bc83c29"
TASK = "e30ee0cb-0be3-4ddc-a10e-d653d25fa266"
REPO = "leandrosilveiradepaula/dark-channel-studio"

class MergeSourceTransport:
    def __init__(self):
        self.calls = []
        self.row = {"sha":SHA,"tree":{"sha":TREE},"message":"Merge existing change",
                    "parents":[{"sha":p} for p in PARENTS]}
        # Synthetic file content; names and source graph match the real
        # incident. No external calls, credentials, or production writes.
        self.files = {"README.md":"Current application; finish missing editorial integration.",
                      "package.json":'{"scripts":{"test":"vitest run"}}',
                      "app/server.js":"function serve() { return null; }",
                      "app/editorial.js":"function editorial() { return {}; }",
                      "app/server.test.js":"test('server', () => {});",
                      "app/editorial.test.js":"test('editorial', () => {});"}
    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        parsed=urlparse(url)
        assert method=="GET" and body is None
        prefix="/repos/"+REPO
        if parsed.path==prefix+"/git/commits/"+SHA:
            return 200,copy.deepcopy(self.row)
        if parsed.path==prefix+"/git/trees/"+TREE:
            assert parse_qs(parsed.query)=={"recursive":["1"]}
            return 200,{"truncated":False,"tree":[{"path":p,"type":"blob"} for p in self.files]}
        if parsed.path.startswith(prefix+"/contents/"):
            assert parse_qs(parsed.query)=={"ref":[SHA]}
            path=parsed.path[len(prefix+"/contents/"):]
            return 200,{"type":"file","encoding":"base64","content":base64.b64encode(self.files[path].encode()).decode()}
        raise AssertionError("unexpected GitHub request")

def fixture():
    binding={"journey_id":JOURNEY,"project_id":PROJECT,"request_id":REQUEST,
             "execution_generation":1,"policy_version":1,"policy_digest":"a"*64,
             "repository":REPO,"source_commit":SHA,"source_ref":"main","source_mode":"main_snapshot",
             "integration_branch":"factory/journey-"+JOURNEY,"preview_branch_prefix":"preview/journey-"+JOURNEY[:8],
             "preview_base_ref":"main","release_base_ref":"main","binding_version":2}
    snapshot={"text":"Complete the existing editorial product","digest":"d"*64}
    discovery={"problem":"existing editorial flow","_evidence":{"provider_ref":"d"}}
    specification={"scope":"complete product","_evidence":{"provider_ref":"s"}}
    source={"id":ORIGIN,"task_id":TASK,"journey_id":JOURNEY,"status":"failed",
            "source_commit":SHA,"execution_route":"direct","metadata":{
            "execution_generation":1,"journey_binding_v2":binding,"journey_request":snapshot,
            "error":"planning has no actionable tasks or decisions",
            "stages":["discovery","specification","planning"],
            "stage_evidence":{"discovery":{"status":"completed","output":discovery},
                              "specification":{"status":"completed","output":specification},
                              "planning":{"status":"failed","output":NON_ACTIONABLE_PLANNING_EVIDENCE}}}}
    resume={"id":RUN,"task_id":TASK,"journey_id":JOURNEY,"status":"running","metadata":{
        "execution_generation":1,"journey_binding_v2":binding,"journey_request":snapshot,"stages":["planning"],
        "resume_checkpoint":{"schema":"journey_v2_planning_recovery_v1","prior_kind":"greenfield",
                             "journey_id":JOURNEY,"project_id":PROJECT,"source_run_id":ORIGIN,
                             "generation":1,"source_commit":SHA,"discovery":discovery,"specification":specification}}}
    journey={"id":JOURNEY,"project_id":PROJECT,"request_id":REQUEST,"request_digest":snapshot["digest"],
             "request_snapshot":snapshot,"binding":binding,"state":"executing","execution_generation":1}
    manifest={"source":"factory-console","onboarding_mode":"greenfield","journey_delivery_binding_v2":{"enabled":True},
              "continuation_request":{"id":"legacy-request","source":"factory-console"}}
    return binding,snapshot,source,resume,journey,manifest

class MergeSourcePreflightTests(unittest.TestCase):
    def test_source_accepts_merge_root_and_normal_but_integration_remains_single_parent(self):
        transport=MergeSourceTransport()
        github=GitHubRestAdapter(repository=REPO,token="synthetic",transport=transport)
        github.assert_source_commit(SHA)
        with self.assertRaisesRegex(RuntimeError,"one parent"):
            github.get_commit_provenance(SHA)
        for parents in ([],[{"sha":PARENTS[0]}]):
            transport.row["parents"]=parents
            github.assert_source_commit(SHA)
        for bad in ({"sha":"f"*40},{"tree":{"sha":"invalid"}},{"parents":[{"sha":SHA}]},
                    {"parents":[{"sha":PARENTS[0]},{"sha":PARENTS[0]}]}):
            transport.row={"sha":SHA,"tree":{"sha":TREE},"message":"Merge","parents":[{"sha":p} for p in PARENTS],**bad}
            with self.assertRaises(PermissionError):
                github.assert_source_commit(SHA)

    def claim(self, native, corrupt=False):
        binding,snapshot,source,resume,journey,manifest=fixture()
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="synthetic")
        q._rpc=lambda name,payload: ({"run_id":RUN,"task_id":TASK,"project_id":PROJECT,"project_key":"dark-channel-studio",
            "execution_generation":1,"stages":["planning"],"context":{"manifest":manifest}} if name=="factory_claim_next_run"
            else (_ for _ in ()).throw(AssertionError("unexpected write RPC "+name)))
        project={"id":PROJECT,"project_key":"dark-channel-studio","repository":REPO}
        def get(path):
            if path.startswith("factory_runs?select=journey_id&id=eq."):
                return [{"journey_id":JOURNEY}]
            if path.startswith("factory_projects?"):
                return [project]
            if path.startswith("factory_journeys?"):
                return [journey]
            if path.startswith("factory_runs?select=id,task_id,journey_id,status,metadata&id=eq."):
                return [resume]
            if path.startswith("factory_runs?select=id,task_id,journey_id,status,execution_route,source_commit,metadata&id=eq."):
                return [source]
            if path.startswith(("factory_project_state_snapshots?","factory_tasks?","factory_project_github_access?")):
                return []
            if path.startswith("factory_runs?select=id,task_id,status,metadata&task_id=eq."):
                return [source]
            raise AssertionError(path)
        q._get=get
        transport=MergeSourceTransport()
        if corrupt:
            transport.row["sha"]="f"*40
        adapter=GitHubRestAdapter(repository=REPO,token="synthetic",transport=transport)
        failures=[]
        q.fail=lambda item,reason: failures.append(reason)
        env=({"FACTORY_PRIMARY_MODEL_PROVIDER":"infodive_ibm_cloud","FACTORY_INFODIVE_VPS_WORKER_ENABLED":"true"}
             if native else {"GITHUB_ACTIONS":"true"})
        with patch.dict("os.environ",env,clear=True), patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter",return_value=adapter) as direct, patch.object(q,"_github_for_project",return_value=adapter) as mint:
            if corrupt:
                with self.assertRaisesRegex(PermissionError,"planning resume provenance invalid"):
                    q.claim_next("worker")
                self.assertEqual(failures,["planning_resume_journey_source_commit_unavailable"])
            else:
                item=q.claim_next("worker")
                self.assertEqual(item.journey_id,JOURNEY)
                self.assertEqual(item.stages,("planning",))
                self.assertEqual(item.context["_verified_resume_prior_stages"],
                                 {k:source["metadata"]["stage_evidence"][k]["output"] for k in ("discovery","specification")})
                evidence=item.context["current_state_facts"]["live_candidate"]["source_evidence"]
                self.assertEqual(evidence["assessed_commit"],SHA)
                self.assertEqual(evidence["status"],"bounded_source_inspected")
                self.assertEqual(len(evidence["inspected_files"]),4)
                self.assertEqual(evidence["request_source_paths"],[])
                self.assertEqual(failures,[])
            if native:
                mint.assert_called_once_with(project)
                direct.assert_not_called()
            else:
                direct.assert_called_once_with(repository=REPO)
                mint.assert_not_called()
        self.assertTrue(all(method=="GET" for method,_ in transport.calls))

    def test_full_actions_claim_uses_merge_source_and_existing_checkpoint(self):
        self.claim(False)

    def test_full_native_claim_mints_exact_repository_and_uses_same_checkpoint(self):
        self.claim(True)

    def test_full_claim_rejects_mismatched_source_with_typed_error(self):
        self.claim(False,corrupt=True)

if __name__=="__main__":
    unittest.main()
