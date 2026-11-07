# RUC/1.0 — CH-DATA-01 — Regularização Auditável dos Campos do Project #2 (Fase CH-1)

> Formato baseado nas diretrizes do Método C.H. e políticas de governança do CHDevFlow. Sem inferência de homologação tácita.

**Cabeçalho:**  
- **Missão/Issue:** [Issue #62 — CH-DATA-01](https://github.com/hallanbrito/CHDevFlow/issues/62)
- **Executor Declarado:** Google Antigravity (AGY) / Peão
- **Coordenação/Auditoria Independente:** ChatGPT (a realizar após entrega)
- **Decisão Final:** Product Owner Hallan (exclusiva para autorização de escritas e homologação)
- **Autonomia e Prova:** CH-1 (Somente leitura) autorizada expressamente na Ordem de Serviço #62
- **Ambiente:** Linux (CachyOS x86_64), Python 3.13 / UV, worktree isolada, branch `agy/ch-data-01`
- **Fonte de Dados:** `LIVE_GITHUB` (GitHub Project #2 exportado via `scripts/ch_project_export.py`)
- **Snapshot SHA-256:** `5b468ac46c0895ffc9631caea4afffae869b553d8c8c1c586688b1ecd2f12f06` (Capturado em 2026-11-07T01:40:45Z)
- **Timestamp:** 2026-11-06T22:45:00-03:00
- **Resultado Técnico:** APROVADO_TECNICAMENTE (Fase CH-1 de inventário e proposição consultiva)
- **Custo Adicional Comprovado:** R$ 0,00
- **Estado Formal:** `READY_FOR_CHATGPT_REVIEW`

---

## 1. Identificação e Escopo Autorizado

A presente entrega cumpre estritamente os requisitos da fase **CH-1 (somente leitura)** estipulados na Ordem de Serviço #62:
- **Atividades Autorizadas Realizadas:**
  1. Extração e validação do snapshot LIVE atualizado do GitHub Project #2 (`hallanbrito/projects/2`) utilizando o exportador oficial `scripts/ch_project_export.py`.
  2. Comparativo formal entre o inventário do diagnóstico F0 (30 issues) e o snapshot LIVE atual (31 issues).
  3. Mapeamento exato de todos os campos e opções válidas do Project #2 com seus identificadores canônicos de GraphQL.
  4. Elaboração da Matriz de Regularização (`MATRIZ-CH-DATA-01.md`) contendo campos atuais, valores propostos, fontes de evidência, nível de confiança, risco, categorização e plano de rollback determinístico.
  5. Divisão da proposta em **6 lotes gerenciáveis de até 5 Issues** para mitigar riscos de governança.
- **Invariantes e Restrições Respeitadas:**
  - **Zero mutações:** Nenhum campo, registro ou dado foi alterado no GitHub Project #2 nesta fase.
  - **Zero código executivo em produção:** Nenhuma homologação foi fabricada, nenhum teste falso foi assumido como PASS.
  - **Zero merge ou deploy:** PR #61, PR #60 e branch `main` permaneceram rigorosamente intocadas.
  - **Custo R$ 0,00:** Operação realizada exclusivamente com ferramentas locais e chamadas à API padrão do GitHub CLI (`gh`).

---

## 2. Resumo Executivo e Comparativo F0 → LIVE

| Dimensão | Diagnóstico F0 (06/11/2026 19:45Z) | Snapshot LIVE CH-DATA-01 (07/11/2026 01:40Z) | Variação / Fato Observado |
|---|---|---|---|
| **Total de Cartões no Project** | 30 | 31 | +1 item recebido (criação legítima da Issue #62 pelo PO) |
| **Integridade de Campos** | 19 campos reportados | 19 campos reportados | Esquema 100% íntegro e estável |
| **Digest SHA-256 do Snapshot** | `8e11dafe...` (parcial/completo) | `5b468ac46c0895ffc9631caea4afffae869b553d8c8c1c586688b1ecd2f12f06` | Snapshot oficial persistido em `.ch_sentinela/project_snapshot.json` |
| **Issues com Core Completo** | 5 (`#2, #6, #7, #58, #59`) | 5 (`#2, #6, #7, #58, #59`) | Estabilidade das tarefas core |
| **Issues com Pendência Cadastral** | 25 | 26 | As 25 originais + Issue #62 (em fase CH-1) |
| **Campos de Governança Complementar** | `NÃO_OBSERVADO` | `NÃO_OBSERVADO` | `Prioridade CH`, `Risco CH` e `Decisao PO` vazios em todos os 31 itens |

---

## 3. Evidências Verificáveis

| ID | Classe | Fonte / Referência | Fato Observado e Limite |
|---|---|---|---|
| **E01** | OBSERVADO | Ordem de serviço do PO [Issue #62](https://github.com/hallanbrito/CHDevFlow/issues/62) | Autorização expressa CH-1 para Peão/AGY executar inventário, cruzamento de evidências e matriz de correção sem mutações. |
| **E02** | OBSERVADO | Execução de `scripts/ch_project_export.py` | Execução ao vivo gerou snapshot com 31 itens, 19 campos, 0 anomalias e digest SHA-256 `5b468ac46c0895ffc9631caea4afffae869b553d8c8c1c586688b1ecd2f12f06`. |
| **E03** | OBSERVADO | `docs/control-center/MATRIZ-CH-DATA-01.md` | Matriz detalhada das 26 issues com campos atuais, valores propostos, IDs de opções, evidências documentais e divisão em 6 lotes. |
| **E04** | OBSERVADO | Histórico de PRs no repositório (`gh pr list`) | Mapeamento inequívoco de PRs integradas à `main`: PR #9 (Issue #8), PR #15 (Issue #14), PR #17 (Issue #16), PR #20 (Issue #19), PR #22 (Issue #21), PR #26 (Issue #27), PR #39 (Issues #32 a #38), PR #42 (Issue #41), PR #55 (Issue #54), PR #57 (Issue #56). |
| **E05** | OBSERVADO | Comentários formais do PO nas Issues | Homologações explícitas registradas pelo PO nas Issues #5, #12, #13, #14, #16, #28, #29, #54, #56. |
| **E06** | OBSERVADO | `git status` na branch `agy/ch-data-01` | Worktree limpa, nenhuma alteração em código de produto ou produção. |

---

## 4. Estrutura dos Lotes Propostos para Decisão do PO

Conforme a Ordem de Serviço #62, a execução de escritas no Project #2 (caso autorizada em CH-2) **não deve ser feita em bloco único**, mas sim deliberada e aplicada em lotes pequenos com verificação prévia de pré-condições:

1. **Lote 1 (5 Issues — #5, #8, #10, #12, #13):** Teste inicial W1, especificação W2-A, governança de segurança da main (CH-SEC-01) e testes piloto P0 read-only.
   - *Destaque:* Preserva estritamente `BACKLOG` e `CH-0` para a Issue #10.
2. **Lote 2 (5 Issues — #14, #16, #18, #19, #21):** Sincronização e automação assistida do Kanban (KSYNC-01 a 03.1) e norma RUC v1.0.
   - *Destaque:* Preserva `Etapa CH=INTEGRADA` para #18, #19 e #21; atribui `Autonomia CH=CH-1` e `CH-2`.
3. **Lote 3 (5 Issues — #24, #27, #28, #29, #32):** Contratos Sentinela (BOOT-00), correção de fallback (BOOT-01), inventário, reconciliação e Épico da CLI (CLI-00).
   - *Destaque:* Preserva estritamente `AGUARDANDO_PO` para #24 (sem promoção de etapa!).
4. **Lote 4 (5 Issues — #33, #34, #35, #36, #37):** Fatias funcionais da CLI v0.1 (CLI-01 a CLI-05) integradas na `main` via PR #39.
   - *Destaque:* Preenche `Autonomia CH=CH-2` com base na execução comprovada da CLI v0.1.
5. **Lote 5 (5 Issues — #38, #40, #41, #54, #56):** Conclusão da CLI (CLI-06), Épico de auditoria (#40), status estrito (#41), falha remota (#54) e despachante W2-B (#56).
   - *Destaque:* Issue #40 mantida em `EM_EXECUCAO` (épico aberto para P1); Issues #54 e #56 com homologação comprovada do PO.
6. **Lote 6 (1 Issue — #62):** Registro cadastral da própria missão atual (CH-DATA-01) em `EM_EXECUCAO`, `AGY`, `CH-1`, `PENDENTE`.

---

## 5. Análise de Risco e Segurança do DAG

- **Princípio Fail-Closed Preservado:** A regularização cadastral dos campos do Project #2 **não altera nem contorna** a regra de segurança do `DAGEngine`.
- Mesmo após o preenchimento de todos os campos cadastrais, as tarefas com etapa `HOMOLOGADA` ou `INTEGRADA` **continuarão classificadas como `BLOQUEADA_DADOS`** enquanto não houver o contrato autenticado de homologação humana exigido pela invariante R3 (`homologacao_verificada=False`).
- Isso comprova a total independência entre a regularização cadastral (objeto de CH-DATA-01) e o mecanismo de verificação criptográfica de homologação (objeto futuro de CH-APPROVAL-01).

---

## 6. Parecer Técnico e Próximos Passos

1. **Conformidade CH-1:** O inventário está 100% concluído, rastreável e documentado em [`docs/control-center/MATRIZ-CH-DATA-01.md`](file:///home/hallan/.gemini/antigravity/worktrees/CHDevFlow/recuperacao_control_center_ch2/docs/control-center/MATRIZ-CH-DATA-01.md).
2. **Recomendação para a Auditoria Independente (ChatGPT):**
   - Verificar a correspondência factual entre as propostas da Matriz e os commits/PRs no repositório.
   - Validar a política de não-promoção de gates humanos (especialmente em #10, #24 e #40).
   - Recomendar ao PO a aprovação dos lotes de 1 a 6.
3. **Decisão do PO:** O PO Hallan deliberará lote a lote quais campos e valores autoriza para mutação real na subsequente fase CH-2.

**Estado Formal:** `READY_FOR_CHATGPT_REVIEW`
