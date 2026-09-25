# Quality Gates

The factory keeps three independent gates:

1. CI: deterministic repository checks.
2. Review/Evaluation: quality evidence.
3. Human gate: risk or product decisions.

A warning does not block by default. A critical review finding blocks. A failed required evaluation blocks. Optional evals can fail without blocking.

This separation prevents a code-quality problem from being confused with a business approval and prevents a human gate from being used as a substitute for testing.
