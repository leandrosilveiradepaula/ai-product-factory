import os
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_product_factory.codex_cli_producer import CodexCliConfig,CodexCliImplementationProducer
from ai_product_factory.execution_worker import DirectExecutionItem


def item():
    return DirectExecutionItem("r","t","demo","owner/repo",7,"Refactor engine","Keep behavior","factory/task-t",False)


class Tests(unittest.TestCase):
    def test_produces_bounded_patch_and_strips_infrastructure_secrets(self):
        seen={}
        def runner(argv,cwd,env,timeout):
            if argv[:2]==("git","clone"):
                checkout=Path(argv[-1])
                checkout.mkdir(parents=True)
                (checkout/"src").mkdir()
                return 0,"",""
            if argv[:2]==("codex","exec"):
                seen["env"]=env
                (cwd/"src"/"engine.py").write_text("value = 2\n",encoding="utf-8")
                return 0,'{"type":"thread.started"}\n{"type":"turn.completed"}\n',""
            if argv[:3]==("git","diff","--name-only"):
                return 0,"src/engine.py\0",""
            if argv[:3]==("git","ls-files","--others"):
                return 0,"",""
            raise AssertionError(argv)
        env={
            "FACTORY_GITHUB_TOKEN":"gh-secret",
            "GITHUB_ACTIONS":"true",
            "GITHUB_REPOSITORY":"owner/factory",
            "OPENAI_FEDERATION_RULE_ID":"idpm_x",
            "OPENAI_IDENTITY_TOKEN_FILE":"/tmp/token",
            "SUPABASE_SECRET_KEY":"sb_secret_x",
            "PATH":os.environ.get("PATH",""),
        }
        with patch.dict("os.environ",env,clear=True):
            out=CodexCliImplementationProducer(CodexCliConfig(timeout_seconds=30),runner=runner).produce(item())
        self.assertEqual(out.files,{"src/engine.py":"value = 2\n"})
        self.assertNotIn("FACTORY_GITHUB_TOKEN",seen["env"])
        self.assertNotIn("SUPABASE_SECRET_KEY",seen["env"])
        self.assertEqual(seen["env"]["OPENAI_FEDERATION_RULE_ID"],"idpm_x")
        self.assertIn("human production merge gate",out.pr_body)

    def test_supports_text_file_deletion(self):
        def runner(argv,cwd,env,timeout):
            if argv[:2]==("git","clone"):
                Path(argv[-1]).mkdir(parents=True)
                return 0,"",""
            if argv[:2]==("codex","exec"):
                return 0,'{"type":"turn.completed"}\n',""
            if argv[:3]==("git","diff","--name-only"):
                return 0,"old.txt\0",""
            if argv[:3]==("git","ls-files","--others"):
                return 0,"",""
            raise AssertionError(argv)
        with patch.dict("os.environ",{"GITHUB_TOKEN":"managed","PATH":os.environ.get("PATH","")},clear=True):
            out=CodexCliImplementationProducer(runner=runner).produce(item())
        self.assertEqual(out.files,{"old.txt":None})

    def test_sensitive_file_change_is_rejected(self):
        def runner(argv,cwd,env,timeout):
            if argv[:2]==("git","clone"):
                checkout=Path(argv[-1]);checkout.mkdir(parents=True)
                (checkout/".env").write_text("SECRET=x")
                return 0,"",""
            if argv[:2]==("codex","exec"):
                return 0,'{"type":"turn.completed"}\n',""
            if argv[:3]==("git","diff","--name-only"):
                return 0,".env\0",""
            if argv[:3]==("git","ls-files","--others"):
                return 0,"",""
            raise AssertionError(argv)
        with patch.dict("os.environ",{"GITHUB_TOKEN":"managed","PATH":os.environ.get("PATH","")},clear=True):
            with self.assertRaises(ValueError):
                CodexCliImplementationProducer(runner=runner).produce(item())

    def test_invalid_jsonl_is_rejected_before_delivery(self):
        def runner(argv,cwd,env,timeout):
            if argv[:2]==("git","clone"):
                Path(argv[-1]).mkdir(parents=True)
                return 0,"",""
            if argv[:2]==("codex","exec"):
                return 0,"not-json\n",""
            raise AssertionError(argv)
        with patch.dict("os.environ",{"GITHUB_TOKEN":"managed","PATH":os.environ.get("PATH","")},clear=True):
            with self.assertRaises(ValueError):
                CodexCliImplementationProducer(runner=runner).produce(item())


if __name__=="__main__":unittest.main()
