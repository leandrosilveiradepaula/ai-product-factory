# Factory Console

Interface operacional da AI Product Factory.

## Security boundary

The browser never receives the Supabase service role. All control-plane reads/writes are server-side. Without server credentials the console uses a minimal local bootstrap state so UI development and CI remain deterministic.

## Local

```bash
npm install
npm run typecheck
npm run build
```
