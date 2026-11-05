# BOOT-00 — Contratos para o Bootstrap Engine (proposta CH-1)

**Issue:** [#24](https://github.com/hallanbrito/CHDevFlow/issues/24) · **Draft PR:** [#25](https://github.com/hallanbrito/CHDevFlow/pull/25) · **Estado:** ESPECIFICAÇÃO ARQUITETURAL DE CONTRATOS (CH-1 DOCUMENTAL) — REVISÃO CONCEITUAL DE ATUALIDADE (03/11/2026) · **Base Histórica de Proposta:** `d2a74426bfa1fab12aafb721c8dad60876f6f8ec` · **Baseline Canônico de Alinhamento (`main`):** `a1aa3935ce3e5a34cd12dbf79c54dd211c02887e` · **PO:** Hallan.

---

## 1. Objetivo: construir primeiro a ferramenta que constrói ferramentas

Fazer a primeira missão percorrer `GitHub Issue → observação → contrato → gate PO → fake worker → evidências → supervisão → AGUARDANDO_PO`, **sem copiar manualmente logs entre ferramentas**. Esta é a arquitetura fundacional da autoaceleração supervisionada do CHDevFlow, concebida para formalizar contratos estáveis e auditáveis.

O Bootstrap Engine é **um coordenador de processos**, não um modelo de IA. Não substitui nem duplica:
- **GitHub Issues/PRs:** verdade durável, autorização e entregas.
- **Project #2:** **visualização/indexação**; rótulos e colunas NÃO dão permissão nem constituem fonte de verdade normativa.
- **KSYNC-03 / Exportador:** leitura e reconciliação conservadora; rotinas de exportação read-only implementadas no CH-ACCESS-01 ([PR #50](https://github.com/hallanbrito/CHDevFlow/pull/50)). Mutações dependem de gate humano do PO.
- **Control Center (`apps/control-center/`):** painel estático somente leitura fundado em CC-00 ([PR #30](https://github.com/hallanbrito/CHDevFlow/pull/30)), com correções de leitura live tratadas em CC-01 ([PR #31](https://github.com/hallanbrito/CHDevFlow/pull/31)).
- **Maestro Router:** recomendação de modelos, estimativas e métricas através de adaptador opcional e sem privilégios de execução no host. Não substitui o roteador nem autoriza execuções diretas não deliberadas pelo PO.
- **AGY/Antigravity e Codex:** **executores**; ambos exigem gate explícito, sandbox e verificação de compatibilidade, nunca atuando como supervisores de sua própria aprovação.

---

## 2. Três contratos mínimos e versionados

Os contratos definidos abaixo estabelecem o protocolo canônico de intercâmbio de dados entre os componentes do motor de autoaceleração.

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
    "base_sha": "a1aa3935ce3e5a34cd12dbf79c54dd211c02887e",
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

No primeiro ciclo: `FakeWorker` retorna `COMPLETED` com artefatos sintéticos e zero side effects (já implementado na Sentinela Python em `apps/bootstrap/sentinela/`). Para fases posteriores, adaptadores **separados** `CodexWorker` e `AgyWorker`: versão e flags verificadas no host, STDOUT/JSON sanitizado, erro/timeout/cancelamento tratados, sem flags de bypass. Nunca injetar texto da Issue no shell. O AGY é prioritário para o futuro piloto real pelo D02; um ensaio mock ou com FakeWorker não troca D02 nem autoriza modelo.

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

`state=AWAITING_PO` **não é aprovação**. Só o PO libera etapa posterior. As evidências devem registrar versão do worker, `run_id`, `base_sha`, diff e testes reais, negações de permissão, redaction de segredos, tempo e eventual custo. O executor não pode escrever ou substituir sua própria avaliação independente.

---

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

---

## 4. Fonte de verdade, coordenação e segurança

| Responsabilidade | Onde vive | Pode alterar decisão humana? |
|---|---|---|
| Missão, autorização e decisão final | Issue/PR GitHub + identidade autenticada | Só PO autenticado |
| Esteira, Etapa CH, status visual | GitHub Project #2 | Não confere permissões |
| Eventos, curso da execução e bloqueios | JSONL privado (0600), `run_id` | Não |
| Exclusão de concorrência e reprise | SQLite local com transação + lock de processo | Não |
| Inferência/modelos | Maestro e provedores autorizados | Não |
| Execução de comandos | Worker isolado, sob supervisor e modelo seguro | Não |

No primeiro ciclo com `FakeWorker`, a reserva e falhas foram simuladas em fixtures offline. Antes de qualquer worker real, é mandatório demonstrar idempotência após crash, trava única por host e checagem de alterações concorrentes; mutex local não é garantia distribuída. O isolamento de branches via `git worktree` **não isola o sistema operacional**; executores devem operar sob permissões estritamente restritas e sem acesso a produção, mundos/saves, Docker de produção, segredos de rede ou credenciais de merge.

Nenhum projeto de produção é alvo da arquitetura BOOT. Invariantes herdadas D01–D07 ratificadas pelo PO:
- **D01 (Host):** notebook com Linux CachyOS.
- **D02 (Agente):** AGY/Antigravity prioritário para piloto real; acionamento no CachyOS a validar.
- **D03 (Autonomia):** CH-2 por missão autorizada, sem merge automático.
- **D04 (Piloto):** HallanCraft somente após autorização explícita; preservação estrita de dados/saves.
- **D05 (Acionamento):** **Disparo manual obrigatório**; sem polling, cron ou daemon.
- **D06 (Limites):** 1 tarefa por vez, 15 minutos (900s) de timeout, até 1 retry exclusivamente após diagnóstico, parada imediata e custo adicional R$ 0 obrigatório.
- **D07 (Identidade):** menor privilégio, segredos protegidos, rastreabilidade completa por run_id/SHA e proteção da branch principal.

---

## 5. Sentinela: vigência irrestrita de D05 (sem loop/daemon)

**D05 vigente e inegociável:** acionamento exclusivamente manual (`--once`); sem polling contínuo, cron ou daemon permanente em background.

- **Proposta prospectiva de `--loop`:** hipótese técnica de permitir observação em loop read-only (`watch --loop --read-only`). **Status: NÃO ADOTADA / NÃO IMPLEMENTADA.** A habilitação de qualquer monitoramento em loop exigiria deliberação explícita do PO com revisão formal de D05, provas de taxa de consumo de API (rate limit) e salvaguardas de recuperação. Permanece proibido executar serviços permanentes ou workers em segundo plano.

---

## 6. Evolução arquitetural e entregas reais na `main`

Historicamente, o BOOT-00 foi redigido como especificação puramente documental quando o repositório ainda não possuía executáveis do motor de autoaceleração. Com a evolução do projeto, as seguintes entregas reais foram homologadas e integradas à branch `main` (`a1aa3935ce3e5a34cd12dbf79c54dd211c02887e`):

1. **Sentinela Python (BOOT-01):** Integrada via [PR #26](https://github.com/hallanbrito/CHDevFlow/pull/26) no diretório `apps/bootstrap/sentinela/`, implementando cliente GitHub read-only, observação com `watch --once`, `FakeWorker`, `SupervisorResult`, gravação de eventos JSONL em `0600` e suíte de testes unitários.
2. **CHDevFlow CLI v0.1 (CLI-00 a CLI-06):** Integrada via [PR #39](https://github.com/hallanbrito/CHDevFlow/pull/39) no diretório `src/chdevflow/`, consolidando o comando instalável `ch` com subcomandos `new`, `status`, `doctor`, `verify`, `mission`, `ruc`, `submit` e `watch`.
3. **Estabilizações P0 (AUD-GERAL-01):**
   - **P0-01 ([PR #42](https://github.com/hallanbrito/CHDevFlow/pull/42)):** `ch status --strict` eliminando falso PASS em projetos sem fundação.
   - **P0-02 ([PR #44](https://github.com/hallanbrito/CHDevFlow/pull/44)):** Empacotamento autossuficiente (`pyproject.toml`, `MANIFEST.in`, build de wheel/sdist incluindo Sentinela e Control Center).
   - **P0-03 ([PR #46](https://github.com/hallanbrito/CHDevFlow/pull/46)) e CH-CI-01 ([PR #48](https://github.com/hallanbrito/CHDevFlow/pull/48)):** CI integral com Node 24 cobrindo CLI, Sentinela e Control Center.
   - **CH-ACCESS-01 ([PR #50](https://github.com/hallanbrito/CHDevFlow/pull/50)):** Exportador read-only auditável do GitHub Project #2.
   - **P0-04 ([PR #52](https://github.com/hallanbrito/CHDevFlow/pull/52)):** Modelo seguro de execução em `ch verify`, eliminando `shell=True` arbitrário e estabelecendo política estrita de Project Trust.

---

## 7. Matriz de classificação dos componentes e gates

Conforme auditoria de atualidade de 03/11/2026, cada elemento da arquitetura de autoaceleração é classificado formalmente:

| Componente / Elemento | Classificação | Evidência Canônica / Situação Observada |
|---|---|---|
| **Contratos Mínimos (`Mission`, `Worker`, `Supervisor`)** | `PARCIAL` | Especificados formalmente no BOOT-00; adotados operacionalmente na Sentinela (`apps/bootstrap/sentinela/src/ch_sentinela/contracts.py`) e CLI (`ch mission`, `ch ruc`). Integração com worker IA real continua pendente. |
| **Sentinela Python com FakeWorker (BOOT-01)** | `IMPLEMENTADO` | Implementada em `apps/bootstrap/sentinela/` ([PR #26](https://github.com/hallanbrito/CHDevFlow/pull/26), [Issue #27](https://github.com/hallanbrito/CHDevFlow/issues/27)), validada por testes e integrada na `main`. |
| **CHDevFlow CLI v0.1 (`src/chdevflow/`)** | `IMPLEMENTADO` | Implementada e integrada na `main` ([PR #39](https://github.com/hallanbrito/CHDevFlow/pull/39), [Issues #32–#38](https://github.com/hallanbrito/CHDevFlow/issues/32)), fornecendo comandos operacionais do C.H. |
| **Estabilizações P0 (P0-01 a P0-04, CI, Access)** | `IMPLEMENTADO` | Totalmente integradas na `main` ([PRs #42, #44, #46, #48, #50, #52](https://github.com/hallanbrito/CHDevFlow/pull/52)), garantindo status estrito, empacotamento, CI integral e modelo seguro de verificação. |
| **Control Center (`apps/control-center/`)** | `PARCIAL` | Fundação em `apps/control-center/` integrada via [PR #30](https://github.com/hallanbrito/CHDevFlow/pull/30); correções de leitura live da [PR #31](https://github.com/hallanbrito/CHDevFlow/pull/31) integradas à `main` em 04/11/2026. A classificação `PARCIAL` se refere à evolução do Control Center, não ao estado pendente da PR #31. |
| **KSYNC-03 / Reconciliação do Kanban** | `PARCIAL` | Leitura auditável implementada (CH-ACCESS-01); mutação assistida permanece estritamente manual pelo PO. |
| **Execução AGY/Codex no Host (BOOT-03 / BOOT-04)** | `NÃO_IMPLEMENTADO` | Executores reais com sandbox no CachyOS continuam não autorizados e não implementados; exigem gates futuros específicos. |
| **Sentinela em Loop / Daemon Permanente (D05-v2)** | `NÃO_IMPLEMENTADO` | Polling ou execução 24/7 não autorizados; D05 permanece estritamente manual (`--once`). |
| **Integração de Modelos via Maestro em Runtime** | `NÃO_IMPLEMENTADO` | O Maestro Router atua como ferramenta externa; o CHDevFlow não delega execução nem roteamento em tempo real a modelos. |
| **Alegação histórica de que "não há demo funcional de BOOT-01"** | `SUPERADO` | Fato superado pela implementação de `apps/bootstrap/sentinela/` funcional e testada na `main`. |
| **Concepção de `bootstrap watch` como CLI isolada** | `SUPERADO` | Fato superado pela integração unificada no comando `ch watch` e ecossistema `chdevflow`. |
| **Execução livre de comandos no `ch verify`** | `SUPERADO` | Fato superado pelo modelo seguro do P0-04 ([PR #52](https://github.com/hallanbrito/CHDevFlow/pull/52)), com allowlist estrita e Project Trust. |

---

## 8. Critérios de aceitação da revisão BOOT-00

- [x] Documento rastreável com os três contratos, esquemas e exemplos sintéticos preservados.
- [x] Rebaseamento conceitual documentado em relação à `main` canônica (`a1aa3935ce3e5a34cd12dbf79c54dd211c02887e`), mantendo o histórico de base original `d2a74426...`.
- [x] Classificação explícita de todos os componentes entre `IMPLEMENTADO`, `PARCIAL`, `NÃO_IMPLEMENTADO` e `SUPERADO`.
- [x] Referência explícita às entregas reais da Sentinela Python, CLI v0.1 e estabilizações P0-01..P0-04.
- [x] Vigência estrita de D05 (disparo manual, sem loop/daemon) e proibição de auto-merge reafirmadas.
- [x] Modificação estritamente restrita a `docs/bootstrap/BOOT-00-CONTRATOS.md` na branch `chatgpt/boot00-bootstrap-engine-contracts`.
- [x] Sem adição de binários, scripts, código executável, credenciais ou alterações em branches de código.
- [x] Suíte de testes do repositório validada sem regressões (`python3 -m unittest discover tests`).

---

## 9. RUC/1.0 — Relatório Universal C.H. deste artefato

1. **Identificação e Contexto:**
   - **Fatia / Tarefa:** BOOT-00 (Revisão Conceitual de Atualidade) · [Issue #24](https://github.com/hallanbrito/CHDevFlow/issues/24) · [Draft PR #25](https://github.com/hallanbrito/CHDevFlow/pull/25).
   - **Autonomia:** CH-1 (Documental / Especificação Arquitetural).
   - **Branch:** `chatgpt/boot00-bootstrap-engine-contracts`.
   - **Baseline Histórico:** `d2a74426bfa1fab12aafb721c8dad60876f6f8ec`.
   - **Baseline Canônico de Alinhamento (`main`):** `a1aa3935ce3e5a34cd12dbf79c54dd211c02887e`.
   - **Data da Revisão:** 03/11/2026.

2. **Resumo da Entrega:**
   - Atualização da especificação arquitetural do Bootstrap Engine atendendo integralmente ao parecer de auditoria (`AJUSTES_RECOMENDADOS / SEM_MERGE`) emitido pelo PO em 03/11/2026 no [Draft PR #25](https://github.com/hallanbrito/CHDevFlow/pull/25) e registrado na [Issue #53](https://github.com/hallanbrito/CHDevFlow/issues/53).
   - Eliminação de contradições factuais prospectivas por meio da classificação sistemática dos componentes em matriz formal (`IMPLEMENTADO`, `PARCIAL`, `NÃO_IMPLEMENTADO`, `SUPERADO`), referenciando as entregas consolidadas da Sentinela Python, CLI v0.1 e P0-01..P0-04.

3. **Fontes Consultadas e Autoridade:**
   - Comentário de auditoria de atualidade do PO (03/11/2026) no [PR #25](https://github.com/hallanbrito/CHDevFlow/pull/25#issuecomment-6613735909).
   - Diretrizes de governança e despacho da [Issue #53](https://github.com/hallanbrito/CHDevFlow/issues/53) (CH-AGY-SEQ-01).
   - Decisões estruturais D01–D07 ratificadas na [Issue #7](https://github.com/hallanbrito/CHDevFlow/issues/7).
   - Entregas integradas canonicamente na `main`: PRs [#26](https://github.com/hallanbrito/CHDevFlow/pull/26), [#39](https://github.com/hallanbrito/CHDevFlow/pull/39), [#42](https://github.com/hallanbrito/CHDevFlow/pull/42), [#44](https://github.com/hallanbrito/CHDevFlow/pull/44), [#46](https://github.com/hallanbrito/CHDevFlow/pull/46), [#48](https://github.com/hallanbrito/CHDevFlow/pull/48), [#50](https://github.com/hallanbrito/CHDevFlow/pull/50), [#52](https://github.com/hallanbrito/CHDevFlow/pull/52).

4. **Evidências Factualmente Observadas:**
   - Commit base da branch: `0b2ff09ed15cf8841443ff0dba25af6bff3bdb0b`.
   - Modificação restrita a 1 único arquivo: `docs/bootstrap/BOOT-00-CONTRATOS.md`.
   - `main` canônica observada em `a1aa3935ce3e5a34cd12dbf79c54dd211c02887e`.
   - Nenhum worker, processo daemon, polling em background ou script executável adicionado.

5. **Verificações e Testes Executados:**
   - Execução da suíte de testes unitários do repositório: `python3 -m unittest discover tests` — 77 testes executados com sucesso (0.052s, OK).
   - Verificação de consistência e sintaxe Markdown: tabelas e schemas JSON estritamente válidos.
   - Verificação de escopo via `git diff --stat`: 1 arquivo modificado (`docs/bootstrap/BOOT-00-CONTRATOS.md`).

6. **Análise de Riscos e Mitigações:**
   - *Risco de descompasso conceitual com o repositório:* Mitigado pelo rebaseamento conceitual explícito apontando para o commit canônico da `main` e matriz de status.
   - *Risco de execução autônoma indevida:* Mitigado pela reafirmação categórica de que D05 manual permanece vigente e que a proposta de loop permanece `NÃO_IMPLEMENTADO`.
   - *Risco de violação de governança:* Mitigado pela ausência de auto-merge, sem alteração de branches protegidas ou modificações no GitHub Project #2.

7. **Alterações Realizadas:**
   - Modificação contida exclusivamente em `docs/bootstrap/BOOT-00-CONTRATOS.md`.

8. **Recomendação Técnica:**
   - Encaminhar a entrega técnica atualizada para nova auditoria independente do ChatGPT e deliberação do PO no [Draft PR #25](https://github.com/hallanbrito/CHDevFlow/pull/25).
   - **Parecer:** `AGUARDANDO_AUDITORIA_CHATGPT` / `SEM_MERGE`.

9. **Decisão PO:**
   - `HOMOLOGADO_DOCUMENTALMENTE_PELO_PO / SEM_MERGE`: homologação expressa em 03/11/2026, restrita ao HEAD `e6dc3a569626ac55b9d5b65dceb26e9044eac450`, registrada no [gate da PR #25](https://github.com/hallanbrito/CHDevFlow/pull/25#issuecomment-6614230031). A homologação histórica não autoriza integração nem se estende automaticamente a novo commit de correção documental. Qualquer merge exige novo gate específico do PO, com revalidação de HEAD, CI, diff e mergeabilidade.
