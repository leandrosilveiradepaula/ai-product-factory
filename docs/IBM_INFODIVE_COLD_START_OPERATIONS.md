# SQL-InfoDive - aquecimento de modelo na IBM (20/11/2026)

A Factory usa a LLM geral SQL-InfoDive diretamente da VPS pelo WireGuard
wg-ibm. Nao usa n8n/LangGraph na execucao.

Evidencia real: autenticacao IBM e /api/models HTTP 200; a primeira
inferencia apos o servidor IBM ter sido ligado excedeu 180 segundos.
Uma nova chamada com timeout HTTP removido respondeu em 3,0 segundos
com conteudo OK e usage de 1532 tokens de entrada/2 de saida.
O carregamento a frio e explicacao plausivel, nao causa comprovada.

O Product Stage tem um guard de cold-start ANTES de qualquer claim:
- Consulta read-only apenas runs existentes com status created ou queued e tarefa queued.
- Sem tarefas: sai imediatamente, sem usar a credencial IBM ou tokens.
- Com tarefas: valida provider, modelo, rota privada, Control Plane,
  budget e taxas aprovadas exatamente zero.
- Usa uma chamada curta com HTTP sem timeout de socket e watchdog
  externo de no maximo 1800 s (configuravel 60 a 3600 s).
- Exige resposta, usage e recibo duravel sanitizado antes de permitir
  que o worker reivindique tarefas e execute o pipeline existente.
- Se falhar, bloqueia o processamento; nunca cria Start, PR, merge,
  creditos, benchmark SQL ou permissao de release.

Operacao: incluir a segunda linha ExecStartPre do template Product Stage
apos realizar merge humano da PR, publicar SHA principal exato e aplicar
systemctl daemon-reload. O timer ja instalado permanece separado.

Receipts locais: /var/lib/ai-product-factory/ibm-warmup-latest.json,
permissao 0600. Nao gravar chaves nem resposta do modelo.

Direct permanece desabilitado ate existirem token GitHub cross-repo
especifico, model_policy.provider=infodive_ibm_cloud e gates validos.
