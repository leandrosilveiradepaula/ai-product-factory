# Work Unit Sandboxes, Context Packets and Repair Loops

## Purpose

Keep parallel implementation isolated, provide each builder only the context it needs, and turn independent Security/QA findings into bounded repair work without granting reviewers write permission.

## Work-unit isolation

Every Change Set builder operates against:

- one exact base commit;
- one dedicated work branch;
- one explicit list of write scopes;
- one Agent Registry assignment;
- one durable work-unit identity.

The Factory commits the generated patch only after verifying that every changed path is inside the assigned scopes. A patch outside those scopes is rejected before the controlled GitHub commit.

Codex continues to use its temporary isolated checkout. Direct and Codex share the same post-generation write-scope enforcement.

## Context Packet

Before a builder invokes a model, the Factory derives a versioned Context Packet from durable Control Plane state.

It contains only:

- task objective and acceptance criteria;
- task key, agent key, capabilities and dependencies;
- repository identity, exact base SHA, work branch and write scopes;
- deterministic Impact Engine evidence;
- current repair finding when applicable;
- explicit safety constraints.

It does not include full chat history, arbitrary project history or credentials.

Secret-like field names and token/key signatures are rejected both in Python before use and again by the Control Plane persistence RPC.

The packet is SHA-256 hashed and persisted as durable evidence.

## Repair loop

Security and QA remain independent read-only lanes.

A failed Security/QA finding may create a repair work unit when:

- the release run belongs to a Change Set;
- the finding has a bounded scope (or a bounded integrated-file fallback exists);
- the maximum repair-cycle count has not been reached.

Repair policy:

1. owner is Development;
2. exact failed candidate becomes provenance for the repair;
3. repair work enters a new Change Set wave;
4. builder receives only finding + permitted scopes + normal Context Packet;
5. integrated repair updates the same final release-candidate branch;
6. the new candidate repeats CI and all required specialist lanes;
7. passing independent recheck marks the repair passed;
8. maximum is three cycles per Change Set/source specialist role;
9. cycle exhaustion or unknown repair scope blocks the Change Set.

Operations findings are not auto-repaired. Operational blockers such as unknown paid cost or provider quota remain fail-closed because they are not safely solved by changing application code.

## Production boundary

Repair automation does not weaken release policy. A repaired candidate still requires all factual DoD/policy evidence and stops at the human production merge gate.
