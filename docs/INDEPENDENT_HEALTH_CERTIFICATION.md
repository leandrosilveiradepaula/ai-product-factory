# Certificacao independente de saude operacional

Escopo: somente observability_operations/health. Fontes GitHub, Console HTTPS e Control Plane; sem Vercel token, mudanca de permissao, modelos pagos, migration ou release.

O runtime OIDC da Factory nao tem uma credencial Vercel. Em vez de inventar uma fonte Vercel READY, este verificador exige o status GitHub correspondente a um deployment realmente concluido no SHA observado pelo proprio endpoint /api/health do Console, com descricao "Deployment has completed", contexto Vercel e destino de deployment do projeto correto. Nao aceita "Canceled by Ignored Build Step" (comum nos commits sem mudanca em Console). Consulta a comparacao GitHub do deployment com main, prova ancestralidade e ausencia de alteracoes em apps/console/**. Isso nao equivale a um recibo da API Vercel READY, nem certifica UX ou login.

A auditoria exige tambem dois eventos schedule_probe.observed mais recentes, ator system/schedule-probe, diagnosticos de RPC autoritativo, intervalo >=10min e ultimo registro <=25min; nao permite selecionar um evento antigo ignorando o mais recente invalido. Projetos ativos e respectivos controles sao verificados por GET no Control Plane; Factory precisa estar running. Controles stopped permanecem validos e nao sao reativados.

O job product-readiness-certification-post-ci com OIDC faz a coleta apos validate push main no SHA exato e repete a checagem LIVE imediatamente antes de begin/persist. Se nao existir fonte, health continua missing; se a fonte se perde entre coleta e escrita, falha antes de persistir prova positiva. Health nao recebe PASS pelo sucesso da CI isoladamente. Traceability e independente.

A prova nao cobre recovery_alerting, authn_authz, critical_e2e, greenfield, release humano, a11y ou rollback. product_ready permanece false ate as 19 verificacoes. Alteracoes apenas em Python, workflow, testes e docs; Preview Console N/A por politica apps/console/**.

Depois do merge humano, confirmar status do job e o campo report.criteria.observability_operations.health.status realmente persistido no Supabase no SHA atual. Nao declarar 3/19 sem essa prova duravel. Referencias: docs/FINALIZATION_EXECUTION_CONTRACT.md e issue #713.
