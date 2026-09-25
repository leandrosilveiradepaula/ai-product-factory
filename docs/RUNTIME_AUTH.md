# Runtime authentication

Authentication is a runtime capability, not a project property.

The factory can recognize three credential strategies:

1. workload identity via OPENAI_WORKLOAD_IDENTITY_FILE;
2. ChatGPT/Codex access token via CHATGPT_ACCESS_TOKEN;
3. OpenAI API key via OPENAI_API_KEY.

Precedence follows that order so short-lived or federated identity can replace long-lived credentials without changing pipeline code.

This module deliberately does not implement the token-exchange protocol for ChatGPT/Codex or workload identity. Those transports are enabled only after the official workspace configuration is confirmed. This avoids guessing an authentication protocol or accidentally sending a ChatGPT credential to the public API endpoint.

Secret values are never returned by the resolver and must never be written to project memory, the control plane, logs, evidence bundles, or source control.
