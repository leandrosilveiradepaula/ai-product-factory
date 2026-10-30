# Source-SHA lifecycle — bounded, fail-closed identity reconciliation (candidate)

## Diagnosis from CRM #203 / #205 / #206

A SHA is a commit identifier, **not** a global journey version. On 29 October
2026 the Factory froze CRM Preview source `eb628ca...` in the Start/Change Set
and produced implementation PR #205 at `4ad04ae...`. An authorized human
merged #205 **into the source PR #203's Preview branch**, producing
`24c8e4c...`. The source PR remains a draft, while a separate PR #206 was
human-merged into production at `fea466...`.

All five identifiers are simultaneously valid. The bug is trying to
reclassify a *consumed source* as a new source merely because the branch moved.

## Lifecycle and ownership

| Identity | Scope | Mutability |
|---|---|---|
| Project delivery_target SHA | Selection cursor for a **future** Start | CAS-only with explicit authority |
| Frozen Change Set source_commit | Source snapshot of one authorized Start | Immutable after binding; historical repair follows a separate gated RPC |
| Work Unit output_commit | Exact bytes of an individual implementation | Immutable evidence |
| Change Set candidate_commit | Current implementation candidate, may advance via bounded CI repair | Audited, scoped CAS |
| Preview merge_sha | Human-integrated implementation in Preview | Immutable receipt; does not authorize a source repin |
| Production release SHA | Human merge of a separately verified production PR | Immutable observation; not inferred from file similarity |

The runner uses the following hierarchy for an advanced branch:

1. Parse registered project/PR/branch/source SHA and check the live ref.
2. Check completed **same-project/same-generation** Change Set receipts at
   the exact old source SHA. If a verified Change Set was merged into that
   Preview branch producing the *exact new head*, classify
   `candidate_source_consumed`. Verify immutable root/Change Set IDs,
   implementation commit and PR, changed file scope, merge SHA and GitHub
   ancestry, with a second current ref/PR check. **Never repin this as a new
   source** even if the source PR subsequently becomes ready.
3. Otherwise, a stable, exact PR still in DRAFT can be classified
   `candidate_draft_hold`. This has no write, no paid call and no CI claim.
4. Otherwise the existing exact-GitHub-PR, latest-native-CI and service-role
   CAS path applies. A changed/unverifiable ref, incomplete history,
   insufficient permissions, a competing write, or mismatching epoch stays
   blocking.

**Deferred is not success.** It is a separately reported non-mutation,
without any claim that a new Start, PR, Preview, merge or release occurred.

## Protect the next journey

An already consumed source is not a reusable Start authorization. A future
Start must choose a new source through an authorized existing-project
rotation/switch and a fresh epoch CAS. The existing `source_commit` and
Change Set metadata remain unchanged. No legacy terminal runs are reopened.

The Change Set builder's live PR admission remains strict for **new**
unbound work. Do not weaken it to accept an arbitrary descendant of an old
source. The frozen source is retained for provenance, not a license for a
second implementation after the source branch moved.

The source transition audit reader accepts both previously authorized
`project.delivery_target.reconciled` and
`project.delivery_target.replaced` records, bound to known system actors,
current generation/version, exact target identity and native CI receipt.
It never synthesizes proof from the latest branch HEAD or a prompt.

## Boundaries / future proof

The existing release report for CRM #205 is `blocked` in the production
release lane, correctly separating its **nonproduction** integration from
the later externally promoted PR #206. This patch does **not** mark that
report released or attach unrelated release PRs by filename similarity.
A separate explicit cross-PR release linkage would require exact signed
provenance and new independent tests before being written to the ledger.

Regression scenarios: authentic consumed-source history; PR/source SHA
identity; forged/unrelated/incomplete Change Set receipts; wrong epoch;
modified integration files; non-fast-forward; repo/branch moved during
read-only verification; source PR remains DRAFT; native CI fails or is stale;
CAS 409 remains blocking. No production merge capabilities, payments,
credentials, Supabase migration or Console code change.

For this candidate `apps/console/**` is unchanged, therefore Console
Preview is not applicable by the current path-specific policy. CI, offline
tests and a **real subsequent scheduled runner observation** are separate
evidence. `product_ready=false` until all six independent domains pass.
