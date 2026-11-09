# Certificacao independente de saude operacional

Escopo: somente observability_operations/health. Fontes GitHub, Console HTTPS e Control Plane; sem Vercel token, mudanca de permissao, modelos pagos, migration ou release.

O runtime OIDC da Factory nao tem uma credencial Vercel. Em vez de inventar uma fonte Vercel READY, este verificador exige o status GitHub correspondente a um deployment realmente concluido no SHA observado pelo proprio endpoint /api/health do Console, com descricao "Deployment has completed", contexto Vercel e destino de deployment do projeto correto. Nao aceita "Canceled by Ignored Build Step" (comum nos commits sem mudanca em Console). Consulta a comparacao GitHub do deployment com main, prova ancestralidade e ausencia de alteracoes em apps/console/**. Isso nao equivale a um recibo da API Vercel READY, nem certifica UX ou login.

A auditoria exige tambem eventos schedule_probe.observed recentes, ator system/schedule-probe e diagnosticos de RPC autoritativo. O ultimo registro deve ter <=25min. Para provar cadencia, o verificador exige duas observacoes validas separadas por >=10min; quando um dispatch extra produz um evento intermediario valido, ele e validado e o verificador pode utilizar a primeira observacao anterior com distancia suficiente (dentro da janela de 50min). Nunca ignora eventos mais recentes ou intermediarios invalidos para buscar um PASS antigo. Projetos ativos e respectivos controles sao verificados por GET no Control Plane; Factory precisa estar running. Controles stopped permanecem validos e nao sao reativados.

O job product-readiness-certification-post-ci com OIDC faz a coleta apos validate push main no SHA exato e repete a checagem LIVE imediatamente antes de begin/persist. Se nao existir fonte, health continua missing; se a fonte se perde entre coleta e escrita, falha antes de persistir prova positiva. Health nao recebe PASS pelo sucesso da CI isoladamente. Traceability e independente.

A prova nao cobre recovery_alerting, authn_authz, critical_e2e, greenfield, release humano, a11y ou rollback. product_ready permanece false ate as 19 verificacoes. Alteracoes apenas em Python, workflow, testes e docs; Preview Console N/A por politica apps/console/**.

Depois do merge humano, confirmar status do job e o campo report.criteria.observability_operations.health.status realmente persistido no Supabase no SHA atual. Nao declarar 3/19 sem essa prova duravel. Referencias: docs/FINALIZATION_EXECUTION_CONTRACT.md e issue #713.

## Correcao operacional da verificacao pos-merge #1311 (09/11/2026)

O run `42638060796` no SHA `ae7d8531b88acff0fff083dea0fec67cf2ae45d7`
coletou um baseline independente (8 passed, 3 partial, 8 missing):
`regression_gates=passed` e tres observacoes visuais parciais provenientes
da captura criptografada #42439592059, sem promover UX, RBAC ou release.
A etapa de persistencia foi cancelada pelo teto anterior de 8 minutos;
**nao existe certificado duravel desse SHA**. O ultimo registro de
certificacao deve continuar sendo tratado como historico, nao como prova
atual.

Na janela da coleta, os probes autenticos ocorreram em 14:45:58 UTC,
14:36:13 UTC e 14:15:52 UTC. O intervalo entre os dois mais novos foi
menor que 10 minutos, apesar do terceiro evento ainda comprovar a janela
e a origem da execucao. A nova selecao valida todos os eventos intermediarios
antes de escolher o par distanciado, sempre fail-closed para ator invalido,
relay, contador inconsistente, data futura ou antiga. O manifest agora
conserva o codigo de bloqueio sanitizado para o criterio `health`.

O timeout do certifier foi ampliado somente no job post-CI de main que tem
trabalho real, pois a dupla verificacao independente envolve consultas GitHub,
Console live e Control Plane. Nenhum custo de modelo, migration, Start, captura
privilegiada, deploy Vercel ou merge automatico foi introduzido. Depois do
merge humano, a unica prova de sucesso e um novo certificado persistido e
SHA-exato no Control Plane. A CI verde da PR nao certifica o produto.
