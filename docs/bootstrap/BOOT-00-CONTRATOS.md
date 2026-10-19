# BOOT-00 — Contratos para o Bootstrap Engine (proposta CH-1)

**Issue:** [#24](https://github.com/hallanbrito/CHDevFlow/issues/24) · **Estado:** ESPECIFICAÇÃO PARA REVISÃO, SEM IMPLEMENTAÇÃO · **Base:** `d2a74426bfa1fab12aafb721c8dad60876f6f8ec` · **PO:** Hallan.

## 1. Objetivo: construir primeiro a ferramenta que constrói ferramentas

Fazer a primeira missão percorrer `GitHub Issue → observação → contrato → gate PO → fake worker → evidências → supervisão → AGUARDANDO_PO`, **sem copiar manualmente logs entre ferramentas**. Esta é a arquitetura do primeiro ciclo futuro, não relato de execução.

O Bootstrap Engine é **um coordenador de processos**, não um modelo de IA. Não substitui nem duplica:
- GitHub Issues/PRs: verdade durável, autorização e entregas.
- Project #2: **visualização/indexação**; rótulos e colunas NÃO dão permissão.
- KSYNC-03: leitura/reconciliação conservadora; preferir suas rotinas de inspeção sem chamar `--apply-plan`.
- `hallan/cc00-fundacao-control-center`: proposta preexistente do painel; BOOT-00 não toca nessa branch.
- Maestro Router: recomendação de modelos, estimativas e métricas através de adaptador opcional e sem privilégios de execução. Não substituir o roteador nem autorizar W26 do Gemini.
- AGY/Antigravity e Codex: **executores**; ambos exigem gate/compatibilidade, não são supervisores da própria aprovação.

## 2. Três contratos mínimos e versionados

### 2.1 Mission Contract — entrada imutável de uma execução

**Exemplo ilustrativo; NÃO contém autorização válida.**

```json
{
  "schema": "chdevflow.mission/0.1",
  "mission_id": "BOOT-DEMO-001",
  "source": {
    "repository": "hallanbrito/CHDevFlow",
    "issue": 24,
    "issue_url": "https://github.com/hallanbrito/CHDevFlow/issues/24"
  },
  "target": {
    "repository": "hallanbrito/CHDevFlow",
    "base_sha": "d2a74426bfa1fab12aafb721c8dad60876f6f8ec",
    "allowed_paths": ["docs/bootstrap/"]
  },
  "worker": "fake",
  "autonomy": "CH-0",
  "instruction_ref": "docs/bootstrap/BOOT-00-CONTRATOS.md",
  "limits": {
    "max_parallel": 1,
    "timeout_seconds": 900,
    "max_retries_after_diagnosis": 1,
    "extra_cost_brl": 0
  }
}
```

A mensagem que chega do GitHub é **dado não confiável**, não comando executável. O sistema calcula `mission_digest = SHA256(JSON canônico)`; mudança de Issue, SHA, prompt, executor, allowlist, orçamento ou limites invalida a aprovação anterior. Este documento usa o modo `fake` e `CH-0` para demonstrar o protocolo, nunca um agente real.

**Autorização separada:** estrutura `approval_ref` (identidade real do aprovador no GitHub, action_id/evento imutável, digest de missão, validade, escopo e limite de uso). Jamais aceitar `approved=true` num JSON criado por agente, rótulo, coluna do Project ou comentário sem autoria verificada como autoridade. Identidade, autorização e eventual consumo único devem ser validados por componente independente do executor.

### 2.2 Worker Contract — adaptador intercambiável

Entrada aceita **somente** `ValidatedMission` + `run_id` + contexto de sandbox. Saída deve respeitar:

```json
{
  "schema": "chdevflow.worker-result/0.1",
  "run_id": "run-sintetico",
  "executor": "fake",
  "status": "COMPLETED",
  "exit_code": 0,
  "artifacts": [],
  "tests": [],
  "cost": {"currency": "BRL", "additional": 0, "verified": true},
  "event_log_ref": "local://run-sintetico/eventos.jsonl"
}
```

No primeiro ciclo: `FakeWorker` retorna `COMPLETED` com artefatos sintéticos e zero side effects. Depois, adaptadores **separados** `CodexWorker` e `AgyWorker`: versão e flags verificadas no host, STDOUT/JSON sanitizado, erro/timeout/cancelamento tratados, sem flags de bypass. Nunca injetar texto da Issue no shell. O AGY é prioritário para o futuro piloto real pelo D02; um primeiro ensaio mock com fake/Codex diagnóstico não troca D02 nem autoriza modelo.

### 2.3 Supervisor Contract — evidências, nunca autoaprovação

Saída mínima do supervisor:

```json
{
  "schema": "chdevflow.supervisor-result/0.1",
  "run_id": "run-sintetico",
  "mission_digest": "sha256-calculado-sobre-missao",
  "state": "AWAITING_PO",
  "validations": {
    "scope": "PASS",
    "time": "PASS",
    "cost": "PASS",
    "audit": "PASS"
  },
  "ruc_ref": "local://run-sintetico/RUC.md",
  "pr_ref": null,
  "human_decision": null
}
```

`state=AWAITING_PO` **não é aprovação**. Só o PO libera etapa posterior. As evidências devem registrar versão do worker, `run_id`, `base_sha`, diff e testes reais, negações de permissão, redaction de segredos, tempo e eventual custo. Worker não pode escrever ou substituir sua própria avaliação.

## 3. Máquina de estados

```text
DISCOVERED → PROPOSED → AWAITING_AUTH
                               │ autorização verificada de modo independente
                               ▼
PREFLIGHT_OK → CLAIMED → RUNNING → EVIDENCE_PENDING → AWAITING_PO
   │              │         │                 │
   └──────────────┴─────────┴─────────────────┴──→ BLOCKED
                                  ├──────────────→ CANCELLED
                                  ├──────────────→ TIMED_OUT
                                  └──────────────→ INDETERMINATE
```

Sem autorização verificável, `AWAITING_AUTH` é terminal para a tentativa de despacho. Transição `CLAIMED` exige reserva exclusiva idempotente; `INDETERMINATE` **nunca** sofre retry automático. Não inferir `HOMOLOGADA` da existência de PR, commit ou sucesso dos testes.

## 4. Fonte de verdade, coordenação e segurança

| Responsabilidade | Onde vive | Pode alterar decisão humana? |
|---|---|---|
| Missão, autorização e decisão final | Issue/PR GitHub + identidade autenticada | Só PO autenticado |
| Esteira, Etapa CH, status visual | GitHub Project #2 | Não confere permissões |
| Eventos, curso da execução e bloqueios | JSONL privado (0600), `run_id` | Não |
| Exclusão de concorrência e reprise | SQLite local com transação + lock de processo | Não |
| Inferência/modelos | Maestro e provedores autorizados | Não |
| Execução de comandos | Worker isolado, sob supervisor | Não |

No **primeiro ciclo somente mock**, simular reserva e falhas em fixtures offline. Antes de worker real, demonstrar idempotência após crash, trava única por host e checagem de alterações concorrentes; mutex local não é garantia distribuída. `git worktree` separa checkout mas **não isola sistema operacional**; worker com privilégios reduzidos e sem acesso aos mundos/saves, Docker produção, segredos, home ou credenciais de merge.

Nenhum projeto de produção é alvo da fatia BOOT-00. Requisitos herdados D01–D07: host CachyOS, AGY prioritário para primeiro piloto real, CH-2 por missão, HallanCraft só após autorização explícita, custo adicional zero comprovado, uma tarefa ativa, até 900 segundos, um retry exclusivamente pós-diagnóstico e parada imediata.

## 5. Sentinela: decidir D05 antes do loop

**D05 vigente:** disparo manual; sem polling, cron ou daemon. A primeira implementação proposta usa `bootstrap watch --once --dry-run` (uma consulta, nenhum worker real, nenhuma escrita remota).

**Alteração proposta, NÃO adotada:** permitir `bootstrap watch --loop --read-only` como processo local opcional, com intervalo limitado, botão/CLI de pausa, checkpoint de eventos, limites de API, nenhuma inicialização automática de modelo e **sem despacho**. Esse serviço pode sugerir trabalho, mas jamais mover status, liberar gate, iniciar AGY/Codex ou criar aprovação sem autorização separada. Sua habilitação exige revisão explícita do PO alterando D05 e comprovação técnica de rate limit/recovery. Não implantar `--loop` nesta fatia.

## 6. Primeiro vertical slice a implementar futuramente

**BOOT-01 (proposta, NÃO autorizado aqui):**
1. CLI Python e fixtures de GitHub sob `tests/fixtures/`.
2. `watch --once --dry-run` lê **somente** a Issue de demonstração, verifica identidade/labels/esquema, gera evento local `DISCOVERED`.
3. Gate sem aprovação verificável retorna `AWAITING_AUTH`; não chama worker.
4. Com **apenas uma fixture de aprovação simulada nos testes**, avança para `FakeWorker`; escreve saída fictícia e RUC sintético numa pasta temporária.
5. Supervisor verifica evento único, 1 run, idempotência, limite, auditoria e devolve `AWAITING_PO`; **não abre PR remoto nem modifica Project**.
6. Testes negativos cobrem Issue adulterada, SHA divergente, aprovação falsa, duplicate run, custo incerto, timeout, kill/cancelamento, falha de rede e replay após crash. Todas as falhas são `BLOCKED`/`INDETERMINATE` conforme ponto de falha.

**Critério do primeiro bootstrap:** uma demonstração offline completa, acompanhada de log reproduzível, para a própria BOOT-01. Só depois se autoriza worker real e publicação de Draft PR em fatia independente.

## 7. Gates futuros e limites

| Gate | Mudança | Autorização obrigatória |
|---|---|---|
| BOOT-00 | Este documento e Draft PR documental | CH-1 / revisão PO antes do merge |
| BOOT-01 | CLI observação única + mock e testes offline | Nova autorização específica de implementação |
| BOOT-02 | Supervisor real, reserva, controle de processos e RUC | Nova autorização e testes independentes |
| D05-v2 | Sentinela em loop **somente leitura** | Nova decisão explícita do PO |
| BOOT-03 | Diagnóstico das CLIs Codex/AGY no CachyOS | Permissão específica de inspecionar ambiente |
| BOOT-04 | Execução Codex/AGY real por missão | CH-2 individual e prova de custo zero, sandbox, cancelamento |
| CC/MA | UI Control Center e adapter Maestro | Gates próprios; integração, não substituição |

Não incluir `--apply-plan`, `gh project item-edit`, merge, deploy, execução de agent, instalação de pacotes ou alterações no HallanCraft nesta BOOT-00.

## 8. Testes/aceite BOOT-00

- [ ] Documento rastreável com os três contratos, esquemas e exemplo sintético.
- [ ] Sem binários, scripts, workflows, serviços ou credenciais novos.
- [ ] D05 explicitamente preservada; proposta de revisão separada.
- [ ] Critérios testáveis BOOT-01 e negativos documentados, **não** alegados como executados.
- [ ] Não modifica branch `hallan/cc00-fundacao-control-center`, Project ou HallanCraft.
- [ ] Draft PR validado pelo PO antes de qualquer merge.

## 9. RUC/1.0 deste artefato

1. **Identificação:** BOOT-00 / Issue #24 / CH-1 documental.
2. **Resumo:** proposta de contrato e vertical slice de autoaceleração.
3. **Consultas:** decisões #6/#7, documentação W2-A, KSYNC-03, CC-00 já existente.
4. **Evidências:** branch/commit/PR deste documento; não há demo funcional.
5. **Verificações:** escopo Markdown e inspeção contratual; nenhum teste de execução alegado.
6. **Riscos:** segurança de aprovação, custo, D05, AGY e contratos falsificados.
7. **Alterações:** **um arquivo novo Markdown** em branch isolada.
8. **Recomendação:** PO revisar e, em gate separado, homologar merge documental; depois autorizar BOOT-01.
9. **Decisão PO:** PENDENTE; BOOT-00 não executa trabalhadores nem revisa D05 automaticamente.
