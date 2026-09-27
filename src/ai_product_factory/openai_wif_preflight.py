from __future__ import annotations

import os

from .openai_provider import GitHubActionsOpenAIWorkloadIdentity


def main() -> int:
    required = (
        "OPENAI_IDENTITY_PROVIDER_ID",
        "OPENAI_SERVICE_ACCOUNT_ID",
        "OPENAI_WIF_AUDIENCE",
        "ACTIONS_ID_TOKEN_REQUEST_URL",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    )
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError("API WIF preflight configuration is incomplete: " + ", ".join(missing))

    identity = GitHubActionsOpenAIWorkloadIdentity.from_env()
    token = identity.get_access_token()
    if not token:
        raise RuntimeError("OpenAI API WIF preflight did not receive an access token")

    print("api_wif_preflight=ok")
    print("auth_mode=workload_identity")
    print("model_call=not_performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
