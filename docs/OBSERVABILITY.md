# Runtime observability

Every model-dependent run should record enough metadata to answer:

- which provider/model was used;
- which authentication strategy was used, by kind only;
- input/output/cached tokens;
- known monetary cost when the provider exposes or the runtime can safely calculate it;
- whether cost is unknown rather than silently treated as zero.

Secret values are never telemetry.

The factory must keep usage and cost separate: a ChatGPT/Codex entitlement can have measurable token or credit usage without being an OpenAI API charge. Unknown cost remains explicitly unknown.


## Delivery efficiency metrics

The Factory derives operational metrics from durable Control Plane evidence only. No model call is made to calculate metrics.

For a source run, `python -m ai_product_factory.runtime_cli --mode delivery-metrics --source-run-id <uuid>` reports:

- queue wait and delivery wall-clock time;
- time to `awaiting_release` and observed release;
- per-stage duration when both `started` and terminal stage events exist;
- planned agents versus actual builder/specialist agents;
- known USD cost and paid events whose cost remains unknown;
- input/output/cached token counts when provider metadata exposes them;
- Codex invocations separately from API monetary cost;
- CI observation and first-pass CI;
- CI repair attempts, specialist repair jobs, and total repairs.

`first_pass_ci` is null until CI evidence exists. Unknown monetary cost is never coerced to zero.

Stage timing is forward-looking: the runtime records a `started` event before each product stage and a `failed` event when execution aborts. Existing historical runs that predate this instrumentation may legitimately have no per-stage duration.

For an end-to-end delivery, the reader groups the planning source run with work-unit runs and the release run linked through the durable execution team plan/change set. This lets planned-vs-actual metrics describe one delivery instead of one isolated worker invocation.

Secret values, raw credentials and authorization headers are never metrics.

## Vercel status is not deployed state (26/10/2026)

The exact Github commit `c44f060...` (PR #1107) returned a Vercel GitHub
commit `success` status, but the owned Vercel deployment
`dpl_9sXYWPdP5Lbxobt7uiGh8rCqJA8k` was `CANCELED` by the configured
ignored-build step. The commit had no `apps/console/**` file changes. This
is a verified Preview-not-applicable case, **not** a READY deployment.
The global auditor must distinguish GitHub provider status from actual
deployment state. Never use GitHub success as proof that the Console changed,
was deployed, is available at the SHA, or passed authenticated visual QA.

After the fix, `global-readiness-post-ci` reads the immutable commit's
first-parent file list (including rename old/new paths), checking at most 30 complete 100-file REST pages and failing closed on
ambiguous inventories. A non-Console commit produces `not_applicable` even
when the provider reports success or failure. For Console changes, success
is only `provider_status_success_unverified` and must be corroborated by
independent exact-SHA Preview/deployment and browser evidence. No Vercel token
is required in the trusted GitHub-only observer. This is evidence reporting
only; it does not generate a product-readiness assessment or invoke models.
