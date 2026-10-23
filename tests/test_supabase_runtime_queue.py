import json
import unittest
from unittest.mock import patch

from ai_product_factory.model_executor import ModelExecutor, ModelResult, ModelRole
from ai_product_factory.product_stage_executor import ProductStageExecutor

from ai_product_factory.runtime_worker import StageEvidence,WorkItem
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode() if self.data is not None else b""


class SupabaseRuntimeQueueTests(unittest.TestCase):
    def test_execution_epoch_requires_positive_generation(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        with patch("urllib.request.urlopen") as call:
            with self.assertRaisesRegex(RuntimeError,"generation"):
                q.assert_execution_epoch(item)
            call.assert_not_called()

    def test_execution_epoch_rejects_bool_zero_negative_and_string(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen") as network:
            for generation in (True, False, 0, -1, "3", 3.0):
                with self.subTest(generation=generation):
                    item=WorkItem("r","t","p","demo",(),{},generation)
                    with self.assertRaisesRegex(RuntimeError,"generation"):
                        q.assert_execution_epoch(item)
            network.assert_not_called()

    def test_stale_epoch_backend_rejection_blocks_stage_and_terminal_writes(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},2,"worker")
        calls=[]
        def rpc(name,payload):
            calls.append(name)
            if name=="factory_assert_claimed_run_epoch":
                raise RuntimeError("project execution epoch revoked")
            raise AssertionError("side effect admitted: "+name)
        q._rpc=rpc
        for operation in (
            lambda: q.record_stage_event(item,"planning","started"),
            lambda: q.record_stage(item,StageEvidence("planning","completed",{})),
            lambda: q.complete(item),
            lambda: q.fail(item,"failure"),
        ):
            with self.assertRaisesRegex(RuntimeError,"revoked"):
                operation()
        self.assertEqual(calls,["factory_assert_claimed_run_epoch"]*4)


    def test_greenfield_real_claim_reconciles_from_explicit_exact_sha_code_without_db_snapshot(self):
        """Regression for the real Proof 2 source/snapshot failure sequence."""
        from unittest.mock import MagicMock
        manifest = {
            "source": "factory-console", "onboarding_mode": "greenfield",
            "bootstrap_request_id": "706c6b5d-f41f-4c23-ac78-df9d9a1e4c7d",
            "continuation_request": {
                "source": "github-owner",
                "summary": "Find a safe fix in src/domain/ticket.ts.",
                "github": {
                    "repository": "leandrosilveiradepaula/ai-product-factory",
                    "issue_number": 1055,
                    "actor_id": 256917842,
                },
            },
        }
        project_id = "70515123-ecbb-4f4b-a38f-75c54250af56"
        repository = "leandrosilveiradepaula/infodive-service-desk"
        sha = "c" * 40
        queue = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="example")
        queue._rpc = lambda name, payload: (
            {"run_id": "run", "task_id": "task", "project_id": project_id,
             "project_key": "infodive-service-desk", "execution_generation": 1,
             "stages": ["reconciliation", "gap_analysis", "planning"],
             "context": {"manifest": manifest}}
            if name == "factory_claim_next_run" else
            (_ for _ in ()).throw(AssertionError("unexpected write RPC: " + name))
        )
        reads = []
        def read(path):
            reads.append(path)
            if "factory_project_state_snapshots?" in path:
                return [{"observed_stage": "verification", "summary": "Browser not ready",
                         "evidence": [{"source": "preview"}],
                         "source_status": {"preview": "blocked"}}]
            if "factory_tasks?" in path:
                return [{"external_key": "root", "title": "Original bootstrap",
                         "status": "completed", "updated_at": "2026-10-16T00:00:00Z"}]
            if "factory_project_github_access?" in path:
                return [{"status": "ready", "repository": repository,
                         "observed_capabilities": {"contents_read": "verified"},
                         "last_verified_at": "2026-10-23T21:00:00Z"}]
            if "factory_projects?" in path:
                return [{"id": project_id, "project_kind": "greenfield",
                         "repository": repository, "manifest": manifest}]
            raise AssertionError("unexpected query: " + path)
        queue._get = read
        github = MagicMock()
        github.repository = repository
        github.get_branch_sha.return_value = sha
        github.list_file_paths.return_value = ("README.md", "package.json", "src/domain/ticket.ts")
        github.get_file_text.side_effect = lambda path, ref: {
            "README.md": "# Service Desk",
            "package.json": '{"name":"infodive-service-desk"}',
            "src/domain/ticket.ts": "export const ticketCanReopen = true;",
        }[path]

        with patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter", return_value=github):
            claimed = queue.claim_next("worker-1")
        self.assertIsNotNone(claimed)
        self.assertNotIn("state_snapshot", claimed.context)
        live = claimed.context["current_state_facts"]["live_candidate"]
        self.assertEqual(live["source_evidence"]["status"], "bounded_source_inspected")
        self.assertIsNone(live["verified_open_pr"])
        self.assertEqual(live["sha"], sha)
        self.assertTrue(all("project_id=eq." + project_id in q for q in reads[:3]))
        github.get_file_text.assert_any_call("src/domain/ticket.ts", ref=sha)
        self.assertEqual(github.get_branch_sha.call_count, 2)

        class FakeProvider:
            def __init__(self): self.calls=[]
            def execute(self, request):
                self.calls.append(request)
                return ModelResult(
                    ModelRole.PRIMARY,
                    '{"observed_stage":"implementation","summary":"live source verified",'
                    '"evidence":[],"gaps":[],"constraints":[],"source_status":{}}',
                    provider_ref="offline-fixture",
                )
        provider=FakeProvider()
        result=ProductStageExecutor(ModelExecutor(primary=provider)).execute(claimed, "reconciliation")
        self.assertEqual(result["summary"], "live source verified")
        self.assertEqual(len(provider.calls), 1)
        self.assertIn("Console greenfield", provider.calls[0].objective)

    def test_empty_paid_planning_records_only_fixed_failure_receipt(self):
        from ai_product_factory.product_stage_output_contract import NON_ACTIONABLE_PLANNING_EVIDENCE
        q = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="secret")
        item = WorkItem("run", "task", "project", "existing", ("planning",), {}, 2, "worker")
        observed = []
        def rpc(name, payload):
            observed.append((name, payload))
            if name not in {"factory_assert_claimed_run_epoch", "factory_record_runtime_stage"}:
                raise AssertionError("unexpected RPC: " + name)
        q._rpc = rpc
        q.record_non_actionable_planning(item)
        self.assertEqual([name for name, _ in observed], [
            "factory_assert_claimed_run_epoch", "factory_record_runtime_stage",
        ])
        self.assertEqual(observed[-1][1]["p_stage"], "planning")
        self.assertEqual(observed[-1][1]["p_status"], "failed")
        self.assertEqual(observed[-1][1]["p_output"], NON_ACTIONABLE_PLANNING_EVIDENCE)
        self.assertNotIn("provider_ref", repr(observed[-1][1]))
        with self.assertRaisesRegex(ValueError, "planning"):
            q.record_non_actionable_planning(WorkItem(
                "run", "task", "project", "existing", ("reconciliation",), {}, 2, "worker"
            ))
        self.assertEqual(len(observed), 2)

    def test_candidate_issue_scope_conflict_blocks_before_code_scan(self):
        from ai_product_factory.source_scope_admission import SourceScopeBlocked
        from unittest.mock import MagicMock
        from types import SimpleNamespace
        q = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="secret")
        sha = "b" * 40
        target = {
            "schema_version": 1, "mode": "open_pr_candidate",
            "repository": "owner/crm", "branch": "preview/current", "sha": sha,
            "candidate_pr_number": 56,
        }
        q._get = lambda path: [{"project_kind": "existing", "repository": "owner/crm",
                                "manifest": {"delivery_target": target,
                                             "continuation_request": {
                                                 "summary": "Implementar a issue CRM #24."
                                             }}}]
        github = MagicMock()
        github.repository = "owner/crm"
        github.get_branch_sha.side_effect = lambda ref: sha if ref == "preview/current" else "a" * 40
        github.get_pull_request.return_value = SimpleNamespace(
            state="open", merged=False, head_sha=sha, head_ref="preview/current",
            head_repository="owner/crm", base_ref="main",
        )
        github.get_file_text.side_effect = lambda path, ref: (
            "## Tarefa autorizada (2026-10-19): atual\nOrigem: CRM issue #33\n"
            if path == "docs/codex/CURRENT_TASK.md" else "# Repository governance\n"
        )
        with patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter", return_value=github):
            with self.assertRaises(SourceScopeBlocked) as failure:
                q._live_candidate_context("project", {})
        self.assertEqual(failure.exception.code, "source_authorization_issue_mismatch")
        github.list_file_paths.assert_not_called()

    def test_only_latest_current_task_reaches_model_context(self):
        from unittest.mock import MagicMock
        from types import SimpleNamespace
        q = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="secret")
        sha = "c" * 40
        target = {"schema_version": 1, "mode": "open_pr_candidate", "repository": "owner/crm",
                  "branch": "preview/current", "sha": sha, "candidate_pr_number": 56}
        q._get = lambda path: [{"project_kind": "existing", "repository": "owner/crm",
                                "manifest": {"delivery_target": target,
                                             "continuation_request": {
                                                 "summary": "Implementar a issue CRM #33."
                                             }}}]
        github = MagicMock()
        github.repository = "owner/crm"
        github.get_branch_sha.side_effect = lambda ref: sha if ref == "preview/current" else "a" * 40
        github.get_pull_request.return_value = SimpleNamespace(
            state="open", merged=False, head_sha=sha, head_ref="preview/current",
            head_repository="owner/crm", base_ref="main",
        )
        tick = chr(96)
        task = (
            "## Authorized task (2026-10-10): obsolete\n"
            "Old code and disabled requirements.\n"
            "## Tarefa autorizada (2026-10-19): active\n"
            "Origem: CRM issue #33\n"
            + tick + "src/lib/current.ts" + tick + "\n"
        )
        github.get_file_text.side_effect = lambda path, ref: (
            task if path == "docs/codex/CURRENT_TASK.md"
            else ("export const safe = true;" if path == "src/lib/current.ts"
                  else "# Repository governance\n")
        )
        github.list_file_paths.return_value = ("src/lib/current.ts",)
        with patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter", return_value=github):
            result = q._live_candidate_context("project", {})
        candidate = result["current_state_facts"]["live_candidate"]
        current = candidate["governance"]["docs/codex/CURRENT_TASK.md"]
        self.assertNotIn("obsolete", current)
        self.assertNotIn("Old code", current)
        self.assertIn("2026-10-19", current)
        self.assertEqual(candidate["source_evidence"]["issue_scope_alignment"]["status"], "matched")
        self.assertEqual(candidate["governance_selection"],
                         "exact_sha_latest_authorized_section_only")

    def test_claimed_run_without_epoch_cannot_write_stage_or_finish(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen",return_value=Response({
            "run_id":"r","task_id":"t","project_id":"p","project_key":"demo",
            "stages":["discovery"],"context":{}
        })):
            with self.assertRaisesRegex(RuntimeError,"generation"):
                q.claim_next("worker")

    def test_noncompleted_stage_evidence_never_persists_product_data(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},2,"worker")
        with patch("urllib.request.urlopen") as network:
            for status in ("started","failed","pending"):
                with self.subTest(status=status):
                    with self.assertRaises(ValueError):
                        q.record_stage(item,StageEvidence("planning",status,{}))
            network.assert_not_called()

    def test_execution_epoch_calls_privileged_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3,"worker")
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.assert_execution_epoch(item)
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rpc/factory_assert_claimed_run_epoch"))
        self.assertEqual(json.loads(req.data),{"p_project_id":"p","p_generation":3,"p_run_id":"r","p_worker_id":"worker"})
        self.assertNotIn(b"secret",req.data)

    def test_claim_maps_rpc_payload_without_leaking_key(self):
        payload={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo","stages":["discovery"],"context":{"x":1},"execution_generation":1}
        with patch("urllib.request.urlopen",return_value=Response(payload)) as call:
            q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
            item=q.claim_next("w")
        self.assertEqual(item.project_key,"demo")
        self.assertEqual(item.stages,("discovery",))
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_claim_next_run"))
        self.assertNotIn(b"secret",req.data)

    def test_real_reconciliation_claim_hydrates_project_scoped_snapshot_and_fresh_facts(self):
        q = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="secret")
        q._live_candidate_context = lambda project_id, context: context
        q._rpc = lambda name, payload: {
            "run_id": "run-crm", "task_id": "task-crm",
            "project_id": "11111111-1111-4111-8111-111111111111",
            "project_key": "crm-infodive", "stages": ["reconciliation", "gap_analysis", "planning"],
            "context": {"manifest": {"continuation_request": {"summary": "CRM PR #56"}}},
            "execution_generation": 1,
        }
        queries = []
        def scoped_get(path):
            queries.append(path)
            if "factory_project_state_snapshots?" in path:
                return [{
                    "id": "snapshot-old", "observed_stage": "operations",
                    "created_at": "2026-10-02T21:47:38Z",
                    "summary": "Reviewed historical CRM baseline",
                    "evidence": [{"source": "github", "commit": "old"}],
                    "gaps": [], "constraints": [],
                    "source_status": {"github_repository": "verified_earlier"},
                }]
            if "factory_tasks?" in path:
                return [{"external_key": "present-in-usd", "title": "historical fix",
                         "status": "completed", "updated_at": "2026-10-15T10:00:00Z"}]
            if "factory_project_github_access?" in path:
                return [{"status": "ready", "repository": "owner/crm",
                         "observed_capabilities": {"contents_write": "verified"},
                         "last_verified_at": "2026-10-15T12:00:00Z"}]
            raise AssertionError("unexpected read " + path)
        q._get = scoped_get
        item = q.claim_next("worker-test")
        self.assertEqual(item.context["state_snapshot"]["summary"], "Reviewed historical CRM baseline")
        self.assertEqual(item.context["state_snapshot"]["provenance"],
                         "historical_control_plane_snapshot_not_live_github")
        self.assertEqual(item.context["state_snapshot"]["recorded_at"], "2026-10-02T21:47:38Z")
        self.assertEqual(item.context["current_state_facts"]["recent_tasks"][0]["status"], "completed")
        self.assertFalse(item.context["current_state_facts"]["github_access"]["live_github_head_verified"])
        self.assertEqual(len(queries), 3)
        self.assertTrue(all("project_id=eq.11111111-1111-4111-8111-111111111111" in v for v in queries))
        self.assertIn("observed_stage=neq.verification", queries[0])
        self.assertIn("limit=24", queries[1])
        self.assertIn("limit=1", queries[2])
        class Provider:
            requests = []
            def execute(self, request):
                self.requests.append(request)
                return ModelResult(ModelRole.PRIMARY, '{"summary":"ok"}', provider_ref="mock", usage={})
        provider = Provider()
        output = ProductStageExecutor(ModelExecutor(primary=provider)).execute(item, "reconciliation")
        self.assertEqual(output["summary"], "ok")
        self.assertEqual(len(provider.requests), 1)
        self.assertIn("historical_control_plane_snapshot_not_live_github", provider.requests[0].context)

    def test_missing_snapshot_or_failed_snapshot_read_cannot_use_paid_model(self):
        q = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="secret")
        q._live_candidate_context = lambda project_id, context: context
        q._rpc = lambda *_: {
            "run_id": "r", "task_id": "t", "project_id": "project", "project_key": "existing",
            "stages": ["reconciliation"], "context": {"manifest": {"reconcile_first": True}},
            "execution_generation": 2,
        }
        for snapshot_rows in (
            [{"observed_stage": "operations", "summary": "", "evidence": [{"source": "x"}]}],
            [{"observed_stage": "verification", "summary": "browser", "evidence": [{"source": "x"}]}],
            [{"observed_stage": "operations", "summary": "historical", "evidence": [],
              "source_status": {}}],
        ):
            q._get = lambda path: snapshot_rows if "factory_project_state_snapshots?" in path else []
            item = q.claim_next("worker")
            self.assertNotIn("state_snapshot", item.context)
            class ForbiddenProvider:
                def execute(self, request):
                    raise AssertionError("paid provider must never be called")
            with self.assertRaisesRegex(ValueError, "durable state snapshot"):
                ProductStageExecutor(ModelExecutor(primary=ForbiddenProvider())).execute(item, "reconciliation")
        q._get = lambda path: (_ for _ in ()).throw(RuntimeError("temporarily unavailable"))
        item = q.claim_next("worker")
        self.assertNotIn("state_snapshot", item.context)

    def test_greenfield_claim_does_not_fetch_existing_project_snapshot(self):
        q = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="secret")
        q._rpc = lambda *_: {
            "run_id": "r", "task_id": "t", "project_id": "p", "project_key": "demo",
            "stages": ["discovery", "specification"], "context": {"summary": "new system"},
            "execution_generation": 1,
        }
        q._get = lambda *_: (_ for _ in ()).throw(AssertionError("greenfield must not load snapshot"))
        item = q.claim_next("worker")
        self.assertEqual(item.context, {"summary": "new system"})

    def test_live_candidate_context_and_sha_drift(self):
        q = SupabaseRuntimeQueue(url="https://example.supabase.co", service_role_key="secret")
        sha = "f5f7d91f8e98cfaf482cca72c974abb7a82f6a5e"
        target = {"schema_version": 1, "mode": "open_pr_candidate",
                  "repository": "owner/crm", "branch": "preview/candidate",
                  "sha": sha, "candidate_pr_number": 56}
        q._get = lambda path: [{"project_kind": "existing", "repository": "owner/crm",
                                "manifest": {"delivery_target": target, "continuation_request": {"summary": "Fix src/components/automations/AutomationBuilder.tsx"}}}]
        from unittest.mock import MagicMock
        from types import SimpleNamespace
        github = MagicMock()
        github.repository = "owner/crm"
        github.get_branch_sha.side_effect = lambda ref: sha if ref == "preview/candidate" else "a" * 40
        github.get_pull_request.return_value = SimpleNamespace(
            state="open", merged=False, head_sha=sha, head_ref="preview/candidate",
            head_repository="owner/crm", base_ref="main")
        tick = chr(96)
        github.get_file_text.side_effect = lambda path, ref: (
            "## Authorized task (2026-10-10): test scope\n"
            + tick + "src/services/SettingsService.ts" + tick
            if path == "docs/codex/CURRENT_TASK.md"
            else ("code evidence" if path.endswith(".ts") else "governance for " + path)
        )
        github.list_file_paths.return_value = ("src/services/SettingsService.ts", "src/components/automations/AutomationBuilder.tsx")
        with patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter", return_value=github):
            evidence = q._live_candidate_context("project-id", {"current_state_facts": {}})
        observed = evidence["current_state_facts"]["live_candidate"]
        self.assertEqual(observed["sha"], sha)
        self.assertIn("AGENTS.md", observed["governance"])
        self.assertTrue(observed["verified_open_pr"]["verified"])
        self.assertEqual(
            observed["source_evidence"]["inspected_files"][0]["path"],
            "src/components/automations/AutomationBuilder.tsx"
        )
        self.assertEqual(observed["source_evidence"]["request_source_paths"],
                         ["src/components/automations/AutomationBuilder.tsx"])
        github.get_file_text.assert_any_call("AGENTS.md", ref=sha)
        github.get_branch_sha.side_effect = lambda ref: "b" * 40
        with patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter", return_value=github):
            with self.assertRaises(PermissionError):
                q._live_candidate_context("project-id", {})
        q._get = lambda path: []
        with self.assertRaises(PermissionError):
            q._live_candidate_context("project-id", {})

    def test_claim_rejects_missing_or_blank_identifiers(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        base={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo",
              "stages":["discovery"],"context":{},"execution_generation":2}
        for key in ("run_id","task_id","project_id","project_key"):
            for invalid in (None,"","  ",42):
                with self.subTest(key=key,invalid=invalid):
                    q._rpc=lambda name,args: {**base,key:invalid}
                    with self.assertRaisesRegex(RuntimeError,"identifiers"):
                        q.claim_next("worker")

    def test_claim_rejects_missing_or_invalid_generation(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        base={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo",
              "stages":["discovery"],"context":{}}
        for generation in (None,0,-1,True,"2"):
            with self.subTest(generation=generation):
                q._rpc=lambda name,args: {**base,"execution_generation":generation}
                with self.assertRaisesRegex(RuntimeError,"generation"):
                    q.claim_next("worker")

    def test_claim_rejects_malformed_rpc_payloads(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        for payload in ([], "unexpected", {"stages":"planning"},
                        {"stages":[None]}, {"stages":[""]},
                        {"stages":[],"context":[]}, {"stages":{}},
                        {"stages":[42]}):
            with self.subTest(payload=payload):
                q._rpc=lambda name,args: payload
                with self.assertRaises((RuntimeError,KeyError,TypeError)):
                    q.claim_next("worker")

    def test_claim_rejects_empty_duplicate_or_whitespace_stages(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        base={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo",
              "context":{},"execution_generation":1}
        for stages in ([],["planning","planning"],[" planning"],["planning "],None):
            with self.subTest(stages=stages):
                q._rpc=lambda name,args: {**base,"stages":stages}
                with self.assertRaisesRegex(RuntimeError,"stages"):
                    q.claim_next("worker")

    def test_claim_rejects_invalid_worker_id_before_network(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen") as network:
            for worker in ("","  ",None,12):
                with self.subTest(worker=worker):
                    with self.assertRaisesRegex(ValueError,"worker id"):
                        q.claim_next(worker)
            network.assert_not_called()

    def test_invalid_stage_name_and_output_never_write(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},2,"worker")
        with patch("urllib.request.urlopen") as network:
            for stage in ("", "  ",None):
                with self.assertRaisesRegex(ValueError,"stage name"):
                    q.record_stage_event(item,stage,"started")
                with self.assertRaisesRegex(ValueError,"stage name"):
                    q.record_stage(item,StageEvidence(stage,"completed",{}))
            for output in (None,[], "invalid"):
                with self.assertRaisesRegex(ValueError,"mapping"):
                    q.record_stage(item,StageEvidence("planning","completed",output))
            network.assert_not_called()

    def test_claim_carries_generation_from_database(self):
        payload={"run_id":"r","task_id":"t","project_id":"p","project_key":"demo",
                 "stages":["discovery"],"context":{},"execution_generation":7}
        with patch("urllib.request.urlopen",return_value=Response(payload)):
            q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
            item=q.claim_next("worker")
        self.assertEqual(item.execution_generation,7)

    def test_terminal_and_stage_rpcs(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3,"worker")
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage(item,StageEvidence("discovery","completed",{"ok":True}))
            q.complete(item);q.fail(item,"x")
        self.assertEqual(call.call_count,7)

    def test_terminal_failure_without_generation_never_writes(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        with patch("urllib.request.urlopen") as call:
            with self.assertRaisesRegex(RuntimeError,"generation"):
                q.fail(item,"error")
            call.assert_not_called()

    def test_reconciliation_and_gap_analysis_use_product_stage_persistence(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","crm-infodive",(),{}, 3,"worker")
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage(item,StageEvidence("reconciliation","completed",{"summary":"ok"}))
            q.record_stage(item,StageEvidence("gap_analysis","completed",{"gaps":[]}))
        urls=[x.args[0].full_url for x in call.call_args_list]
        self.assertEqual(sum(url.endswith("/rest/v1/rpc/factory_record_runtime_stage") for url in urls),2)
        self.assertEqual(sum(url.endswith("/rest/v1/rpc/factory_persist_product_stage") for url in urls),2)

    def test_stage_lifecycle_event_uses_existing_runtime_stage_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3,"worker")
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage_event(item,"planning","started")
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_record_runtime_stage"))
        body=json.loads(req.data.decode())
        self.assertEqual(body["p_stage"],"planning")
        self.assertEqual(body["p_status"],"started")
        self.assertEqual(body["p_output"],{})

    def test_stage_lifecycle_event_rejects_unknown_status(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3,"worker")
        with self.assertRaises(ValueError):
            q.record_stage_event(item,"planning","mystery")


    def test_invalid_stage_event_never_contacts_backend(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3,"worker")
        with patch("urllib.request.urlopen") as call:
            with self.assertRaises(ValueError):
                q.record_stage_event(item,"planning","invalid")
            call.assert_not_called()

    def test_missing_generation_blocks_stage_write(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{})
        with patch("urllib.request.urlopen") as call:
            with self.assertRaisesRegex(RuntimeError,"generation"):
                q.record_stage(item,StageEvidence("planning","completed",{}))
            call.assert_not_called()

    def test_non_executed_stage_evidence_cannot_bypass_worker_to_persistence(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3,"worker")
        for output in (
            {"placeholder":True},
            {"simulated":"true"},
            {"execution_mode":"dry-run"},
        ):
            with self.subTest(output=output), patch("urllib.request.urlopen") as call:
                with self.assertRaisesRegex(ValueError,"product_stage_output_not_executed"):
                    q.record_stage(item,StageEvidence("planning","completed",output))
                call.assert_not_called()

    def test_retry_failed_run_uses_privileged_rpc_without_leaking_secret_in_body(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        payload={"source_run_id":"old","run_id":"new","status":"queued","task_status":"queued"}
        with patch("urllib.request.urlopen",return_value=Response(payload)) as call:
            out=q.retry_failed_run("old","operator retry after fix")
        self.assertEqual(out["run_id"],"new")
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_retry_failed_run"))
        body=json.loads(req.data.decode())
        self.assertEqual(body,{"p_source_run_id":"old","p_reason":"operator retry after fix"})
        self.assertNotIn(b"secret",req.data)

    def test_retry_failed_run_requires_source_and_reason_before_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen") as call:
            with self.assertRaises(ValueError):q.retry_failed_run("","reason")
            with self.assertRaises(ValueError):q.retry_failed_run("old"," ")
        call.assert_not_called()

    def test_recovery_rpc_is_bounded_and_service_secret_not_in_body(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen",return_value=Response({"requeued":1,"failed":0})) as call:
            out=q.recover_expired(3)
        self.assertEqual(out,{"requeued":1,"failed":0})
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_recover_expired_runs"))
        self.assertNotIn(b"secret",req.data)

    def test_decision_resume_recovery_uses_dedicated_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        with patch("urllib.request.urlopen",return_value=Response({"created":1,"existing":0,"blocked":0})) as call:
            out=q.resume_resolved_decisions()
        self.assertEqual(out,{"created":1,"existing":0,"blocked":0})
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_resume_resolved_decisions"))
        self.assertEqual(json.loads(req.data.decode()),{})
        self.assertNotIn(b"secret",req.data)


    def test_terminal_descendant_reconciliation_uses_dedicated_rpc(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        payload={"completed_children":2,"cancelled_children":3,"superseded_change_sets":1}
        with patch("urllib.request.urlopen",return_value=Response(payload)) as call:
            out=q.reconcile_terminal_descendants()
        self.assertEqual(out,payload)
        req=call.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/rest/v1/rpc/factory_reconcile_terminal_task_descendants"))
        self.assertEqual(json.loads(req.data.decode()),{})
        self.assertNotIn(b"secret",req.data)


    def test_planning_stage_persists_execution_team_plan(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","demo",(),{},3,"worker")
        output={"tasks":[],"_team_plan":{"version":1,"status":"ready","profiles_selected":0,"planned_worker_peak":0,"blockers":[]}}
        with patch("urllib.request.urlopen",return_value=Response(None)) as call:
            q.record_stage(item,StageEvidence("planning","completed",output))
        urls=[x.args[0].full_url for x in call.call_args_list]
        self.assertTrue(any(url.endswith("/rest/v1/rpc/factory_record_execution_team_plan") for url in urls))
        self.assertGreaterEqual(call.call_count,3)


    def test_planning_decision_gate_skips_team_plan_and_change_set_materialization(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        item=WorkItem("r","t","p","crm-infodive",(),{"manifest":{}}, 3,"worker")
        output={
            "tasks":[{"task_key":"debug","title":"Debug","required_capabilities":["implementation"],"scope_keys":["src"],"depends_on":[]}],
            "decisions_needed":[{"decision_key":"approve_debug_contract","question":"What may remain visible?"}],
            "_team_plan":{"version":1,"status":"ready","profiles_selected":1,"planned_worker_peak":1,"blockers":[]},
        }
        calls=[]
        def rpc(name,payload):
            calls.append((name,payload))
            if name=="factory_persist_product_stage":
                return {"human_gate_id":"gate-1","created_tasks":0}
            if name=="factory_record_definition_of_done":
                return {"id":"dod-1"}
            if name in {
                "factory_assert_claimed_run_epoch",
                "factory_record_runtime_stage",
                "factory_record_requirement_trace",
                "factory_record_project_brain_snapshot",
            }:
                return {}
            raise AssertionError(name)
        q._rpc=rpc
        q.record_stage(item,StageEvidence("planning","completed",output))
        names=[name for name,_ in calls]
        self.assertIn("factory_persist_product_stage",names)
        self.assertNotIn("factory_record_execution_team_plan",names)
        self.assertNotIn("factory_materialize_change_set",names)
        self.assertIn("factory_record_definition_of_done",names)


    def test_rebuild_team_plan_uses_persisted_engineering_plan_and_materializes_ready_change_set(self):
        from ai_product_factory.agent_scheduler import AgentProfile
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        q._get=lambda path: (
            [{"id":"run-1","task_id":"task-1"}] if path.startswith("factory_runs?")
            else [{"id":"task-1","project_id":"project-1"}] if path.startswith("factory_tasks?")
            else [{"id":"project-1","manifest":{"engineering_plan":{"tasks":[{"task_key":"api","title":"API","required_capabilities":["implementation"],"scope_keys":["src"],"depends_on":[]}]}}}]
        )
        calls=[]
        def rpc(name,payload):
            calls.append((name,payload))
            if name=="factory_record_execution_team_plan":
                return {"id":"tp-1","status":"ready"}
            if name=="factory_materialize_change_set":
                return {"change_set_id":"cs-1","builder_work_units":1,"status":"planned"}
            raise AssertionError(name)
        q._rpc=rpc
        profile=AgentProfile("development","development",("implementation",),("github_write",),{"preferred":"primary"},1,1.0,True)
        out=q.rebuild_team_plan("run-1",(profile,))
        self.assertEqual(out["status"],"ready")
        self.assertEqual(out["change_set"]["change_set_id"],"cs-1")
        self.assertEqual([name for name,_ in calls],["factory_record_execution_team_plan","factory_materialize_change_set"])


class CurrentStateFactsMigrationTests(unittest.TestCase):
    def test_claim_next_run_includes_current_control_plane_facts(self):
        from pathlib import Path
        sql=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261004200200_factory_claim_current_state_facts.sql").read_text()
        compact=" ".join(sql.split())
        self.assertIn("'current_state_facts'",sql)
        self.assertIn("'recent_tasks'",sql)
        self.assertIn("factory_project_github_access",sql)
        self.assertIn("'observed_capabilities'",sql)
        self.assertIn("'pending_human_gates'",sql)
        self.assertIn("factory_human_gates",sql)
        self.assertIn("limit 25",sql.lower())
        self.assertNotIn("token",sql.lower())
        self.assertIn("revoke all on function public.factory_claim_next_run(text)",compact.lower())
        self.assertIn("grant execute on function public.factory_claim_next_run(text) to service_role",compact.lower())


class ProductStagePersistenceMigrationTests(unittest.TestCase):
    def test_reconciliation_runtime_migration_preserves_agent_fields(self):
        from pathlib import Path
        sql=(Path(__file__).resolve().parents[1]/"supabase/migrations/20261004145700_reconcile_product_stage_runtime.sql").read_text()
        self.assertIn("'reconciliation'",sql)
        self.assertIn("'gap_analysis'",sql)
        self.assertIn("factory_project_state_snapshots",sql)
        self.assertIn("'gap_analysis'",sql)
        self.assertIn("agent_role,required_capabilities,scope_keys",sql.replace("\n","" ).replace(" ",""))
        self.assertIn("preferred_agent_role",sql)
        self.assertIn("security invoker",sql.lower())


    def test_checkpointed_planning_claim_reuses_exact_source_without_paid_pre_stages(self):
        import copy
        project_id="2d30e00a-ff72-4044-b838-011c263ed672"
        root_id="e174ef34-e9a4-4088-af0e-785efba663cc"
        source_id="090cd768-b6e5-44ce-9d77-92f9ffe9620d"
        new_id="6cbdb11b-8263-4cb6-bb86-09f33ae470de"
        snapshot_id="c702b7e7-58b4-49ad-8be9-ee87b4f3c15d"
        request_id="2a0161b6-1c8d-a921-1a7a-293322e0bb0c"
        recon={"summary":"verified source","observed_stage":"repository",
               "evidence":[{"sha":"a"*40}],"gaps":[],
               "constraints":[],"source_status":{"github":"verified"}}
        gap={"gaps":[{"type":"ux"}],"recommended_next_work":[{"work":"fix"}],
             "_evidence":{"provider_ref":"paid-real-stage"}}
        request={"id":request_id,"source":"github-owner"}
        manifest={"continuation_request":request,"gap_analysis":gap}
        proof={"schema":"checkpointed_product_planning_v1",
               "source_run_id":source_id,"source_generation":6,
               "snapshot_id":snapshot_id,"request_id":request_id,
               "project_id":project_id,"reconciliation":recon,"gap_analysis":gap}
        claimed={"id":new_id,"task_id":root_id,"status":"running",
                 "metadata":{"stages":["planning"],"execution_generation":6,
                             "continuation_request_id":request_id,
                             "resume_checkpoint":proof}}
        source={"id":source_id,"task_id":root_id,"status":"failed",
                "execution_route":"direct","metadata":{
                    "stages":["reconciliation","gap_analysis","planning"],
                    "execution_generation":6,"continuation_request_id":request_id,
                    "error":"reserved provider cost exceeds remaining budget"}}
        snap={"id":snapshot_id,"run_id":source_id,"project_id":project_id,**recon}
        proj={"id":project_id,"manifest":manifest}
        rows={"runs_new":[claimed],"runs_source":[source],
              "snapshots":[snap],"project":[proj]}

        def exercise(rows):
            q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
            q._rpc=lambda *_:{
                "run_id":new_id,"task_id":root_id,"project_id":project_id,
                "project_key":"crm-infodive","execution_generation":6,
                "stages":["planning"],"context":{"manifest":manifest}}
            calls=[]
            def get(path):
                calls.append(path)
                if path.startswith("factory_runs?"):
                    return rows["runs_new"] if "id=eq."+new_id in path else rows["runs_source"]
                if path.startswith("factory_project_state_snapshots?"):
                    return rows["snapshots"]
                if path.startswith("factory_projects?"):
                    return rows["project"]
                raise AssertionError("unexpected query")
            q._get=get
            q._live_candidate_context=lambda pid,ctx:ctx
            failures=[]
            q.fail=lambda item,reason:failures.append(reason)
            return q,calls,failures

        q,reads,failures=exercise(rows)
        item=q.claim_next("worker")
        self.assertEqual(item.stages,("planning",))
        self.assertEqual(item.context["_verified_resume_prior_stages"],
                         {"reconciliation":recon,"gap_analysis":gap})
        self.assertEqual(item.context["_verified_resume_origin"]["source_run_id"],source_id)
        self.assertEqual(len(reads),4)
        self.assertEqual(failures,[])
        self.assertFalse(any("rpc/" in path for path in reads))

        class PlanningProvider:
            def __init__(self):self.calls=[]
            def execute(self,request):
                self.calls.append(request)
                return ModelResult(ModelRole.PRIMARY,json.dumps({
                    "tasks":[{"task_key":"fix-ux","scope_keys":["src/app/ux.tsx"],
                              "required_capabilities":["implementation"],"depends_on":[]}],
                    "decisions_needed":[]}))
        provider=PlanningProvider()
        handler=ProductStageExecutor(ModelExecutor(primary=provider))
        output=handler.execute(item,"planning")
        self.assertEqual(len(provider.calls),1)
        payload=json.loads(provider.calls[0].context)
        self.assertEqual(payload["prior_stages"]["reconciliation"],recon)
        self.assertEqual(payload["prior_stages"]["gap_analysis"],gap)
        self.assertNotIn("gap_analysis",payload["intake"]["manifest"])
        self.assertEqual(output["tasks"][0]["task_key"],"fix-ux")

        # No individual source/output, project or epoch drift may pay for
        # planning: the claim fails and its durable failure is recorded.
        mutants=(
            lambda r:r["runs_new"][0]["metadata"]["resume_checkpoint"].update(
                source_generation=5),
            lambda r:r["runs_new"][0]["metadata"]["resume_checkpoint"].update(
                request_id="bad"),
            lambda r:r["runs_source"][0].update(status="completed"),
            lambda r:r["runs_source"][0]["metadata"].update(error="different failure"),
            lambda r:r["runs_source"][0]["metadata"].update(execution_generation=5),
            lambda r:r["snapshots"][0].update(summary="injected"),
            lambda r:r["snapshots"][0].update(run_id="foreign"),
            lambda r:r["project"][0]["manifest"]["gap_analysis"].update(
                recommended_next_work=[]),
        )
        for mutate in mutants:
            with self.subTest(mutate=str(mutate)):
                altered=copy.deepcopy(rows)
                mutate(altered)
                q,_,failures=exercise(altered)
                with self.assertRaisesRegex(PermissionError,"planning resume provenance invalid"):
                    q.claim_next("worker")
                self.assertEqual(failures,["planning_resume_provenance_preflight_failed"])

    def test_regular_single_stage_planning_does_not_require_resume(self):
        q=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="secret")
        q._rpc=lambda *_:{
            "run_id":"r","task_id":"t","project_id":"p",
            "project_key":"greenfield","execution_generation":2,
            "stages":["planning"],"context":{"manifest":{"goal":"ship"}}}
        q._get=lambda path:[{"id":"r","task_id":"t","status":"running","metadata":{}}]
        item=q.claim_next("worker")
        self.assertEqual(item.stages,("planning",))
        self.assertNotIn("_verified_resume_prior_stages",item.context)


if __name__=="__main__":
    unittest.main()
