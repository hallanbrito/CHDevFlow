# RUC/1.0 — CH-DATA-01 — Regularização Auditável dos Campos do Project #2 (Revisão R1)

> Formato baseado nas diretrizes do Método C.H. e políticas de governança do CHDevFlow. Sem inferência de homologação tácita.

**Cabeçalho:**
- **Missão/Issue:** [Issue #62 — CH-DATA-01](https://github.com/hallanbrito/CHDevFlow/issues/62)
- **Revisão:** R1 após auditoria independente ChatGPT ([comentário #6700637806](https://github.com/hallanbrito/CHDevFlow/issues/62#issuecomment-6700637806))
- **Executor Declarado:** Google Antigravity (AGY) / Peão
- **Coordenação/Auditoria Independente:** ChatGPT
- **Decisão Final:** Product Owner Hallan (exclusiva para deliberação de lotes e homologação)
- **Autonomia e Prova:** CH-1 (Somente leitura e proposta documental) autorizada expressamente na Ordem de Serviço #62
- **Ambiente:** Linux (CachyOS x86_64), Python 3.13 / UV, worktree isolada, branch `agy/ch-data-01`
- **Nota de Governança da Branch:** A branch `agy/ch-data-01` foi derivada da branch `agy/cc-quality-01` (PR #61 / PR #60 empilhada) e possui commits à frente de `main`. Em estrito fail-closed, **esta branch não criará PR de integração contra a `main`** sem o prévio isolamento dos documentos ou desempilhamento da base.
- **Fonte de Dados:** `LIVE_GITHUB` (GitHub Project #2 exportado via `scripts/ch_project_export.py`)
- **Snapshot SHA-256:** `5b468ac46c0895ffc9631caea4afffae869b553d8c8c1c586688b1ecd2f12f06` (Capturado em 2026-11-07T01:40:45Z)
- **Timestamp da R1:** 2026-11-06T22:58:00-03:00
- **Resultado Técnico:** APROVADO_TECNICAMENTE (Fase CH-1 documental reformulada)
- **Custo Adicional Comprovado:** R$ 0,00
- **Estado Formal:** `READY_FOR_CHATGPT_REVIEW`

---

## 1. Identificação e Escopo Autorizado

A presente revisão R1 atende integralmente às exigências da auditoria independente ([comentário #6700637806](https://github.com/hallanbrito/CHDevFlow/issues/62#issuecomment-6700637806)), sanando as inconsistências preliminares:
1. **Correção de Referência SHA:** Retificada a divergência de hash para o HEAD auditado real da branch `agy/ch-data-01`.
2. **Reconciliação F0 $\rightarrow$ LIVE:** Documentadas e explicadas as diferenças de títulos e Card IDs entre o diagnóstico preliminar F0 e o snapshot canônico LIVE.
3. **Desacoplamento e Hierarquia de Campos:**
   - **Nível I (Core Obrigatório):** `Etapa CH`, `Esteira` e `Autonomia CH` (necessários para o Grafo DAG).
   - **Nível II (Gate do PO):** `Decisao PO` restrita a `PENDENTE` em todas as tarefas onde não há declaração textual expressa e nominal do PO aprovando a homologação (ex.: diferenciando #54 de #56).
   - **Nível III (Governança Complementar):** `Prioridade CH` e `Risco CH` separados como opcionais consultivos, classificados como `ADIAR` para não inflar o escopo do DAG.
4. **Autonomia Histórica vs Permissão Vigente:** Definido que `Autonomia CH` registra unicamente o nível sob o qual a missão pretérita foi executada, sem conceder autorização retrospectiva ou executiva presente.
5. **Pré-condições Atômicas por Item:** Substituição da condicionante ingênua de snapshot global por checagem atômica de `card_id`, campo nulo no momento da escrita, read-back de confirmação e rollback baseado no estado anterior.
6. **Alerta de Entrada e CH-GOV-01:** Registro da anomalia de entrada da Issue #62 e recomendação de gate preventivo.

---

## 2. Reconciliação F0 $\rightarrow$ LIVE

O diagnóstico F0 (`docs/control-center/DIAGNOSTICO-F0-CC-QUALITY-01.md`), realizado sob estrito orçamento temporal de 30s, utilizou aproximações manuais em certos títulos e Card IDs. O snapshot extraído pelo `ch_project_export.py` em 07/11/2026 (01:40:45Z) representa a verdade factual canônica:

- **Issues Reconciliadas:** #5, #6, #7, #8, #10, #12, #13, #14, #16, #18, #19, #21, #24, #27, #28, #29, #32 a #38, #40, #54, #56.
- **Card IDs de GraphQL:** Os identificadores canônicos no formato `PVTI_...` foram extraídos diretamente da API GraphQL e mapeados de forma biunívoca a cada Issue em `MATRIZ-CH-DATA-01.md`.
- **Nova Issue #62:** Ausente no F0, incluída no LIVE com Card ID `PVTI_lAHOBsbaWM4Bnmd9zhGtvdU`.

---

## 3. Tabela de Evidências Verificáveis

| ID | Classe | Fonte / Referência | Fato Observado e Limite |
|---|---|---|---|
| **E01** | OBSERVADO | Ordem de serviço [Issue #62](https://github.com/hallanbrito/CHDevFlow/issues/62) | Autorização expressa CH-1 para Peão/AGY elaborar inventário e matriz de correção sem mutações. |
| **E02** | OBSERVADO | Parecer de Auditoria ChatGPT [#6700637806](https://github.com/hallanbrito/CHDevFlow/issues/62#issuecomment-6700637806) | Auditoria independente apontando as correções necessárias para a R1 documental. |
| **E03** | OBSERVADO | Snapshot LIVE `project_snapshot.json` | 31 itens, 19 campos, 0 anomalias de ID, digest `5b468ac46c0895ffc9631caea4afffae869b553d8c8c1c586688b1ecd2f12f06`. |
| **E04** | OBSERVADO | `docs/control-center/MATRIZ-CH-DATA-01.md` (R1) | Matriz reformulada com 3 níveis de campos, 6 lotes, pré-condições atômicas e fontes nominais de evidência. |
| **E05** | OBSERVADO | Comentário PO na Issue #54 (`6666235173`) | Comprova literalmente `INTEGRADA_NA_MAIN / AGUARDANDO_HOMOLOGACAO_POS_MERGE_SE_APLICAVEL`. Impede classificar como HOMOLOGADA. |
| **E06** | OBSERVADO | Comentário PO na Issue #56 (`6692250102`) | Comprova literalmente `INTEGRADA_NA_MAIN / PO_HOMOLOGOU`. Permite classificar como HOMOLOGADA. |
| **E07** | OBSERVADO | Comentário PO na Issue #8 (`6251707916`) | Comprova que a proposta da W2-A foi integrada na main, mas sua homologação técnica permanece separada. Mantém INTEGRADA. |
| **E08** | OBSERVADO | Comentário PO na Issue #40 | Comprova que o épico de auditoria permanece OPEN para o backlog P1. Proíbe classificar como HOMOLOGADA; propõe EM_EXECUCAO. |
| **E09** | OBSERVADO | `git status` na branch `agy/ch-data-01` | Worktree limpa, sem mutações em código de produto ou produção. |

---

## 4. Estrutura Reformulada dos 6 Lotes

| Lote | Escopo | Issues | Destaques de Governança R1 |
|---|---|---|---|
| **Lote 1** | Fundação e Testes | #5, #8, #10, #12, #13 | Preserva `INTEGRADA` em #8 (conforme PO); preserva `BACKLOG` e `CH-0` em #10; #12 e #13 com homologações explícitas; #5 com decisão do PO pendente entre homologar teste ou arquivar card. |
| **Lote 2** | Sincronização Kanban | #14, #16, #18, #19, #21 | Preserva `INTEGRADA` em #18, #19 e #21 com `Decisao PO = PENDENTE`; preenche `Autonomia CH` comprovada (`CH-1` e `CH-2`). |
| **Lote 3** | Sentinela e CLI-00 | #24, #27, #28, #29, #32 | Preserva estritamente `AGUARDANDO_PO` em #24 sem promoção; propõe `INTEGRADA` para o épico #32 com homologação pendente. |
| **Lote 4** | Fatias CLI-01 a CLI-05 | #33, #34, #35, #36, #37 | Preserva `INTEGRADA` em todas (merge PR #39); preenche `Autonomia CH = CH-2`; `Decisao PO = PENDENTE`. |
| **Lote 5** | CLI-06, Auditoria e W2-B | #38, #40, #41, #54, #56 | Propropõe `EM_EXECUCAO` para épico #40 (aberto para P1); propõe estritamente `INTEGRADA` para #54 (aguardando homologação pós-merge conforme PO); propõe `HOMOLOGADA` para #56 (`PO_HOMOLOGOU` comprovado). |
| **Lote 6** | Governança Atual | #62 | Registra CH-DATA-01 em `EM_EXECUCAO`, `AGY`, `CH-1`, `PENDENTE`. |

---

## 5. Avaliação da Regra Fail-Closed do DAG

A regularização documental proposta atua exclusivamente sobre os dados cadastrais do GitHub Project #2.
- O motor do DAG (`DAGEngine`) manterá as tarefas com etapa `HOMOLOGADA` ou `INTEGRADA` como **`BLOQUEADA_DADOS`** enquanto não houver o artefato autenticado de homologação humana exigido pela política R3 (`homologacao_verificada=False`).
- A integridade e a segurança do fluxo permanecem 100% blindadas.

---

## 6. Proposta de Gate Preventivo de Entrada (CH-GOV-01)

A criação da Issue #62 com campos core vazios demonstra a necessidade de um gate de entrada automatizado ou assistido:
- **Proposta:** Criação de uma fatia consultiva `CH-GOV-01` para implementar verificação preventiva na adição de issues ao Project #2, garantindo que cartões entrem com `Etapa CH = BACKLOG`, `Autonomia CH = CH-0` e `Esteira` definida.

---

## 7. Conclusão e Estado Formal

A presente revisão R1 atende rigorosamente a todos os apontamentos da auditoria independente, eliminando qualquer inferência tácita de homologação, reconciliando o histórico F0 vs LIVE e estabelecendo um protocolo atômico e seguro de lote.

- **Draft PR:** Nenhuma PR criada ou mesclada nesta fase.
- **Branch:** [`agy/ch-data-01`](https://github.com/hallanbrito/CHDevFlow/tree/agy/ch-data-01)
- **Custo:** R$ 0,00 mantido.

**Estado Formal:** `READY_FOR_CHATGPT_REVIEW`
