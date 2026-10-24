# Escopos exatos em novos diretórios de repositórios existentes

Incidente real, 24/10/2026: [CRM issue #194](https://github.com/leandrosilveiradepaula/crm-infodive/issues/194) iniciou nova run legítima da Factory `7a4a88ac-2ad2-42bc-bc6b-5135035b0d84`, criou backlog `b1c393f5-5272-49d8-9a9d-c9e3c1d5a092` e roteou Direct `bd5a2e8d-413e-442b-8f23-6ef3016ea39e`. O planner preservou os cinco caminhos autorizados; porém o resolvedor `_bounded_file_scope` só reconhecia arquivos novos quando o **diretório pai imediato** já possuía um arquivo. Em uma rota Next.js nova `src/app/(dashboard)/service-desk/page.tsx` e novo pacote `src/lib/service-desk/...`, o diretório imediato não existe antes do trabalho. O código os classificava como escopos semânticos e os substituía por caminhos antigos encontrados na árvore (inclusive código Gemini alheio), criando `repository.write_scopes` incorreto. O executor recusou as escritas, mas essa recusa ocorreu tarde demais.

## Contrato da correção

- Um arquivo literalmente nomeado e autorizado em `scope_keys` de Work Unit pode ser criado dentro de **um** novo diretório de código se seu ancestral imediato já tem arquivos verificáveis no **SHA base fixado**.
- Nunca ampliar esse caminho para `src/**`, `tests/**`, `.`, prefixo de diretório ou arquivo vizinho. Os scopes finais do pacote continuam **nomes exatos** e o commit continua validado por `enforce_write_scopes`.
- Uma localização com dois ou mais níveis de diretório novos, um caminho secreto/oculto, migração não autorizada, travessia ou arquivo com formato não permitido continua bloqueada. Uma entrada que *parece arquivo concreto* mas não consegue ser verificada **nunca vira fallback semântico** para arquivo não relacionado. A falha ocorre antes da chamada do modelo.
- Sem alterações de banco, migrações, Vercel, Console, serviço pago ou código CRM; apenas Python Factory, regressão determinística e este registro.

## Validações

Executar `python -m unittest tests.test_existing_new_directory_scopes -v`, a suíte `validate` e testes de aceitação normais da Factory. Nenhum modelo pago para testar o fix. Após merge humano de PR da Factory, não reabrir a run Direct bloqueada silenciosamente nem reexecutar Product Stage. Verificar se há RPC de recuperação *estritamente original SHA/epoch/scope* apropriada; se não existir, registrar dependência e criar recuperação durável separada. Integração final do Service Desk na `main` do CRM segue gate humano.
