# Bloco 1 — dupla varredura de segredos por histórico e árvore exata

Data: 06/11/2026. Escopo: `security/secrets_dependencies` e somente verificação de segredos.

## Lacuna operacional removida

A execução prévia do `gitleaks/gitleaks-action` verificava histórico/diff de PR, mas a saída positiva não certificava que todos os arquivos *atuais*, incluindo arquivos introduzidos por merges intermediários, haviam sido examinados. Uma saída verde dessa primeira etapa não pode se tornar `security/secrets_dependencies=passed`.

A segunda etapa do mesmo job verifica o HEAD exato do PR e seu objeto Git tree, produz um `git archive` de somente arquivos rastreados em diretório efêmero, rejeita tar path traversal, link simbólico, entrada duplicada e tamanhos fora do limite. O scanner Gitleaks v8.24.3 da action pinada executa `dir` contra o snapshot, com configuração padrão independente do repositório, `--ignore-gitleaks-allow` e caminho de ignore externo vazio. Não usa baseline de isenção, tokens de acesso, serviços pagos ou banco.

O scanner gera recibo de apenas SHA, Git tree OID, quantidade de arquivos, versão e resultados booleanos. Nunca publica logs do scanner, valores suspeitos ou relatório detalhado. O scanner retorna achados de oito fixtures pré-existentes já examinadas: um literal PEM de normalização, seis UUIDs sintéticos e um token deliberadamente inválido usado em testes negativos. A aceitação é restrita à correspondência EXATA de oito tuplas (caminho, linha, rule ID, blob Git SHA1). Cada arquivo continua sendo varrido: não existe exclusão por caminho, rule ID genérico ou baseline de achados. Qualquer novo achado, remoção/inserção de fixture, mudança de linha, mudança do blob ou alteração da regra bloqueia a etapa. O recibo registra `raw_finding_count=8`, `zero_unreviewed_findings=true`, `scan_without_findings=false`, `secrets_dependencies_certified=false`. Isso não é uma varredura sem alertas e nunca deve ser narrado dessa forma.

Resultado não-zero fora do conjunto exato revisado, falha de configuração, scanner ausente, árvore incompleta, tar perigoso ou mudança de identidade bloqueiam a etapa. O recibo sanitizado é conservado mesmo na falha; a ausência de artefato não é um PASS.

## Condições de certificação

Esta é uma **prova adicional** à varredura de histórico, não uma certificação da segurança inteira. Ela não prova segurança de Auth/RBAC/tenant, ausência de vazamentos em commits históricos já removidos nem gestão e revogação de credenciais; tampouco prova de dependências CVE, que têm scanner separado. O recibo define explicitamente `secrets_dependencies_certified=false` e `block1_certified=false` mesmo após sucesso.

Revisão e merge de produção permanecem humanos; nenhuma mudança de `apps/console/**`, Preview Console N/A, sem migrations nem alterações do projeto piloto. Após merge, comparar o SHA do workflow e da certificação durável, sem promover PASS a partir de um simples check verde.
