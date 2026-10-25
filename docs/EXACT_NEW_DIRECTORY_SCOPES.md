# Escopos exatos em novos diretórios de repositórios existentes

Incidente real, 24/10/2026: [CRM issue #194](https://github.com/leandrosilveiradepaula/crm-infodive/issues/194) iniciou nova run legítima da Factory `7a4a88ac-2ad2-42bc-bc6b-5135035b0d84`, criou backlog `b1c393f5-5272-49d8-9a9d-c9e3c1d5a092` e roteou Direct `bd5a2e8d-413e-442b-8f23-6ef3016ea39e`. O planner preservou os cinco caminhos autorizados; porém o resolvedor `_bounded_file_scope` só reconhecia arquivos novos quando o **diretório pai imediato** já possuía um arquivo. Em uma rota Next.js nova `src/app/(dashboard)/service-desk/page.tsx` e novo pacote `src/lib/service-desk/...`, o diretório imediato não existe antes do trabalho. O código os classificava como escopos semânticos e os substituía por caminhos antigos encontrados na árvore (inclusive código Gemini alheio), criando `repository.write_scopes` incorreto. O executor recusou as escritas, mas essa recusa ocorreu tarde demais.

## Contrato da correção

- Um arquivo literalmente nomeado e autorizado em `scope_keys` de Work Unit pode ser criado dentro de **um** novo diretório de código se seu ancestral imediato já tem arquivos verificáveis no **SHA base fixado**.
- Nunca ampliar esse caminho para `src/**`, `tests/**`, `.`, prefixo de diretório ou arquivo vizinho. Os scopes finais do pacote continuam **nomes exatos** e o commit continua validado por `enforce_write_scopes`.
- Uma localização com dois ou mais níveis de diretório novos, um caminho secreto/oculto, migração não autorizada, travessia ou arquivo com formato não permitido continua bloqueada. Uma entrada que *parece arquivo concreto* mas não consegue ser verificada **nunca vira fallback semântico** para arquivo não relacionado. A falha ocorre antes da chamada do modelo.
- Não altera o banco CRM, Vercel, Console, serviços pagos ou código CRM. A recuperação administrativa usa uma migration separada e human-gated do **Control Plane da Factory**.

## Validações

Executar `python -m unittest tests.test_existing_new_directory_scopes -v`, a suíte `validate` e testes de aceitação normais da Factory. Nenhum modelo pago para testar o fix. Após merge humano de PR da Factory, não reabrir a run Direct bloqueada silenciosamente nem reexecutar Product Stage. Verificar se há RPC de recuperação *estritamente original SHA/epoch/scope* apropriada; se não existir, registrar dependência e criar recuperação durável separada. Integração final do Service Desk na `main` do CRM segue gate humano.


## Recuperação tipada após correção de código (versão preparada, NÃO aplicada)

A migration `20261024235800_resume_blocked_literal_scope_misresolution.sql` adiciona função SECURITY INVOKER/service_role-only, sem políticas públicas, para enfileirar **somente** Work Units de repositório existente com status `blocked`, `blocker.type=repository_governance`, erro de `repository.write_scopes` original, pacote registrado com ausência comprovada de escopos literais do planner, nenhum commit ou merge produzido, SHA candidato idêntico ao pinned, Control Plane na geração corrente, lease vazia, cardinalidade exata e ausência de replay anterior. Limite de 3; `SKIP LOCKED` e auditoria detalhada. A função reabre somente a mesma tarefa/run/Change Set para o resolvedor corrigido, nunca Product Stage pago e nunca um release.

O `candidate-repin` da Factory executará a RPC com script determinístico após **merge humano da PR e autorização/aplicação separada dessa nova migration**; sem a migration emitirá `blocked_migration_not_applied` e não mexerá no histórico. CI Python e PostgreSQL descartável comprovam ACL, mismatch, execução concorrente, recuperação uma vez e estados exatos. Um wake autêntico posterior processará Direct com as reservas normais, não roda modelo no script de recuperação. Nenhum sucesso de Preview/Service Desk é inferido disso.
