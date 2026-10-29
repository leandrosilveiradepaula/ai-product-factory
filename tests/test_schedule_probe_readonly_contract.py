"""The external watchdog must not create scheduler telemetry or any writes.

The production runner keeps the original default telemetry behavior.
"""
import unittest
from unittest.mock import Mock
from ai_product_factory.schedule_probe import SupabaseScheduleProbe


class ReadOnlyProbeContract(unittest.TestCase):
    def setup_probe(self):
        probe = object.__new__(SupabaseScheduleProbe)
        probe._status_partitioned_rows = Mock(side_effect=[([], ()), ([], ())])
        probe._execution_signals = Mock(return_value={
            'product_work': False, 'routed_execution_work': False,
            'codex_manual_work': False, 'integration_work': False,
            'ci_work': False, 'release_work': False,
            'specialist_security_work': False,
            'specialist_qa_work': False,
            'specialist_operations_work': False,
        })
        probe._get = Mock(return_value=[])
        probe._get_optional = Mock(return_value=[])
        probe._portfolio_dispatch_candidates = Mock(return_value=[])
        probe._record_telemetry = Mock(return_value=True)
        return probe

    def test_external_probe_is_read_only_even_when_run_name_is_schedule(self):
        from unittest.mock import patch
        probe = self.setup_probe()
        with patch.dict('os.environ', {'GITHUB_EVENT_NAME': 'schedule'}):
            result = probe.probe(record_telemetry=False)
        self.assertFalse(result['work_detected'])
        self.assertFalse(result['telemetry_recorded'])
        probe._record_telemetry.assert_not_called()

    def test_native_runner_telemetry_is_unchanged(self):
        probe = self.setup_probe()
        result = probe.probe()
        self.assertTrue(result['telemetry_recorded'])
        probe._record_telemetry.assert_called_once()

    def test_refuse_nonboolean_telemetry_flag(self):
        probe = self.setup_probe()
        with self.assertRaises(ValueError):
            probe.probe(record_telemetry='false')
        probe._get.assert_not_called()
        probe._record_telemetry.assert_not_called()


if __name__ == '__main__':
    unittest.main()