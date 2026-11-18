# Platform Change Set — reconciliação segura de SHA congelado

## Incidente UX/UI #1506
A run Direct `6e021307-b11c-4870-8d46-06ec4c730196` executou o planejamento já persistido,
mas foi bloqueada pela invariante:
`PermissionError: frozen Change Set source differs from verified candidate`.

O Change Set `5d0656f0-aec3-42f2-93e2-bee0e2155fbf` foi planejado no SHA
`88536c68af9e7d71b7a167b2f5ac227bbb5d77d7`. Merges humanos posteriores
alteraram `main`, sem modificar as superfícies do Console solicitadas pela auditoria.
A Factory recusou executar sobre um SHA congelado sem reconciliação explícita.

## Recuperação genérica, limitada e auditável
A migration `20261118022000_platform_blocked_change_set_source_repin.sql` instala
`factory_repin_blocked_platform_source_v1`, **inerte até autorização de produção**
e acessível somente a `service_role`, `SECURITY INVOKER`.

Operador autorizado deve:
1. Consultar o GitHub `main` em SHA completo e comparar `old_sha...new_sha`;
   aceitar somente `status=ahead`, `behind_by=0` e até 30 commits / 100 arquivos.
2. Conferir a lista integral de caminhos contra `scope_keys`, governança e áreas
   do Console protegidas. Sem interseção com o escopo de escrita.
3. Verificar que o branch exato do work unit ainda aponta para `old_sha` e
   fazer fast-forward CAS desse branch para o SHA `main` verificado.
   Não tocar em `main` e não usar force-push.
4. Reconfirmar `main`, verificar `service_role` e parâmetros, e chamar uma
   única vez a RPC com a evidência GitHub sanitizada (inclui SHA do branch).
5. Confirmar novo `source_commit` no Change Set, base do work unit,
   status `queued` da mesma run e evento `change_set.platform_source_repinned`.
6. Acordar o scheduler via comando OWNER autenticado, acompanhar PR/CI,
   Preview somente se Console mudar, e **parar em gate humano de merge**.

Esta RPC não amplia as permissões de escrita, não replaneja, não autoriza gastos
fora do ledger e não publica produção. Identidade de GitHub continua verificada
por operador/broker externo; a base de dados verifica o contrato formal e
recusa evidência inconsistente. Sem prova externa verdadeira, não executar.
