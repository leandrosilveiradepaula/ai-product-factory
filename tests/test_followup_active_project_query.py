"""Prove DB-side project filtering precedes bounded CI/Preview/Release scans."""
import unittest
from unittest.mock import patch

from ai_product_factory.followup_active_project_query import active_project_followup_query
from ai_product_factory.ci_followup_queue import SupabaseCIFollowupQueue
from ai_product_factory.preview_followup_queue import SupabasePreviewFollowupQueue
from ai_product_factory.release_followup_queue import SupabaseReleaseFollowupQueue


class ActiveProjectFollowupQueryTests(unittest.TestCase):
    def test_three_fk_joins_filter_running_projects_before_fifo_limit(self):
        for status, limit in (("ci_pending", 1), ("awaiting_release", 12), ("preview_ready", 50)):
            with self.subTest(status=status):
                path = active_project_followup_query(status=status, limit=limit)
                self.assertEqual(path.count("!inner("), 3)
                self.assertIn("factory_tasks!inner(factory_projects!inner(", path)
                self.assertIn("factory_project_execution_controls!inner(state,generation)", path)
                self.assertIn("&factory_tasks.factory_projects.is_active=eq.true", path)
                self.assertIn("&factory_tasks.factory_projects.factory_project_execution_controls.state=eq.running", path)
                self.assertIn("&factory_tasks.factory_projects.factory_project_execution_controls.generation=gt.0", path)
                self.assertIn("&status=eq." + status, path)
                self.assertIn("&order=created_at.asc,id.asc&limit=" + str(limit), path)
                for pilot in ("crm-infodive", "service-desk", "agente-sql", "project_kind"):
                    self.assertNotIn(pilot, path)

    def test_unapproved_state_or_unbounded_window_is_rejected(self):
        for status in ("paused", "running", "ci_pendin", None, 1):
            with self.subTest(status=status), self.assertRaises(ValueError):
                active_project_followup_query(status=status, limit=1)
        for limit in (0, 51, -1, True, 1.0, None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                active_project_followup_query(status="ci_pending", limit=limit)

    def test_all_three_queues_use_server_filter_on_first_scan(self):
        for cls, status in ((SupabaseCIFollowupQueue, "ci_pending"),
                            (SupabaseReleaseFollowupQueue, "awaiting_release"),
                            (SupabasePreviewFollowupQueue, "preview_ready")):
            with self.subTest(queue=cls.__name__):
                queue = cls(url="https://example.supabase.co", secret_key="sb_secret_test")
                with patch.object(queue, "_get", return_value=[]) as get:
                    self.assertIsNone(queue.next_pending())
                get.assert_called_once()
                self.assertEqual(get.call_args.args[0], active_project_followup_query(
                    status=status, limit=50 if status=="preview_ready" else 1))

    def test_exclusions_keep_active_project_filter(self):
        for cls, status in ((SupabaseCIFollowupQueue, "ci_pending"),
                            (SupabaseReleaseFollowupQueue, "awaiting_release"),
                            (SupabasePreviewFollowupQueue, "preview_ready")):
            with self.subTest(queue=cls.__name__):
                queue = cls(url="https://example.supabase.co", secret_key="sb_secret_test")
                with patch.object(queue, "_get", return_value=[]) as get:
                    self.assertIsNone(queue.next_pending(exclude_run_ids=("blocked",)))
                self.assertEqual(get.call_args.args[0], active_project_followup_query(
                    status=status, limit=50 if status=="preview_ready" else 12))

    def test_rest_relationship_failure_has_no_unfiltered_fallback(self):
        for cls in (SupabaseCIFollowupQueue, SupabaseReleaseFollowupQueue,
                    SupabasePreviewFollowupQueue):
            with self.subTest(queue=cls.__name__):
                queue=cls(url="https://example.supabase.co", secret_key="sb_secret_test")
                with patch.object(queue, "_get", side_effect=RuntimeError("PGRST relationship unavailable")) as get:
                    with self.assertRaisesRegex(RuntimeError, "relationship unavailable"):
                        queue.next_pending()
                get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
