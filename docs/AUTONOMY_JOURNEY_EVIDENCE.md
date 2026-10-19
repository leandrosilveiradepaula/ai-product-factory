# Prova operacional de autonomia: jornada nova, somente leitura

Data de introducao: 19/10/2026. Produto principal: AI Product Factory.
CRM e outros repositorios sao somente projetos piloto, nunca o foco do produto.

## Problema real que esta entrega resolve

Um teste verde da propria Factory nao prova que um trabalho novo atravessou
Idea -> Discovery -> Spec -> Planning -> Work Units -> PR -> CI -> Review ->
Preview -> Gate humano -> Release observado -> Operacao.

A limpeza auditada de registros historicos e a PR #983 retiraram duas
fontes de falso progresso: backlog obsoleto e CI parcialmente concluida.
Faltava um mecanismo que acompanhasse uma unica jornada NOVA, nao um
inventario de eventos acumulados de projetos antigos.

## Cinco blocos funcionais

1. Start humano e linhagem. Exige factory_project_execution_commands
   command=start com result.run_id exato, actor_id, created_at apos cutoff
   e projeto/repository validos. O cadastro draft nao implica inicio.
2. Execucao verificavel. Relaciona Product Stage de discovery, specification
   e planning ao run, Change Set e Work Unit ao root task, run de
   implementacao e output_commit que o GitHub confirme como SHA existente.
3. CI e Preview exatos. Receipts create_pr e candidate_commit devem
   apontar ao mesmo PR e SHA observados no GitHub, inclusive repo/head/base.
   Workflow CI completo e obrigatorio. Preview N/A exige evento duravel
   release.preview_not_required para SHA e PR; Preview requerido exige
   deployment, browser evidence e recibos da mesma linhagem. A lista
   de arquivos da PR e paginada sem assumir que 100 itens sao o total,
   incluindo previous_filename de arquivos renomeados.
4. Gate humano e release. awaiting_release so tem prova por run e evento
   release.awaiting_human_merge exatos. Human release so conta quando
   PR merged no GitHub, merge_sha verificado no audit e relatorio released.
   Operacao precisa de evidencia adicional. Nem release autoriza declarar
   product_ready do produto inteiro.
5. Prova repetivel e isolada. CLI somente leitura, workflow disparado
   MANUALMENTE com OIDC e JSON sanitizado como artifact por workflow run.
   Testes negativos para ausencia de Start, run de outro projeto, falha
   de etapa inicial, commit inexistente, alteracao de SHA/PR, Preview
   nao verificado, merge adiantado e inventario truncado.

## Como executar apenas DEPOIS de um Start explicito

1. Cadastrar projeto de teste no Console como draft, verificando que
   nao existe autostart.
2. Clicar em Iniciar (acao humana), anotar project_key, data UTC e
   opcionalmente o bootstrap run UUID.
3. Executar manualmente em GitHub Actions:
   Fresh Factory autonomy journey evidence (read-only).
   Informar project_key, since_utc, opcional run_id, e require_at_least,
   por exemplo awaiting_release.
4. Ler o JSON do run e o artifact de sete dias. Um gate sem evidencia
   causa falha do teste, mas nao dispara nenhum worker ou chamada paga.

Com ambiente operacional autenticado, somente leitura:

    PYTHONPATH=src python scripts/audit_autonomy_journey.py \
      --project-key meu-projeto \
      --since-utc 2026-10-19T20:00:00Z \
      --require-at-least awaiting_release

O arquivo nao deve conter prompts, payloads crus, tokens, credenciais ou
dados de negocio. Cross-repo segue a GitHub App oficial ou credencial
cross-repo explicita. GITHUB_TOKEN nativo nao tem alcance cross-repo.

## Estados do relatorio

- not_started: nenhum Start operador observado apos cutoff.
- in_progress: o Start e valido, mas a proxima prova nao chegou.
- blocked: erro terminal, SHA/PR inconsistente ou evidencia indisponivel.
- awaiting_human_merge: producao depende de merge humano.
- observed_complete: release e operacao observados, nao product_ready.

A trilha e sequencial: uma etapa futura verde nunca preenche uma anterior
ausente. Dados/identidade malformados ou inventario parcial falham fechados.
Nao apagar registros historicos para tentar ganhar aprovacao.

## Limite honesto de conclusao

Esta implementacao e seus testes deterministas provam o comportamento do
AVALIADOR e o mecanismo de consulta. Nao provam o E2E real da Factory ate
que exista um trabalho novo iniciado manualmente e executado de fato.
Nao gerar chamadas pagas somente para simular sucesso nem reabrir itens
ja aposentados do CRM ou da Factory.
