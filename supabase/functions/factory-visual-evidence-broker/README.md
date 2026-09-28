# Authenticated visual evidence broker

This Supabase Edge Function is the privileged bridge used by
`.github/workflows/authenticated-visual-evidence.yml`.

It exists so GitHub Actions can create one short-lived Console operator for
browser evidence without receiving a Supabase service-role key.

## Trust boundary

The function uses custom GitHub OIDC authentication and validates:

- issuer: `https://token.actions.githubusercontent.com`;
- audience: `factory-visual-evidence`;
- repository name and immutable repository numeric ID;
- immutable repository owner numeric ID;
- `refs/heads/main`;
- GitHub Environment `openai-api`;
- exact workflow ref for `authenticated-visual-evidence.yml`;
- event type limited to `push` or `workflow_dispatch`.

The Edge Function itself uses the Supabase-managed service-role environment
only server-side. That credential is never returned to GitHub Actions.

## Lifecycle

1. `provision`
   - validates the candidate SHA against the OIDC `sha` claim;
   - creates a random Auth user;
   - grants only Factory `operator` role, never `admin`;
   - creates a short-lived visual-evidence registry row;
   - returns one-run credentials and an artifact encryption key.
2. The GitHub workflow signs in through the real Console login form and captures
   the authenticated pages.
3. Screenshots are encrypted before artifact upload.
4. `captured` records successful capture.
5. `cleanup` removes the operator row and Auth user.
6. `expire` removes the operator when possible and marks failed runs expired.

The operator and decryption key are ephemeral. Consumers must remove the
registry row after local evidence recovery.

## Deployment

The deployed function name is `factory-visual-evidence-broker`.
`verify_jwt=false` is intentional only because this function performs its own
cryptographic GitHub OIDC verification with `jose`.

Do not replace the custom validation with anonymous access, a reusable bypass
token, public RLS policy, or a browser-visible Supabase administrative key.
