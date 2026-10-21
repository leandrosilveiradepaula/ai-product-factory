"""Preview cursor and exact probe-to-worker SHA binding are fail-closed."""
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from ai_product_factory.runtime_cli import (
    _next_authorized_preview_with_cursor, run_preview_once,
)
from ai_product_factory.preview_followup_queue import SupabasePreviewFollowupQueue
from ai_product_factory.followup_fair_cursor import SupabaseFollowupFairCursor
from ai_product_factory.project_followup_guard import ProjectFollowupRevoked

PID="123e4567-e89b-42d3-a456-426614174000"
SHA="a"*40


class Cursor:
    def __init__(self,offset=0):
        self.offset=offset
        self.history=[]
    def read_offset(self,lane):
        assert lane=="preview"
        return self.offset
    def reserve_next(self,lane,value):
        self.history.append(value)
        self.offset=value


class Queue:
    def __init__(self,rows):
        self.rows=rows
    def next_pending(self,*,exclude_run_ids=(),offset=0):
        return next((row for row in self.rows[offset:offset+50]
                     if row.run_id not in exclude_run_ids),None)


def item(index):
    return SimpleNamespace(run_id=str(index),candidate_commit=SHA,
                           project_key="generic-project",project_id=PID,
                           execution_generation=1,require_execution_generation=True)


class PreviewFairnessTests(unittest.TestCase):
    def test_thirteen_items_reach_next_window_after_twelve_revoked(self):
        q=Queue([item(n) for n in range(13)])
        cursor=Cursor()
        def guard(candidate):
            if candidate.run_id!="12":
                raise ProjectFollowupRevoked("project_execution_epoch_revoked")
            return 1
        with patch("ai_product_factory.runtime_cli._assert_project_followup",side_effect=guard):
            first,waiting=_next_authorized_preview_with_cursor(q,cursor)
            self.assertIsNone(first)
            self.assertEqual(waiting["status"],"project_execution_epoch_revoked")
            second,waiting=_next_authorized_preview_with_cursor(q,cursor)
        self.assertEqual(second.run_id,"12")
        self.assertIsNone(waiting)
        self.assertEqual(cursor.history,[12,24])

    def test_shrunk_queue_wraps_once(self):
        c=Cursor(36)
        with patch("ai_product_factory.runtime_cli._assert_project_followup",return_value=1):
            selected,waiting=_next_authorized_preview_with_cursor(Queue([item(0)]),c)
        self.assertEqual(selected.run_id,"0")
        self.assertIsNone(waiting)
        self.assertEqual(c.history,[48,12])

    def test_cursor_failure_never_reads_queue(self):
        c=Cursor()
        c.reserve_next=Mock(side_effect=RuntimeError("unavailable"))
        q=Mock()
        with self.assertRaises(RuntimeError):
            _next_authorized_preview_with_cursor(q,c)
        q.next_pending.assert_not_called()

    def test_pinned_worker_rejects_changed_sha_before_github(self):
        target="123e4567-e89b-42d3-a456-426614174000"
        candidate=SimpleNamespace(run_id=target,candidate_commit="b"*40)
        with patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue") as q, \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            q.return_value.next_pending.return_value=candidate
            with self.assertRaisesRegex(RuntimeError,"candidate changed"):
                run_preview_once(expected_run_id=target,expected_candidate_sha=SHA)
        github.assert_not_called()

    def test_pinned_candidate_missing_must_not_fallback(self):
        target="123e4567-e89b-42d3-a456-426614174000"
        with patch("ai_product_factory.runtime_cli.SupabasePreviewFollowupQueue") as q, \
             patch("ai_product_factory.runtime_cli.GitHubRestAdapter") as github:
            q.return_value.next_pending.return_value=None
            result=run_preview_once(expected_run_id=target,expected_candidate_sha=SHA)
        self.assertEqual(result["status"],"preview_candidate_unavailable")
        github.assert_not_called()

    def test_cursor_lane_stride_is_preserved(self):
        cur=SupabaseFollowupFairCursor(url="https://x.supabase.co",secret_key="sb_secret_test")
        with patch("urllib.request.urlopen") as network:
            for lane,val in (("preview",8),("ci",12),("release",12)):
                with self.assertRaises(ValueError):
                    cur.reserve_next(lane,val)
            network.assert_not_called()

    def test_queue_pinned_lookup_filters_run_before_any_further_reads(self):
        q=SupabasePreviewFollowupQueue(url="https://x.supabase.co",secret_key="sb_secret_test")
        target="123e4567-e89b-42d3-a456-426614174000"
        with patch.object(q,"_get",return_value=[]) as get:
            self.assertIsNone(q.next_pending(required_run_id=target))
        self.assertIn("&id=eq."+target,get.call_args.args[0])
        self.assertIn("state=eq.running",get.call_args.args[0])
        with patch.object(q,"_get") as get:
            with self.assertRaises(ValueError):
                q.next_pending(required_run_id=target,offset=12)
            get.assert_not_called()


if __name__=="__main__":
    unittest.main()
