import json
import unittest
from unittest.mock import patch

from ai_product_factory.deployment import DeploymentRequest
from ai_product_factory.evidence import EvidenceBundle
from ai_product_factory.github_vercel_preview import GitHubVercelPreviewAdapter,GitHubVercelPreviewConfig
from ai_product_factory.release_policy import ReleaseEnvironment


class Response:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return json.dumps(self.data).encode()


def request(environment=ReleaseEnvironment.PREVIEW):
    evidence=EvidenceBundle("abc","abc","success",metadata={"quality_gate_passed":True})
    return DeploymentRequest("demo",environment,"abc",evidence)


class Tests(unittest.TestCase):
    def config(self):return GitHubVercelPreviewConfig(repository="owner/repo",token="token",poll_attempts=2,poll_interval_seconds=0)

    def test_discovers_preview_host_from_vercel_check_output(self):
        payload={"check_runs":[{
            "id":41,"status":"completed","conclusion":"success","app":{"slug":"vercel"},
            "output":{"summary":"Go to https://vercel.live/open-feedback/demo-git-abc-team.vercel.app?via=x"},
        }]}
        with patch("urllib.request.urlopen",return_value=Response(payload)):
            out=GitHubVercelPreviewAdapter(self.config(),sleeper=lambda _:None).deploy(request())
        self.assertEqual(out.status,"success")
        self.assertEqual(out.preview_url,"https://demo-git-abc-team.vercel.app")
        self.assertEqual(out.deployment_ref,"41")

    def test_ignores_non_vercel_checks_and_polls(self):
        first=Response({"check_runs":[{"id":1,"status":"completed","conclusion":"success","app":{"slug":"github-actions"}}]})
        second=Response({"check_runs":[{"id":2,"status":"completed","conclusion":"success","app":{"slug":"vercel"},"output":{"summary":"demo.vercel.app"}}]})
        with patch("urllib.request.urlopen",side_effect=[first,second]):
            out=GitHubVercelPreviewAdapter(self.config(),sleeper=lambda _:None).deploy(request())
        self.assertEqual(out.preview_url,"https://demo.vercel.app")

    def test_refuses_production(self):
        with self.assertRaises(PermissionError):
            GitHubVercelPreviewAdapter(self.config()).deploy(request(ReleaseEnvironment.PROD))

    def test_missing_token_fails_closed(self):
        with self.assertRaises(ValueError):
            GitHubVercelPreviewAdapter(GitHubVercelPreviewConfig(repository="owner/repo",token=""))


if __name__=="__main__":unittest.main()
