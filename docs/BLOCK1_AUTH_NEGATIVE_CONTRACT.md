# Bloco 1 — contrato negativo de Auth/RBAC (05/11/2026)

Após merge humano da PR #1242, `main=f36630c475d08f8ca2a14d6c85f61ffee547d725`. Esta entrega trata uma lacuna real no parsing de respostas Supabase Auth: o Console antes aceitava objetos JSON com `role` arbitrário, linhas ambíguas, `is_active` ausente, user id não UUID ou sessão com token inválido sem verificar contrato em runtime.

`apps/console/lib/auth-api.ts` agora recusa respostas inválidas antes de produzir `ConsoleOperator` ou `AuthSession`: user UUID, email opcional string/null, sessão com tokens não vazios e expiração positiva, e **exatamente uma** linha ativa com role `operator` ou `admin`. Não cria/promove usuário nem altera permissões no banco.

`apps/console/tests/auth-api-boundaries.test.mjs` testa dados sintéticos e mocks locais, incluindo rejeição de role `owner`, operador inativo, linhas duplicadas, token vazio, user inválido, expiração negativa e sucesso de operador válido. `validate/test` executa a suíte em Node 22.

**Limite:** mocks adversariais não são teste autenticado real nem substituem prova de navegador, Supabase Auth/RLS, usuário não autorizado e separação de tenant. `security/authn_authz` e `security/data_access_boundaries` continuam pendentes de certificação independente no SHA de `main`. Esta PR não toca Supabase, secrets, produção, modelos pagos, permissões ou merge automático. Mudança em `apps/console/**` exige Preview real conforme política vigente, com evidência browser no candidato antes de merge humano.
