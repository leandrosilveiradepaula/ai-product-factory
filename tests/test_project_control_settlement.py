import json
import unittest
from unittest.mock import patch
from ai_product_factory.project_control_settlement import SupabaseProjectControlSettlement


class SettlementTests(unittest.TestCase):
    def test_empty_does_not_mutate(self):
        with patch("ai_product_factory.project_control_settlement.resolve_supabase_server_config") as config:
            config.return_value.url = "https://example.invalid"
            config.return_value.headers = {}
            service = SupabaseProjectControlSettlement()
        with patch.object(service, "_request", return_value=[]) as request:
            self.assertEqual(service.settle_pending()["settled"], 0)
            request.assert_called_once()

    def test_only_pending_controls_settle(self):
        with patch("ai_product_factory.project_control_settlement.resolve_supabase_server_config") as config:
            config.return_value.url = "https://example.invalid"
            config.return_value.headers = {}
            service = SupabaseProjectControlSettlement()
        with patch.object(service, "_request", side_effect=[
            [{"project_id": "uuid", "state": "pausing"}],
            [{"project_key": "example"}],
            {"state": "paused", "changed": True},
        ]) as request:
            result = service.settle_pending()
        self.assertEqual(result["settled"], 1)
        self.assertEqual(request.call_args.args[0], "rpc/factory_settle_project_control_v1")

    def test_invalid_response_fails_closed(self):
        with patch("ai_product_factory.project_control_settlement.resolve_supabase_server_config") as config:
            config.return_value.url = "https://example.invalid"
            config.return_value.headers = {}
            service = SupabaseProjectControlSettlement()
        with patch.object(service, "_request", return_value={"bad": True}):
            with self.assertRaises(RuntimeError):
                service.settle_pending()

    def test_stopping_settles_only_after_database_ack(self):
        with patch("ai_product_factory.project_control_settlement.resolve_supabase_server_config") as config:
            config.return_value.url = "https://example.invalid"
            config.return_value.headers = {}
            service = SupabaseProjectControlSettlement()
        with patch.object(service, "_request", side_effect=[
            [{"project_id": "uuid", "state": "stopping"}],
            [{"project_key": "example"}],
            {"state": "stopping", "changed": False},
        ]) as request:
            result = service.settle_pending()
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["settled"], 0)
        self.assertEqual(result["results"][0]["state"], "stopping")
        self.assertEqual(request.call_args.args[1], {"p_project_key": "example"})

    def test_running_control_is_never_settled(self):
        with patch("ai_product_factory.project_control_settlement.resolve_supabase_server_config") as config:
            config.return_value.url = "https://example.invalid"
            config.return_value.headers = {}
            service = SupabaseProjectControlSettlement()
        with patch.object(service, "_request", return_value=[
            {"project_id": "uuid", "state": "running"}
        ]) as request:
            with self.assertRaises(RuntimeError):
                service.settle_pending()
            request.assert_called_once()

    def test_unknown_database_ack_is_rejected(self):
        with patch("ai_product_factory.project_control_settlement.resolve_supabase_server_config") as config:
            config.return_value.url = "https://example.invalid"
            config.return_value.headers = {}
            service = SupabaseProjectControlSettlement()
        with patch.object(service, "_request", side_effect=[
            [{"project_id": "uuid", "state": "pausing"}],
            [{"project_key": "example"}],
            {"state": "running", "changed": True},
        ]):
            with self.assertRaises(RuntimeError):
                service.settle_pending()
