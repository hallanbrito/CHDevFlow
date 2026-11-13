# CH-AUTO-02 — Supervisão Horária da Esteira Peão / AGY

> **Estado do componente:** `IMPLEMENTADO_NAO_ATIVADO`  
> **Próxima fase:** `AGUARDANDO_AUDITORIA_CHATGPT` / `AGUARDANDO_PO`  
> **Execução autônoma:** ESTRITAMENTE DESATIVADA  
> **Custo adicional autorizado:** R$ 0,00  
> **Issue de referência:** [#69](https://github.com/hallanbrito/CHDevFlow/issues/69)  
> **Fontes canônicas:** [#53](https://github.com/hallanbrito/CHDevFlow/issues/53), [#56](https://github.com/hallanbrito/CHDevFlow/issues/56), [#62](https://github.com/hallanbrito/CHDevFlow/issues/62), [GitHub Project #2](https://github.com/users/hallanbrito/projects/2)

---

## 1. Objetivo e Escopo

Implementar o mecanismo que, futuramente, quando expressamente autorizado pelo Product Owner (PO), consultará a cada 60 minutos o GitHub Project #2, identificará missões elegíveis na Esteira AGY/Peão, executará no máximo uma missão sequencial por vez e entregará relatórios auditáveis para homologação independente do ChatGPT.

Nesta fatia, o mecanismo está **completamente implementado e testado offline**, mas a **execução automática permanece desativada por padrão (`enabled: false`, `dry_run: true`)**. Nenhuma automação, daemon, cron, systemd timer ou GitHub Action periódico foi ativado.

---

## 2. Inspecção da Arquitetura e Resolução de Conflitos

### 2.1 Conflito com Issue #53 (Fila Única Sequencial)
- **Diretriz da #53:** Fila sequencial única, determinística e idempotente; no máximo uma missão ativa por vez; sem workers paralelos ou daemons concorrentes.
- **Implementação do CH-AUTO-02:** O supervisor adota trava atômica de ciclo (`HourlySupervisorLock`) que impede a sobreposição de ciclos horários. A seleção de tarefas ordena estritamente por prioridade canônica (`P0` > `P1` > `P2` > `P3`) e número de issue, selecionando no máximo uma única missão (`max_parallel: 1`). Tarefas já concluídas ou em andamento são filtradas pelo checkpoint local, garantindo idempotência e prevenindo reprocessamento duplicado.

### 2.2 Conflito com Issue #56 (W2-B Dispatcher e Adaptadores)
- **Diretriz da #56:** O núcleo de despacho e adaptadores simulados (FakeAdapter / CodexExecFake / AgyPrintFake) estabelecem os contratos D01–D07 de limites (900s, 1 run, 1 retry condicionado, custo R$ 0).
- **Implementação do CH-AUTO-02:** O supervisor não duplica a lógica do despachante. Ele atua como orquestrador superior de governança que avalia a elegibilidade de cartões do Project #2 e, no modo simulação, delega a validação estrita de contrato ao `DryRunDispatcher`, sem disparar processos de agentes reais.

### 2.3 Conflito com Issue #62 (CH-DATA-01/R2 — Governança do Project #2)
- **Diretriz da #62:** O Project #2 é fonte canônica somente-leitura para agentes; proibida qualquer mutação de campos sem lote de aprovação exata do PO. Rótulos e colunas do Kanban não constituem autorização de execução.
- **Implementação do CH-AUTO-02:** O supervisor realiza operações estritamente de leitura (read-only) via `export_project_snapshot` e `LeitorGitHub`.
  - Nunca infere o campo `Esteira` a partir de labels (como `ch:agy`).
  - Lê rigorosamente os 7 campos canônicos: `Esteira`, `Etapa CH`, `Status`, `Prioridade CH`, `Risco CH`, `Autonomia CH` e `Decisao PO`.
  - Qualquer dado ausente, divergente ou inacessibilidade da API resulta em `BLOQUEADO_DADOS` (política fail-closed).
  - Etapas visuais como `PRONTA` ou `HOMOLOGADA` não concedem execução sem o campo `Decisao PO == "APROVADO"` e contrato de autorização verificável.

### 2.4 Conflito com Issue #69 (CH-AUTO-01 — Despachante Real Supervisionado)
- **Diretriz da #69:** Manter implementação inerte, sem ativação operacional, com proposta documentada de timer.
- **Implementação do CH-AUTO-02:** O agendamento horário foi projetado via systemd user timer no Linux, com unidades `ch-peao-supervisor.service` e `ch-peao-supervisor.timer` fornecidas desativadas e acompanhadas de procedimento de auditoria prévia.

---

## 3. Ciclo Horário Supervisionado (8 Etapas)

```mermaid
flowchart TD
    A["1. Início do Ciclo (60 min)"] --> B["2. Aquisição de Lock Exclusivo"]
    B --> C["3. Consulta Read-Only ao Project #2"]
    C -->|Falha / Inacessível| D["Registra BLOQUEADO_DADOS"]
    C -->|Sucesso| E["4. Leitura dos 7 Campos Canônicos"]
    E --> F{"5. Esteira == AGY?"}
    F -->|Não| G["Desconsidera do Peão"]
    F -->|Sim| H{"6. Decisão PO == APROVADO & Custo R$ 0?"}
    H -->|Não| I["Marca AGUARDANDO_PO / BLOQUEADO"]
    H -->|Sim| J["7. Fila Sequencial (Top 1)"]
    J --> K{"8. Ativação Autorizada?"}
    K -->|Não (Padrão)| L["Dry-Run / INERTE (0 processos)"]
    K -->|Futuro Autorizado| M["Execução Supervisionada"]
    D --> N["9. Dossiê Auditável: CHDEVFLOW — RELATÓRIO AGY"]
    I --> N
    L --> N
    M --> N
    N --> O["10. Liberação do Lock"]
```

1. **Consulta Autenticada:** Executa leitura determinística e sanitizada do Project #2.
2. **Leitura dos 7 Campos Canônicos:** Inspeciona `Esteira`, `Etapa CH`, `Status`, `Prioridade CH`, `Risco CH`, `Autonomia CH` e `Decisao PO`.
3. **Filtro Exclusivo de Esteira:** Seleciona apenas cartões comprovadamente da Esteira `AGY` (rejeitando inferências por labels).
4. **Verificação de Autorização e Contrato:** Confere identidade do autorizador (`hallanbrito`), SHA de baseline, limites D06, escopo de caminhos e custo incremental R$ 0.
5. **Fila Sequencial e Idempotente:** Ordena por prioridade (`P0` > `P1` > `P2` > `P3`) e descarte de tarefas já concluídas ou em andamento no checkpoint.
6. **Seleção de Missão Única:** Seleciona no máximo uma missão por ciclo.
7. **Execução Inerte (Dry-Run):** Prova estrutural de zero subprocessos de agentes reais disparados nesta fase.
8. **Dossiê Auditável:** Gera o relatório padronizado `CHDEVFLOW — RELATÓRIO AGY` para revisão independente do ChatGPT.

---

## 4. Formato Obrigatório do Relatório

Todo ciclo de supervisão produz o relatório estruturado no padrão obrigatório:

```markdown
**CHDEVFLOW — RELATÓRIO AGY**

- Data e horário da verificação: <timestamp_utc>
- Snapshot/identificador da leitura do Project: <snapshot_sha256>
- Quantidade de cartões identificados: <total> (Esteira Peão: <peao_count>)
- Missões elegíveis e bloqueadas: Elegíveis: [<lista>] | Bloqueadas: [<lista_e_motivos>]
- Missão selecionada e evidência de autorização: <#issue e autorização ou Nenhuma>
- Branch, commit e Draft PR: Branch: `<branch>` | Commit: `<sha>` | Draft PR: <link ou Nenhum>
- Testes executados e resultados reais: <testes> | Resultado: <resultado>
- CI e pendências: <ci_status>
- Custos confirmados ou não verificados: R$ 0,00 (confirmado: sem chamadas pagas)
- Riscos e bloqueios: <riscos>
- Próximo responsável: <ChatGPT ou PO>
```

Quando não houver alterações nem novas tarefas autorizadas, o supervisor emite apenas registro resumido local em logs, prevenindo notificações repetitivas.

---

## 5. Configuração e Agendamento Futuro

### 5.1 Arquivo de Configuração (`config/supervisor_peao.json`)
```json
{
  "$schema": "chdevflow.supervisor-config/1.0",
  "enabled": false,
  "dry_run": true,
  "interval_minutes": 60,
  "lane": "AGY",
  "project_owner": "hallanbrito",
  "project_number": 2,
  "canonical_repository": "hallanbrito/CHDevFlow",
  "max_parallel": 1,
  "timeout_seconds": 900,
  "max_retries_after_diagnosis": 1,
  "extra_cost_allowed_brl": 0.0,
  "status_operacional": "IMPLEMENTADO_NAO_ATIVADO"
}
```

### 5.2 Unidades systemd User (Linux)
- `systemd/ch-peao-supervisor.service`: Executa `ch supervise --once --dry-run`.
- `systemd/ch-peao-supervisor.timer`: Disparo a cada 60 minutos (`OnCalendar=*:00:00`).

---

## 6. Instruções para Futura Ativação (SEM ATIVÁ-LA AGORA)

> [!CAUTION]
> **Aviso Importante:** Esta implementação **NÃO** autoriza a ativação do timer nem da execução autônoma. Qualquer alteração deste estado exige **nova decisão explícita e verificável do PO (Hallan)**.

Quando houver autorização expressa do PO em novo gate:

1. **Instalação das unidades no ambiente Linux do operador:**
   ```bash
   mkdir -p ~/.config/systemd/user
   cp systemd/ch-peao-supervisor.service ~/.config/systemd/user/
   cp systemd/ch-peao-supervisor.timer ~/.config/systemd/user/
   systemctl --user daemon-reload
   ```

2. **Verificação do estado desativado antes de qualquer ação:**
   ```bash
   systemctl --user status ch-peao-supervisor.timer
   # Deve reportar: inactive (dead)
   ```

3. **Ativação operacional controlada (apenas após aprovação formal do PO):**
   ```bash
   # Habilitar e iniciar o timer horário
   systemctl --user enable --now ch-peao-supervisor.timer
   ```

4. **Monitoramento e auditoria:**
   ```bash
   systemctl --user list-timers
   journalctl --user -u ch-peao-supervisor.service -f
   ```

5. **Procedimento de Parada Imediata (Rollback / Fail-Safe):**
   ```bash
   systemctl --user stop ch-peao-supervisor.timer
   systemctl --user disable ch-peao-supervisor.timer
   systemctl --user stop ch-peao-supervisor.service
   ```
