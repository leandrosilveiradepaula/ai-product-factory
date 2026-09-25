# Release autonomy

The Factory uses an environment-aware release policy.

Low-risk changes may proceed autonomously in development and preview environments.

Under the current production policy, production releases require a human gate even when the underlying change is otherwise low risk. This is a deliberate safety boundary, not a limitation of an MVP.

Independent risk gates remain active in every environment for destructive data changes, sensitive access expansion, creation of a paid service, and material requirement changes.

The policy may evolve through an explicit product/security decision, with evidence and audit history, rather than being silently weakened by runtime code.
