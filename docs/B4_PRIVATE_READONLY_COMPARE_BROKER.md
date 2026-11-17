# B4 — Comparação privada e imutável via GitHub App (sem entregar token ao certificador)

## Diagnóstico factual — 17/11/2026

A jornada original `dark-channel-studio` já concluiu merge humano, release observado, Change Set `completed` e operação persistida. A certificação independente no SHA Factory `705e517d599d4815a0aa7c506a25584570441b22` executou 17/19 em `workflow_run` [#44179881759](https://github.com/leandrosilveiradepaula/ai-product-factory/actions/runs/44179881759), faltando somente `test_strategy/critical_e2e` e `functional_completeness/critical_journeys`. O recibo exato revela `b4_cross_repo_read_unavailable`. A guarda monotônica impediu regressão e manteve o certificado persistido 18/19.

A origem não é falta de RLS, CI, Preview ou release. O projeto Studio está autorizado no registro `factory_project_github_access` em `auth_mode=github_app`, `status=ready`, instalação e repo id presentes. Entretanto, o certifier `workflow_run` não pode solicitar um GitHub App token ao broker: **essa proibição é intencional**. O fallback `FACTORY_GITHUB_TOKEN` não forneceu uma comparação válida naquele evento, e não deve ser forçado a acessar repositórios privados de clientes.

## Solução permanente — genérica para qualquer greenfield

Uma nova rota de leitura no broker Supabase já existente, `POST /github-app/read-only-compare`, executa somente uma comparação GitHub com a GitHub App **dentro do servidor**. Entrada obrigatória: `{repository,predecessor,current}`, onde os dois SHAs são exatos de 40 hex. Ela aceita exclusivamente identidade OIDC assinada da Factory em `main`, no workflow autorizado `autonomous-runner.yml`, evento `workflow_run` e `run_attempt=1`.

Antes de consultar o GitHub, o broker comprova no Control Plane:

- um projeto greenfield ativo em `operations`, de repositório exatamente igual ao pedido;
- um único Change Set concluído, cujo commit candidato é `current`;
- um release do mesmo run observado como `observed_manual_merge`, com SHA de merge válido;
- um snapshot independente de navegador `browser_verified`, com `candidate_commit=predecessor`, `run_id IS NULL`, identidades e limites fail-closed;
- uma instalação GitHub App ativa, `ready`, id do repositório e id da instalação revalidados na própria GitHub API.

Somente então pede ao GitHub **um installation token temporário com `contents:read`**, restrito ao repo solicitado. A rota não retorna, grava ou registra esse token. Executa GET de comparação, valida ahead/behind, total de commits, máximo de 25 commits, até 50 arquivos, nomes seguros e status allowlisted, e retorna apenas `status`, contagens e nomes/status dos arquivos, sem patches, textos, URL de origem ou credenciais.

O certifier `workflow_run` passa a chamar essa rota com seu próprio JWT OIDC, sem executar `resolve_github_token`, sem usar `GITHUB_TOKEN` nativo, sem tentar `FACTORY_GITHUB_TOKEN` e sem permitir fallback. O verificador Python **repete independentemente** todas as regras de linhagem de arquivos não-runtime, CI, especialistas, browser, auditoria, human merge, operações e política de release; a nova rota não emite nem transforma PASS em critério.

## Gate de ativação e rollback

**Sensível — deploy humano obrigatório:** a alteração em GitHub é apenas candidato. **Merge da PR não publica a Edge Function.** A rota acrescenta um canal de leitura privada de comparação limitado a projetos já publicados, embora não amplie permissões da instalação da App. O proprietário deve autorizar expressamente o deploy da revisão do broker Supabase em produção, após revisar CI e threat model. Não executar deploy com autorização genérica de merge.

Ordem de ativação:
1. CI de PR, testes de contrato, regressões Python e verificações negativas de endpoint, token e runtime.
2. Merge humano da PR Factory.
3. Autorização humana **específica** para deploy do broker Edge em Supabase projeto `fjplmxfcshhbmzgvyqlm`.
4. Deploy exato, inspecionar status ativo e verificar que a rota de emissão `/github-app/token` continua negando `workflow_run`; a rota de comparação deve recusar sem OIDC.
5. Nova certificação somente via **primeira tentativa `workflow_run` vinculada a um `validate push` do SHA atual** (nunca re-run do job), ou acionar o caminho oficial de certificação fresh ao próximo push humano. Não manipular Control Plane nem gravar certificado manualmente.

Rollback: redeploy Edge Function anterior sem rota `read-only-compare`; os trabalhos de certificação B4 ficarão fail-closed em `missing`, e o certificado 18/19 ficará preservado. O runtime normal da Factory, repositórios dos clientes e as tabelas de controle não sofrem mudanças. Nenhuma migration, token persistido, custo de modelo ou benchmark.

## Segurança

- Nunca autorizar `workflow_run` em `/github-app/token`.
- Não retornar token GitHub App nem PAT ao Actions, navegador ou código gerado.
- Não permitir busca de outro repositório que não esteja registrado/ativo e concluído no Control Plane.
- Os verificadores nunca inferem `product_ready` do Preview; produção continua gate humano.
