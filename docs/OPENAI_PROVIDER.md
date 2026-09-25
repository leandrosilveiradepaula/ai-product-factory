# OpenAI Provider

The primary-model provider uses the OpenAI Responses API.

Default routing:

- low complexity -> `gpt-5.6-luna`;
- medium/high -> `gpt-5.6-terra`;
- very high -> `gpt-5.6-sol`, unless the execution router selects Codex.

Security and cost controls:

- `OPENAI_API_KEY` comes only from server-side environment;
- requests use `store=false`;
- output is capped with `max_output_tokens`;
- reasoning effort is explicit;
- usage returned by the API is surfaced to the runtime ledger;
- no API key is stored in project memory, Supabase payloads, logs, or source control.

The provider is optional at import time and fails closed only when an actual model-dependent step is executed without credentials.
