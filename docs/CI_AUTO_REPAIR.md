# CI Auto-Repair

CI failures are handled as a bounded state machine rather than an unbounded agent loop.

Default policy:

- maximum 2 repair attempts;
- every repair requires structured failure evidence;
- repairs go through the Direct Executor when they fit its safety limits;
- every attempt is persisted as tool usage;
- after the maximum attempts, the run moves to `failed_gate`.

A later executor may reclassify a difficult repair to Codex, but Codex is not the default repair path.
