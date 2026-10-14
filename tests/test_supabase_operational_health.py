import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from ai_product_factory.supabase_operational_health import SupabaseOperationalHealthReader


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode()


class Tests(unittest.TestCase):
    def test_maps_operational_health_without_side_effects(self):
        runs=[
            {"id":"r1","task_id":"t1","status":"running","attempt_count":1,"last_error":None,"lease_expires_at":"2026-01-01T00:00:00+00:00"},
            {"id":"r2","task_id":"t2","status":"preparing_codex_manual","attempt_count":1,"last_error":None,"lease_expires_at":"2026-01-01T00:00:00+00:00"},
            {"id":"r3","task_id":"t3","status":"failed","attempt_count":3,"last_error":"maximum attempts reached","lease_expires_at":None},
        ]
        tasks=[{"id":"t3","status":"failed"}]
        usage=[{"id":"u1","tool_family":"openai","estimated_cost":"1.25"},{"id":"u2","tool_family":"model","estimated_cost":None},{"id":"u3","tool_family":"github","estimated_cost":None}]
        with patch("urllib.request.urlopen",side_effect=[Response(runs),Response(tasks),Response([]),Response(usage)]):
            reader=SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x")
            out=reader.read(budget=Decimal("5"),now=datetime(2026,9,26,tzinfo=timezone.utc))
        self.assertEqual(out.expired_leases,2)
        self.assertEqual(out.dead_letter_runs,1)
        self.assertEqual(out.failed_runs,1)
        self.assertEqual(out.unknown_cost_events,1)
        self.assertEqual(out.known_cost,Decimal("1.25"))



    def test_full_cost_history_uses_second_page_without_understating_budget(self):
        first=[
            {"id":f"usage-{i:04d}","tool_family":"openai","estimated_cost":"0.01"}
            for i in range(1000)
        ]
        second=[{"id":"usage-1000","tool_family":"openai","estimated_cost":"0.50"}]
        with patch("urllib.request.urlopen",side_effect=[
            Response([]),Response([]),Response(first),Response(second),
        ]) as calls:
            reader=SupabaseOperationalHealthReader(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            )
            health=reader.read(budget=Decimal("10"),now=datetime(2026,10,14,tzinfo=timezone.utc))
        self.assertEqual(health.known_cost,Decimal("10.50"))
        self.assertEqual(health.unknown_cost_events,0)
        first_query=calls.call_args_list[2].args[0].full_url
        second_query=calls.call_args_list[3].args[0].full_url
        self.assertIn("order=created_at.desc,id.desc",first_query)
        self.assertIn("offset=0",first_query)
        self.assertIn("offset=1000",second_query)

    def test_duplicate_usage_between_pages_fails_closed(self):
        first=[
            {"id":f"usage-{i:04d}","tool_family":"model","estimated_cost":"0.01"}
            for i in range(1000)
        ]
        second=[{"id":"usage-0999","tool_family":"model","estimated_cost":"0.20"}]
        with patch("urllib.request.urlopen",side_effect=[
            Response([]),Response([]),Response(first),Response(second),
        ]):
            with self.assertRaisesRegex(RuntimeError,"invalid or duplicate ID"):
                SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x").read()

    def test_malformed_or_negative_cost_never_reduces_spend(self):
        for value in ("-0.01","NaN","Infinity","not-a-number"):
            with self.subTest(cost=value),patch("urllib.request.urlopen",side_effect=[
                Response([]),Response([]),
                Response([{"id":"usage-1","tool_family":"model","estimated_cost":value}])
            ]):
                with self.assertRaisesRegex(RuntimeError,"invalid amount"):
                    SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x").read()

    def test_unknown_paid_cost_on_later_page_is_observed(self):
        first=[
            {"id":f"usage-{i:04d}","tool_family":"github","estimated_cost":"0.00"}
            for i in range(1000)
        ]
        second=[{"id":"usage-late","tool_family":"model","estimated_cost":None}]
        with patch("urllib.request.urlopen",side_effect=[
            Response([]),Response([]),Response(first),Response(second),
        ]):
            health=SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x").read()
        self.assertEqual(health.unknown_cost_events,1)

    def test_malformed_usage_id_or_family_fails_closed(self):
        for row in (
            {"tool_family":"openai","estimated_cost":"1"},
            {"id":"", "tool_family":"openai","estimated_cost":"1"},
            {"id":"usage-1","tool_family":None,"estimated_cost":"1"},
        ):
            with self.subTest(row=row),patch("urllib.request.urlopen",side_effect=[
                Response([]),Response([]),Response([row])
            ]):
                with self.assertRaisesRegex(RuntimeError,"cost usage inventory"):
                    SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x").read()

    def test_dead_letter_only_counts_failed_run_whose_task_is_still_failed(self):
        runs=[{
            "id":"r1","task_id":"t1","status":"failed","attempt_count":3,
            "last_error":"maximum attempts reached","lease_expires_at":None,
        }]
        with patch("urllib.request.urlopen",side_effect=[
            Response(runs),Response([{"id":"t1","status":"integrated"}]),
            Response([]),Response([]),
        ]):
            health=SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x").read()
        self.assertEqual(health.failed_runs,0)
        self.assertEqual(health.dead_letter_runs,0)

    def test_missing_failed_task_lookup_fails_closed(self):
        runs=[{"id":"r1","task_id":"t1","status":"failed","last_error":"maximum attempts"}]
        with patch("urllib.request.urlopen",side_effect=[Response(runs),Response([])]):
            with self.assertRaisesRegex(RuntimeError,"lookup is incomplete"):
                SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x").read()

    def test_preview_age_is_counted_without_deployment(self):
        runs=[{"id":"old","status":"preview_ready","created_at":"2026-10-05T00:00:00Z"}, {"id":"new","status":"preview_ready","created_at":"2026-10-13T17:00:00Z"}]
        with patch("urllib.request.urlopen",side_effect=[Response([]),Response(runs),Response([])]) as calls:
            reader=SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x")
            out=reader.read(now=datetime(2026,10,13,18,tzinfo=timezone.utc))
        self.assertIn("status=eq.preview_ready",calls.call_args_list[1].args[0].full_url)
        self.assertEqual(out.stale_preview_runs,1)

    def test_historical_failed_run_is_not_actionable_when_task_recovered(self):
        runs=[
            {"id":"r1","task_id":"t1","status":"failed","attempt_count":1,"last_error":"historical failure","lease_expires_at":None},
        ]
        tasks=[{"id":"t1","status":"integrated"}]
        usage=[]
        with patch("urllib.request.urlopen",side_effect=[Response(runs),Response(tasks),Response([]),Response(usage)]):
            reader=SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x")
            out=reader.read(now=datetime(2026,9,30,tzinfo=timezone.utc))
        self.assertEqual(out.failed_runs,0)
        self.assertEqual(out.dead_letter_runs,0)

    def test_two_historical_dogfood_audits_do_not_trigger_preview_warning(self):
        from ai_product_factory.operational_alerts import evaluate_operational_alerts
        audits=[
            {"id":"audit1","status":"preview_ready","created_at":"2026-10-07T15:51:04Z",
             "metadata":{"source":"dogfood_manual_audit","purpose":"product_readiness_assessment"}},
            {"id":"audit2","status":"preview_ready","created_at":"2026-10-07T16:42:41Z",
             "metadata":{"source":"dogfood_manual_audit","purpose":"product_readiness_assessment"}},
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(audits),Response(audits),Response([])]):
            reader=SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x")
            health=reader.read(now=datetime(2026,10,14,10,tzinfo=timezone.utc))
        self.assertEqual(health.stale_preview_runs,0)
        self.assertEqual(evaluate_operational_alerts(health),())

    def test_real_delivery_and_fresh_runs_count_independently(self):
        preview=[
            {"id":"audit","status":"preview_ready","created_at":"2026-10-01T00:00:00Z",
             "metadata":{"source":"dogfood_manual_audit"}},
            {"id":"old","status":"preview_ready","created_at":"2026-10-03T00:00:00Z",
             "metadata":{"github_issue":{"number":9}}},
            {"id":"fresh","status":"preview_ready","created_at":"2026-10-14T09:00:00Z",
             "metadata":{"github_issue":{"number":10}}},
        ]
        with patch("urllib.request.urlopen",side_effect=[Response([]),Response(preview),Response([])]):
            health=SupabaseOperationalHealthReader(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            ).read(now=datetime(2026,10,14,10,tzinfo=timezone.utc))
        self.assertEqual(health.stale_preview_runs,1)

    def test_older_delivery_not_hidden_by_newest_200_terminal_runs(self):
        terminal=[{"id":str(i),"status":"completed","created_at":"2026-10-14T09:00:00Z"} for i in range(200)]
        preview=[{"id":"old","created_at":"2026-10-01T00:00:00Z","metadata":{}}]
        with patch("urllib.request.urlopen",side_effect=[Response(terminal),Response(preview),Response([])]) as calls:
            health=SupabaseOperationalHealthReader(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            ).read(now=datetime(2026,10,14,10,tzinfo=timezone.utc))
        self.assertEqual(health.stale_preview_runs,1)
        self.assertIn("order=created_at.asc",calls.call_args_list[1].args[0].full_url)

    def test_excess_preview_partition_fails_closed(self):
        preview=[{"id":str(i),"created_at":"2026-10-01T00:00:00Z","metadata":{}} for i in range(201)]
        with patch("urllib.request.urlopen",side_effect=[Response([]),Response(preview)]) as calls:
            with self.assertRaisesRegex(RuntimeError,"200-run boundary"):
                SupabaseOperationalHealthReader(
                    url="https://x.supabase.co",secret_key="sb_secret_x"
                ).read(now=datetime(2026,10,14,tzinfo=timezone.utc))
        self.assertEqual(calls.call_count,2)

    def test_missing_delivery_timestamp_fails_closed(self):
        preview=[{"id":"delivery","metadata":{}}]
        with patch("urllib.request.urlopen",side_effect=[Response([]),Response(preview)]):
            with self.assertRaisesRegex(RuntimeError,"creation time"):
                SupabaseOperationalHealthReader(
                    url="https://x.supabase.co",secret_key="sb_secret_x"
                ).read(now=datetime(2026,10,14,tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
