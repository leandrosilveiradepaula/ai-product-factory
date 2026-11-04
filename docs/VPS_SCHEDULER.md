# VPS Linux como agendador de wake da AI Product Factory

Padrão reutilizado de `crypto-intelligence-agent` OPS23: `systemd` timer + serviço
`oneshot` + script Python mínimo. **Somente disparo**: Python/CI da Factory
continua no GitHub Actions, e a fonte de verdade durável permanece no Supabase.

## Contrato

- O timer pode disparar a cada 15 minutos, sem SLA de conclusão e sem retries no
  mesmo serviço (`Restart=no`, `Persistent=false`).
- O script chama somente
  `POST /repos/leandrosilveiradepaula/ai-product-factory/actions/workflows/autonomous-runner.yml/dispatches`
  com `{"ref":"main","inputs":{"vps_wake":"true"}}`.
- O workflow existente mantém `schedule-probe`, autorização OIDC do
  Control Plane, CAS e limites de custos, integração, CI, Preview e gate humano.
- A entrada `vps_wake=true` permite o job `candidate-repin` e a recuperação
  determinística já versionada da jornada CRM #209, sem mudar
  `FACTORY_PRIMARY_MODEL_ENABLED` nem invocar o executor pago.
- Não criar Start, task, execução SQL financeira, PR/merge nem publicar release
  diretamente da VPS. A VPS não recebe segredos do Supabase ou da OpenAI.
- O GitHub Actions `schedule` permanece como **redundância** até comprovar
  a operação de `systemd` no servidor e recibos vinculados à jornada.

## Implantação (somente mediante autorização de alteração da VPS)

No servidor correto, com usuário administrador, instalar/revisar os arquivos
`deploy/systemd/ai-product-factory-vps-wake.service` e
`deploy/systemd/ai-product-factory-vps-wake.timer`.
Os caminhos fixados no serviço são:
`/opt/ai-product-factory` (checkout somente-leitura),
`/usr/bin/python3`, usuário `factory-wake` sem root,
`/etc/ai-product-factory/vps-wake.env` (somente leitura do usuário do serviço).

1. Criar usuário sem shell interativo e diretórios de modo privado,
   sem interferir no Crypto Intelligence Agent ou em outros serviços.
2. Configurar `FACTORY_VPS_GITHUB_TOKEN` em `vps-wake.env`, fora do
   repositório, sem passar tokens por argumentos, URLs, logs ou commits.
   O token deve ter **Actions: write somente neste repositório**.
   Preferir token de instalação GitHub App de curta validade quando
   houver mecanismo existente para renová-lo; caso contrário, token de
   granularidade mínima, com rotação. Não reutilizar `FACTORY_GITHUB_TOKEN`
   que concede escrita cross-repo no CRM.
3. Garantir checkout de `main` no commit correto e o script
   `scripts/dispatch_factory_vps_wake.py`. Não fazer auto-pull do
   checkout pelo timer; atualização de versão é operação controlada.
4. Instalar as duas unidades em `/etc/systemd/system`; verificar com
   `systemd-analyze verify` e
   `systemd-analyze calendar '*-*-* *:00/15:00 UTC'`.
5. `systemctl daemon-reload`; iniciar **apenas** o timer com
   `systemctl enable --now ai-product-factory-vps-wake.timer`.
   Conferir `systemctl list-timers`,
   `systemctl status ai-product-factory-vps-wake.timer` e
   `journalctl -u ai-product-factory-vps-wake.service`.
6. Verificar resposta local `accepted`, localizar no GitHub o
   `workflow_dispatch` da Factory no SHA `main`, conferir
   `candidate-repin` executado, o recibo OIDC, o estado no Supabase,
   o CI nativo CRM e a ausência de chamadas pagas.
7. Só após a prova operacional, tornar a VPS o agendador primário e
   avaliar remover o cron do GitHub em PR separado, mantendo backup
   de outro tipo. Até lá os disparos duplicados são contidos pela
   concorrência GitHub e pelos CAS do Control Plane.

### Diagnósticos fail-closed

`permission_denied`: token inválido/sem `Actions: write`.
`workflow_not_found`: workflow não habilitado ou caminho errado.
`workflow_input_rejected`: versão do workflow incompatível.
`transport_error`/`transient_error`: falha de rede/provedor; não presumir
sucesso nem repetir o POST no mesmo lançamento.
`accepted`: GitHub aceitou **enfileirar**, não prova que o workflow
concluiu ou que o CRM foi reparado. Inspecionar a execução, SHA, jobs e
estado durável do banco.

### Reversão

`systemctl disable --now ai-product-factory-vps-wake.timer`. Essa ação
desativa somente os próximos disparos da VPS; jobs já aceitos pelo
GitHub seguem sujeitos aos gates de execução e devem ser verificados.
Manter os cron nativos enquanto não houver evidência operacional da VPS.
