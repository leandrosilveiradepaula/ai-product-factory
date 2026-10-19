# Direct Executor

The Direct Executor handles small and medium code changes when the execution router decides Codex is unnecessary.

## Safety limits

Default limits:

- at most 12 files per changeset;
- at most 200 KB of UTF-8 text;
- no absolute paths;
- no parent-directory traversal;
- no writes under `.git`;
- no common secret-bearing files such as `.env`;
- no private-key/certificate suffixes such as `.pem` or `.key`.

The executor does not bypass the normal GitHub flow. It commits through the existing autonomous GitHub loop and records evidence in the control plane.

## Escalation

If a task cannot fit safely inside these limits, the factory should reclassify it. That may mean splitting the task or escalating it to a specialized executor such as Codex.


## Safe repository context in real Change Set runs (2026-10-19)

The Direct/Change Set builder reads context at the **exact candidate SHA**. It must never pretend that a clipped file is a complete editable source:

- The explicit exact-file write targets and repository governance context must be read **in full**. If these exceed the 128 KiB context budget, fail closed with a replan/narrow-scope error before a model call, branch commit or paid action.
- Optional files share the remaining context budget (up to 16 KiB each) using deterministic head/tail excerpts and a SHA-256/byte-count marker. Omitting optional context when no space remains is preferable to exceeding the total bound.
- A redacted context file, or a file shown only as an excerpt, is **read-only for the current run** even under a broad write scope. A producer attempting to overwrite it is blocked before GitHub commit. This protects existing project data from whole-file rewrites based on partial context.
- Keep write-scope enforcement and existing human decisions authoritative. Context selection is not approval to edit.
- Run `PYTHONPATH=src python -m unittest tests.test_repository_snapshot_safety -v` for the offline regression; CI must still validate the exact candidate SHA. No retry of historical blocked CRM runs is implied by landing this change.

A known CRM run previously failed with `repository context snapshot too large`. This change fixes the size-control path in the Factory, **not** CRM implementation logic or its separate pending human planning gate.
