# Runtime observability

Every model-dependent run should record enough metadata to answer:

- which provider/model was used;
- which authentication strategy was used, by kind only;
- input/output/cached tokens;
- known monetary cost when the provider exposes or the runtime can safely calculate it;
- whether cost is unknown rather than silently treated as zero.

Secret values are never telemetry.

The factory must keep usage and cost separate: a ChatGPT/Codex entitlement can have measurable token or credit usage without being an OpenAI API charge. Unknown cost remains explicitly unknown.
