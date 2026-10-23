# J5 — Especialistas somente com prova do candidato atual

Este runbook trata somente das lanes determinísticas de Security, QA e Operations, entre CI nativa verde e avaliação de Preview. **Não é certificação E2E externa da Factory**.

## Diagnóstico e cinco blocos de proteção

1. **Identidade durável da branch.** O claim de especialista consulta factory_runs.branch_name da mesma run que carrega a prova de create_pr/candidate. Sem branch não produtiva válida, a análise falha fechada antes de ler a PR. Não inferir a branch a partir de dados do GitHub.
2. **Admissão estrita da PR.** Antes da inspeção, exigir número, repository de origem, branch e SHA idênticos ao item persistido; PR aberta, não-draft e não mergeada, com base e SHA-base informados. Forks e snapshots incompletos não fornecem evidência de revisão.
3. **Rechecagem após a inspeção.** Depois de ler arquivos, checks e/ou saúde operacional, consultar novamente identidade completa da PR e SHA real do ref de origem. Branch/PR/base movidos entre leituras resultam em blocked, nunca passed/failed sobre commit diferente. Não executar API paga nem alterar a PR.
4. **Cobertura real de segurança.** Patches GitHub ausentes, vazios, binários ou não inspecionáveis geram unreviewable_diff crítico e saída blocked. Uma PR sem arquivos gera empty_diff_inventory; inventário com mais de 3.000 registros falha. O scanner registra unreviewable_paths, diff_content_available=false e não declara cobertura de segredos, SQL ou workflows quando bytes estão indisponíveis. Não transformar ausência de evidência em falso Security PASS nem em reparo inventado de código.
5. **Regressão e escopo.** Testes offline exercitam origem falsa/fork, draft, PR fechada/mergeada, SHA de branch movido, retarget da base, drift durante todas as lanes, CI efetivamente verde, custo desconhecido e diff ausente. Teste de claim confirma binding do branch_name. Nenhum recurso Supabase/Vercel ou modelo pago é necessário.

## Limites da comprovação

A dupla leitura e o ref reduzem TOCTOU, mas o GitHub não fornece transação atômica entre GET da PR e escrita posterior no Control Plane. Completion segue protegida por lease/claim token e geração do projeto; Preview e release têm seus próprios gates de SHA. Avaliação do especialista, isoladamente, não permite merge automático nem equivale a product_ready.

Um arquivo binário legítimo pode exigir outro mecanismo de verificação ou revisão separada. A ausência do patch nunca é suprida silenciosamente. Sem evidência verificável, a lane permanece bloqueada.

## Evidências operacionais necessárias

Registrar por especialista: project/run/job/PR, role, SHA candidato, branch e base, resultado passed/failed/blocked, findings estruturados, recibo atômico de traceability e recheck. Um passed precisa de PR e ref finais consistentes. Não reutilizar evidências de outra run, tentativa ou SHA.

Preview continua obrigatório por padrão, salvo política N/A explícita com recibo durável. A Factory aguarda merge de produção pelo operador; runtime e GitHub adapter permanecem sem auto-merge.

**Gate:** esta mudança de código requer CI/acceptance verdes e merge humano ao publicar main em produção. Nenhuma migration, pagamento, alteração de piloto ou Preview da Console é introduzido.
