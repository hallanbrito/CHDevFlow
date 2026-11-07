# Matriz de Regularização Auditável dos Campos do GitHub Project #2 — CH-DATA-01

> **Documento Normativo Consultivo (Fase CH-1 — Somente Leitura)**  
> **Missão:** [Issue #62 — CH-DATA-01](https://github.com/hallanbrito/CHDevFlow/issues/62)  
> **Executor Declarado:** Google Antigravity (AGY) / Peão  
> **Revisor Independente:** ChatGPT  
> **Decisor:** Product Owner Hallan  
> **Nível de Autonomia:** CH-1 (Somente leitura e proposta consultiva. Nenhuma mutação foi aplicada ao Project #2.)  
> **Data do Snapshot LIVE:** 2026-11-07T01:40:45Z  
> **Digest SHA-256 do Snapshot:** `5b468ac46c0895ffc9631caea4afffae869b553d8c8c1c586688b1ecd2f12f06`  
> **Ferramenta de Extração:** `scripts/ch_project_export.py`  

---

## 1. Sumário Executivo do Snapshot LIVE

Em 07/11/2026 (01:40:45 UTC), extraímos o snapshot integral do GitHub Project #2 (`hallanbrito/projects/2`) utilizando o exportador oficial `scripts/ch_project_export.py` sob governança fail-closed.

- **Total de Cartões Recebidos:** 31 / 31 reportados (integridade 100% confirmada).
- **Total de Campos Recebidos:** 19 / 19 reportados (esquema íntegro).
- **Unicidade de Card IDs:** Aprovada (0 anomalias de duplicação).
- **População de Issues:**
  - **5 Issues** possuem cadastro core completo (`Etapa CH`, `Esteira`, `Autonomia CH`): `#2`, `#6`, `#7`, `#58`, `#59`.
  - **26 Issues** possuem pelo menos um campo core não preenchido (`NÃO_OBSERVADO`). Destas, 25 são as herdadas do diagnóstico F0 e 1 é a nova Issue `#62` (CH-DATA-01).
- **Campos de Governança Complementar (`Prioridade CH`, `Risco CH`, `Decisao PO`):** Encontram-se como `NÃO_OBSERVADO` em todos os 31 itens do projeto.

---

## 2. Catálogo Canônico de Campos e Opções do Project #2

| Campo | ID do Campo no GitHub | Tipo | Opções Válidas e seus IDs Canônicos |
|---|---|---|---|
| **Etapa CH** | `PVTSSF_lAHOBsbaWM4Bnmd9zhmKTLs` | Single Select | `BACKLOG` (`0226f1e2`), `PRONTA` (`974bae3f`), `EM_EXECUCAO` (`7d63bd08`), `EM_REVISAO` (`e0b51e89`), `AGUARDANDO_PO` (`25d7d572`), `APROVADA` (`0fcdecd7`), `PARCIAL` (`6d5f86f8`), `CORRECOES` (`d2b85773`), `REPROVADA` (`5987593c`), `INTEGRADA` (`29382ca9`), `HOMOLOGADA` (`6527cf07`) |
| **Esteira** | `PVTSSF_lAHOBsbaWM4Bnmd9zhmKTL4` | Single Select | `Hallan` (`0bfba1bb`), `ChatGPT` (`b31ae0fa`), `Codex` (`3fee45a7`), `AGY` (`cb7f46ed`) |
| **Autonomia CH** | `PVTSSF_lAHOBsbaWM4Bnmd9zhmKTN0` | Single Select | `CH-0` (`d04f05f0`), `CH-1` (`446303b1`), `CH-2` (`d65d7f47`), `CH-3` (`ff83f5f7`) |
| **Prioridade CH** | `PVTSSF_lAHOBsbaWM4Bnmd9zhmKTM0` | Single Select | `P0` (`e970b069`), `P1` (`bb365bbf`), `P2` (`fd754fe5`), `P3` (`0465aa3f`) |
| **Risco CH** | `PVTSSF_lAHOBsbaWM4Bnmd9zhmKTNc` | Single Select | `BAIXO` (`0a016dc9`), `MEDIO` (`49fde1c0`), `ALTO` (`d1b6fc16`), `CRITICO` (`1240f852`) |
| **Decisao PO** | `PVTSSF_lAHOBsbaWM4Bnmd9zhmKTN4` | Single Select | `PENDENTE` (`36521eed`), `APROVADO` (`da18a9ff`), `PARCIAL` (`6429cc22`), `AJUSTES` (`f01270d6`), `REPROVADO` (`c245c8ff`) |

---

## 3. Categorização das Ações e Regras de Segurança

Em estrita observância à Ordem de Serviço #62:
1. **Regra de Não-Sobrescrita:** Campos já preenchidos legitimamente são mantidos intactos (`PRESERVAR`).
2. **Sem Fabricação de Homologação:** A etapa `INTEGRADA` no Project não é automaticamente promovida para `HOMOLOGADA`, exceto onde há prova documental inequívoca e expressa de homologação assinada pelo PO.
3. **Sem Inferência Retrospectiva de Permissão:** O preenchimento de `Autonomia CH` documenta o nível sob o qual a missão operou; não autoriza execuções passadas nem futuras.
4. **Categorias de Classificação:**
   - **(A) Preenchimento Seguro e Comprovável:** Dados suportados por PR integrada e decisão documentada.
   - **(B) Valores de Governança / Autonomia CH:** Registro formal do nível de autonomia CH autorizado.
   - **(C) Etapa CH Controvertida:** Casos onde a etapa depende de deliberação do PO (ex: épicos abertos com sub-tarefas integradas).
   - **(D) Antigos Testes / Arquivamento:** Itens experimentais que podem ser arquivados ou mantidos documentais.

---

## 4. Matriz Dividida em Lotes de até 5 Issues

### Lote 1 — Transição Inicial e Testes Fundacionais (#5, #8, #10, #12, #13)

| Campo | Issue #5 | Issue #8 | Issue #10 | Issue #12 | Issue #13 |
|---|---|---|---|---|---|
| **URL da Issue** | [#5](https://github.com/hallanbrito/CHDevFlow/issues/5) | [#8](https://github.com/hallanbrito/CHDevFlow/issues/8) | [#10](https://github.com/hallanbrito/CHDevFlow/issues/10) | [#12](https://github.com/hallanbrito/CHDevFlow/issues/12) | [#13](https://github.com/hallanbrito/CHDevFlow/issues/13) |
| **Project Card ID** | `PVTI_lAHOBsbaWM4Bnmd9zhBnlhQ` | `PVTI_lAHOBsbaWM4Bnmd9zhBoCZM` | `PVTI_lAHOBsbaWM4Bnmd9zhBob5k` | `PVTI_lAHOBsbaWM4Bnmd9zhBot8U` | `PVTI_lAHOBsbaWM4Bnmd9zhBo44A` |
| **Título** | [TESTE W1] Validar inclusão automática | W2-A — Especificação documental despachante | CH-SEC-01 — Preparar proteção da main | P0-CODEX — Testar leitura Kanban (CH-0) | P0-AGY — Testar leitura offline (CH-0) |
| **Status GitHub / Project** | `CLOSED` / `Done` | `OPEN` / `Todo` | `OPEN` / `Todo` | `CLOSED` / `Done` | `CLOSED` / `Done` |
| **Etapa CH Atual → Proposta** | `NÃO_OBSERVADO` → `HOMOLOGADA` (`6527cf07`) | `INTEGRADA` → `INTEGRADA` (PRESERVAR) | `BACKLOG` → `BACKLOG` (PRESERVAR) | `HOMOLOGADA` → `HOMOLOGADA` (PRESERVAR) | `HOMOLOGADA` → `HOMOLOGADA` (PRESERVAR) |
| **Esteira Atual → Proposta** | `NÃO_OBSERVADO` → `Hallan` (`0bfba1bb`) | `ChatGPT` → `ChatGPT` (PRESERVAR) | `Hallan` → `Hallan` (PRESERVAR) | `Codex` → `Codex` (PRESERVAR) | `AGY` → `AGY` (PRESERVAR) |
| **Autonomia Atual → Proposta** | `NÃO_OBSERVADO` → `CH-0` (`d04f05f0`) | `NÃO_OBSERVADO` → `CH-1` (`446303b1`) | `NÃO_OBSERVADO` → `CH-0` (`d04f05f0`) | `NÃO_OBSERVADO` → `CH-0` (`d04f05f0`) | `NÃO_OBSERVADO` → `CH-0` (`d04f05f0`) |
| **Prioridade Atual → Proposta** | `NÃO_OBSERVADO` → `P3` (`0465aa3f`) | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) | `NÃO_OBSERVADO` → `P0` (`e970b069`) | `NÃO_OBSERVADO` → `P0` (`e970b069`) | `NÃO_OBSERVADO` → `P0` (`e970b069`) |
| **Risco Atual → Proposta** | `NÃO_OBSERVADO` → `BAIXO` (`0a016dc9`) | `NÃO_OBSERVADO` → `BAIXO` (`0a016dc9`) | `NÃO_OBSERVADO` → `ALTO` (`d1b6fc16`) | `NÃO_OBSERVADO` → `BAIXO` (`0a016dc9`) | `NÃO_OBSERVADO` → `BAIXO` (`0a016dc9`) |
| **Decisão PO Atual → Proposta** | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `PENDENTE` (`36521eed`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) |
| **Fonte da Evidência** | [Comentário PO #6250735633](https://github.com/hallanbrito/CHDevFlow/issues/5#issuecomment-6250735633) | PR #9 merged (`313a5ef`) e [comentário PO #6251707916](https://github.com/hallanbrito/CHDevFlow/issues/8#issuecomment-6251707916) | Issue #10 aberta pelo PO; Draft PR #11 | [Comentário PO formalizando homologação](https://github.com/hallanbrito/CHDevFlow/issues/12#issuecomment-6251508201) | [Comentário PO formalizando homologação](https://github.com/hallanbrito/CHDevFlow/issues/13#issuecomment-6251508302) |
| **Confiança / Risco** | ALTA / BAIXO | MÁXIMA / BAIXO | ALTA / MÉDIO | MÁXIMA / BAIXO | MÁXIMA / BAIXO |
| **Categoria da Ação** | (D) Teste antigo | (A) Preenchimento comprovável | (B) Governança (preserva BACKLOG) | (A) Homologação expressa | (A) Homologação expressa |
| **Ação Recomendada** | **PROPOR** (ou arquivar card) | **PROPOR** | **PROPOR** | **PROPOR** | **PROPOR** |

---

### Lote 2 — Sincronização do Kanban e Governança RUC (#14, #16, #18, #19, #21)

| Campo | Issue #14 | Issue #16 | Issue #18 | Issue #19 | Issue #21 |
|---|---|---|---|---|---|
| **URL da Issue** | [#14](https://github.com/hallanbrito/CHDevFlow/issues/14) | [#16](https://github.com/hallanbrito/CHDevFlow/issues/16) | [#18](https://github.com/hallanbrito/CHDevFlow/issues/18) | [#19](https://github.com/hallanbrito/CHDevFlow/issues/19) | [#21](https://github.com/hallanbrito/CHDevFlow/issues/21) |
| **Project Card ID** | `PVTI_lAHOBsbaWM4Bnmd9zhBo_SY` | `PVTI_lAHOBsbaWM4Bnmd9zhBpFjQ` | `PVTI_lAHOBsbaWM4Bnmd9zhBqUV8` | `PVTI_lAHOBsbaWM4Bnmd9zhBsQKA` | `PVTI_lAHOBsbaWM4Bnmd9zhB5o9E` |
| **Título** | RUC-01 — Relatório Universal C.H. v1.0 | KSYNC-01 — Automatizar esteiras e BACKLOG | KSYNC-02 — Planejar sincronização segura | KSYNC-03 — Automação assistida do Kanban | KSYNC-03.1 — Reconciliação inteligente |
| **Status GitHub / Project** | `CLOSED` / `Done` | `CLOSED` / `Done` | `CLOSED` / `Done` | `OPEN` / `Todo` | `OPEN` / `Todo` |
| **Etapa CH Atual → Proposta** | `HOMOLOGADA` (PRESERVAR) | `HOMOLOGADA` (PRESERVAR) | `INTEGRADA` (PRESERVAR) | `INTEGRADA` (PRESERVAR) | `INTEGRADA` (PRESERVAR) |
| **Esteira Atual → Proposta** | `ChatGPT` (PRESERVAR) | `ChatGPT` (PRESERVAR) | `ChatGPT` (PRESERVAR) | `ChatGPT` (PRESERVAR) | `ChatGPT` (PRESERVAR) |
| **Autonomia Atual → Proposta** | `NÃO_OBSERVADO` → `CH-1` (`446303b1`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-1` (`446303b1`) | `NÃO_OBSERVADO` → `CH-1` (`446303b1`) | `NÃO_OBSERVADO` → `CH-1` (`446303b1`) |
| **Prioridade Atual → Proposta** | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) | `NÃO_OBSERVADO` → `P2` (`fd754fe5`) | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) |
| **Risco Atual → Proposta** | `NÃO_OBSERVADO` → `BAIXO` (`0a016dc9`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `BAIXO` (`0a016dc9`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) |
| **Decisão PO Atual → Proposta** | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) |
| **Fonte da Evidência** | PR #15 merged (`b28905a`) por hallanbrito | PR #17 merged (`f19baef`) por hallanbrito | Issue fechada como planejamento concluído | PR #20 merged (`e51ef3a`) por hallanbrito | PR #22 merged (`8e12361`) por hallanbrito |
| **Confiança / Risco** | MÁXIMA / BAIXO | MÁXIMA / BAIXO | MÁXIMA / BAIXO | MÁXIMA / BAIXO | MÁXIMA / BAIXO |
| **Categoria da Ação** | (A) Preenchimento comprovável | (A) Preenchimento comprovável | (A) Preenchimento comprovável | (A) Preenchimento comprovável | (A) Preenchimento comprovável |
| **Ação Recomendada** | **PROPOR** | **PROPOR** | **PROPOR** | **PROPOR** | **PROPOR** |

---

### Lote 3 — Bootstrap Engine, Auditorias e Fundação CLI (#24, #27, #28, #29, #32)

| Campo | Issue #24 | Issue #27 | Issue #28 | Issue #29 | Issue #32 |
|---|---|---|---|---|---|
| **URL da Issue** | [#24](https://github.com/hallanbrito/CHDevFlow/issues/24) | [#27](https://github.com/hallanbrito/CHDevFlow/issues/27) | [#28](https://github.com/hallanbrito/CHDevFlow/issues/28) | [#29](https://github.com/hallanbrito/CHDevFlow/issues/29) | [#32](https://github.com/hallanbrito/CHDevFlow/issues/32) |
| **Project Card ID** | `PVTI_lAHOBsbaWM4Bnmd9zhB9jIc` | `PVTI_lAHOBsbaWM4Bnmd9zhB-X28` | `PVTI_lAHOBsbaWM4Bnmd9zhCLqME` | `PVTI_lAHOBsbaWM4Bnmd9zhCNaiA` | `PVTI_lAHOBsbaWM4Bnmd9zhDDnJU` |
| **Título** | BOOT-00 — Contratos do motor Bootstrap | AGY-BOOT01-AUD01 — Corrigir fallback | KSYNC-INV-01 — Inventário read-only | CH-REC-01 — Reconciliação integral | CLI-00 — CHDevFlow CLI v0.1: transformar |
| **Status GitHub / Project** | `OPEN` / `Todo` | `OPEN` / `Todo` | `CLOSED` / `Done` | `CLOSED` / `Done` | `OPEN` / `Todo` |
| **Etapa CH Atual → Proposta** | `AGUARDANDO_PO` (PRESERVAR) | `INTEGRADA` (PRESERVAR) | `HOMOLOGADA` (PRESERVAR) | `HOMOLOGADA` (PRESERVAR) | `NÃO_OBSERVADO` → `INTEGRADA` (`29382ca9`) |
| **Esteira Atual → Proposta** | `ChatGPT` (PRESERVAR) | `AGY` (PRESERVAR) | `AGY` (PRESERVAR) | `ChatGPT` (PRESERVAR) | `AGY` (PRESERVAR) |
| **Autonomia Atual → Proposta** | `NÃO_OBSERVADO` → `CH-1` (`446303b1`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-0` (`d04f05f0`) | `NÃO_OBSERVADO` → `CH-1` (`446303b1`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) |
| **Prioridade Atual → Proposta** | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) | `NÃO_OBSERVADO` → `P0` (`e970b069`) | `NÃO_OBSERVADO` → `P2` (`fd754fe5`) | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) | `NÃO_OBSERVADO` → `P0` (`e970b069`) |
| **Risco Atual → Proposta** | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `BAIXO` (`0a016dc9`) | `NÃO_OBSERVADO` → `BAIXO` (`0a016dc9`) | `NÃO_OBSERVADO` → `ALTO` (`d1b6fc16`) |
| **Decisão PO Atual → Proposta** | `NÃO_OBSERVADO` → `PENDENTE` (`36521eed`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) |
| **Fonte da Evidência** | Draft PR #25 aberto; issue em `AGUARDANDO_PO` | PR #26 merged (`359ef1b`) por hallanbrito | Inventário read-only concluído e aceito | Reconciliação concluída e aceita | PR #39 consolidado da CLI v0.1 merged (`ea50d49`) |
| **Confiança / Risco** | MÁXIMA / BAIXO (preserva gate) | MÁXIMA / BAIXO | MÁXIMA / BAIXO | MÁXIMA / BAIXO | ALTA / MÉDIO |
| **Categoria da Ação** | (B) Governança (sem promoção) | (A) Preenchimento comprovável | (A) Preenchimento comprovável | (A) Preenchimento comprovável | (C) Épico integrado na main |
| **Ação Recomendada** | **PROPOR** | **PROPOR** | **PROPOR** | **PROPOR** | **PROPOR** (ou HOMOLOGADA sob PO) |

---

### Lote 4 — Fatias da CLI v0.1 (#33, #34, #35, #36, #37)

| Campo | Issue #33 | Issue #34 | Issue #35 | Issue #36 | Issue #37 |
|---|---|---|---|---|---|
| **URL da Issue** | [#33](https://github.com/hallanbrito/CHDevFlow/issues/33) | [#34](https://github.com/hallanbrito/CHDevFlow/issues/34) | [#35](https://github.com/hallanbrito/CHDevFlow/issues/35) | [#36](https://github.com/hallanbrito/CHDevFlow/issues/36) | [#37](https://github.com/hallanbrito/CHDevFlow/issues/37) |
| **Project Card ID** | `PVTI_lAHOBsbaWM4Bnmd9zhDDnlw` | `PVTI_lAHOBsbaWM4Bnmd9zhDDnno` | `PVTI_lAHOBsbaWM4Bnmd9zhDDnpA` | `PVTI_lAHOBsbaWM4Bnmd9zhDDnqc` | `PVTI_lAHOBsbaWM4Bnmd9zhDDnsk` |
| **Título** | CLI-01 — Empacotamento e núcleo inicial | CLI-02 — Manifesto, ch new e ch status | CLI-03 — ch doctor e adapters de stack | CLI-04 — ch verify e evidências | CLI-05 — ch mission, ch ruc e ch submit |
| **Status GitHub / Project** | `OPEN` / `Todo` | `OPEN` / `Todo` | `OPEN` / `Todo` | `OPEN` / `Todo` | `OPEN` / `Todo` |
| **Etapa CH Atual → Proposta** | `INTEGRADA` (PRESERVAR) | `INTEGRADA` (PRESERVAR) | `INTEGRADA` (PRESERVAR) | `INTEGRADA` (PRESERVAR) | `INTEGRADA` (PRESERVAR) |
| **Esteira Atual → Proposta** | `AGY` (PRESERVAR) | `AGY` (PRESERVAR) | `AGY` (PRESERVAR) | `AGY` (PRESERVAR) | `AGY` (PRESERVAR) |
| **Autonomia Atual → Proposta** | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) |
| **Prioridade Atual → Proposta** | `NÃO_OBSERVADO` → `P0` (`e970b069`) | `NÃO_OBSERVADO` → `P0` (`e970b069`) | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) | `NÃO_OBSERVADO` → `P0` (`e970b069`) | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) |
| **Risco Atual → Proposta** | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) |
| **Decisão PO Atual → Proposta** | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) |
| **Fonte da Evidência** | PR #39 merged na main (`ea50d49`); RUC-CLI-01 | PR #39 merged na main (`ea50d49`); RUC-CLI-02 | PR #39 merged na main (`ea50d49`); RUC-CLI-03 | PR #39 merged na main (`ea50d49`); RUC-CLI-04 | PR #39 merged na main (`ea50d49`); RUC-CLI-05 |
| **Confiança / Risco** | MÁXIMA / BAIXO | MÁXIMA / BAIXO | MÁXIMA / BAIXO | MÁXIMA / BAIXO | MÁXIMA / BAIXO |
| **Categoria da Ação** | (A) Preenchimento comprovável | (A) Preenchimento comprovável | (A) Preenchimento comprovável | (A) Preenchimento comprovável | (A) Preenchimento comprovável |
| **Ação Recomendada** | **PROPOR** | **PROPOR** | **PROPOR** | **PROPOR** | **PROPOR** |

---

### Lote 5 — CLI Final, Auditoria Geral e Despachante W2-B (#38, #40, #41, #54, #56)

| Campo | Issue #38 | Issue #40 | Issue #41 | Issue #54 | Issue #56 |
|---|---|---|---|---|---|
| **URL da Issue** | [#38](https://github.com/hallanbrito/CHDevFlow/issues/38) | [#40](https://github.com/hallanbrito/CHDevFlow/issues/40) | [#41](https://github.com/hallanbrito/CHDevFlow/issues/41) | [#54](https://github.com/hallanbrito/CHDevFlow/issues/54) | [#56](https://github.com/hallanbrito/CHDevFlow/issues/56) |
| **Project Card ID** | `PVTI_lAHOBsbaWM4Bnmd9zhDDnus` | `PVTI_lAHOBsbaWM4Bnmd9zhDOUQ4` | `PVTI_lAHOBsbaWM4Bnmd9zhDOUZk` | `PVTI_lAHOBsbaWM4Bnmd9zhGV8xI` | `PVTI_lAHOBsbaWM4Bnmd9zhGXa-M` |
| **Título** | CLI-06 — ch watch e ensaio E2E | AUD-GERAL-01 — Estabilização v0.1.0 | AUD-GERAL-P0-01 — Status estrito | P1-CLI-REMOTE-01 — Falha remota ch mission | W2-B — Dispatcher Codex + Peão |
| **Status GitHub / Project** | `OPEN` / `Todo` | `OPEN` / `Todo` | `CLOSED` / `Done` | `OPEN` / `Todo` | `OPEN` / `Todo` |
| **Etapa CH Atual → Proposta** | `INTEGRADA` (PRESERVAR) | `NÃO_OBSERVADO` → `EM_EXECUCAO` (`7d63bd08`) | `INTEGRADA` (PRESERVAR) | `NÃO_OBSERVADO` → `HOMOLOGADA` (`6527cf07`) | `NÃO_OBSERVADO` → `HOMOLOGADA` (`6527cf07`) |
| **Esteira Atual → Proposta** | `AGY` (PRESERVAR) | `AGY` (PRESERVAR) | `AGY` (PRESERVAR) | `NÃO_OBSERVADO` → `AGY` (`cb7f46ed`) | `NÃO_OBSERVADO` → `Codex` (`3fee45a7`) |
| **Autonomia Atual → Proposta** | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) | `NÃO_OBSERVADO` → `CH-2` (`d65d7f47`) |
| **Prioridade Atual → Proposta** | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) | `NÃO_OBSERVADO` → `P0` (`e970b069`) | `NÃO_OBSERVADO` → `P0` (`e970b069`) | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) |
| **Risco Atual → Proposta** | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `ALTO` (`d1b6fc16`) | `NÃO_OBSERVADO` → `ALTO` (`d1b6fc16`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) | `NÃO_OBSERVADO` → `MEDIO` (`49fde1c0`) |
| **Decisão PO Atual → Proposta** | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `PENDENTE` (`36521eed`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) | `NÃO_OBSERVADO` → `APROVADO` (`da18a9ff`) |
| **Fonte da Evidência** | PR #39 merged (`ea50d49`); RUC-CLI-06 | Épico aberto para P1 conforme comentário PO | PR #42 merged (`80fce9d`) por hallanbrito | PR #55 merged (`ffadabe`); [Gate formal do PO](https://github.com/hallanbrito/CHDevFlow/issues/54#issuecomment-6691452291) | PR #57 merged (`f8eea14`); [Encerramento e homologação do PO](https://github.com/hallanbrito/CHDevFlow/issues/56#issuecomment-6692250102) |
| **Confiança / Risco** | MÁXIMA / BAIXO | ALTA / MÉDIO | MÁXIMA / BAIXO | MÁXIMA / BAIXO | MÁXIMA / BAIXO |
| **Categoria da Ação** | (A) Preenchimento comprovável | (C) Épico aberto com P0 integrado | (A) Preenchimento comprovável | (A) Homologação formal expressa | (A) Homologação formal expressa |
| **Ação Recomendada** | **PROPOR** | **PROPOR** | **PROPOR** | **PROPOR** | **PROPOR** |

---

### Lote 6 — Regularização da Governança Atual (#62)

| Campo | Issue #62 |
|---|---|
| **URL da Issue** | [#62](https://github.com/hallanbrito/CHDevFlow/issues/62) |
| **Project Card ID** | `PVTI_lAHOBsbaWM4Bnmd9zhGtvdU` |
| **Título** | CH-DATA-01 — Regularização auditável dos campos do Project #2 |
| **Status GitHub / Project** | `OPEN` / `Todo` |
| **Etapa CH Atual → Proposta** | `NÃO_OBSERVADO` → `EM_EXECUCAO` (`7d63bd08`) |
| **Esteira Atual → Proposta** | `NÃO_OBSERVADO` → `AGY` (`cb7f46ed`) |
| **Autonomia Atual → Proposta** | `NÃO_OBSERVADO` → `CH-1` (`446303b1`) |
| **Prioridade Atual → Proposta** | `NÃO_OBSERVADO` → `P1` (`bb365bbf`) |
| **Risco Atual → Proposta** | `NÃO_OBSERVADO` → `BAIXO` (`0a016dc9`) |
| **Decisão PO Atual → Proposta** | `NÃO_OBSERVADO` → `PENDENTE` (`36521eed`) |
| **Fonte da Evidência** | [Ordem de serviço #62](https://github.com/hallanbrito/CHDevFlow/issues/62) pelo PO: autorização CH-1 para Peão/AGY |
| **Confiança / Risco** | MÁXIMA / BAIXO (somente leitura) |
| **Categoria da Ação** | (B) Governança ativa em CH-1 |
| **Ação Recomendada** | **PROPOR** |

---

## 5. Pré-condições de Execução e Plano de Rollback

### 5.1 Pré-condições Obrigatórias Antes de Qualquer Escrita (Fase CH-2 Futura)
1. **Verificação de Integridade do Snapshot:**
   Antes de aplicar mutações autorizadas em qualquer lote, a ferramenta de escrita deve executar:
   ```bash
   python3 scripts/ch_project_export.py --validate-only
   ```
   Se o total de cartões diferir de 31 ou o digest divergir de `5b468ac46c0895ffc9631caea4afffae869b553d8c8c1c586688b1ecd2f12f06`, a operação deve **ABORTAR IMEDIATAMENTE (fail-closed)** solicitando nova revisão.
2. **Checagem de Campo Vazio (Sem Sobrescrita):**
   A ferramenta de mutação deve confirmar que cada campo a ser preenchido encontra-se estritamente vazio (`NÃO_OBSERVADO` / null). Se qualquer campo já contiver valor no momento da escrita, a mutação para aquele item deve ser interrompida.
3. **Autorização Específica por Lote:**
   Nenhum lote pode ser executado sem a aprovação prévia expressa do PO contendo a lista exata dos campos autorizados.

### 5.2 Plano de Rollback Determinístico Campo-a-Campo
Como todos os campos alvos da proposta encontram-se atualmente vazios (`NÃO_OBSERVADO` / null), o rollback determinístico consiste na remoção do valor atribuído via API GraphQL do GitHub Projects (`clearProjectV2ItemFieldValue`), retornando o campo ao estado nulo original:

```graphql
mutation ClearField($projectId: ID!, $itemId: ID!, $fieldId: ID!) {
  clearProjectV2ItemFieldValue(input: {
    projectId: $projectId
    itemId: $itemId
    fieldId: $fieldId
  }) {
    projectV2Item { id }
  }
}
```

O snapshot `.ch_sentinela/project_snapshot.json` gravado em 07/11/2026 às 01:40:45Z serve como baseline criptográfico inalterável do estado prévio para fins de auditoria e restauração.
