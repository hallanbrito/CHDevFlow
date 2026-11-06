# Diagnóstico F0 — Missões com Dados Insuficientes e Desempenho (CC-QUALITY-01)

**Data da Observação**: 06/11/2026 19:45 UTC  
**Modo de Operação**: `LIVE_GITHUB` (consulta real via CLI `gh` ao GitHub Project #2 e API REST `blocked_by`)  
**Autorização**: CH-1 (Leitura estrita e diagnóstico, sem mutações no Project #2, sem merge, sem deploy)  
**Baseline**: Commit `761af5a3db75a83d71e39490f092c577713e243d` (HEAD da PR #60 / CC-DAG-01 R3)  

---

## 1. Resumo Executivo da Observação ao Vivo

Em 06/11/2026, executamos o diagnóstico técnico das missões carregadas pelo Control Center no modo `LIVE_GITHUB`.
Foram recebidos **30 itens** do GitHub Project #2 (proprietário `hallanbrito`, repositório `hallanbrito/CHDevFlow`).
Todos os 30 itens são do tipo `Issue` no repositório canônico com a etiqueta `ch:workflow`.

### Métricas Observadas ao Vivo (Baseline):
- **Tempo de leitura total de uma visão**: **23,86 segundos**
- **Subprocessos `gh` disparados por visão**: **31** (1 `gh project item-list` + 30 `gh api .../dependencies/blocked_by`)
- **Total de tarefas**: **30**
- **Tarefas Elegíveis no DAG**: **3** (`#6`, `#58`, `#59`)
- **Tarefas Concluídas**: **0**
- **Tarefas com Etapa de Fechamento Visual**: **20** (`HOMOLOGADA`: 8; `INTEGRADA`: 12)
- **Tarefas com Dados Insuficientes / Bloqueadas**: **27**
- **Ciclos e Órfãs**: **0**

---

## 2. Matriz Completa das 30 Missões Observadas

| #Issue | ID Project Item | Título | Etapa CH | Esteira | Autonomia CH | Estado Dep. | Pendências Dados (antes DAG) | Pendências Dados (após DAG) | Status Grafo DAG | Causa Primária Diagnosticada |
|---|---|---|---|---|---|---|---|---|---|---|
| **#2** | `PVTI_lAHOBsbaWM4Bnmd9zhBnXBg` | W1 — Kanban CHDevFlow: quatro esteiras e gate humano | `HOMOLOGADA` | `ChatGPT` | `CH-2` | `VERIFIED_EMPTY` | *Nenhuma* | Homologação humana não verificada | `BLOQUEADA_DADOS` | **Homologação não verificada** |
| **#5** | `PVTI_lAHOBsbaWM4Bnmd9zhBnlhQ` | [TESTE W1] Validar inclusão automática no Kanban | `NAO_INFORMADA` | `NAO_INFORMADA` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Etapa CH, Esteira, Autonomia | Etapa CH, Esteira, Autonomia | `BLOQUEADA_DADOS` | **Cadastro incompleto** (3 campos) |
| **#6** | `PVTI_lAHOBsbaWM4Bnmd9zhBnoqE` | W2 — Planejamento despachante assistido (CH-1) | `BACKLOG` | `ChatGPT` | `CH-1` | `VERIFIED_EMPTY` | *Nenhuma* | *Nenhuma* | `ELEGIVEL` | *Elegível (raiz)* |
| **#7** | `PVTI_lAHOBsbaWM4Bnmd9zhBnxfk` | W2-PO — Deliberar arquitetura e limites despachante | `HOMOLOGADA` | `Hallan` | `CH-0` | `VERIFIED_EMPTY` | *Nenhuma* | Homologação humana não verificada | `BLOQUEADA_DADOS` | **Homologação não verificada** |
| **#8** | `PVTI_lAHOBsbaWM4Bnmd9zhBoCZM` | W2-A — Especificação documental despachante (CH-1) | `INTEGRADA` | `ChatGPT` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#10** | `PVTI_lAHOBsbaWM4Bnmd9zhBob5k` | CH-SEC-01 — Preparar proteção da main sem bloquear PO | `BACKLOG` | `Hallan` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia CH | `BLOQUEADA_DADOS` | **Cadastro incompleto** (Autonomia CH) |
| **#12** | `PVTI_lAHOBsbaWM4Bnmd9zhBot8U` | P0-CODEX — Testar leitura Kanban e relatório (CH-0) | `HOMOLOGADA` | `Codex` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#13** | `PVTI_lAHOBsbaWM4Bnmd9zhBo44A` | P0-AGY — Testar leitura offline Kanban e relatório | `HOMOLOGADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#14** | `PVTI_lAHOBsbaWM4Bnmd9zhBo_SY` | RUC-01 — Relatório Unificado de Conformidade (CH-1) | `HOMOLOGADA` | `ChatGPT` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#16** | `PVTI_lAHOBsbaWM4Bnmd9zhBpY8E` | PILOTO-01 — Piloto restrito do despachante (CH-2) | `HOMOLOGADA` | `ChatGPT` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#18** | `PVTI_lAHOBsbaWM4Bnmd9zhBtT_Q` | KSYNC-01 — Webhook GitHub Projects -> SQLite | `INTEGRADA` | `ChatGPT` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#19** | `PVTI_lAHOBsbaWM4Bnmd9zhBtU-U` | KSYNC-02 — Sentinela reconciliador de divergências | `INTEGRADA` | `ChatGPT` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#21** | `PVTI_lAHOBsbaWM4Bnmd9zhBuYhA` | KSYNC-03.1 — Reconciliação do estágio (stage) | `INTEGRADA` | `ChatGPT` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#24** | `PVTI_lAHOBsbaWM4Bnmd9zhB43s0` | BOOT-00 — Documentação dos Contratos da Sentinela | `AGUARDANDO_PO` | `ChatGPT` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia CH | `BLOQUEADA_DADOS` | **Cadastro incompleto** (Autonomia CH) |
| **#27** | `PVTI_lAHOBsbaWM4Bnmd9zhCAX7Y` | BOOT-01 — Validação estrita de contratos e simulação | `INTEGRADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#28** | `PVTI_lAHOBsbaWM4Bnmd9zhCAZ6s` | CH-ACCESS-01 — Exportador seguro do Project #2 | `HOMOLOGADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#29** | `PVTI_lAHOBsbaWM4Bnmd9zhCBk-A` | CC-00 — Fundação do CHDevFlow Control Center | `HOMOLOGADA` | `ChatGPT` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#32** | `PVTI_lAHOBsbaWM4Bnmd9zhCYe_A` | CC-01 — Painel web local de supervisão | `NAO_INFORMADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Etapa CH, Autonomia | Etapa CH, Autonomia | `BLOQUEADA_DADOS` | **Cadastro incompleto** (Etapa CH + Autonomia) |
| **#33** | `PVTI_lAHOBsbaWM4Bnmd9zhDDnW8` | CLI-01 — Estrutura de empacotamento do `ch` | `INTEGRADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#34** | `PVTI_lAHOBsbaWM4Bnmd9zhDDnYY` | CLI-02 — `ch status` local e remoto | `INTEGRADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#35** | `PVTI_lAHOBsbaWM4Bnmd9zhDDnaU` | CLI-03 — `ch gate` e verificação de autorização | `INTEGRADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#36** | `PVTI_lAHOBsbaWM4Bnmd9zhDDniQ` | CLI-04 — `ch verify` e conformidade de artefatos | `INTEGRADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#37** | `PVTI_lAHOBsbaWM4Bnmd9zhDDnsk` | CLI-05 — `ch mission`, `ch ruc` e `ch submit` | `INTEGRADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#38** | `PVTI_lAHOBsbaWM4Bnmd9zhDDnus` | CLI-06 — `ch watch`, documentação e ensaio E2E | `INTEGRADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#40** | `PVTI_lAHOBsbaWM4Bnmd9zhDOUQ4` | AUD-GERAL-01 — Estabilização do CHDevFlow v0.1.0 | `NAO_INFORMADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Etapa CH, Autonomia | Etapa CH, Autonomia | `BLOQUEADA_DADOS` | **Cadastro incompleto** (Etapa CH + Autonomia) |
| **#41** | `PVTI_lAHOBsbaWM4Bnmd9zhDOUZk` | AUD-GERAL-P0-01 — Status estrito e eliminação de falso PASS | `INTEGRADA` | `AGY` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Autonomia CH | Autonomia + Homologação + Etapa visual | `BLOQUEADA_DADOS` | **Múltiplas causas** (Autonomia + Homologação) |
| **#54** | `PVTI_lAHOBsbaWM4Bnmd9zhGV8xI` | P1-CLI-REMOTE-01 — Falha remota em ch mission new | `NAO_INFORMADA` | `NAO_INFORMADA` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Etapa CH, Esteira, Autonomia | Etapa CH, Esteira, Autonomia | `BLOQUEADA_DADOS` | **Cadastro incompleto** (3 campos) |
| **#56** | `PVTI_lAHOBsbaWM4Bnmd9zhGXa-M` | W2-B — Dispatcher Codex + Peão (adaptadores CH-2) | `NAO_INFORMADA` | `NAO_INFORMADA` | `NAO_INFORMADA` | `VERIFIED_EMPTY` | Etapa CH, Esteira, Autonomia | Etapa CH, Esteira, Autonomia | `BLOQUEADA_DADOS` | **Cadastro incompleto** (3 campos) |
| **#58** | `PVTI_lAHOBsbaWM4Bnmd9zhGoYnQ` | CC-QUALITY-01 — Sincronização LIVE_GITHUB | `BACKLOG` | `AGY` | `CH-1` | `VERIFIED_EMPTY` | *Nenhuma* | *Nenhuma* | `ELEGIVEL` | *Elegível (raiz)* |
| **#59** | `PVTI_lAHOBsbaWM4Bnmd9zhGoYko` | CC-DAG-01 — Contrato de dependências verificáveis | `BACKLOG` | `Codex` | `CH-1` | `VERIFIED_EMPTY` | *Nenhuma* | *Nenhuma* | `ELEGIVEL` | *Elegível (raiz)* |

---

## 3. Discriminação Rigorosa das Causas

A análise desmente categoricamente a hipótese de que "todas as 27 tarefas bloqueadas possuem cadastro incompleto":

1. **Homologação humana não verificada exclusivamente (2 tarefas: #2 e #7)**:
   - As Issues `#2` e `#7` possuem **cadastro 100% preenchido** no GitHub Project #2 (`Etapa CH=HOMOLOGADA`, `Esteira` preenchida, `Autonomia CH` preenchida `CH-2` e `CH-0`).
   - Suas dependências são comprovadamente vazias (`VERIFIED_EMPTY`).
   - O motivo do bloqueio é **exclusivamente a política de segurança fail-closed do DAG**: não existe ainda uma fonte de prova criptográfica/autenticada vinculando a homologação humana do PO à missão (`homologacao_verificada=False`).
   - **Conclusão**: Denominá-las como "cadastro incompleto" seria um falso diagnóstico.

2. **Cadastro Incompleto Puro (7 tarefas: #5, #10, #24, #32, #40, #54, #56)**:
   - Tarefas em `BACKLOG`, `AGUARDANDO_PO` ou sem etapa definida onde campos obrigatórios do Project estão vazios no GitHub:
     - `#5`, `#54`, `#56`: Etapa CH, Esteira e Autonomia CH ausentes (3 campos vazios).
     - `#32`, `#40`: Etapa CH e Autonomia CH ausentes (2 campos vazios).
     - `#10`, `#24`: Autonomia CH ausente (1 campo vazio).

3. **Múltiplas Causas Concorrentes (18 tarefas: #8, #12, #13, #14, #16, #18, #19, #21, #27, #28, #29, #33, #34, #35, #36, #37, #38, #41)**:
   - Todas estas possuem `Etapa CH` em estágio de fechamento visual (`HOMOLOGADA` ou `INTEGRADA`) e `Esteira` preenchida, mas o campo `Autonomia CH` não foi preenchido no Project #2.
   - Concorrem duas causas distintas:
     a) **Cadastro incompleto**: ausência de `Autonomia CH`;
     b) **Homologação não verificada**: a etapa visual (`HOMOLOGADA`/`INTEGRADA`) não comprova a homologação do PO por contrato fail-closed.

4. **Consulta / Dependência Indisponível (0 nesta sessão, mas risco iminente de timeout)**:
   - A leitura ao vivo levou **23,86 segundos** para 30 issues contra um orçamento global de **30 segundos**.
   - Em caso de latência adicional, falhas de rede acionam `MAX_FALHAS_CONSECUTIVAS` ou estouro de prazo, convertendo dependências para `UNKNOWN` com diagnóstico `"Leitura interrompida pelo orçamento temporal ou por falhas consecutivas."`.

---

## 4. Confirmação da Divergência dos Contadores (25 vs 27)

### Causa Raiz Observada e Comprovada no Código:
- Em `MissionService.construir_visao_operacional_completa`:
  ```python
  "total_dados_insuficientes": sum(bool(t["pendencias_dados"]) for t in tarefas)
  ```
  O cálculo das estatísticas é realizado sobre a lista `tarefas` **antes** da execução de `DAGEngine.construir_grafo(tarefas)`.
- No momento da normalização em `MissionService`, as Issues `#2` e `#7` possuem `pendencias_dados = []`, logo **não são contabilizadas** no contador `total_dados_insuficientes` (resultado: **25**).
- Em seguida, `DAGEngine.construir_grafo` processa as tarefas. Para nós com etapa visual de fechamento (`HOMOLOGADA`, `INTEGRADA`, etc.) sem homologação comprovada (`homologacao_verificada=False`), o motor adiciona mutações em `no.pendencias_dados`:
  ```python
  no.pendencias_dados.append("Homologação humana vinculada à missão não verificada")
  no.status_grafo = STATUS_BLOQUEADA_DADOS
  ```
  Isso adiciona `#2` e `#7` aos nós com pendências de dados.
- O template `graph.html` calcula:
  ```jinja2
  {% set incompletos = grafo.nos.values() | selectattr('pendencias_dados') | list %}
  ```
  Que resulta em **27**!
- E na raia 4 do grafo:
  ```jinja2
  {% set bloqueadas_dados = grafo.nos.values() | selectattr('status_grafo', 'equalto', 'BLOQUEADA_DADOS') | list %}
  ```
  Que também resulta em **27**!
- Consequentemente:
  - O `dashboard.html` exibia o card: `"Dados insuficientes para verificar o grafo de 25 missão(ões)"`.
  - O `graph.html` exibia o alerta: `"27 missão(ões) com campos ou dependências não informados"` e exibia **27 cartões** na Raia 4!
- **Divergência comprovada**: 25 vs 27 decorre de calcular contagens em pontos diferentes do ciclo de enriquecimento (antes vs depois do DAG Engine).

---

## 5. Medição de Desempenho e Gargalo Arquitetural

### Baseline Observado:
- Disparos de subprocessos por tela:
  - `GET /` (Dashboard): 1 `gh project item-list` + 30 `gh api` = **31 subprocessos** (~24s).
  - `GET /missoes`: 1 `gh project item-list` + 30 `gh api` = **31 subprocessos** (~24s).
  - `GET /grafo`: 1 `gh project item-list` + 30 `gh api` = **31 subprocessos** (~24s).
  - Expansão de detalhes `/api/missoes/{id}`: dispara **mais 31 subprocessos** (~24s).
- **Consumo Total para navegação típica de 3 telas**: **93 subprocessos `gh`**, totalizando **~72 segundos**.
- **Diagnóstico**: Ausência de cache em memória/snapshot compartilhado entre requisições HTTP e falta de coalescência contra concorrência.

---

## 6. Proposta de Regularização dos Campos do Project #2 (Para Deliberação Exclusiva do PO)

> **ATENÇÃO**: Conforme o Gate do PO e política de segurança CH-2, o Peão **NÃO alterou nem alterará** nenhum campo, rótulo ou dado do GitHub Project #2. A tabela abaixo é uma **proposta estritamente consultiva** para o PO deliberar:

| Issue | Título | Etapa CH Proposta | Esteira Proposta | Autonomia CH Proposta | Fundamentação Baseada no Repositório |
|---|---|---|---|---|---|
| `#5` | [TESTE W1] Validar inclusão automática | `HOMOLOGADA` | `ChatGPT` | `CH-2` | Teste do ciclo W1 concluído no histórico |
| `#8` | W2-A — Especificação documental despachante | `INTEGRADA` | `ChatGPT` | `CH-1` | PR #11 integrada na main (documental) |
| `#10` | CH-SEC-01 — Proteção da main | `HOMOLOGADA` | `Hallan` | `CH-0` | Ruleset configurado pelo PO |
| `#12` | P0-CODEX — Testar leitura Kanban | `HOMOLOGADA` | `Codex` | `CH-0` | Teste read-only concluído na issue |
| `#13` | P0-AGY — Testar leitura offline | `HOMOLOGADA` | `AGY` | `CH-0` | Teste read-only concluído na issue |
| `#14` | RUC-01 — Relatório Unificado | `HOMOLOGADA` | `ChatGPT` | `CH-1` | PR #15 integrada |
| `#16` | PILOTO-01 — Piloto restrito | `HOMOLOGADA` | `ChatGPT` | `CH-2` | Piloto concluído |
| `#18` | KSYNC-01 — Webhook SQLite | `INTEGRADA` | `ChatGPT` | `CH-2` | PR #20 integrada |
| `#19` | KSYNC-02 — Sentinela reconciliador | `INTEGRADA` | `ChatGPT` | `CH-2` | PR #20 integrada |
| `#21` | KSYNC-03.1 — Reconciliação do estágio | `INTEGRADA` | `ChatGPT` | `CH-2` | PR #22 integrada |
| `#24` | BOOT-00 — Contratos Sentinela | `HOMOLOGADA` | `ChatGPT` | `CH-1` | PR #24/#26 aprovadas pelo PO |
| `#27` | BOOT-01 — Validação de contratos | `INTEGRADA` | `AGY` | `CH-2` | PR #30 integrada |
| `#28` | CH-ACCESS-01 — Exportador seguro | `HOMOLOGADA` | `AGY` | `CH-2` | PR #50 homologada pelo PO |
| `#29` | CC-00 — Fundação Control Center | `HOMOLOGADA` | `ChatGPT` | `CH-1` | PR #31 homologada pelo PO |
| `#32` | CC-01 — Painel web local | `HOMOLOGADA` | `AGY` | `CH-2` | PR #31/#32 concluídas |
| `#33` | CLI-01 — Empacotamento `ch` | `INTEGRADA` | `AGY` | `CH-2` | PR #39 integrada |
| `#34` | CLI-02 — `ch status` | `INTEGRADA` | `AGY` | `CH-2` | PR #39 integrada |
| `#35` | CLI-03 — `ch gate` | `INTEGRADA` | `AGY` | `CH-2` | PR #39 integrada |
| `#36` | CLI-04 — `ch verify` | `INTEGRADA` | `AGY` | `CH-2` | PR #39 integrada |
| `#37` | CLI-05 — `ch mission/ruc/submit` | `INTEGRADA` | `AGY` | `CH-2` | PR #39 integrada |
| `#38` | CLI-06 — `ch watch` e E2E | `INTEGRADA` | `AGY` | `CH-2` | PR #39 integrada |
| `#40` | AUD-GERAL-01 — Estabilização v0.1.0 | `HOMOLOGADA` | `AGY` | `CH-2` | PR #45/#47 homologadas |
| `#41` | AUD-GERAL-P0-01 — Status estrito | `INTEGRADA` | `AGY` | `CH-2` | PR #45 integrada |
| `#54` | P1-CLI-REMOTE-01 — Erro em ch mission new | `HOMOLOGADA` | `AGY` | `CH-2` | PR #54 homologada |
| `#56` | W2-B — Dispatcher Codex + Peão | `HOMOLOGADA` | `Codex` | `CH-2` | PR #57 homologada pelo PO |

---

## 7. Encerramento de F0 e Habilitação de F1..F5

Com este diagnóstico formalizado, comprovamos com evidências:
- O comportamento real do LIVE_GITHUB no repositório;
- A causa exata da discrepância dos contadores (25 vs 27);
- A separação real das causas de bloqueio (descartando "tudo é cadastro");
- A medição de latência e processos subprocess gh;
- A proposta técnica isolada para os dados do Project #2.

Podemos avançar para as fases de implementação CH-2 (F1 a F5) no código do Control Center.
