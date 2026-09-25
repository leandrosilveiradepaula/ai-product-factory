# Pipeline Engine

The Pipeline Engine composes existing bounded components into one execution path:

```text
task
  -> plan/branch
  -> direct implementation
  -> pull request
  -> review/evals
  -> CI
      pending -> wait
      failed  -> bounded repair
      green + human gate -> wait
      green + no human gate -> merge
```

No stage is allowed to loop without a configured limit. Product/risk approval remains separate from code quality and CI.
