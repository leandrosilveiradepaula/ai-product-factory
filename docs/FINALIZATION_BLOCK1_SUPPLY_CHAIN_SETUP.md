# Bloco 1 — rodada 2: cadeia de dependências e setup reproduzível

Data: 05/11/2026. Continuação da PR #1240, mergeada humanamente em `3def0a7e6db3bc18bc460fd201a761da56a9aefb`. O CI push #42058690431 passou; a certificação independente permanece vinculada ao Control Plane, não a um relatório de código.

## Provas executáveis nesta rodada

- `python scripts/audit_block1_supply_chain.py`: compara dependências diretas do `apps/console/package.json` com o lockfile npm v3; exige versões exatas quando especificadas; varre `.github/workflows/*.yml|yaml` por ações não fixadas em SHA de 40 dígitos e por atribuições literais de credenciais de alto risco. O relatório **não imprime valores de segredo**.
- `python scripts/exercise_block1_setup.py`: executa os dois comandos CLI do README no checkout atual em subprocessos com `PATH`, `PYTHONPATH` e `PYTHONDONTWRITEBYTECODE` somente. Não herda variáveis de provedor, tokens, credenciais ou outros segredos; timeout 30s; saída resumida sem stdout de potencial dado sensível.
- `tests/test_block1_supply_chain.py` e `tests/test_block1_setup_exercise.py`: regressões negativas para drift de lockfile, action sem SHA, segredo literal, symlink, README divergente e ambiente sem credenciais.
- `validate/test` exige execução dos dois preflights e da suíte completa antes de `factory-acceptance`.

## O que **não** fica certificado por isso

A auditoria de fonte **não** equivale a scanner de CVEs npm/Python, varredura independente de segredos em histórico Git, teste de autenticação real ou prova de ausência de exposição de credenciais no navegador. O setup isolado comprova apenas os dois comandos locais do README, não instalação de produção, operador real, incidentes nem rollback produtivo.

Para `security/secrets_dependencies`, obter artefatos reais do scanner de segredos/dependências no SHA exato e revisão de tokens no browser. Para `documentation/setup_configuration`, vincular resultado do CI a um verificador independente confiável; para `documentation/operations` e `release_rollback`, executar preflight e recuperação isolados, com recibos.

**Gates preservados:** sem migration, alteração RLS, novo serviço pago, token, merge automático, rollback de produção ou Start fictício. Nenhum PASS é concedido por mera presença de arquivo.
