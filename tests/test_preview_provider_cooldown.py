from datetime import datetime,timedelta,timezone
import unittest

from scripts.preview_provider_cooldown import observe_rate_limit

NOW=datetime(2026,10,14,16,50,tzinfo=timezone.utc)
SHA1="a"*40
SHA2="b"*40

class PreviewProviderCooldownTests(unittest.TestCase):
 def run_case(self,statuses,now=NOW,pulls=None):
  def fetch(method,url,headers):
   self.assertEqual(method,"GET")
   self.assertTrue(headers["Authorization"].startswith("Bearer "))
   if "/pulls?" in url:
    return pulls if pulls is not None else [{"head":{"sha":SHA1}}]
   if url.endswith("/commits/"+SHA1+"/status"):
    return {"statuses":statuses}
   raise AssertionError(url)
  return observe_rate_limit(token="token",repository="test/repo",now=now,get_json=fetch)

 def test_recent_vercel_rate_limit_blocks_until_full_window(self):
  status={"context":"Vercel","state":"failure","description":"Deployment rate limited — retry in 24 hours.","created_at":NOW.isoformat()}
  result=self.run_case([status])
  self.assertFalse(result["allowed"])
  self.assertEqual(result["state"],"provider_rate_limited")
  self.assertEqual(result["source"],"github_vercel_commit_status")
  self.assertEqual(result["earliest_recheck_at"],(NOW+timedelta(hours=24)).isoformat())

 def test_stale_rate_limit_is_not_permanent(self):
  stamp=(NOW-timedelta(hours=25)).isoformat()
  result=self.run_case([{"context":"Vercel","state":"failure","description":"Deployment rate limited — retry in 24 hours.","updated_at":stamp}])
  self.assertTrue(result["allowed"])
  self.assertFalse(result["authoritative_quota"])

 def test_generic_vercel_failure_does_not_invent_provider_quota(self):
  result=self.run_case([{"context":"Vercel","state":"failure","description":"Deployment failed.","created_at":NOW.isoformat()}])
  self.assertTrue(result["allowed"])

 def test_other_status_context_not_trusted_as_vercel(self):
  result=self.run_case([{"context":"Factory Preview browser evidence","state":"failure","description":"Deployment rate limited","created_at":NOW.isoformat()}])
  self.assertTrue(result["allowed"])

 def test_future_timestamp_blocks_closed(self):
  with self.assertRaisesRegex(RuntimeError,"clock tolerance"):
   self.run_case([{"context":"Vercel","state":"failure","description":"Deployment rate limited","created_at":(NOW+timedelta(hours=10)).isoformat()}])

 def test_malformed_or_overlong_pr_list_blocks_closed(self):
  with self.assertRaisesRegex(RuntimeError,"inventory"):
   self.run_case([],pulls=[{"head":{"sha":SHA2}} for _ in range(51)])
  with self.assertRaisesRegex(RuntimeError,"candidate SHA"):
   self.run_case([],pulls=[{"head":{"sha":"bad"}}])

 def test_missing_statuses_blocks_closed(self):
  def fetch(method,url,headers):
   if "/pulls?" in url:return [{"head":{"sha":SHA1}}]
   return {}
  with self.assertRaisesRegex(RuntimeError,"statuses"):
   observe_rate_limit(token="token",repository="test/repo",now=NOW,get_json=fetch)

 def test_invalid_repository_and_token_rejected(self):
  for token,repo in [("","a/b"),("key","invalid")]:
   with self.assertRaises(RuntimeError):
    observe_rate_limit(token=token,repository=repo,now=NOW,get_json=lambda *x:None)

if __name__=="__main__":
 unittest.main()
