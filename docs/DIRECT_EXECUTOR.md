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
