import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from ai_product_factory.nonproduction_preview_merge import verify_nonproduction_preview_merge
from ai_product_factory.runtime_cli import run_release_once


HEAD="a"*40
MERGE="b"*40
MAIN="c"*40
TIP="d"*40


def item():
    return SimpleNamespace(
        run_id="r",repository="owner/crm",candidate_commit=HEAD,pr_number=180,
        branch="factory/change-set-9e4647f6",release_source="delivery",
        merge_sha=None,issue_number=179,project_id="p",
    )


def pr(merged=True,base="preview/hardening-release-candidate"):
    return SimpleNamespace(
        number=180,head_sha=HEAD,head_ref=item().branch,
        head_repository="owner/crm",base_ref=base,
        state="closed" if merged else "open",
        merged=merged,merge_commit_sha=MERGE if merged else None,
    )


def github():
    g=MagicMock()
    g.get_branch_sha.side_effect=lambda branch: MERGE if branch.startswith("preview/") else MAIN
    g.get_commit_statuses.return_value=[{"context":"Vercel","state":"success"}]
    return g


class NonproductionMergeObserverTests(unittest.TestCase):
    def test_observes_exact_preview_merge_without_production_release(self):
        g=github()
        result=verify_nonproduction_preview_merge(g,item(),pr())
        self.assertEqual(result["merge_sha"],MERGE)
        self.assertEqual(result["candidate_commit"],HEAD)
        self.assertEqual(result["base_ref"],"preview/hardening-release-candidate")
        self.assertIs(result["production_released"],False)
        g.compare_commits.assert_not_called()

    def test_pending_vercel_and_absent_status_wait(self):
        for statuses in ([{"context":"Vercel","state":"pending"}],[],[{"context":"Vercel Preview Comments","state":"success"}]):
            with self.subTest(statuses=statuses):
                g=github()
                g.get_commit_statuses.return_value=statuses
                self.assertIsNone(verify_nonproduction_preview_merge(g,item(),pr()))

    def test_vercel_failure_does_not_approve(self):
        g=github()
        g.get_commit_statuses.return_value=[{"context":"Vercel","state":"failure"}]
        with self.assertRaisesRegex(RuntimeError,"Vercel deployment failed"):
            verify_nonproduction_preview_merge(g,item(),pr())

    def test_diverged_branch_or_invalid_identity_fails_closed(self):
        g=github()
        g.get_branch_sha.side_effect=lambda branch: TIP if branch.startswith("preview/") else MAIN
        g.compare_commits.return_value={"status":"diverged","ahead_by":2,"behind_by":1}
        with self.assertRaisesRegex(RuntimeError,"bounded ancestor"):
            verify_nonproduction_preview_merge(g,item(),pr())
        altered=pr()
        altered.head_sha=MAIN
        with self.assertRaisesRegex(RuntimeError,"drifted"):
            verify_nonproduction_preview_merge(g,item(),altered)
        altered=pr()
        altered.base_ref="main"
        with self.assertRaisesRegex(RuntimeError,"preview"):
            verify_nonproduction_preview_merge(g,item(),altered)

    def test_descendant_tip_is_bounded_and_second_read_is_required(self):
        g=github()
        g.get_branch_sha.side_effect=lambda branch: TIP if branch.startswith("preview/") else MAIN
        g.compare_commits.return_value={"status":"ahead","ahead_by":1,"behind_by":0}
        receipt=verify_nonproduction_preview_merge(g,item(),pr())
        self.assertEqual(receipt["observed_base_tip"],TIP)
        self.assertEqual(g.get_branch_sha.call_count,3)

    def test_branch_moves_during_observation_is_rejected(self):
        g=github()
        heads=iter([MERGE,MAIN,TIP])
        g.get_branch_sha.side_effect=lambda branch:next(heads)
        with self.assertRaisesRegex(RuntimeError,"target moved"):
            verify_nonproduction_preview_merge(g,item(),pr())

    def test_real_release_lane_calls_only_preview_observer(self):
        g=github()
        g.get_pull_request.return_value=pr()
        store=MagicMock()
        store.find_verified_nonproduction_browser_snapshot.return_value={
            "snapshot_id":"12345678-1234-1234-1234-123456789012",
            "preview_url":"https://example-git-preview.vercel.app",
            "verifier_run_id":12345,
        }
        store.observe_nonproduction_preview_merge.return_value={
            "run_id":"r","status":"integrated","merge_sha":MERGE,"release_completed":False,
        }
        with patch("ai_product_factory.runtime_cli.SupabaseReleaseFollowupQueue") as queue_cls,patch(
            "ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=g),patch(
            "ai_product_factory.runtime_cli.SupabaseDeliveryStore",return_value=store):
            queue_cls.return_value.next_pending.return_value=item()
            result=run_release_once()
        self.assertEqual(result["status"],"integrated_nonproduction")
        self.assertIs(result["release_completed"],False)
        store.observe_nonproduction_preview_merge.assert_called_once()
        observed=store.observe_nonproduction_preview_merge.call_args.kwargs["verified_evidence"]
        self.assertEqual(observed["postmerge_browser_snapshot_id"],
                         "12345678-1234-1234-1234-123456789012")
        self.assertEqual(observed["verifier_run_id"],"12345")
        store.finalize_console_human_release.assert_not_called()
        store.update_run_status.assert_not_called()
        g.close_issue.assert_not_called()

    def test_missing_merged_sha_browser_evidence_waits_without_mutation(self):
        g=github()
        g.get_pull_request.return_value=pr()
        store=MagicMock()
        store.find_verified_nonproduction_browser_snapshot.return_value=None
        with patch("ai_product_factory.runtime_cli.SupabaseReleaseFollowupQueue") as queue_cls,patch(
            "ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=g),patch(
            "ai_product_factory.runtime_cli.SupabaseDeliveryStore",return_value=store):
            queue_cls.return_value.next_pending.return_value=item()
            result=run_release_once()
        self.assertEqual(result["status"],"wait_postmerge_browser_evidence")
        store.observe_nonproduction_preview_merge.assert_not_called()

    def test_open_preview_pr_waits_and_never_mutates(self):
        g=github()
        g.get_pull_request.return_value=pr(False)
        store=MagicMock()
        with patch("ai_product_factory.runtime_cli.SupabaseReleaseFollowupQueue") as queue_cls,patch(
            "ai_product_factory.runtime_cli.GitHubRestAdapter",return_value=g),patch(
            "ai_product_factory.runtime_cli.SupabaseDeliveryStore",return_value=store):
            queue_cls.return_value.next_pending.return_value=item()
            result=run_release_once()
        self.assertEqual(result["status"],"awaiting_nonproduction_merge")
        store.observe_nonproduction_preview_merge.assert_not_called()

    def test_snapshot_reader_requires_exact_sha_and_verified_browser(self):
        import json
        from unittest.mock import patch
        from ai_product_factory.supabase_delivery_store import SupabaseDeliveryStore
        class Response:
            def __init__(self,data):self.data=data
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):return json.dumps(self.data).encode()
        row={
            "id":"12345678-1234-1234-1234-123456789012",
            "evidence":{
                "candidate_commit":MERGE,"target_repository":"owner/crm",
                "preview":{"url":"https://demo.vercel.app","provider":"vercel",
                           "status":"browser_verified","browser_verifier_run_id":4321}},
            "source_status":{"vercel_preview":"resolved","browser_visual_validation":"success"},
            "constraints":{"production_merge_authorized":False},"gaps":[],
        }
        with patch("urllib.request.urlopen",return_value=Response([row])):
            store=SupabaseDeliveryStore(url="https://x.supabase.co",service_role_key="secret")
            found=store.find_verified_nonproduction_browser_snapshot(
                project_id="p",repository="owner/crm",merge_sha=MERGE)
        self.assertEqual(found["snapshot_id"],row["id"])
        invalid={**row,"evidence":{**row["evidence"],"candidate_commit":HEAD}}
        with patch("urllib.request.urlopen",return_value=Response([invalid])):
            self.assertIsNone(store.find_verified_nonproduction_browser_snapshot(
                project_id="p",repository="owner/crm",merge_sha=MERGE))
        bad={**row,"source_status":{"vercel_preview":"resolved","browser_visual_validation":"failure"}}
        with patch("urllib.request.urlopen",return_value=Response([bad])):
            with self.assertRaisesRegex(RuntimeError,"not a verified"):
                store.find_verified_nonproduction_browser_snapshot(
                    project_id="p",repository="owner/crm",merge_sha=MERGE)

    def test_contract_keeps_production_path_independent(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        runtime=(root/"src/ai_product_factory/runtime_cli.py").read_text()
        self.assertIn("if getattr(pr,\"base_ref\",None) not in (None,\"main\")",runtime)
        self.assertIn("SupabaseTraceabilityStore().record_delivery_evidence(",runtime)
        module=(root/"src/ai_product_factory/nonproduction_preview_merge.py").read_text()
        self.assertNotIn("merge_pull_request(",module)
        self.assertNotIn("mark_released(",module)


if __name__=="__main__":unittest.main()
