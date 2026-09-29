# Multi-Agent Architecture

Status: architecture baseline for issue #363.

## Objective

Use specialist agents to shorten the critical path of a software project without turning the Factory into an uncontrolled group chat, duplicating model calls, weakening permissions, or creating merge/release ambiguity.

The Factory remains a deterministic Python/Postgres orchestrator. Models contribute semantic decomposition and bounded implementation/review work. They do not own concurrency, credentials, production release, cost gates, or durable state transitions.

## Design principles

1. **Minimum sufficient team.** Do not activate all specialists by default. Select the smallest set that covers the work and required independent reviews.
2. **Deterministic orchestration.** Dependency ordering, capacity, scope locking, tool permission, budget and release gates are code/Control Plane decisions.
3. **Semantic planning, deterministic allocation.** The Product model describes tasks, capabilities, scopes and dependencies once. The Execution Team Planner maps that structure to the live Agent Registry without another paid model call.
4. **Parallelize independence, not uncertainty.** Work may fan out only when dependencies are satisfied and scopes do not overlap.
5. **One owner per work unit.** A task must be executable by one specialist profile. Cross-specialist validation is a separate lane/work unit.
6. **Independent reviewers.** Security and QA should not silently edit the implementation they evaluate. Findings flow back to a builder as bounded repair work.
7. **Least privilege.** A specialist receives only the tools its profile allows. Read-only reviewers are not granted write permissions merely to fit a generic worker.
8. **Evidence over conversation.** Agents exchange structured artifacts, commits, evaluations and Control Plane records rather than free-form peer chat.
9. **One releasable change set.** Parallel builder outputs should converge on a controlled integration candidate before CI/Preview/release.
10. **Human production gate remains invariant.** Multi-agent speed does not authorize production merge.

## Roles

### Product / Planning

Owns problem framing, specification, engineering-plan decomposition and dependency semantics. It should emit stable task keys, capabilities, scopes, dependencies and a preferred role only when materially justified.

It is not a code-writing worker.

### Development

Primary code implementation, migrations, integrations and debugging. It may use Direct or Codex according to the existing routing/cost policy.

### UI/UX

Owns UI implementation, design fidelity, accessibility and UI-specific browser work. It is a builder profile and may write only within assigned scopes.

### Security

Independent review lane for authentication, authorization, RLS, secrets, supply chain and sensitive access. Default posture is read-only. Security findings produce structured evaluation evidence and, when repair is needed, a new bounded Development/UI work unit.

### QA & Evaluation

Independent validation lane for deterministic tests, regression, evals, browser evidence and quality gates. Deterministic tools are preferred; a model is fallback when judgement is necessary.

### Operations & Observability

Owns CI/deployment diagnostics, quotas, costs, health and operational readiness. It should prefer deterministic provider APIs and Control Plane state. Operations does not become a generic code writer.

## Execution Team Plan

Each completed engineering plan produces a versioned Execution Team Plan.

Inputs:

- engineering-plan tasks;
- live active Agent Registry;
- task capabilities;
- preferred role;
- dependency graph;
- scope keys;
- per-agent maximum concurrency;
- local agent cost budget and model/tool policy.

Outputs:

- selected specialist profiles;
- excluded profiles and reason;
- task-to-specialist assignment;
- planned worker count per specialist;
- execution waves;
- peak planned parallelism;
- blockers;
- advisory specialist lanes that are required by policy but do not yet have a safe executor;
- explicit fail-closed blockers when a task is assigned to a specialist whose dedicated lane is not yet implemented.

The selection policy is minimum-capability-cover-with-least-privilege.

Hard constraints are evaluated before optimization:

1. agent must be active;
2. one agent must cover every capability of its assigned task;
3. explicit preferred role must be satisfiable;
4. tasks may not run in the same wave when scopes conflict;
5. per-agent concurrency must not be exceeded;
6. dependencies must be resolvable and acyclic;
7. a task that cannot be safely owned fails closed rather than being assigned to a convenient generalist.

Tie-breaking favors:

1. explicit preferred role;
2. fewer excess capabilities;
3. fewer allowed tools;
4. smaller local budget;
5. available concurrency;
6. stable agent key ordering.

This makes the decision reproducible and explainable.

## Work graph and waves

The engineering plan is a DAG of work units. The Team Planner converts the DAG into waves.

A wave is the maximum safe set of currently-ready tasks subject to:

- dependency completion;
- non-overlapping repository scopes;
- specialist slot limits.

Example:

    Wave 1
      Development worker A -> API
      Development worker B -> migration
      UI worker A          -> screen

    Wave 2
      Security             -> auth/data review
      QA                   -> deterministic tests

    Wave 3
      Operations           -> Preview/operational verification

Wave count is not a fixed lifecycle requirement. If only one task exists, one specialist can be enough. If several independent work units exist, fan-out is desirable.

## Scope locking

Repository paths are durable conflict domains. Parent/child scopes conflict, for example src/auth and src/auth/session.

Two workers must not write them concurrently.

Future improvement: scope mode should evolve from exclusive-only to read / write locks. Reviewers could then read an implementation scope without blocking unrelated read-only checks while still preventing two writers from racing.

## Target lane architecture

The current runtime has Product, Direct/Codex builder execution, CI, Preview and release observation. The target architecture adds purpose-built specialist lanes rather than forcing every profile through Direct.

### Builder lanes

- Development
- UI

Output: isolated patch/commit artifact plus evidence.

### Review lane

- Security

Input: integrated candidate or bounded diff.
Output: pass/fail/finding set with severity, file/scope references and required remediation.

No direct code write by default.

### QA lane

- QA

Input: integrated candidate plus acceptance criteria.
Output: deterministic test/eval/browser evidence.

A failed criterion creates repair work for the owning builder profile.

### Operations lane

- Operations

Input: candidate, provider state and release policy.
Output: quota/readiness/deployment/health evidence.

It never authorizes the production merge.

## Change Set / integration model

Parallel implementation should not produce a set of unrelated release PRs that must be manually understood and merged in arbitrary order.

The target unit is a **Change Set**:

- one user objective;
- one engineering plan;
- one Execution Team Plan;
- multiple work units/branches or isolated workspaces;
- one controlled integration branch;
- one final release-candidate PR.

Recommended flow:

1. create change set and integration base at the approved source commit;
2. fan out independent builder work units;
3. each builder returns a bounded patch/commit;
4. deterministic integrator applies outputs in dependency order;
5. conflict => repair work, never blind force merge;
6. Security/QA evaluate the integrated candidate;
7. builder repair loops operate against explicit findings;
8. final candidate goes through CI + Preview;
9. human merges production;
10. release observer records the merge.

This removes most merge-order ambiguity and ensures reviewers evaluate what will actually ship.

## Context strategy

Do not give every agent the entire project history.

Each work unit should receive a context packet containing:

- objective;
- acceptance criteria relevant to the work unit;
- exact dependency outputs it needs;
- allowed scopes;
- repository/base SHA;
- relevant architecture/project constraints;
- tool permissions;
- cost/model policy;
- previous findings for that same work unit.

This reduces token usage, cross-task contamination and accidental edits.

The durable Control Plane remains shared memory. Agents should exchange references to evidence rather than copying full conversations.

## Model strategy

Agent profile and model are independent concepts.

Order of preference remains:

1. deterministic tool;
2. direct executor;
3. primary model;
4. Codex for work whose complexity justifies it.

Examples:

- Operations quota check: provider API, no model.
- QA unit tests: deterministic runner, no model.
- Security dependency scan: deterministic scanner first; model only to interpret ambiguous findings.
- small Development change: Primary/Direct.
- large cross-file refactor: Codex when its independent auth/cost gate is ready.

The Team Planner must not call a model merely to decide how many agents to use.

## Adaptive concurrency

Static max_concurrency is a ceiling, not a target.

Effective concurrency should be the minimum of profile ceiling, runnable independent work, provider quota, cost budget and repository contention budget.

The controller should lower concurrency when:

- scope conflicts/rebases rise;
- CI queue latency rises;
- repair rate rises;
- provider quota enters attention/critical state;
- unknown paid cost exists;
- repeated failures suggest a shared root cause.

It may increase concurrency when:

- the DAG contains independent scopes;
- recent conflict rate is low;
- CI/provider capacity is healthy;
- first-pass success remains high.

Changes to concurrency policy must be evidence-backed and auditable.

## Learning and improvement loop

The Factory should improve agent routing from telemetry, but it must not silently rewrite its own safety policy.

Record planned versus actual:

- selected profiles;
- planned/actual workers;
- planned/actual waves;
- queue wait;
- task execution duration;
- critical-path duration;
- first-pass success;
- CI failures;
- security findings;
- QA findings;
- repair loops;
- scope conflicts;
- PR conflicts;
- model/token/cost usage;
- Codex invocation;
- Preview failures;
- release lead time.

Primary optimization metrics:

- **lead time:** objective -> release-ready;
- **parallel efficiency:** serial estimated time / actual critical path;
- **first-pass yield:** work units passing review without repair;
- **rework ratio:** repair work / original work;
- **conflict rate:** scope/integration conflicts per change set;
- **cost per successful change set**;
- **specialist utilization**;
- **quality escape rate:** defects discovered after the relevant review stage.

Policy updates can be proposed automatically but should be applied through normal source control, tests and release gates.

## Evals for the Team Planner

Maintain an offline routing corpus with representative tasks:

- one-line UI change;
- backend endpoint;
- auth feature;
- schema migration;
- CI change;
- large full-stack feature;
- security hardening;
- regression-only request;
- operational incident;
- broad refactor.

For every case assert:

- expected required specialist roles;
- roles that must not be selected;
- maximum acceptable worker count;
- dependency ordering;
- expected scope serialization;
- tool-permission boundary;
- expected Direct/Codex eligibility;
- human-gate expectation.

The eval should punish overstaffing as well as missing required specialists.

## Failure model

Fail closed when:

- no active specialist covers a task;
- a preferred role is unavailable and changing the owner would violate intent;
- dependency cannot be resolved;
- dependency cycle exists;
- scope ownership is ambiguous;
- required reviewer lane is unavailable for a high-risk change;
- tool permission does not match route;
- budget/quota blocks execution;
- candidate identity changes during review/Preview.

Recovery must resume from durable state rather than asking models to reconstruct history.

## Implementation phases

### Phase A — implemented by #363

- deterministic Execution Team Planner;
- live Agent Registry input;
- no extra model call;
- selected/excluded profiles with explanations;
- planned workers;
- dependency/scope-aware waves;
- blocker detection;
- versioned Control Plane persistence;
- project-detail Console visibility;
- advisory detection for specialist lanes that are not safe to schedule yet.

### Phase B — dedicated read-only specialist lanes

Implemented in #366:
- Security review worker over the exact candidate diff using deterministic security invariants;
- QA worker requiring green checks for the exact candidate SHA;
- Operations worker evaluating Preview applicability plus operational/cost health;
- durable queue, leases, bounded retries, findings/evidence and audit trail;
- Preview remains unavailable until all required specialist jobs pass;
- no generic github_write grant to reviewers and no paid model call merely to perform review.

Still pending:
- bounded model fallback for genuinely ambiguous findings;
- automatic repair-work generation from failed findings, implemented with Change Sets.

### Phase C — Change Set integration

Implemented in #367:
- one durable Change Set per ready Team Plan;
- builder work units materialized by stable task key and execution wave;
- immutable source SHA fixed by the first builder;
- each work unit receives an isolated exact-base branch and produces no release PR;
- completed units in a wave are integrated into one integration branch;
- overlapping changed files and stale base commits fail closed;
- later waves start from the previously integrated candidate;
- builder and integrator recovery is bounded;
- after the final wave, exactly one release-candidate PR is created;
- the existing CI -> Specialist Lanes -> Preview -> human release pipeline validates the exact integrated candidate.

The GitHub runtime adapter still has no merge capability.

### Phase D — adaptive scheduler

Implemented in #368:
- effective concurrency is a runtime ceiling, never a target;
- bounded by runnable independent work and Agent Registry max_concurrency;
- paid-cost unknown or critical/blocked quota fail closed to zero workers;
- quota attention/unknown, repair rate, first-pass yield and CI queue pressure reduce parallelism;
- every decision is persisted with pressure snapshot and reasons;
- the GitHub Actions worker matrix is filtered before workers start.

Still pending:
- measured scope-conflict rate from Change Sets;
- full planned-vs-actual critical-path telemetry;
- Shadow Mode comparison before tuning-policy rollout.

### Phase E — routing evals and continuous improvement

Implemented in #369:
- offline Team Planner corpus with 10 representative work classes;
- required/forbidden role assertions and maximum worker-peak thresholds;
- explicit overstaffing, under-staffing and wrong-role failures;
- no model/provider/network dependency.

Still pending:
- planned-vs-actual production telemetry;
- compare routing-policy revisions in Shadow Mode before rollout;
- adaptive thresholds from observed outcomes.

No paid benchmark runs are implicit.

## Non-goals

- six agents on every task;
- peer-to-peer agent group chat as the main control plane;
- agents choosing their own permissions;
- agents sharing long conversational memory by default;
- automatic production merge;
- giving reviewers write access merely to reuse the builder worker;
- using Codex as the orchestrator;
- hidden self-modification of routing or safety policy.


## Requirement traceability and Definition of Done

Planning tasks carry independently verifiable acceptance criteria. The Factory deterministically derives stable requirement keys and links each requirement to the materialized task. Requirement evidence is never inferred from code generation: only observed delivery evidence such as exact-candidate CI, independent QA/Security, verified Preview/browser evidence and observed human merge is persisted.

The Definition of Done is a versioned list of explicit checks, phases, reasons and evidence types. It is not a model-generated score. Readiness is represented as satisfied and missing checks. Production human release remains a human-only evidence type.

Migration validation, rollback analysis and API contract checks are compiled when applicable but remain visibly missing until a dedicated validator records evidence. The following Policy-as-Code phase will decide which available checks are hard runtime gates.
