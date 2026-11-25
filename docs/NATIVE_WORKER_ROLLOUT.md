# Implantação controlada do worker nativo (VPS)
 
## Incidente e objetivo

O worker nativo de produto/Direct está em checkout root-owned, com SHA fixado em
`/etc/ai-product-factory/infodive.env`. O conector administrativo só consegue ler
esse diretório. Após #1601, main está em `030242886371e11591acaf34d13706a60e78075a`; o worker permanece
em `4d5efbe946055a633d7ae26487ec5fb7f0d06f11`. As correções no GitHub não chegam
ao processo que executa o modelo privado até sincronização local.

Este controlador substitui a repetição manual do procedimento, não o gate humano.
A credencial existente `FACTORY_VPS_GITHUB_TOKEN` já retornou HTTP 200 para
main, PR #1601, associação commit/PR, execução 45687281333 e seus jobs. Não há
necessidade identificada de nova chave ou aumento de escopo. O controller usa
somente GET, nunca o endpoint de dispatch/merge. O checkout usa a credencial
Git já provisionada, separada do token de wake.

## Contrato de execução

- Instalar uma cópia **fixa, revisada e root-owned** do controller fora do checkout.
  Não executar código atualizado da main como root a cada ciclo. Uma mudança no
  controller exige revisão e instalação administrativa própria.
- Verificar main exata, PR associada efetivamente mergeada pelo OWNER
  (ID 256917842), último push CI do workflow validate (ID 367143797), tentativa
  exata e ambos os jobs test/factory-acceptance. Falhar fechado se faltar prova,
  ocorrer rerun pendente, mudança concorrente ou resposta ambígua.
- Exigir fast-forward, checkout limpo, origem HTTPS oficial, SHA da configuração
  igual ao checkout. Alteração em dependências, filtros Git ou unidades
  instaladas exige atualização administrativa específica.
- Não interromper worker ativo. Suspender apenas os timers existentes, verificar
  novamente o estado, atualizar checkout e pin, restaurar os timers originalmente
  ativos. Journal root-only com SHAs (sem credenciais) permite recuperação após
  interrupção. O worker continua exigindo o próprio preflight e o epoch.
- Sem auto-merge, alteração de RLS, migrations, chamada de modelo, atualização
  de credenciais, ativação de jornada ou declaração de certificação.
- Esta operação só instala uma revisão previamente aprovada pelo merge humano.
  Não concede acesso de escrita ao MCP nem modifica a infraestrutura financeira.

## Ativação única (gate administrativo real)

Após merge humano desta PR e CI pós-merge aprovada, um administrador instala
os três arquivos exatos do SHA aprovado, com proprietário root e permissões
indicadas. Usar o checkout root-owned existente, fazer fetch do main e verificar
SHA e integridade da árvore antes de copiar. Não copiar segredos ou gerar token.

```bash
# Neste ponto, TARGET deve ser o merge SHA explicitamente aprovado deste rollout.
cd /opt/ai-product-factory/worker
git fetch --no-tags origin main
test "$(git rev-parse FETCH_HEAD)" = "$TARGET"
install -d -o root -g root -m 0700 /var/lib/ai-product-factory-rollout
install -d -o root -g root -m 0755 /usr/local/libexec
git show "$TARGET:scripts/factory_native_worker_rollout.py" > /usr/local/libexec/ai-product-factory-worker-rollout.py
chown root:root /usr/local/libexec/ai-product-factory-worker-rollout.py
chmod 0700 /usr/local/libexec/ai-product-factory-worker-rollout.py
for unit in service timer; do
  git show "$TARGET:docs/systemd/ai-product-factory-worker-rollout.$unit.template" > "/etc/systemd/system/ai-product-factory-worker-rollout.$unit"
  chown root:root "/etc/systemd/system/ai-product-factory-worker-rollout.$unit"
  chmod 0644 "/etc/systemd/system/ai-product-factory-worker-rollout.$unit"
done
systemctl daemon-reload
systemctl enable --now ai-product-factory-worker-rollout.timer
systemctl start ai-product-factory-worker-rollout.service
```

A instalação precisa de root apenas uma vez e da autorização específica para
o serviço root fixo. Depois, o timer consulta o GitHub e instala somente main
já autorizada e aprovada. Recibo em journal contém apenas SHAs, PR e CI.
Se o serviço estiver ocupado, a atualização é adiada; não matar o processo.
Em caso de erro, preservar a versão anterior ou bloquear se a identidade
não puder ser comprovada. Para desativar a automação:
`systemctl disable --now ai-product-factory-worker-rollout.timer`.
A retomada da jornada Dark Channel segue separada: confirmar o worker atualizado
e então aplicar o script de recuperação aprovado #1601, preservando o ledger
no Supabase. Não considerar rollout isolado como produto concluído.

**Estado:** candidato inerte no GitHub; nenhuma instalação root realizada por
este documento.
