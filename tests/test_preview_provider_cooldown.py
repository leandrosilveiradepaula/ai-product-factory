from datetime import datetime,timedelta,timezone
from itertools import count
import unittest

from scripts.preview_provider_cooldown import observe_rate_limit

NOW=datetime(2026,10,14,16,50,tzinfo=timezone.utc)
SHA1="a"*40
SHA2="b"*40
SHA3="c"*40
PR_NUMBERS=count(1)


def pr(sha=SHA1, *, state="open", updated_at=NOW):
    return {"number":next(PR_NUMBERS),"state":state,"updated_at":updated_at.isoformat(),"head":{"sha":sha}}


class PreviewProviderCooldownTests(unittest.TestCase):
 def run_case(self,statuses,now=NOW,pulls=None,status_map=None):
  def fetch(method,url,headers):
   self.assertEqual(method,"GET")
   self.assertTrue(headers["Authorization"].startswith("Bearer "))
   if "/pulls?" in url:
    self.assertIn("per_page=100",url)
    page=int(url.rsplit("page=",1)[1])
    rows=pulls if pulls is not None else [pr()]
    if not isinstance(rows,list):return rows
    if "state=open" in url:
     rows=[row for row in rows if isinstance(row,dict) and row.get("state")=="open"]
    else:self.assertIn("state=all",url)
    return rows[(page-1)*100:page*100]
   for sha in (SHA1,SHA2,SHA3):
    if url.endswith("/commits/"+sha+"/status"):
     return {"statuses":status_map[sha] if status_map is not None else statuses}
   raise AssertionError(url)
  return observe_rate_limit(token="token",repository="test/repo",now=now,get_json=fetch)

 def test_recent_vercel_rate_limit_blocks_until_full_window(self):
  status={"context":"Vercel","state":"failure","description":"Deployment rate limited - retry in 24 hours.","created_at":NOW.isoformat()}
  result=self.run_case([status])
  self.assertFalse(result["allowed"])
  self.assertEqual(result["state"],"provider_rate_limited")
  self.assertEqual(result["source"],"github_vercel_commit_status")
  self.assertEqual(result["earliest_recheck_at"],(NOW+timedelta(hours=24)).isoformat())

 def test_closed_pr_recent_failure_remains_visible(self):
  rate={"context":"Vercel","state":"failure","description":"Deployment rate limited - retry in 24 hours.","created_at":NOW.isoformat()}
  result=self.run_case([rate],pulls=[pr(SHA1,state="closed")])
  self.assertFalse(result["allowed"])

 def test_old_closed_pr_does_not_consume_status_requests(self):
  result=self.run_case([],pulls=[pr(SHA1,state="closed",updated_at=NOW-timedelta(days=3))])
  self.assertTrue(result["allowed"])
  self.assertEqual(result["checked_prs"],0)

 def test_stale_rate_limit_is_not_permanent(self):
  stamp=(NOW-timedelta(hours=25)).isoformat()
  result=self.run_case([{"context":"Vercel","state":"failure","description":"Deployment rate limited - retry in 24 hours.","updated_at":stamp}])
  self.assertTrue(result["allowed"])
  self.assertFalse(result["authoritative_quota"])

 def test_newer_success_supersedes_older_failure_on_same_commit(self):
  old=(NOW-timedelta(hours=1)).isoformat()
  blocked={"context":"Vercel","state":"failure","description":"Deployment rate limited","created_at":old}
  restored={"context":"Vercel","state":"success","description":"Deployment has completed","created_at":NOW.isoformat()}
  result=self.run_case([blocked,restored])
  self.assertTrue(result["allowed"])

 def test_newer_pending_does_not_clear_rate_limit(self):
  old=(NOW-timedelta(hours=1)).isoformat()
  blocked={"context":"Vercel","state":"failure","description":"Deployment rate limited","created_at":old}
  pending={"context":"Vercel","state":"pending","description":"Deploying","created_at":NOW.isoformat()}
  self.assertFalse(self.run_case([blocked,pending])["allowed"])

 def test_generic_failure_does_not_invent_provider_quota(self):
  result=self.run_case([{"context":"Vercel","state":"failure","description":"Deployment failed.","created_at":NOW.isoformat()}])
  self.assertTrue(result["allowed"])

 def test_other_status_context_is_ignored(self):
  result=self.run_case([{"context":"Factory Preview browser evidence","state":"failure","description":"Deployment rate limited","created_at":NOW.isoformat()}])
  self.assertTrue(result["allowed"])

 def test_future_timestamp_blocks_closed(self):
  with self.assertRaisesRegex(RuntimeError,"clock tolerance"):
   self.run_case([{"context":"Vercel","state":"failure","description":"Deployment rate limited","created_at":(NOW+timedelta(hours=10)).isoformat()}])

 def test_malformed_or_overlong_recent_pr_inventory_blocks_closed(self):
  with self.assertRaisesRegex(RuntimeError,"paginated beyond safe bound"):
   self.run_case([],pulls=[pr(SHA1) for _ in range(500)])
  with self.assertRaisesRegex(RuntimeError,"candidate SHA"):
   self.run_case([],pulls=[pr("invalid")])

 def test_real_world_52_recent_prs_do_not_fail_at_previous_limit_of_50(self):
  result=self.run_case([],pulls=[pr(SHA1) for _ in range(52)])
  self.assertTrue(result["allowed"])
  self.assertEqual(result["checked_prs"],52)
  self.assertFalse(result["authoritative_quota"])

 def test_recent_prs_page_2_is_checked_not_silently_truncated(self):
  old_rate={"context":"Vercel","state":"failure","description":"Deployment rate limited - retry in 24 hours.","created_at":NOW.isoformat()}
  result=self.run_case([],pulls=[pr(SHA1) for _ in range(100)]+[pr(SHA2)],status_map={SHA1:[],SHA2:[old_rate],SHA3:[]})
  self.assertFalse(result["allowed"])
  self.assertEqual(result["sha"],SHA2)

 def test_older_open_pr_is_checked_independently_of_recent_update_window(self):
  older_open=pr(SHA2,state="open",updated_at=NOW-timedelta(days=5))
  rate={"context":"Vercel","state":"failure","description":"Deployment rate limited","created_at":NOW.isoformat()}
  result=self.run_case([],pulls=[pr(SHA1,state="closed",updated_at=NOW-timedelta(days=5)),older_open],status_map={SHA1:[],SHA2:[rate],SHA3:[]})
  self.assertFalse(result["allowed"])
  self.assertEqual(result["sha"],SHA2)

 def test_recent_inventory_requires_descending_update_order(self):
  with self.assertRaisesRegex(RuntimeError,"descending order"):
   self.run_case([],pulls=[pr(SHA1,updated_at=NOW-timedelta(hours=2)),pr(SHA2,updated_at=NOW)])
  with self.assertRaisesRegex(RuntimeError,"missing update timestamp"):
   self.run_case([],pulls=[{"state":"open","head":{"sha":SHA1}}])

 def test_missing_statuses_blocks_closed(self):
  def fetch(method,url,headers):
   if "/pulls?" in url:return [pr()]
   return {}
  with self.assertRaisesRegex(RuntimeError,"statuses"):
   observe_rate_limit(token="token",repository="test/repo",now=NOW,get_json=fetch)

 def test_duplicate_sha_is_checked_once(self):
  result=self.run_case([],pulls=[pr(SHA1),pr(SHA1,state="closed")])
  self.assertTrue(result["allowed"])
  self.assertEqual(result["checked_prs"],2)

 def test_invalid_pr_number_blocks_closed(self):
  with self.assertRaisesRegex(RuntimeError,"invalid PR number"):
   self.run_case([],pulls=[{"number":True,"state":"open","updated_at":NOW.isoformat(),"head":{"sha":SHA1}}])

 def test_duplicate_identity_with_changed_head_blocks_closed(self):
  same=pr(SHA1)
  altered={**same,"head":{"sha":SHA2}}
  def fetch(method,url,headers):
   if "/pulls?" in url:
    return [same] if "state=all" in url else [altered]
   return {"statuses":[]}
  with self.assertRaisesRegex(RuntimeError,"changed across"):
   observe_rate_limit(token="token",repository="test/repo",now=NOW,get_json=fetch)

 def test_invalid_repository_and_token_rejected(self):
  for token,repo in [("","a/b"),("key","invalid")]:
   with self.assertRaises(RuntimeError):
    observe_rate_limit(token=token,repository=repo,now=NOW,get_json=lambda *x:None)

if __name__=="__main__":
 unittest.main()
