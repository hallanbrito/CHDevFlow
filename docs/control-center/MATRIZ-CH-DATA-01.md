# Matriz de Regularização Auditável dos Campos do GitHub Project #2 — CH-DATA-01 (Revisão R1)

> **Documento Normativo Consultivo (Fase CH-1 — Somente Leitura)**
> **Missão:** [Issue #62 — CH-DATA-01](https://github.com/hallanbrito/CHDevFlow/issues/62)
> **Revisão:** R1 após auditoria independente ChatGPT ([comentário #6700637806](https://github.com/hallanbrito/CHDevFlow/issues/62#issuecomment-6700637806))
> **Executor Declarado:** Google Antigravity (AGY) / Peão
> **Revisor Independente:** ChatGPT
> **Decisor:** Product Owner Hallan
> **Nível de Autonomia:** CH-1 (Somente leitura e proposta consultiva. Nenhuma mutação foi aplicada ao Project #2.)
> **Data do Snapshot LIVE:** 2026-11-07T01:40:45Z
> **Digest SHA-256 do Snapshot LIVE:** `5b468ac46c0895ffc9631caea4afffae869b553d8c8c1c586688b1ecd2f12f06`
> **Ferramenta Oficial de Extração:** `scripts/ch_project_export.py`
> **HEAD Auditado:** `7578bd0073b841891a37548378cda1524f3df8d2` (branch `agy/ch-data-01`)

---

## 1. Reconciliação Factual Obrigatória: Diagnóstico F0 vs Snapshot LIVE

Conforme apontado na auditoria independente, o diagnóstico preliminar F0 (`docs/control-center/DIAGNOSTICO-F0-CC-QUALITY-01.md`), produzido em 06/11/2026 sob orçamento de leitura rápida, continha discrepâncias em títulos e Card IDs atribuídos a várias Issues (#16, #18, #19, #21, #24, #27 a #36).

A tabela abaixo reconcilia formalmente essas divergências e **estabelece o Snapshot LIVE exportado em 07/11/2026 como a única fonte canônica factual** para fins de Card IDs e títulos das missões:

| #Issue | Card ID no F0 (Histórico/Incorreto) | Card ID Canônico no LIVE (`project_snapshot.json`) | Título no F0 | Título Real Canônico no GitHub LIVE | Causa da Divergência |
|---|---|---|---|---|---|
| **#5** | `PVTI_lAHOBsbaWM4Bnmd9zhBnlhQ` | `PVTI_lAHOBsbaWM4Bnmd9zhBnlhQ` | [TESTE W1] Validar inclusão automática no Kanban | [TESTE W1] Validar inclusão automática no Kanban CHDevFlow | Ajuste textual de título no GitHub |
| **#16** | `PVTI_lAHOBsbaWM4Bnmd9zhBpY8E` | `PVTI_lAHOBsbaWM4Bnmd9zhBpFjQ` | PILOTO-01 — Piloto restrito do despachante (CH-2) | KSYNC-01 — Automatizar esteiras e BACKLOG do GitHub Project via gh | F0 mapeou Card ID e título do piloto W2 em vez da Issue #16 real |
| **#18** | `PVTI_lAHOBsbaWM4Bnmd9zhBtT_Q` | `PVTI_lAHOBsbaWM4Bnmd9zhBqUV8` | KSYNC-01 — Webhook GitHub Projects -> SQLite | KSYNC-02 — Planejar sincronização segura de todo o Kanban (CH-1) | F0 mapeou identificador de tarefa intermediária |
| **#19** | `PVTI_lAHOBsbaWM4Bnmd9zhBtU-U` | `PVTI_lAHOBsbaWM4Bnmd9zhBsQKA` | KSYNC-02 — Sentinela reconciliador de divergências | KSYNC-03 — Automação assistida do Kanban com gate do PO (MVP) | Deslocamento de índice no diagnóstico F0 |
| **#21** | `PVTI_lAHOBsbaWM4Bnmd9zhBuYhA` | `PVTI_lAHOBsbaWM4Bnmd9zhB5o9E` | KSYNC-03.1 — Reconciliação do estágio (stage) | KSYNC-03.1 — Reconciliação inteligente de etapas (evidências, sem transição automática) | Deslocamento de índice e título parcial |
| **#24** | `PVTI_lAHOBsbaWM4Bnmd9zhB43s0` | `PVTI_lAHOBsbaWM4Bnmd9zhB9jIc` | BOOT-00 — Documentação dos Contratos da Sentinela | BOOT-00 — Contratos para o motor de autoaceleração do CHDevFlow | Card ID incorreto no F0 |
| **#27** | `PVTI_lAHOBsbaWM4Bnmd9zhCAX7Y` | `PVTI_lAHOBsbaWM4Bnmd9zhB-X28` | BOOT-01 — Validação estrita de contratos e simulação | AGY-BOOT01-AUD01 — Corrigir fallback fictício da leitura do GitHub | F0 associou à PR #26 em vez da Issue #27 |
| **#28** | `PVTI_lAHOBsbaWM4Bnmd9zhCAZ6s` | `PVTI_lAHOBsbaWM4Bnmd9zhCLqME` | CH-ACCESS-01 — Exportador seguro do Project #2 | KSYNC-INV-01 — Inventário read-only do Kanban Project #2 (AGY) | F0 associou ao Épico CH-ACCESS-01 (#49) |
| **#29** | `PVTI_lAHOBsbaWM4Bnmd9zhCBk-A` | `PVTI_lAHOBsbaWM4Bnmd9zhCNaiA` | CC-00 — Fundação do CHDevFlow Control Center | CH-REC-01 — Reconciliação integral auditável do Kanban Project #2 | F0 associou à PR #23 em vez da Issue #29 |
| **#32** | `PVTI_lAHOBsbaWM4Bnmd9zhCYe_A` | `PVTI_lAHOBsbaWM4Bnmd9zhDDnJU` | CC-01 — Painel web local de supervisão | CLI-00 — CHDevFlow CLI v0.1: transformar o Método C.H. em ferramenta instalável | F0 associou ao branch CC-01 em vez da CLI-00 |
| **#33-#36** | `PVTI_...DDnW8/YY/aU/iQ` | `PVTI_...DDnlw/no/pA/qc` | Títulos parciais da CLI | Títulos completos canônicos da CLI | Sufixos de GraphQL refinados pelo exportador |
| **#62** | *(Inexistente no F0)* | `PVTI_lAHOBsbaWM4Bnmd9zhGtvdU` | *(Não existia)* | CH-DATA-01 — Regularização auditável dos campos do Project #2 | Nova Issue criada pelo PO após o diagnóstico F0 |

---

## 2. Separação Estrita dos Níveis de Campos (P1 da Auditoria)

A auditoria apontou com razão que propor `Decisao PO = APROVADO` e valores para `Prioridade CH` e `Risco CH` em bloco para todos os 26 itens inflou indevidamente o escopo com julgamentos subjetivos e inferências inválidas.

Nesta revisão R1, estabelece-se a separação formal em **três categorias funcionais**:

### Nível I — Campos Core Obrigatórios (Necessários para Roteamento e Grafo DAG)
São os 3 campos exigidos pelo motor do Control Center e pela Sentinela para classificar e destravar o fluxo operacional:
1. **Etapa CH** (`PVTSSF_lAHOBsbaWM4Bnmd9zhmKTLs`)
2. **Esteira** (`PVTSSF_lAHOBsbaWM4Bnmd9zhmKTL4`)
3. **Autonomia CH** (`PVTSSF_lAHOBsbaWM4Bnmd9zhmKTN0`) — *Define estritamente o nível histórico sob o qual a tarefa foi executada; NÃO concede permissão executiva presente ou futura.*

### Nível II — Homologação Formal e Decisão PO (Gate Humano Inviolável)
- **Decisão PO** (`PVTSSF_lAHOBsbaWM4Bnmd9zhmKTN4`):
  - **Regra de Ouro:** Merge de PR, fechamento de Issue no GitHub ou rótulo visual `HOMOLOGADA` **NÃO constituem homologação humana**.
  - Apenas as missões com **declaração textual expressa, nominal e datada do PO** contendo o termo "homologado" ou equivalente explícito recebem a proposta `APROVADO`.
  - Todas as demais missões recebem a proposta estrita **`PENDENTE`** ou **`ADIAR_AO_PO`**.

### Nível III — Campos de Governança Complementar (Opcionais no Project #2)
- **Prioridade CH** (`PVTSSF_lAHOBsbaWM4Bnmd9zhmKTM0`) e **Risco CH** (`PVTSSF_lAHOBsbaWM4Bnmd9zhmKTNc`):
  - Estão vazios (`NÃO_OBSERVADO`) em **todos os 31 itens** do Project #2.
  - **Não são campos bloqueantes para o Grafo DAG**.
  - Nesta revisão R1, são apresentados como sugestões consultivas secundárias, mantendo-se como **`ADIAR`** para deliberação estratégica do PO, sem condicionar a regularização dos campos core.

---

## 3. Catálogo de Campos e Opções Canônicas no GitHub Project #2

```
• Etapa CH (ID: PVTSSF_lAHOBsbaWM4Bnmd9zhmKTLs)
    BACKLOG: 0226f1e2 | PRONTA: 974bae3f | EM_EXECUCAO: 7d63bd08 | EM_REVISAO: e0b51e89
    AGUARDANDO_PO: 25d7d572 | APROVADA: 0fcdecd7 | PARCIAL: 6d5f86f8 | CORRECOES: d2b85773
    REPROVADA: 5987593c | INTEGRADA: 29382ca9 | HOMOLOGADA: 6527cf07

• Esteira (ID: PVTSSF_lAHOBsbaWM4Bnmd9zhmKTL4)
    Hallan: 0bfba1bb | ChatGPT: b31ae0fa | Codex: 3fee45a7 | AGY: cb7f46ed

• Autonomia CH (ID: PVTSSF_lAHOBsbaWM4Bnmd9zhmKTN0)
    CH-0: d04f05f0 | CH-1: 446303b1 | CH-2: d65d7f47 | CH-3: ff83f5f7

• Decisão PO (ID: PVTSSF_lAHOBsbaWM4Bnmd9zhmKTN4)
    PENDENTE: 36521eed | APROVADO: da18a9ff | PARCIAL: 6429cc22 | AJUSTES: f01270d6 | REPROVADO: c245c8ff

• Prioridade CH (ID: PVTSSF_lAHOBsbaWM4Bnmd9zhmKTM0)
    P0: e970b069 | P1: bb365bbf | P2: fd754fe5 | P3: 0465aa3f

• Risco CH (ID: PVTSSF_lAHOBsbaWM4Bnmd9zhmKTNc)
    BAIXO: 0a016dc9 | MEDIO: 49fde1c0 | ALTO: d1b6fc16 | CRITICO: 1240f852
```

---

## 4. Matriz de Regularização R1 — Lotes de até 5 Issues

### Legenda de Decisão dos Campos:
- **`APLICÁVEL`**: Valor core suportado por evidência direta inequívoca e consensual;
- **`APROVAÇÃO_PO_PENDENTE`**: Valor controverso, gate humano em aberto ou ausência de ato explícito do PO;
- **`ADIAR`**: Campo complementar ou item de teste antigo cuja deliberação deve ser separada da regularização core;
- **`PRESERVAR`**: Campo já preenchido legitimamente no Project #2, intocado por segurança.

---

### LOTE 1 (5 Issues) — Fundação W1, Especificação W2-A, Proteção da Main e Pilotos P0

#### 1. Issue #5 — `[TESTE W1] Validar inclusão automática no Kanban CHDevFlow`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhBnlhQ` | **GitHub State:** `CLOSED` | **Status Project:** `Done`
- **Valores Atuais:** `Etapa CH`: null | `Esteira`: null | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** [Comentário do PO #6250735633](https://github.com/hallanbrito/CHDevFlow/issues/5#issuecomment-6250735633) ("Resultado do teste automático — aprovado ✅ ... gatilho Auto-add disparou").
- **Análise R1:** É uma issue de teste pontual de integração. O PO aprovou o teste de auto-add, não uma fatia de código. Preencher como `HOMOLOGADA` documenta a conclusão no board; alternativamente, o PO pode optar por arquivar o card do Project #2.
- **Proposta Core (Nível I):**
  - `Etapa CH`: Propor `HOMOLOGADA` (`6527cf07`) — **Status:** `APROVAÇÃO_PO_PENDENTE` (PO decide se mantém homologada ou arquiva)
  - `Esteira`: Propor `Hallan` (`0bfba1bb`) — **Status:** `APLICÁVEL` (criada e conferida pelo PO)
  - `Autonomia CH`: Propor `CH-0` (`d04f05f0`) — **Status:** `APLICÁVEL` (teste sem agentes)
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — Apenas para o escopo do teste. Confiança: MÉDIA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P3` (`0465aa3f`), `Risco CH`: `BAIXO` (`0a016dc9`) — **Status:** `ADIAR`.

#### 2. Issue #8 — `W2-A — Especificação documental do despachante (CH-1; sem código)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhBoCZM` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: `INTEGRADA` (`29382ca9`) | `Esteira`: `ChatGPT` (`b31ae0fa`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Título explícito `(CH-1; sem código)`. PR #9 merged (`313a5ef`). [Comentário do PO #6251707916](https://github.com/hallanbrito/CHDevFlow/issues/8#issuecomment-6251707916) declara literalmente: "A proposta documental da W2-A foi integrada; sua revisão/homologação técnica permanece uma decisão separada, não presumida pelo ato de conservar o merge".
- **Análise R1:** A etapa `INTEGRADA` já existente deve ser rigorosamente mantida; **NÃO promover para `HOMOLOGADA`**, respeitando a declaração textual do PO.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `INTEGRADA` — **Status:** `PRESERVAR` (intocado)
  - `Esteira`: `ChatGPT` — **Status:** `PRESERVAR` (intocado)
  - `Autonomia CH`: Propor `CH-1` (`446303b1`) — **Status:** `APLICÁVEL` (título e PR #9 comprovam CH-1 documental). Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Homologação expressamente pendente conforme comentário PO. Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `BAIXO` — **Status:** `ADIAR`.

#### 3. Issue #10 — `CH-SEC-01 — Preparar proteção da main sem bloquear o PO`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhBob5k` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: `BACKLOG` (`0226f1e2`) | `Esteira`: `Hallan` (`0bfba1bb`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Draft PR #11 aberto. Ruleset configurado pelo PO na `main`. A Issue permanece aberta em `BACKLOG`.
- **Análise R1:** Preservar `BACKLOG` e `Esteira=Hallan` impede qualquer disparo automático indevido.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `BACKLOG` — **Status:** `PRESERVAR` (intocado)
  - `Esteira`: `Hallan` — **Status:** `PRESERVAR` (intocado)
  - `Autonomia CH`: Propor `CH-0` (`d04f05f0`) — **Status:** `APLICÁVEL` (planejamento consultivo humano). Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Draft PR #11 não homologada. Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P0`, `Risco CH`: `ALTO` — **Status:** `ADIAR`.

#### 4. Issue #12 — `P0-CODEX — Testar leitura do Kanban e relatório CH (CH-0)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhBot8U` | **GitHub State:** `CLOSED` | **Status Project:** `Done`
- **Valores Atuais:** `Etapa CH`: `HOMOLOGADA` (`6527cf07`) | `Esteira`: `Codex` (`3fee45a7`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** [Comentário textual expresso do PO #6251508201](https://github.com/hallanbrito/CHDevFlow/issues/12#issuecomment-6251508201): "HOMOLOGAÇÃO FORMAL DO PO — P0-CODEX (offline CH-0) ... Decisão expressa do Product Owner — 18/10/2026: homologar os pilotos P0-CODEX (#12) e P0-AGY (#13)".
- **Análise R1:** Caso canônico de homologação nominal explícita do PO.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `HOMOLOGADA` — **Status:** `PRESERVAR` (intocado)
  - `Esteira`: `Codex` — **Status:** `PRESERVAR` (intocado)
  - `Autonomia CH`: Propor `CH-0` (`d04f05f0`) — **Status:** `APLICÁVEL` (offline CH-0 declarado no título e homologação). Confiança: MÁXIMA.
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — **Status:** `APLICÁVEL` (suportado por ato formal do PO). Confiança: MÁXIMA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P0`, `Risco CH`: `BAIXO` — **Status:** `ADIAR`.

#### 5. Issue #13 — `P0-AGY — Testar leitura offline do Kanban e relatório CH (CH-0)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhBo44A` | **GitHub State:** `CLOSED` | **Status Project:** `Done`
- **Valores Atuais:** `Etapa CH`: `HOMOLOGADA` (`6527cf07`) | `Esteira`: `AGY` (`cb7f46ed`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** [Comentário textual expresso do PO #6251508302](https://github.com/hallanbrito/CHDevFlow/issues/13#issuecomment-6251508302): "HOMOLOGAÇÃO FORMAL DO PO — P0-AGY (offline CH-0) ... Decisão expressa do Product Owner — 18/10/2026: homologar os pilotos P0-CODEX (#12) e P0-AGY (#13)".
- **Análise R1:** Caso canônico de homologação nominal explícita do PO.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `HOMOLOGADA` — **Status:** `PRESERVAR` (intocado)
  - `Esteira`: `AGY` — **Status:** `PRESERVAR` (intocado)
  - `Autonomia CH`: Propor `CH-0` (`d04f05f0`) — **Status:** `APLICÁVEL` (offline CH-0 declarado). Confiança: MÁXIMA.
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — **Status:** `APLICÁVEL` (suportado por ato formal do PO). Confiança: MÁXIMA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P0`, `Risco CH`: `BAIXO` — **Status:** `ADIAR`.

---

### LOTE 2 (5 Issues) — RUC v1.0 e Sincronização do Kanban (KSYNC-01 a 03.1)

#### 6. Issue #14 — `RUC-01 — Relatório Universal C.H. v1.0 (especificação documental)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhBo_SY` | **GitHub State:** `CLOSED` | **Status Project:** `Done`
- **Valores Atuais:** `Etapa CH`: `HOMOLOGADA` (`6527cf07`) | `Esteira`: `ChatGPT` (`b31ae0fa`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** PR #15 `[RUC-01][CH-1]` merged na `main` (`b28905a`) por hallanbrito em 18/10/2026. Norma v1.0 homologada pelo PO.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `HOMOLOGADA` — **Status:** `PRESERVAR`
  - `Esteira`: `ChatGPT` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-1` (`446303b1`) — **Status:** `APLICÁVEL` (norma documental CH-1). Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — **Status:** `APLICÁVEL`. Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `BAIXO` — **Status:** `ADIAR`.

#### 7. Issue #16 — `KSYNC-01 — Automatizar esteiras e BACKLOG do GitHub Project via gh`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhBpFjQ` | **GitHub State:** `CLOSED` | **Status Project:** `Done`
- **Valores Atuais:** `Etapa CH`: `HOMOLOGADA` (`6527cf07`) | `Esteira`: `ChatGPT` (`b31ae0fa`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** PR #17 merged na `main` (`f19baef`) por hallanbrito em 18/10/2026. Implementou script de sincronização e testes. Issue fechada como concluída pelo PO.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `HOMOLOGADA` — **Status:** `PRESERVAR`
  - `Esteira`: `ChatGPT` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-2` (`d65d7f47`) — **Status:** `APLICÁVEL` (código + testes executados em PR). Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — **Status:** `APLICÁVEL`. Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `MEDIO` — **Status:** `ADIAR`.

#### 8. Issue #18 — `KSYNC-02 — Planejar sincronização segura de todo o Kanban (CH-1)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhBqUV8` | **GitHub State:** `CLOSED` | **Status Project:** `Done`
- **Valores Atuais:** `Etapa CH`: `INTEGRADA` (`29382ca9`) | `Esteira`: `ChatGPT` (`b31ae0fa`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Título traz expressamente `(CH-1)`. Issue de planejamento concluída e fechada em 18/10/2026.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `INTEGRADA` — **Status:** `PRESERVAR` (não promover para HOMOLOGADA)
  - `Esteira`: `ChatGPT` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-1` (`446303b1`) — **Status:** `APLICÁVEL`. Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — **Status:** `APROVAÇÃO_PO_PENDENTE` (ratificar encerramento do planejamento). Confiança: MÉDIA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P2`, `Risco CH`: `BAIXO` — **Status:** `ADIAR`.

#### 9. Issue #19 — `KSYNC-03 — Automação assistida do Kanban com gate do PO (MVP)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhBsQKA` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: `INTEGRADA` (`29382ca9`) | `Esteira`: `ChatGPT` (`b31ae0fa`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** PR #20 `[KSYNC-03][CH-1]` merged na `main` (`e51ef3a`) por hallanbrito em 19/10/2026. Issue permaneceu aberta no GitHub para acompanhamento.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `INTEGRADA` — **Status:** `PRESERVAR` (não promover)
  - `Esteira`: `ChatGPT` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-1` (`446303b1`) — **Status:** `APLICÁVEL` (assistente com gate humano CH-1). Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Issue em aberto, homologação não formalizada textualmente. Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `MEDIO` — **Status:** `ADIAR`.

#### 10. Issue #21 — `KSYNC-03.1 — Reconciliação inteligente de etapas (evidências, sem transição automática)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhB5o9E` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: `INTEGRADA` (`29382ca9`) | `Esteira`: `ChatGPT` (`b31ae0fa`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** PR #22 `[KSYNC-03.1][CH-1]` merged na `main` (`8e12361`) por hallanbrito em 19/10/2026.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `INTEGRADA` — **Status:** `PRESERVAR`
  - `Esteira`: `ChatGPT` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-1` (`446303b1`) — **Status:** `APLICÁVEL`. Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `MEDIO` — **Status:** `ADIAR`.

---

### LOTE 3 (5 Issues) — Bootstrap Engine, Auditorias e Fundação CLI

#### 11. Issue #24 — `BOOT-00 — Contratos para o motor de autoaceleração do CHDevFlow`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhB9jIc` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: `AGUARDANDO_PO` (`25d7d572`) | `Esteira`: `ChatGPT` (`b31ae0fa`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Draft PR #25 aberto, não integrado. Ordem de serviço #62 alerta expressamente: "Não promover AGUARDANDO_PO para aprovada".
- **Análise R1:** Preservar rigorosamente `Etapa CH = AGUARDANDO_PO` para não furar o gate humano.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `AGUARDANDO_PO` — **Status:** `PRESERVAR` (estritamente intocado)
  - `Esteira`: `ChatGPT` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-1` (`446303b1`) — **Status:** `APLICÁVEL` (contratos documentais). Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Confiança: MÁXIMA (aguardando deliberação humana).
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `MEDIO` — **Status:** `ADIAR`.

#### 12. Issue #27 — `AGY-BOOT01-AUD01 — Corrigir fallback fictício da leitura do GitHub`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhB-X28` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: `INTEGRADA` (`29382ca9`) | `Esteira`: `AGY` (`cb7f46ed`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** PR #26 (`feat(boot-01): Sentinela Python`) merged na `main` (`359ef1b`) por hallanbrito em 20/10/2026. Auditoria de eliminação de fixtures fictícias executada em CH-2 por AGY.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `INTEGRADA` — **Status:** `PRESERVAR`
  - `Esteira`: `AGY` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-2` (`d65d7f47`) — **Status:** `APLICÁVEL` (trabalho técnico de código/testes com PR). Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Homologação técnica pós-merge não documentada individualmente. Confiança: MÉDIA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P0`, `Risco CH`: `MEDIO` — **Status:** `ADIAR`.

#### 13. Issue #28 — `KSYNC-INV-01 — Inventário read-only do Kanban Project #2 (AGY)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhCLqME` | **GitHub State:** `CLOSED` | **Status Project:** `Done`
- **Valores Atuais:** `Etapa CH`: `HOMOLOGADA` (`6527cf07`) | `Esteira`: `AGY` (`cb7f46ed`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Inventário read-only concluído e aceito pelo PO em 20/10/2026.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `HOMOLOGADA` — **Status:** `PRESERVAR`
  - `Esteira`: `AGY` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-0` (`d04f05f0`) — **Status:** `APLICÁVEL` (estritamente read-only). Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P2`, `Risco CH`: `BAIXO` — **Status:** `ADIAR`.

#### 14. Issue #29 — `CH-REC-01 — Reconciliação integral auditável do Kanban Project #2`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhCNaiA` | **GitHub State:** `CLOSED` | **Status Project:** `Done`
- **Valores Atuais:** `Etapa CH`: `HOMOLOGADA` (`6527cf07`) | `Esteira`: `ChatGPT` (`b31ae0fa`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Reconciliação documental realizada sob gate humano e fechada pelo PO em 20/10/2026.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `HOMOLOGADA` — **Status:** `PRESERVAR`
  - `Esteira`: `ChatGPT` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-1` (`446303b1`) — **Status:** `APLICÁVEL`. Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `BAIXO` — **Status:** `ADIAR`.

#### 15. Issue #32 — `CLI-00 — CHDevFlow CLI v0.1: transformar o Método C.H. em ferramenta instalável`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhDDnJU` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: null | `Esteira`: `AGY` (`cb7f46ed`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Épico consolidado da CLI v0.1. O código foi integrado à `main` via PR #39 (`ea50d49`) por hallanbrito em 24/10/2026. A issue permaneceu aberta no GitHub.
- **Análise R1 (Caso Controvertido P1):** O F0 sugeria `HOMOLOGADA`. Porém, como o épico permanece aberto e não há ato textual de homologação final da release v0.1, a proposta mais segura e conservadora é **`INTEGRADA`**. O PO decidirá se prefere `HOMOLOGADA`.
- **Proposta Core (Nível I):**
  - `Etapa CH`: Propor `INTEGRADA` (`29382ca9`) — **Status:** `APROVAÇÃO_PO_PENDENTE` (controversa: integrada vs homologada). Confiança: MÉDIA.
  - `Esteira`: `AGY` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-2` (`d65d7f47`) — **Status:** `APLICÁVEL` (implementação de pacote e CLI). Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Homologação da release v0.1 sujeita ao PO. Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P0`, `Risco CH`: `ALTO` — **Status:** `ADIAR`.

---

### LOTE 4 (5 Issues) — Fatias da CLI v0.1 (#33 a #37) Integradas via PR #39

#### 16 a 20. Issues #33, #34, #35, #36, #37
- **Cards ID:**
  - #33: `PVTI_lAHOBsbaWM4Bnmd9zhDDnlw` (`CLI-01 — Empacotamento e núcleo inicial`)
  - #34: `PVTI_lAHOBsbaWM4Bnmd9zhDDnno` (`CLI-02 — Manifesto, ch new e ch status`)
  - #35: `PVTI_lAHOBsbaWM4Bnmd9zhDDnpA` (`CLI-03 — ch doctor e adapters de stack`)
  - #36: `PVTI_lAHOBsbaWM4Bnmd9zhDDnqc` (`CLI-04 — ch verify e evidências estruturadas`)
  - #37: `PVTI_lAHOBsbaWM4Bnmd9zhDDnsk` (`CLI-05 — ch mission, ch ruc e ch submit`)
- **Valores Atuais em Todas:** `Etapa CH`: `INTEGRADA` (`29382ca9`) | `Esteira`: `AGY` (`cb7f46ed`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Todas foram fatias implementadas em CH-2 pelo Peão (AGY) e integradas conjuntamente na `main` pelo PR consolidado #39 (`ea50d49`) por hallanbrito em 24/10/2026.
- **Análise R1:** Preservar `Etapa CH = INTEGRADA` e `Esteira = AGY`. Preencher `Autonomia CH = CH-2` comprovada. Não inferir homologação individual; marcar `Decisao PO = PENDENTE`.
- **Proposta Core (Nível I) para #33 a #37:**
  - `Etapa CH`: `INTEGRADA` — **Status:** `PRESERVAR` em todas
  - `Esteira`: `AGY` — **Status:** `PRESERVAR` em todas
  - `Autonomia CH`: Propor `CH-2` (`d65d7f47`) — **Status:** `APLICÁVEL` em todas. Confiança: ALTA.
- **Proposta Decisão PO (Nível II) para #33 a #37:** Propor `PENDENTE` (`36521eed`) — Homologação individual das fatias aguarda deliberação do PO. Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P0` (#33, #34, #36) / `P1` (#35, #37), `Risco CH`: `MEDIO` — **Status:** `ADIAR`.

---

### LOTE 5 (5 Issues) — CLI E2E, Auditoria Geral, Falha Remota e Despachante W2-B

#### 21. Issue #38 — `CLI-06 — ch watch, documentação e ensaio E2E do CHDevFlow CLI`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhDDnus` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: `INTEGRADA` (`29382ca9`) | `Esteira`: `AGY` (`cb7f46ed`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Integrada via PR #39. Relatório de auditoria CLI documentado em `6b5c5be`.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `INTEGRADA` — **Status:** `PRESERVAR`
  - `Esteira`: `AGY` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-2` (`d65d7f47`) — **Status:** `APLICÁVEL`. Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `MEDIO` — **Status:** `ADIAR`.

#### 22. Issue #40 — `AUD-GERAL-01 — Estabilização do CHDevFlow antes da release v0.1.0`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhDOUQ4` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: null | `Esteira`: `AGY` (`cb7f46ed`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** Épico aberto para backlog P1. Comentário formal do PO: "As Issues #41, #43, #45 e #51 estão encerradas; os PRs #42, #44, #46 e #52 estão integrados. O épico permanece OPEN para o backlog P1".
- **Análise R1 (Correção Crítica P1):** O F0 sugeria erroneamente `HOMOLOGADA`. O próprio comentário do PO atesta que o épico está aberto para P1. Propor **`EM_EXECUCAO`** (ou `BACKLOG`).
- **Proposta Core (Nível I):**
  - `Etapa CH`: Propor `EM_EXECUCAO` (`7d63bd08`) — **Status:** `APROVAÇÃO_PO_PENDENTE`. Confiança: ALTA.
  - `Esteira`: `AGY` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-2` (`d65d7f47`) — **Status:** `APLICÁVEL`. Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Confiança: MÁXIMA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P0`, `Risco CH`: `ALTO` — **Status:** `ADIAR`.

#### 23. Issue #41 — `AUD-GERAL-P0-01 — Status estrito e eliminação de falso PASS`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhDOUZk` | **GitHub State:** `CLOSED` | **Status Project:** `Done`
- **Valores Atuais:** `Etapa CH`: `INTEGRADA` (`29382ca9`) | `Esteira`: `AGY` (`cb7f46ed`) | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** PR #42 merged na `main` (`80fce9d`) em 24/10/2026. Issue fechada no encerramento de P0.
- **Proposta Core (Nível I):**
  - `Etapa CH`: `INTEGRADA` — **Status:** `PRESERVAR`
  - `Esteira`: `AGY` — **Status:** `PRESERVAR`
  - `Autonomia CH`: Propor `CH-2` (`d65d7f47`) — **Status:** `APLICÁVEL`. Confiança: ALTA.
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — Concluída no fechamento de P0. Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P0`, `Risco CH`: `ALTO` — **Status:** `ADIAR`.

#### 24. Issue #54 — `P1-CLI-REMOTE-01 — Falha remota em ch mission new deve retornar erro (AGY)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhGV8xI` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: null | `Esteira`: null | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual (P1 da Auditoria):** PR #55 merged na `main` (`ffadabe`) pelo PO em 05/11/2026. O comentário de encerramento do PO `#6666235173` diz literalmente: `INTEGRADA_NA_MAIN / AGUARDANDO_HOMOLOGACAO_POS_MERGE_SE_APLICAVEL`.
- **Análise R1 (Correção Crítica P1):** O F0 sugeria `HOMOLOGADA`. Contudo, como o PO registrou expressamente `AGUARDANDO_HOMOLOGACAO_POS_MERGE`, a Etapa CH proposta deve ser estritamente **`INTEGRADA`** (e NÃO `HOMOLOGADA`!), e a Decisão PO deve ser **`PENDENTE`**.
- **Proposta Core (Nível I):**
  - `Etapa CH`: Propor `INTEGRADA` (`29382ca9`) — **Status:** `APLICÁVEL`. Confiança: ALTA.
  - `Esteira`: Propor `AGY` (`cb7f46ed`) — **Status:** `APLICÁVEL` (Peão implementou PR #55). Confiança: MÁXIMA.
  - `Autonomia CH`: Propor `CH-2` (`d65d7f47`) — **Status:** `APLICÁVEL`. Confiança: MÁXIMA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — Homologação pós-merge expressamente pendente conforme o PO. Confiança: MÁXIMA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `MEDIO` — **Status:** `ADIAR`.

#### 25. Issue #56 — `W2-B — Dispatcher Codex + Peão (adaptadores simulados, CH-2)`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhGXa-M` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: null | `Esteira`: null | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** PR #57 merged na `main` (`f8eea14`) em 05/11/2026. [Comentário formal de encerramento do PO #6692250102](https://github.com/hallanbrito/CHDevFlow/issues/56#issuecomment-6692250102) registra textualmente: `INTEGRADA_NA_MAIN / PO_HOMOLOGOU / SEM_RELEASE / SEM_DEPLOY`.
- **Análise R1:** Diferentemente da #54, aqui o PO registrou nominalmente `PO_HOMOLOGOU`. Portanto, a proposta de `HOMOLOGADA` é legítima e sustentada por ato comprovado.
- **Proposta Core (Nível I):**
  - `Etapa CH`: Propor `HOMOLOGADA` (`6527cf07`) (ou `INTEGRADA` se o PO preferir reter) — **Status:** `APROVAÇÃO_PO_PENDENTE`. Confiança: ALTA.
  - `Esteira`: Propor `Codex` (`3fee45a7`) (ou `AGY`) — **Status:** `APLICÁVEL` (executores da W2-B). Confiança: ALTA.
  - `Autonomia CH`: Propor `CH-2` (`d65d7f47`) — **Status:** `APLICÁVEL`. Confiança: MÁXIMA.
- **Proposta Decisão PO (Nível II):** Propor `APROVADO` (`da18a9ff`) — Suportado pelo registro textual `PO_HOMOLOGOU`. Confiança: ALTA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `MEDIO` — **Status:** `ADIAR`.

---

### LOTE 6 (1 Issue) — Demanda Ativa CH-DATA-01

#### 26. Issue #62 — `CH-DATA-01 — Regularização auditável dos campos do Project #2`
- **Card ID:** `PVTI_lAHOBsbaWM4Bnmd9zhGtvdU` | **GitHub State:** `OPEN` | **Status Project:** `Todo`
- **Valores Atuais:** `Etapa CH`: null | `Esteira`: null | `Autonomia CH`: null | `Decisao PO`: null
- **Evidência Factual:** [Ordem de serviço #62](https://github.com/hallanbrito/CHDevFlow/issues/62) aberta pelo PO em 06/11/2026: "Demanda selecionada pelo PO: CH-DATA-01. Fase atual: CH-1, somente leitura."
- **Proposta Core (Nível I):**
  - `Etapa CH`: Propor `EM_EXECUCAO` (`7d63bd08`) — **Status:** `APLICÁVEL` (reflete a execução da fase CH-1). Confiança: MÁXIMA.
  - `Esteira`: Propor `AGY` (`cb7f46ed`) — **Status:** `APLICÁVEL` (Peão é o executor atribuído). Confiança: MÁXIMA.
  - `Autonomia CH`: Propor `CH-1` (`446303b1`) — **Status:** `APLICÁVEL` (fase autorizada CH-1). Confiança: MÁXIMA.
- **Proposta Decisão PO (Nível II):** Propor `PENDENTE` (`36521eed`) — **Status:** `APLICÁVEL` (aguarda revisão e autorização de lote). Confiança: MÁXIMA.
- **Campos Complementares (Nível III):** `Prioridade CH`: `P1`, `Risco CH`: `BAIXO` — **Status:** `ADIAR`.

---

## 5. Pré-condições Atômicas e Protocolo de Escrita Segura (P1 da Auditoria)

Em resposta direta ao item 4 e 5 da auditoria independente:

1. **Rejeição de Pré-condição Global Ingênua:**
   A pré-condição de escrita **não exigirá** a imutabilidade global do digest do snapshot de 31 itens, pois a criação de uma nova issue no repositório alteraria o hash do projeto sem invalidar as propostas locais do lote.
2. **Pré-condições Obrigatórias Atômicas por Item e Campo:**
   Para cada mutação autorizada pelo PO a ser executada em CH-2:
   - **Verificação de Identidade:** O `card_id` retornado pela API deve ser idêntico ao registrado nesta matriz.
   - **Verificação de Valor Atual Vazio:** O campo alvo deve conter valor nulo / `NÃO_OBSERVADO`. Se o campo já contiver qualquer valor no momento da escrita, a mutação para aquele item deve ser **imediatamente abortada (fail-closed)**.
   - **Read-Back Pós-Escrita:** Após cada mutação individual, a ferramenta deve ler de volta o campo atualizado e confirmar que o valor gravado corresponde exatamente ao `option_id` autorizado.
3. **Rollback Seguro Baseado em Estado Prévio:**
   - O comando de rollback (`clearProjectV2ItemFieldValue`) só pode ser invocado se for comprovado que o valor atual no campo ainda corresponde à mutação recém-aplicada, **evitando apagar edições manuais posteriores realizadas pelo PO**.
4. **Governança da Ferramenta de Mutação (Sem GraphQL Ad Hoc):**
   - Nenhuma escrita será realizada via scripts ad hoc não auditados. A ferramenta de automação para a fase CH-2 deverá estender os contratos seguros de `scripts/ch_project_assist.py` ou passar por auditoria independente de segurança com aprovação expressa do PO antes de qualquer disparo.

---

## 6. Proposta Preventiva para Futura Fatia CH-GOV-01 (Gate de Entrada)

A inclusão imediata da Issue #62 no Project #2 com os três campos core vazios evidencia uma lacuna estrutural no fluxo de entrada de demandas:
- **Diagnóstico:** O webhook GitHub Actions atual adiciona automaticamente qualquer issue com `ch:workflow` ao Project #2, mas não inicializa `Etapa CH`, `Esteira` ou `Autonomia CH`.
- **Recomendação:** Formalizar a demanda **CH-GOV-01 (Gate de Entrada de Governança)** para:
  1. Integrar validação preventiva de entrada (ex: via CLI `ch project assist` ou automação somente leitura em n8n/workflow);
  2. Inicializar cartões recém-criados automaticamente em `Etapa CH = BACKLOG` e `Autonomia CH = CH-0` (fail-closed);
  3. Prevenir a reincidência de cartões com dados insuficientes no momento da criação.
