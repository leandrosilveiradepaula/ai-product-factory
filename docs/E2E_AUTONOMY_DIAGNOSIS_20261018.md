# Autonomia ponta a ponta — diagnóstico em 18/10/2026

## Evidências de execução

- Factory main 7825dbb685498c1adb1467cd12c7abdcccfd420b teve validate #39091118975 verde. CI da Factory não comprova entrega de produto.
- Intake real pelo Console: https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38796434797 . Product Stage retornou claimed=true, status=completed; o probe seguinte naquela execução retornou dispatch_work=false e as etapas seguintes foram ignoradas. **Esse skip específico era correto para a fila vazia.**
- Causa-raiz estrutural verificada no YAML: se o Product Stage emitir dispatch_work=true em repository_dispatch ou em backup workflow_run autorizado, dispatch, direct, codex, codex-manual e preview não reconheciam esses eventos. Continuação elegível esperava outro cron. Preflight Codex também ignorava dispatch_work do Product Stage concluído na mesma execução.
- Greenfield Service Desk gerou trabalho real: 13 work units integradas em oito ondas, commits e https://github.com/leandrosilveiradepaula/infodive-service-desk/pull/7 . A PR foi mergeada por pessoa antes de CI/QA/Preview, e o Control Plane bloqueou corretamente run 605212cf-b47e-418a-b4c4-79ad1efc6f59 e Change Set effc36be-212c-42f2-928b-97381b6d8a28. Nenhum release validado foi observado.
- QA externo https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/38895967648 falhou antes de checkout por ausência da credencial FACTORY_GITHUB_TOKEN naquele workflow; não substituí-la por GITHUB_TOKEN.
- Control Plane em 18/10 tem quatro projetos, zero work units executáveis, zero gates humanos pendentes; schedule_probe audit id 1075 registrou work_detected=false. Não iniciar novos modelos apenas para testar orçamento.

## Correção funcional

1. Intake segue aceitando apenas App bot, tipo de evento e origem exatos. Backup segue exigindo evento agendado, conclusão bem-sucedida, repo/branch corretos e verificação de liveness.
2. Ambos os eventos agora podem continuar automaticamente por dispatch, Direct, Codex ou Preview, **apenas** se o probe durável ou Product Stage fornecer trabalho elegível. Um product_work isolado não dispara escrita.
3. Codex recém-planejado é incluído no preflight de credencial; modo manual continua opt-in. Os gates de autenticacão, limite financeiro, Protected Environment, review e Preview existentes continuam.
4. Workflow_dispatch manual continua exigindo flags específicos. Não se introduz capacidade de merge no runtime e nem migration/deploy.

## Quatro níveis de comprovação

| Funcionalidade | Evidência | Nível |
| --- | --- | --- |
| Cadastro/Start/Pause/Resume/Stop/Restart | RPCs versionadas e PostgreSQL QA isolado | Integração; não demonstrado em ciclo novo neste diagnóstico |
| Product Stage/Direct/Change Sets | Runs, commits e PR do Service Desk | Execução real parcial |
| Correção de continuidade de intake/backup | YAML e teste contratual no CI SHA exato | Implementado e testado; execução real com fila elegível ainda pendente |
| CI/QA/Preview/release do produto | Merge precoce, credencial QA ausente, blocked auditável | Não comprovado, release negado corretamente |

**Experimento prioritário depois da correção:** registrar projeto de teste como draft, verificar que não iniciou, dar Start humano, deixar fila e trabalhadores prosseguirem, exigir uma PR com CI e Preview aplicáveis validados, efetuar merge humano só então observar release. Isso requer credenciais/provider/billing legítimos disponíveis e não autoriza chamadas pagas só para sondagem. Migration da PR #931 é gate independente, não aplicado automaticamente.
