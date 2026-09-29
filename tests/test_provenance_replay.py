import unittest
from unittest.mock import MagicMock

from ai_product_factory.provenance_replay import (
    SupabaseProvenanceStore,build_run_provenance,canonical_hash,
)


class ProvenanceReplayTests(unittest.TestCase):
    def test_provenance_snapshot_is_stable_and_versions_decisions(self):
        packet={"sha256":"a"*64}
        snapshot=build_run_provenance(
            run_id="run",project_key="demo",route="direct",agent_key="development",
            context_packet=packet,team_plan={"version":3},project_manifest={"preview":{"required":True}},
            candidate_commit="b"*40,
        )
        self.assertEqual(snapshot["context_packet_hash"],"a"*64)
        self.assertEqual(snapshot["team_plan_version"],3)
        self.assertEqual(snapshot["versions"]["release_policy"],"v1")
        self.assertEqual(
            snapshot["snapshot_hash"],
            canonical_hash({k:v for k,v in snapshot.items() if k!="snapshot_hash"}),
        )

    def test_replay_store_requires_zero_effect_model_free_request(self):
        store=SupabaseProvenanceStore.__new__(SupabaseProvenanceStore)
        store._rpc=MagicMock(return_value={
            "replay_id":"rp","source_run_id":"run","mode":"shadow","status":"ready",
            "effect":"none","model_calls_allowed":False,"snapshot_hash":"a"*64,
        })
        replay=store.create_replay("run","shadow")
        self.assertEqual(replay.effect,"none")
        self.assertFalse(replay.model_calls_allowed)

    def test_shadow_decision_hashes_input_and_has_no_execution_api(self):
        store=SupabaseProvenanceStore.__new__(SupabaseProvenanceStore)
        store._rpc=MagicMock(return_value={"shadow_decision_id":"s","effect":"none","status":"evaluated"})
        out=store.record_shadow(
            source_run_id="run",replay_id="rp",component="router",component_version="2",
            input_value={"complexity":"high"},decision={"route":"direct"},
            observed_outcome={"first_pass":True},
        )
        payload=store._rpc.call_args.args[1]
        self.assertEqual(payload["p_input_hash"],canonical_hash({"complexity":"high"}))
        self.assertEqual(out["effect"],"none")

    def test_improvement_proposal_is_source_control_only_and_not_auto_applied(self):
        store=SupabaseProvenanceStore.__new__(SupabaseProvenanceStore)
        store._rpc=MagicMock(return_value={
            "proposal_id":"p","status":"proposed","requires_source_control":True,"auto_apply":False,
        })
        out=store.propose(
            source_run_id="run",proposal_key="router-v2",
            evidence={"shadow_delta":{"lead_time":-0.1}},
            proposed_change={"router_policy_version":"2"},
        )
        self.assertTrue(out["requires_source_control"])
        self.assertFalse(out["auto_apply"])


if __name__=="__main__":
    unittest.main()
