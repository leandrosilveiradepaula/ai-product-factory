# Bloco 1: ensaio executável de rollback de código (não produtivo)

Critério parcial: `documentation/release_rollback`. O contrato de finalização exige
reproduzir uma reversão e verificar o gate de release, não apenas citar um runbook.

O workflow `.github/workflows/block1-offline-revert-evidence.yml` cria uma cópia
temporária de repositório Git **sem remote**. Executa baseline commit, alteração
reversível, `git revert --no-edit`, compara o Git tree final e os bytes originais,
garante worktree limpa, três commits distintos e testa `evaluate_release(PROD)`
contra bypass de aprovação humana. Regressões negativas incluem política de
produção insegura, comando Git falho e tentativa de injetar diretório externo.

O recibo `factory-block1-isolated-git-revert-v1` retém somente digests da árvore,
estados booleanos, três commits e ausência de remote; não contém secrets nem
identidade de usuário. `block1_certified=false`, `production_writes=0`,
`production_rollback_executed=false` e `schema_rollback_executed=false`.

**Limites:** um revert isolado prova a mecânica do Git e a política determinística,
não executa rollback do Console, CRM, Supabase ou database migrations. Não é
critério integral certificado; a reconciliação com incidente/QA/capacidade de
rollback reais continua pendente. Não ativa modelo, não cria Start nem auto-merge.

A CI `validate/test` também executa os testes negativos. Depois de merge humano,
confirmar `validate` em `main` e o certificado real no Supabase: `product_ready`
permanece `false` enquanto qualquer domínio requerido estiver incompleto.
