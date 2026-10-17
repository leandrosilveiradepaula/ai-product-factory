import unittest
from unittest.mock import patch
from ai_product_factory.project_control_settlement import SupabaseProjectControlSettlement

def uid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"

def service():
    with patch("ai_product_factory.project_control_settlement.resolve_supabase_server_config") as config:
        config.return_value.url = "https://example.invalid"
        config.return_value.headers = {}
        return SupabaseProjectControlSettlement()

def acknowledgement(state="paused", changed=True, version=1):
    return {"state": state, "changed": changed, "version": version}

class SettlementTests(unittest.TestCase):
    def test_empty_does_not_mutate(self):
        app = service()
        with patch.object(app, "_request", return_value=[]) as request:
            self.assertEqual(app.settle_pending(), {"pending": 0, "settled": 0, "results": []})
            request.assert_called_once()

    def test_only_pending_controls_settle(self):
        app = service()
        with patch.object(app, "_request", side_effect=[
            [{"project_id": uid(1), "state": "pausing"}],
            [{"project_key": "example"}],
            acknowledgement(),
        ]) as request:
            result = app.settle_pending()
        self.assertEqual(result["settled"], 1)
        self.assertEqual(request.call_args.args[0], "rpc/factory_settle_project_control_v1")

    def test_invalid_response_fails_closed(self):
        app = service()
        with patch.object(app, "_request", return_value={"bad": True}):
            with self.assertRaisesRegex(RuntimeError, "invalid pending"):
                app.settle_pending()

    def test_stopping_waits_for_database_ack(self):
        app = service()
        with patch.object(app, "_request", side_effect=[
            [{"project_id": uid(1), "state": "stopping"}],
            [{"project_key": "example"}],
            acknowledgement("stopping", False),
        ]) as request:
            result = app.settle_pending()
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["settled"], 0)
        self.assertEqual(result["results"][0]["state"], "stopping")
        self.assertEqual(request.call_args.args[1], {"p_project_key": "example"})

    def test_running_control_never_settles(self):
        app = service()
        with patch.object(app, "_request", return_value=[
            {"project_id": uid(1), "state": "running"}
        ]) as request:
            with self.assertRaises(RuntimeError):
                app.settle_pending()
            request.assert_called_once()

    def test_unknown_database_ack_rejected(self):
        app = service()
        with patch.object(app, "_request", side_effect=[
            [{"project_id": uid(1), "state": "pausing"}],
            [{"project_key": "example"}],
            acknowledgement("running"),
        ]):
            with self.assertRaisesRegex(RuntimeError, "invalid project settlement"):
                app.settle_pending()

    def test_keyset_pagination_never_skips_rows_during_settlement(self):
        app = service()
        queried_pages = []
        claimed_keys = []
        def fake_request(path, payload=None):
            if path.startswith("factory_project_execution_controls?"):
                queried_pages.append(path)
                if "project_id=gt." in path:
                    return [{"project_id": uid(n), "state": "stopping"} for n in range(101, 103)]
                return [{"project_id": uid(n), "state": "pausing"} for n in range(1, 101)]
            if path.startswith("factory_projects?"):
                index = int(path.split("id=eq.", 1)[1].split("&", 1)[0][-12:])
                return [{"project_key": f"project-{index}"}]
            if path == "rpc/factory_settle_project_control_v1":
                claimed_keys.append(payload["p_project_key"])
                return acknowledgement("stopped" if len(claimed_keys) > 100 else "paused")
            raise AssertionError(path)
        with patch.object(app, "_request", side_effect=fake_request):
            result = app.settle_pending()
        self.assertEqual(result["pending"], 102)
        self.assertEqual(result["settled"], 102)
        self.assertEqual(len(claimed_keys), 102)
        self.assertEqual(len(set(claimed_keys)), 102)
        self.assertEqual(len(queried_pages), 2)
        self.assertIn("project_id=gt." + uid(100), queried_pages[1])
        self.assertNotIn("offset=", queried_pages[1])

    def test_nonmonotonic_page_and_invalid_uuid_fail_closed(self):
        app = service()
        with patch.object(app, "_request", return_value=[{"project_id": "uuid", "state": "pausing"}]) as request:
            with self.assertRaisesRegex(RuntimeError, "invalid project identifier"):
                app.settle_pending()
            request.assert_called_once()

        def fake_request(path, payload=None):
            if path.startswith("factory_project_execution_controls?"):
                if "project_id=gt." in path:
                    return [{"project_id": uid(100), "state": "pausing"}]
                return [{"project_id": uid(n), "state": "pausing"} for n in range(1, 101)]
            if path.startswith("factory_projects?"):
                return [{"project_key": "project"}]
            return acknowledgement()
        with patch.object(app, "_request", side_effect=fake_request):
            with self.assertRaisesRegex(RuntimeError, "non-monotonic"):
                app.settle_pending()

    def test_invalid_ack_version_or_pending_changed_is_rejected(self):
        for ack in [acknowledgement(version=True), acknowledgement(version=-1),
                    acknowledgement("pausing", True)]:
            with self.subTest(ack=ack):
                app = service()
                with patch.object(app, "_request", side_effect=[
                    [{"project_id": uid(1), "state": "pausing"}],
                    [{"project_key": "example"}],
                    ack,
                ]):
                    with self.assertRaisesRegex(RuntimeError, "invalid project settlement"):
                        app.settle_pending()

if __name__ == "__main__":
    unittest.main()
