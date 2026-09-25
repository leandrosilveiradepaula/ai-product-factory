# Release autonomy

The MVP uses environment-aware release policy.

Low-risk changes may proceed autonomously in development and preview environments.

Production releases always require a human gate in v0.1, even when the underlying change is otherwise low risk.

Independent risk gates remain active in every environment for destructive data changes, sensitive access expansion, creation of a paid service, and material requirement changes.

This expands autonomy where rollback and blast radius are limited without silently weakening the production boundary.
