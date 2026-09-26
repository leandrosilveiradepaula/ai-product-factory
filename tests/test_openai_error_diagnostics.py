import json
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from ai_product_factory.model_executor import ModelRequest
from ai_product_factory.models import Complexity
from ai_product_factory.openai_provider import OpenAIResponsesProvider,_default_transport

class Tests(unittest.TestCase):
 def test_http_error_transport_returns_structured_error_without_secret(self):
  payload=json.dumps({"error":{"message":"quota exhausted","type":"insufficient_quota","code":"credit_balance_exhausted"}}).encode()
  exc=HTTPError("https://api.openai.com/v1/responses",429,"Too Many Requests",{"x-request-id":"req_123"},BytesIO(payload))
  with patch("urllib.request.urlopen",side_effect=exc):
   status,data=_default_transport("POST","https://api.openai.com/v1/responses",{"Authorization":"Bearer secret"},b"{}")
  self.assertEqual(status,429);self.assertEqual(data["error"]["code"],"credit_balance_exhausted");self.assertEqual(data["_request_id"],"req_123");self.assertNotIn("secret",json.dumps(data))

 def test_provider_surfaces_safe_error_code(self):
  def transport(*args):
   return 429,{"error":{"message":"quota exhausted","type":"insufficient_quota","code":"project_spend_limit_exceeded"},"_request_id":"req_x"}
  p=OpenAIResponsesProvider(api_key="secret",transport=transport)
  with self.assertRaises(RuntimeError) as ctx:
   p.execute_for_complexity(ModelRequest(task_id="t",objective="x"),Complexity.LOW,reasoning_effort="none")
  text=str(ctx.exception);self.assertIn("project_spend_limit_exceeded",text);self.assertIn("req_x",text);self.assertNotIn("secret",text)

if __name__=="__main__":unittest.main()
