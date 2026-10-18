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
        usage=[{"id":1,"tool_family":"openai","estimated_cost":"1.25"},{"id":2,"tool_family":"model","estimated_cost":None},{"id":3,"tool_family":"github","estimated_cost":None}]
        with patch("urllib.request.urlopen",side_effect=[Response(runs),Response(tasks),Response([]),Response(usage)]):
            reader=SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x")
            out=reader.read(budget=Decimal("5"),now=datetime(2026,9,26,tzinfo=timezone.utc))
        self.assertEqual(out.expired_leases,2)
        self.assertEqual(out.dead_letter_runs,1)
        self.assertEqual(out.failed_runs,1)
        self.assertEqual(out.unknown_cost_events,1)
        self.assertEqual(out.known_cost,Decimal("1.25"))



    def test_real_postgres_bigint_id_works_in_cost_inventory(self):
        usage=[
            {"id":101,"tool_family":"github","estimated_cost":None},
            {"id":100,"tool_family":"openai","estimated_cost":"0.125"},
            {"id":"99","tool_family":"model","estimated_cost":"0.250"},
        ]
        with patch("urllib.request.urlopen",side_effect=[
            Response([]),Response([]),Response(usage)
        ]) as calls:
            health=SupabaseOperationalHealthReader(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            ).read(now=datetime(2026,10,14,tzinfo=timezone.utc))
        self.assertEqual(health.known_cost,Decimal("0.375"))
        self.assertEqual(health.unknown_cost_events,0)
        self.assertIn("select=id,tool_family,estimated_cost",calls.call_args_list[2].args[0].full_url)

    def test_signed_bigint_range_and_identity_types_fail_closed(self):
        for invalid in (None,False,True,0,-1,1.0,"abc","1.2","",str(2**63),2**63):
            with self.subTest(identity=invalid),patch("urllib.request.urlopen",side_effect=[
                Response([]),Response([]),Response([
                    {"id":invalid,"tool_family":"openai","estimated_cost":"0.01"}
                ])
            ]):
                with self.assertRaisesRegex(RuntimeError,"invalid ID"):
                    SupabaseOperationalHealthReader(
                        url="https://x.supabase.co",secret_key="sb_secret_x"
                    ).read()

    def test_full_cost_history_uses_second_page_without_understating_budget(self):
        first=[
            {"id":i+1,"tool_family":"openai","estimated_cost":"0.01"}
            for i in range(1000)
        ]
        second=[{"id":1001,"tool_family":"openai","estimated_cost":"0.50"}]
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
            {"id":i+1,"tool_family":"model","estimated_cost":"0.01"}
            for i in range(1000)
        ]
        second=[{"id":"1000","tool_family":"model","estimated_cost":"0.20"}]
        with patch("urllib.request.urlopen",side_effect=[
            Response([]),Response([]),Response(first),Response(second),
        ]):
            with self.assertRaisesRegex(RuntimeError,"invalid or duplicate ID"):
                SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x").read()

    def test_malformed_or_negative_cost_never_reduces_spend(self):
        for value in ("-0.01","NaN","Infinity","not-a-number"):
            with self.subTest(cost=value),patch("urllib.request.urlopen",side_effect=[
                Response([]),Response([]),
                Response([{"id":1,"tool_family":"model","estimated_cost":value}])
            ]):
                with self.assertRaisesRegex(RuntimeError,"invalid amount"):
                    SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x").read()

    def test_unknown_paid_cost_on_later_page_is_observed(self):
        first=[
            {"id":i+1,"tool_family":"github","estimated_cost":"0.00"}
            for i in range(1000)
        ]
        second=[{"id":1001,"tool_family":"model","estimated_cost":None}]
        with patch("urllib.request.urlopen",side_effect=[
            Response([]),Response([]),Response(first),Response(second),
        ]):
            health=SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x").read()
        self.assertEqual(health.unknown_cost_events,1)

    def test_malformed_usage_id_or_family_fails_closed(self):
        for row in (
            {"tool_family":"openai","estimated_cost":"1"},
            {"id":"", "tool_family":"openai","estimated_cost":"1"},
            {"id":1,"tool_family":None,"estimated_cost":"1"},
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
        with patch("urllib.request.urlopen",side_effect=[Response(list(reversed(audits))),Response(audits),Response([])]):
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
        terminal=[{"id":f"{i:04d}","status":"completed","created_at":"2026-10-14T09:00:00Z"} for i in range(199,-1,-1)]
        preview=[{"id":"old","created_at":"2026-10-01T00:00:00Z","metadata":{}}]
        with patch("urllib.request.urlopen",side_effect=[Response(terminal),Response([]),Response(preview),Response([])]) as calls:
            health=SupabaseOperationalHealthReader(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            ).read(now=datetime(2026,10,14,10,tzinfo=timezone.utc))
        self.assertEqual(health.stale_preview_runs,1)
        self.assertIn("order=created_at.asc",calls.call_args_list[2].args[0].full_url)

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


    def test_failed_incident_behind_200_newer_completed_runs_is_detected(self):
        first=[{"id":f"run-{i:04d}","status":"completed","task_id":f"t-{i}"}
               for i in range(200)]
        older=[{"id":"old-failed","task_id":"t-failed","status":"failed",
                "last_error":"maximum attempts reached","lease_expires_at":None}]
        with patch("urllib.request.urlopen",side_effect=[
            Response(first),Response(older),Response([{"id":"t-failed","status":"failed"}]),
            Response([]),Response([])
        ]) as calls:
            out=SupabaseOperationalHealthReader(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            ).read(now=datetime(2026,10,14,tzinfo=timezone.utc))
        self.assertEqual(out.failed_runs,1)
        self.assertEqual(out.dead_letter_runs,1)
        first_query=calls.call_args_list[0].args[0].full_url
        second_query=calls.call_args_list[1].args[0].full_url
        self.assertIn("order=created_at.desc,id.desc",first_query)
        self.assertIn("offset=0",first_query)
        self.assertIn("offset=200",second_query)
        self.assertTrue(all(call.args[0].get_method()=="GET" for call in calls.call_args_list))

    def test_expired_lease_older_than_200_runs_is_not_hidden(self):
        first=[{"id":f"run-{i:04d}","status":"completed"} for i in range(200)]
        older=[{"id":"stale-lease","status":"running",
                "lease_expires_at":"2026-10-01T00:00:00Z"}]
        with patch("urllib.request.urlopen",side_effect=[
            Response(first),Response(older),Response([]),Response([])
        ]):
            out=SupabaseOperationalHealthReader(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            ).read(now=datetime(2026,10,14,tzinfo=timezone.utc))
        self.assertEqual(out.expired_leases,1)

    def test_recovered_failed_run_on_later_page_remains_nonactionable(self):
        first=[{"id":f"run-{i:04d}","status":"completed"} for i in range(200)]
        older=[{"id":"old-failed","task_id":"t-recovered","status":"failed",
                "last_error":"maximum attempts reached"}]
        with patch("urllib.request.urlopen",side_effect=[
            Response(first),Response(older),
            Response([{"id":"t-recovered","status":"integrated"}]),
            Response([]),Response([])
        ]):
            out=SupabaseOperationalHealthReader(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            ).read(now=datetime(2026,10,14,tzinfo=timezone.utc))
        self.assertEqual(out.failed_runs,0)
        self.assertEqual(out.dead_letter_runs,0)

    def test_run_inventory_duplicate_across_pages_fails_closed(self):
        first=[{"id":f"run-{i:04d}","status":"completed"} for i in range(200)]
        with patch("urllib.request.urlopen",side_effect=[
            Response(first),Response([{"id":"run-0199","status":"completed"}])
        ]):
            with self.assertRaisesRegex(RuntimeError,"duplicate ID"):
                SupabaseOperationalHealthReader(
                    url="https://x.supabase.co",secret_key="sb_secret_x"
                ).read()

    def test_specialist_and_repair_run_phases_are_known_operational_states(self):
        # Both statuses are emitted by the production specialist pipeline. The
        # operations reviewer must be able to inventory them without masking
        # genuine unknown statuses or inventing successful releases.
        for active_status in ("specialist_review_pending", "repair_pending"):
            with self.subTest(status=active_status), patch(
                "urllib.request.urlopen", side_effect=[
                    Response([{"id":"crm-run","task_id":"crm-task",
                               "status":active_status,
                               "created_at":"2026-10-18T20:29:00Z"}]),
                    Response([]),
                    Response([]),
                ]
            ):
                result=SupabaseOperationalHealthReader(
                    url="https://x.supabase.co",secret_key="sb_secret_x"
                ).read(now=datetime(2026,10,18,20,30,tzinfo=timezone.utc))
            self.assertEqual(result.failed_runs,0)
            self.assertEqual(result.dead_letter_runs,0)
            self.assertEqual(result.expired_leases,0)
            self.assertEqual(result.unknown_cost_events,0)
            self.assertEqual(result.known_cost,Decimal("0"))

    def test_malformed_and_unknown_run_statuses_fail_closed(self):
        for invalid in ({"id":"x","status":"unexpected"}, {"id":"x","status":None},
                        {"id":None,"status":"completed"}, "malformed"):
            with self.subTest(invalid=invalid), patch("urllib.request.urlopen",
                    side_effect=[Response([invalid])]):
                with self.assertRaises(RuntimeError):
                    SupabaseOperationalHealthReader(
                        url="https://x.supabase.co",secret_key="sb_secret_x"
                    ).read()

    def test_run_inventory_hard_limit_rejects_partial_health(self):
        from ai_product_factory.supabase_operational_health import (
            RUN_PAGE_SIZE,MAX_RUN_PAGES
        )
        pages=[
            Response([{"id":f"run-{page*RUN_PAGE_SIZE+i:05d}",
                       "status":"completed"} for i in range(RUN_PAGE_SIZE)])
            for page in range(MAX_RUN_PAGES)
        ]
        with patch("urllib.request.urlopen",side_effect=pages) as calls:
            with self.assertRaisesRegex(RuntimeError,"pagination boundary"):
                SupabaseOperationalHealthReader(
                    url="https://x.supabase.co",secret_key="sb_secret_x"
                ).read()
        self.assertEqual(calls.call_count,MAX_RUN_PAGES)

    def test_failed_task_status_lookup_is_batched_and_complete(self):
        failed=[{"id":f"r-{i}","task_id":f"t-{i}","status":"failed",
                 "last_error":"maximum attempts"} for i in range(150)]
        # IDs sort lexically, and the reader must fetch every group.
        task_keys=sorted({row["task_id"] for row in failed})
        task_batches=[
            [{"id":id,"status":"failed"} for id in task_keys[:100]],
            [{"id":id,"status":"integrated"} for id in task_keys[100:]],
        ]
        with patch("urllib.request.urlopen",side_effect=[
            Response(failed),Response(task_batches[0]),Response(task_batches[1]),
            Response([]),Response([])
        ]) as calls:
            result=SupabaseOperationalHealthReader(
                url="https://x.supabase.co",secret_key="sb_secret_x"
            ).read()
        self.assertEqual(result.failed_runs,100)
        self.assertEqual(result.dead_letter_runs,100)
        self.assertIn("id=in.(",calls.call_args_list[1].args[0].full_url)
        self.assertIn("id=in.(",calls.call_args_list[2].args[0].full_url)

    def test_run_rows_with_invalid_timestamps_or_order_are_rejected(self):
        for invalid in ("bad", "2026-10-14T12:00:00", 42):
            with self.subTest(invalid=invalid),patch("urllib.request.urlopen",
                side_effect=[Response([{"id":"r1","status":"completed","created_at":invalid}])]):
                with self.assertRaisesRegex(RuntimeError,"creation time"):
                    SupabaseOperationalHealthReader(
                        url="https://x.supabase.co",secret_key="sb_secret_x"
                    ).read()
        rows=[
            {"id":"r1","status":"completed","created_at":"2026-10-14T11:00:00Z"},
            {"id":"r2","status":"completed","created_at":"2026-10-14T12:00:00Z"},
        ]
        with patch("urllib.request.urlopen",side_effect=[Response(rows)]):
            with self.assertRaisesRegex(RuntimeError,"not sorted"):
                SupabaseOperationalHealthReader(
                    url="https://x.supabase.co",secret_key="sb_secret_x"
                ).read()



if __name__ == "__main__":
    unittest.main()
