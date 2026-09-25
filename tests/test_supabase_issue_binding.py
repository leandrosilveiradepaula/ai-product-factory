import json,unittest
from unittest.mock import patch
from ai_product_factory.github_rest import GitHubIssue
from ai_product_factory.supabase_issue_binding import SupabaseIssueBindingStore
class Response:
 def __enter__(self):return self
 def __exit__(self,*a):return False
class Tests(unittest.TestCase):
 def test_binding_uses_rpc_without_secret_in_body(self):
  with patch("urllib.request.urlopen",return_value=Response()) as call:
   SupabaseIssueBindingStore(url="https://x.supabase.co",service_role_key="secret").bind_issue(run_id="r",issue=GitHubIssue(7,"T","B","https://i/7"))
  req=call.call_args.args[0];self.assertTrue(req.full_url.endswith("/rpc/factory_bind_github_issue"))
  payload=json.loads(req.data.decode());self.assertEqual(payload["p_issue_number"],7);self.assertNotIn(b"secret",req.data)
if __name__=="__main__":unittest.main()
