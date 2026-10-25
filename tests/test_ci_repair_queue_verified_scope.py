"""A failing test is not authority for an arbitrary model patch."""
import unittest

from ai_product_factory.ci_followup_queue import CIFollowupItem
from ai_product_factory.ci_repair_queue import DurableCIFailure, SupabaseCIRepairQueue

SHA="a"*40
SUMMARY=(
 "Verified failed GitHub Actions step (run and attempt bound); "
 "Verified native Vitest count: "
 "test=src/lib/sidebar-navigation-contract.test.ts "
 "source=src/components/layout/Sidebar.tsx expected=16 actual=17"
)


def item():
    return CIFollowupItem(
       run_id="123e4567-e89b-42d3-a456-426614174002",
       project_key="crm-infodive",repository="owner/crm",
       issue_number=7,branch="factory/change-set-a",pr_number=197,
       candidate_commit=SHA,human_gate_required=False,
       change_set_id="123e4567-e89b-42d3-a456-426614174001",
       project_id="123e4567-e89b-42d3-a456-426614174000",
       execution_generation=12,require_execution_generation=True,
    )


def failure(summary=SUMMARY,name="native-ci/tests",failure_class="code"):
    return DurableCIFailure(
       name=name,conclusion="failure",failure_class=failure_class,
       details_url="https://github.com/owner/crm/actions/runs/123/job/456",
       summary=summary,
    )


class AttestedNativeTestRepairQueueTests(unittest.TestCase):
    def test_verified_static_count_routes_only_to_gated_new_function(self):
        q=object.__new__(SupabaseCIRepairQueue)
        calls=[]
        q._rpc=lambda name,payload:calls.append((name,payload)) or {"status":"repair_pending"}
        ret=q.enqueue_failure(item=item(),failures=(failure(),),max_attempts=3)
        self.assertEqual(ret["status"],"repair_pending")
        self.assertEqual(calls[0][0],"factory_enqueue_ci_repair_verified_test_scope_v1")
        self.assertEqual(calls[0][1]["p_candidate_commit"],SHA)
        self.assertEqual(calls[0][1]["p_failures"][0]["summary"],SUMMARY)

    def test_opaque_test_failure_is_never_sent_to_legacy_rpc_or_model(self):
        for receipt in (
            "Verified failed GitHub Actions step (run and attempt bound)",
            SUMMARY.replace("actual=17","actual=20"),
            SUMMARY.replace("expected=16","expected=17"),
            SUMMARY.replace("src/lib/sidebar-navigation-contract.test.ts","../private.test.ts"),
            SUMMARY.replace("src/components/layout/Sidebar.tsx","src/../secret.tsx"),
        ):
            with self.subTest(receipt=receipt[:90]):
                q=object.__new__(SupabaseCIRepairQueue)
                calls=[]
                q._rpc=lambda name,payload:calls.append(name) or {}
                with self.assertRaises(PermissionError):
                    q.enqueue_failure(item=item(),failures=(failure(receipt),))
                self.assertEqual(calls,[])

    def test_mixed_tests_and_other_failure_cannot_expand_scopes(self):
        q=object.__new__(SupabaseCIRepairQueue)
        q._rpc=lambda *_:self.fail("attempted RPC after invalid failures")
        with self.assertRaises(PermissionError):
            q.enqueue_failure(item=item(),failures=(
               failure(),failure(name="native-ci/typescript")
            ))

    def test_normal_typecheck_retains_existing_service_role_rpc(self):
        q=object.__new__(SupabaseCIRepairQueue)
        calls=[]
        q._rpc=lambda name,payload:calls.append(name) or {"status":"repair_pending"}
        q.enqueue_failure(item=item(),failures=(
            failure("Verified native TypeScript identifiers only: src/x.ts:1:1 TS2307",
                    name="native-ci/typescript"),
        ))
        self.assertEqual(calls,["factory_enqueue_ci_repair"])


if __name__=="__main__":
    unittest.main()
