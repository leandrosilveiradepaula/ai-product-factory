# GitHub Autonomous Loop

The factory owns the deterministic GitHub lifecycle around an implementation.

```text
Issue
  -> branch
  -> persisted plan
  -> implementation commit(s)
  -> pull request
  -> CI
       pending -> wait
       failed  -> implementation
       green + human gate -> wait for user
       green + no gate    -> squash merge
  -> close issue
```

## Runtime credentials

Use `GITHUB_TOKEN` only in a trusted server-side runtime. The token is never stored in the repository.

## Boundaries

The GitHub loop does not decide product requirements and does not generate code by itself. Those responsibilities belong to Product/Engineering planning and the execution router.

## Atomic commits

`GitHubRestAdapter.commit_files` uses the Git data API (blobs -> tree -> commit -> ref update) so one logical factory step produces one logical commit even when multiple files change.
