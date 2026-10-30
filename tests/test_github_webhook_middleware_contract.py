"""Guard the GitHub App webhook's only public route against Console session redirects.

The webhook endpoint uses a signed GitHub HMAC, strict payload validation and
service-role-only SQL gates. No other Console API is made public.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIDDLEWARE = (ROOT / "apps/console/middleware.ts").read_text()
WEBHOOK = (ROOT / "apps/console/app/api/integrations/github-app/webhook/route.ts").read_text()


class WebhookMiddlewareContract(unittest.TestCase):
    def test_exact_github_webhook_path_bypasses_operator_session_only(self):
        self.assertIn('path==="/api/integrations/github-app/webhook"', MIDDLEWARE)
        self.assertIn('path==="/api/health"', MIDDLEWARE)
        self.assertIn('path.startsWith("/login")', MIDDLEWARE)
        self.assertIn('path.startsWith("/unauthorized")', MIDDLEWARE)
        self.assertNotIn('path.startsWith("/api/integrations")', MIDDLEWARE)
        self.assertNotIn('path.startsWith("/api/")', MIDDLEWARE)
        self.assertIn('if(!user)', MIDDLEWARE)
        self.assertIn('url.pathname="/login"', MIDDLEWARE)

    def test_public_webhook_still_requires_hmac_and_strict_sql_authority(self):
        self.assertIn('process.env.FACTORY_GITHUB_WEBHOOK_ENABLED!=="true"', WEBHOOK)
        self.assertLess(WEBHOOK.index("getGitHubWebhookVerificationConfig()"),
                        WEBHOOK.index("authenticateGitHubWebhook("))
        self.assertLess(WEBHOOK.index("authenticateGitHubWebhook("),
                        WEBHOOK.index("claimExternalWebhookWake("))
        self.assertLess(WEBHOOK.index("claimExternalWebhookWake("),
                        WEBHOOK.index("requestIntakeWorkerWake()"))
        self.assertNotIn("requireConsoleAdmin", WEBHOOK)


if __name__ == "__main__":
    unittest.main()
