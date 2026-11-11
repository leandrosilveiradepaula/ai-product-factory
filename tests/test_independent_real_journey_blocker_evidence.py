from __future__ import annotations

import unittest

from ai_product_factory.independent_real_journey_blocker_evidence import (
    RealJourneyBlockerEvidenceBlocked, verify_real_journey_blockers,
)
from tests.test_block1_real_journeys_readonly import CRM, JOURNEY, PID, RETIRED


def source(*, journeys=None, greenfield=None):
    def get(path):
        if path.startswith("factory_projects?") and "project_key=eq.crm-infodive" in path:
            return CRM
        if path.startswith("factory_journeys?"):
            assert "project_id=eq." + PID in path
            return [JOURNEY] if journeys is None else journeys
        if path.startswith("factory_projects?") and "project_kind=eq.greenfield" in path:
            return RETIRED if greenfield is None else greenfield
        raise AssertionError("unexpected query")
    return get


class RealJourneyBlockerEvidenceTests(unittest.TestCase):
    def test_retains_real_blocker_without_claiming_e2e(self):
        receipt = verify_real_journey_blockers(control_plane_get=source()).receipt()
        self.assertEqual(receipt["crm_blocker"], "human_merge_or_release_unverified")
        self.assertFalse(receipt["critical_e2e_certified"])
        self.assertFalse(receipt["critical_journeys_certified"])
        self.assertFalse(receipt["retired_service_desk_eligible"])
        self.assertEqual(receipt["writes"], 0)

    def test_forged_or_unavailable_sources_fail_closed(self):
        for getter in (
            lambda path: [],
            source(journeys=[{**JOURNEY, "request_source": "forged"}]),
        ):
            with self.subTest(getter=getter), self.assertRaises(RealJourneyBlockerEvidenceBlocked):
                verify_real_journey_blockers(control_plane_get=getter)

    def test_pipeline_revalidates_blocker_before_persistence(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/autonomous-runner.yml").read_text()
        builder = (root / "scripts/build_readiness_evidence_manifest.py").read_text()
        certifier = (root / "scripts/certify_product_readiness.py").read_text()
        self.assertIn("--verify-real-journey-blockers", workflow)
        self.assertIn("real_journey_blocker_evidence", builder)
        self.assertIn("real journey blocker receipt changed before persistence", certifier)


if __name__ == "__main__":
    unittest.main()
