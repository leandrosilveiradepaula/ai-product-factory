# Pipeline Engine

The Pipeline Engine composes bounded implementation and delivery components into
one execution path:

```text
task
  -> plan / branch
  -> implementation producer (Direct or selective Codex)
  -> pull request
  -> review / evals
  -> CI
      pending -> wait
      failed  -> bounded repair / correction
      green   -> Preview applicability
                    required     -> exact Preview + browser/e2e evidence
                    not required -> durable non-applicability evidence
  -> awaiting_release
  -> human PR merge
  -> release observer records the already-completed merge
  -> operations
```

No stage may loop without a configured limit. Product/risk approval remains
separate from code quality and CI.

Production is never merged by the runtime. CI, quality gates and verified
Preview are prerequisites for release readiness, not authorization to merge.
The GitHub runtime adapter intentionally has no merge capability.
