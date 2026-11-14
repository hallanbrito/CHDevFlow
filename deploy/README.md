# Guia de Configuração e Futura Ativação Operacional

**Missão:** CH-AUTO-MULTI-01  
**Estado Atual:** `IMPLEMENTADO_NAO_ATIVADO` • `DESATIVADO POR PADRÃO`  
**Governança:** Autorização do Product Owner (Hallan de Sousa Brito) é estritamente obrigatória antes de qualquer ativação.

---

## 1. Visão Geral da Infraestrutura de Agendamento Multi-Repositório

A fase CH-AUTO-MULTI-01 implementou a arquitetura do supervisor multi-repositório com intervalo configurável de 60 minutos. Três alternativas de agendamento foram estruturadas e deixadas **estritamente desativadas**:

1. **Systemd Timer (`deploy/systemd/chdevflow-supervisor-multi.timer`)**: Recomendado para execução em servidores Linux ou no host de desenvolvimento CachyOS.
2. **Cron Job (`deploy/cron/chdevflow-supervisor-multi.cron`)**: Alternativa tradicional para distribuições sem systemd.
3. **Sidecar de Automação Antigravity (`deploy/sidecars/ch-auto-multi-01/sidecar.json`)**: Configuração para orquestração gerenciada pelo IDE.

---

## 2. Instruções de Ativação Futura (Condicionada a Novo Gate do PO)

> [!CAUTION]
> **NÃO EXECUTAR ESTES PASSOS ANTES DA AUTORIZAÇÃO FORMAL DO PRODUCT OWNER.**
> O AGY e o ChatGPT não possuem autoridade para ativar o agendamento real.

### Opção A: Ativação via Systemd (Linux / CachyOS)

Quando a operação automática for autorizada pelo PO em nova Issue:

1. Copiar as unidades para o diretório de serviços do sistema ou do usuário:
   ```bash
   # Para serviço de usuário (sem privilégios de root)
   mkdir -p ~/.config/systemd/user/
   cp deploy/systemd/chdevflow-supervisor-multi.service ~/.config/systemd/user/
   cp deploy/systemd/chdevflow-supervisor-multi.timer ~/.config/systemd/user/
   ```

2. Recarregar as definições do systemd:
   ```bash
   systemctl --user daemon-reload
   ```

3. Verificar a prévia do timer sem iniciar o serviço:
   ```bash
   systemctl --user list-timers --all
   ```

4. Habilitar e iniciar exclusivamente o timer:
   ```bash
   systemctl --user enable --now chdevflow-supervisor-multi.timer
   ```

5. Para suspender ou desativar imediatamente:
   ```bash
   systemctl --user stop chdevflow-supervisor-multi.timer
   systemctl --user disable chdevflow-supervisor-multi.timer
   ```

---

### Opção B: Ativação via Antigravity Automations Dashboard

Caso o PO opte por operar o ciclo via Antigravity IDE:

1. O arquivo `deploy/sidecars/ch-auto-multi-01/sidecar.json` deve ser referenciado ou movido para `~/.gemini/config/sidecars/ch-auto-multi-01/sidecar.json`.
2. O PO abre o painel de automações (`sidecar://dashboard`) e faz a ativação manual com consentimento explícito de permissões.

---

## 3. Plano de Rollback e Contenção de Falhas

Se ocorrer qualquer comportamento anômalo:

1. **Parada Imediata do Timer**:
   ```bash
   systemctl --user stop chdevflow-supervisor-multi.timer
   ```
2. **Liberação do Lock de Concorrência**:
   Caso uma execução tenha sido abortada abruptamente, o arquivo `.ch_sentinela/fila_sequencial_multi_repo.json` mantém a chave e o motivo da falha. Para liberar o lock manualmente:
   ```bash
   python -c "from chdevflow.core.multi_repo_queue import FilaSequencialMultiRepo; FilaSequencialMultiRepo().cancelar_reserva('chave', 'Cancelamento manual pelo operador')"
   ```
3. **Preservação de Logs**: Todos os eventos estruturados são gravados em `.ch_sentinela/` com modo de permissão restrito `0o600`.
