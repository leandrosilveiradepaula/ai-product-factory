## B1-B4 certification scope

Factory-Block: B2
Factory-Criteria: test_strategy/regression_gates
Factory-Intent: advance
Factory-Acceptance: Independently verified Supabase certificate persisted on the exact main SHA, with no regression in any previously passing criterion.
Factory-Scope: leandrosilveiradepaula/ai-product-factory
Factory-Cross-Repo: read-only
Factory-Human-Gates: human-review; never automatic production merge

## Independent proof

Document the exact test, the failure mode, the certifier evidence source and why it can promote the named criterion. A green PR does not certify any of the 19 criteria. For regression repairs use Factory-Intent: repair-regression and provide a real Factory issue as Factory-Incident.

## Constraints

No external project writes, model calls for probing, unauthorized migration, RLS relaxation, synthetic Start or automatic production merge.
