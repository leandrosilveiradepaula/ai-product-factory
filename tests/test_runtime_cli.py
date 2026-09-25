from unittest.mock import patch
import pytest
from ai_product_factory.runtime_auth import AuthKind
from ai_product_factory.runtime_cli import build_handler
from ai_product_factory.product_stage_executor import ProductStageExecutor

def test_runtime_builds_primary_handler_for_api_key():
 with patch.dict("os.environ",{"OPENAI_API_KEY":"test"},clear=True):
  handler=build_handler()
 assert isinstance(handler,ProductStageExecutor)

def test_runtime_fails_before_claim_when_auth_is_missing():
 with patch.dict("os.environ",{},clear=True):
  with pytest.raises(RuntimeError) as exc:build_handler()
 assert AuthKind.NONE.value in str(exc.value)

def test_unimplemented_chatgpt_token_does_not_silently_fall_back():
 with patch.dict("os.environ",{"CHATGPT_ACCESS_TOKEN":"x"},clear=True):
  with pytest.raises(RuntimeError) as exc:build_handler()
 assert AuthKind.CHATGPT_ACCESS_TOKEN.value in str(exc.value)
