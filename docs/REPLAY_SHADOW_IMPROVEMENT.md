# Replay, Provenance, Shadow Mode and Improvement Proposals

## Goal

Make Factory decisions reproducible and comparable without giving replay/shadow experiments any operational authority.

## Provenance

Before a Change Set builder invokes a model, the Factory records a hash-stable provenance snapshot containing:

- run and project identity;
- execution route and agent key;
- exact candidate/base commit;
- Context Packet hash;
- Team Planner version;
- router policy version;
- adaptive concurrency version;
- release policy version;
- project manifest hash.

The provenance snapshot never contains credentials and is server-side only.

## Replay

Replay requests are offline/shadow artifacts only.

Hard invariants:

- effect is always none;
- model calls are disabled by schema;
- replay never dispatches work;
- replay never changes queue state;
- replay never changes release policy;
- replay never changes production.

A replay copies the durable provenance snapshot of a source run and can be used by deterministic offline evaluators.

## Shadow Mode

A shadow decision stores:

- source run;
- replay id;
- component and candidate component version;
- hash of the same factual input;
- alternate decision;
- observed real outcome when available.

The shadow result is comparable evidence only. It has no tool permission and no runtime side effects.

## Self-improvement

The Factory may create an improvement proposal from accumulated evidence.

Every proposal is born with:

- status proposed;
- requires_source_control=true;
- auto_apply=false.

A proposal must become normal engineering work: issue, branch, tests, evals, PR, Preview and human release where applicable. The Factory does not silently rewrite its own routing, policies, prompts or safety boundaries.

## Intended metrics

Replay/shadow analysis can compare:

- lead time;
- planned vs actual workers/waves;
- first-pass yield;
- repair ratio;
- scope/integration conflicts;
- CI queue delay;
- cost per successful Change Set;
- specialist utilization;
- quality escape rate.

The purpose is to improve future source-controlled policies, not to create autonomous self-modification.