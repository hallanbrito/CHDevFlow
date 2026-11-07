# RUC — CC-DAG-01 — Implementação CH-2

## 1. Identificação

- Missão: [Issue #59](https://github.com/hallanbrito/CHDevFlow/issues/59), gate do PO [comentário 6691485065](https://github.com/hallanbrito/CHDevFlow/issues/59#issuecomment-6691485065).
- Executor declarado: Codex. Coordenação e auditoria independente: ChatGPT. Decisão final: PO Hallan.
- Fonte: repositório local isolado `/tmp/chdevflow-cc-dag-01`, branch `codex/cc-dag-01`; consultas GitHub apenas de leitura para gate/baseline.
- Baseline `origin/main` e `main` remota verificados: `f8eea14e03c687c4b2ba2a0f628c7c6948d7a6dd`.
- SHA da implementação original: `f98b59cd890c87d4961bf3ab309f6b0f678fe664`. HEAD final da R1: `de33246df857d6159435a425accd9dcc2d79e305`. Commit técnico R2 com CI verde: `0c8d032e60dd2bf7f55aef55cae98a6410fdb03a`. O commit documental posterior deste RUC será o HEAD apresentado na Draft PR.
- Observação inicial: 06/11/2026, 18:04 UTC; R1 atualizada em 19:24 UTC; R2 atualizada em 19:34 UTC. Estado formal: `AWAITING_PO`.
- R1: [revisão independente da Draft PR #60](https://github.com/hallanbrito/CHDevFlow/pull/60) sobre o HEAD `e880163ff5275e725cec0df5fb1d9a35e34ba618`; correções P1-A, P1-B e P2 na mesma branch. O HEAD final da R1 consta na PR.
- R2: reauditoria sobre `de33246df857d6159435a425accd9dcc2d79e305` apontou P1-C, no qual a prova positiva de A podia satisfazer C apesar de B, pré-requisito interno de A, permanecer pendente. Correção focalizada na mesma Draft PR #60.

## 2. Resumo executivo

O Control Center passou a consultar `blocked_by` nativo e distinguir lista vazia verificada de dados indisponíveis. A regra do DAG deixa de satisfazer dependências por `INTEGRADA`, `DONE`, `CLOSED`, `PROD_OK` ou `HOMOLOGADA` visual isolada. Não há prova de homologação humana autenticada e vinculada à missão disponível nos contratos atuais; por segurança, a leitura ao vivo fornece `homologacao_verificada=False` e bloqueia essas dependências. Nenhum agente real foi despachado.

Na R1, prova positiva interna também não supera dependência órfã, externa ou inválida; a consulta ao vivo recebeu prazo global de 30 segundos e interrompe novas tentativas após duas falhas consecutivas. O painel distingue etapas visuais de conclusão de homologações verificadas.

Na R2, a conclusão satisfatória exige também a conclusão verificável de todos os pré-requisitos internos, transitivamente. Não existe exceção de override autorizada pelo PO neste contrato. A regra de elegibilidade continua sem autorizar execução de agentes.

## 3. Consultas e atividades

Issue #59 e gate do PO lidos pelo conector GitHub. `origin/main` confirmado por `git ls-remote` e pela API de branch; ambos permaneceram no baseline. Criado worktree isolado e implementados leitor, fachada, normalização, DAG, apresentação mínima, testes e contrato em `CC-DAG-01-CONTRATO.md`. Nenhum campo/cartão do Project #2 foi alterado.

Na R1, li a revisão independente da PR #60 e confirmei o CI verde do HEAD anterior. Corrigi os três achados apenas no worktree existente, executei testes offline e atualizei este RUC. O primeiro CI da R1 revelou uma expectativa antiga da rota do grafo: a fixture sem homologação verificável já não possui missão na antiga “Linha de Frente”. Ajustei o teste para exigir o aviso de dados insuficientes e a ausência de prova humana. Nenhum outro projeto ou frente foi alterado.

Na R2, li a reauditoria da PR #60 e confirmei o CI verde do HEAD final da R1. Alterei apenas o DAG, seu teste e o contrato técnico: nós provisoriamente concluídos são reclassificados se qualquer pré-requisito interno não estiver concluído, repetindo a verificação até estabilizar. Nenhum contrato executivo da Sentinela foi alterado.

## 4. Evidências verificáveis

| ID | Classe | Evidência |
|---|---|---|
| E01 | OBSERVADO | Branch remota `main` e `origin/main`: `f8eea14e03c687c4b2ba2a0f628c7c6948d7a6dd`. |
| E02 | OBSERVADO | Gate CH-2 no comentário 6691485065 da Issue #59. |
| E03 | OBSERVADO | Commit de implementação `f98b59cd890c87d4961bf3ab309f6b0f678fe664`; 11 arquivos da missão. |
| E04 | OBSERVADO | Suíte Sentinela: `Ran 73 tests`, `OK`. |
| E05 | OBSERVADO | Testes selecionados do Control Center: `50 passed, 4 deselected in 0.15s`. |
| E06 | OBSERVADO | Renderização offline Jinja de `missions.html` e `graph.html`; compilação Python e `git diff --check` sem erro. |
| E07 | OBSERVADO | GET de `/grafo` via TestClient encerrou por timeout tanto no worktree desta missão como no baseline `main`, com a mesma instalação Python. |
| E08 | OBSERVADO | [CI Integral 42267583587](https://github.com/hallanbrito/CHDevFlow/actions/runs/42267583587) do HEAD anterior `e880163`: `completed/success`; jobs de raiz, Sentinela e Control Center com `success`. A revisão independente relata 443 testes. |
| E09 | OBSERVADO | Revisão da PR #60, HEAD `e880163`, apontou P1-A (órfã com prova positiva), P1-B (timeouts acumuláveis) e P2 (contagens visuais/RUC). |
| E10 | OBSERVADO | R1 local: `56 passed, 4 deselected` nos testes selecionados do Control Center; Sentinela `Ran 73 tests`, `OK`; `compileall` e `git diff --check` sem erro. |
| E11 | OBSERVADO | [CI Integral 42278591815](https://github.com/hallanbrito/CHDevFlow/actions/runs/42278591815) do commit R1 `6d8e72b`: raiz e Sentinela passaram; Control Center teve `85 passed, 1 failed`, exclusivamente `test_rota_grafo_html`, que ainda esperava “Linha de Frente” na fixture sem homologação. |
| E12 | OBSERVADO | O teste de rota foi corrigido para verificar “Dados insuficientes — análise pendente” e “Homologação humana vinculada à missão não verificada”. |
| E13 | OBSERVADO | [CI Integral 42279112809](https://github.com/hallanbrito/CHDevFlow/actions/runs/42279112809) do commit `e365352`: `completed/success`; raiz `290 tests, OK`, Sentinela `73 tests, OK`, Control Center `86 passed`. Compilação e prévia offline também passaram. |
| E14 | OBSERVADO | [CI Integral 42279407550](https://github.com/hallanbrito/CHDevFlow/actions/runs/42279407550) do HEAD final R1 `de33246df857d6159435a425accd9dcc2d79e305`: `success`; raiz 290, Sentinela 73, Control Center 86 aprovados. |
| E15 | OBSERVADO | Reauditoria ChatGPT da PR #60 sobre `de33246` apontou P1-C: B pendente → A homologada com prova True → C indevidamente elegível. |
| E16 | OBSERVADO | R2 local: Control Center selecionado `58 passed, 4 deselected in 0.35s`; Sentinela `Ran 73 tests`, `OK`; `git diff --check` sem erro. O teste da cadeia B→A→C passou nas ordens normal e inversa. |
| E17 | OBSERVADO | [CI Integral 42280555707](https://github.com/hallanbrito/CHDevFlow/actions/runs/42280555707) do commit técnico R2 `0c8d032e60dd2bf7f55aef55cae98a6410fdb03a`: `success`; raiz 290, Sentinela 73, Control Center 88 aprovados (451 no total). Compilação e prévia offline passaram. |

## 5. Verificações e resultados

| Critério | Resultado | Evidência / limite |
|---|---|---|
| `blocked_by` paginado, identidade, vazio verificado e falhas | PASSOU | Testes offline do leitor na suíte Sentinela. |
| Dependência externa, falha parcial, 403, JSON inválido e resolução para item | PASSOU | Testes offline LIVE_GITHUB selecionados. |
| `INTEGRADA`/`DONE`/`CLOSED`/`PROD_OK` sem homologação não desbloqueiam | PASSOU | Testes do DAG, inclusive ciclo e autodependência. |
| Suíte Sentinela | PASSOU | E04. |
| Testes selecionados Control Center | PASSOU | E05. |
| Rotas web via ASGI/TestClient local | INCONCLUSIVO | Timeout reproduzido no baseline; quatro testes excluídos da rodada selecionada. As rotas passaram no CI completo. E07/E17. |
| Homologação humana real verificável | NÃO_EXECUTADO | Contrato atual não oferece fonte autenticada e vinculada à missão; permanece bloqueada. |
| CI do HEAD anterior da Draft PR | PASSOU | E08; inclui rotas web no ambiente CI. |
| R1: órfã com prova positiva e sucessora | PASSOU | Teste A→órfã; B→A, incluindo `UNKNOWN`/`INVALID` com prova positiva. |
| R1: múltiplos timeouts e prazo global | PASSOU | Duas falhas interrompem consultas posteriores; resposta recebida após prazo vira `UNKNOWN`. |
| R1: contagens visualmente distintas | PASSOU | Teste de estatísticas e renderização Jinja offline: etapa visual 1, homologação verificada 0. |
| Primeiro CI remoto da R1 | FALHOU | E11; uma expectativa legada da rota contradizia o bloqueio conservador. |
| CI remoto do HEAD com correção de teste | PASSOU | E13. O commit documental final deste RUC terá verificação própria, registrada na entrega. |
| CI remoto do HEAD final R1 | PASSOU | E14. |
| R2: B pendente → A com prova positiva → C | PASSOU | E16/E17; A e C bloqueadas, inclusive com entrada em ordem inversa. |
| CI remoto do commit técnico R2 | PASSOU | E17. O commit documental final terá verificação própria registrada na entrega. |

## 6. Riscos e bloqueios

1. Não há verificador de prova de homologação real; qualquer dependência, mesmo com `Etapa CH=HOMOLOGADA`, permanece bloqueada na leitura ao vivo. Esta é a limitação funcional deliberada do gate conservador.
2. Project e Issues não são consultados em transação atômica. As respostas pertencem à mesma requisição do painel e recebem horário, mas mudanças simultâneas podem ocorrer entre consultas.
3. `gh api --paginate` segue os links de paginação; uma omissão silenciosa desses links pelo servidor não é detectável apenas pelo payload.
4. A credencial local do `gh` não autenticou a consulta ao vivo nesta sessão. Nenhum teste dependente da rede foi declarado aprovado.
5. A instalação local de FastAPI/Starlette mantém o travamento de TestClient também no baseline; testes HTTP completos exigem ambiente corrigido/auditoria independente.
6. O prazo global limita a latência das dependências a 30 segundos por visão, mas uma consulta ao Project ainda pode consumir todo o orçamento; nesse caso, as dependências ficam `UNKNOWN`.

## 7. Alterações realizadas

`apps/bootstrap/sentinela/src/ch_sentinela/github_reader.py`, `apps/bootstrap/sentinela/tests/test_github_reader.py`, `apps/control-center/src/ch_control_center/{adapters/sentinela_adapter.py,graph/dag_engine.py,services/mission_service.py,templates/graph.html,templates/missions.html}`, `apps/control-center/tests/{test_dag_engine.py,test_live_github_regression.py,test_mission_service.py}` e `docs/control-center/CC-DAG-01-CONTRATO.md`. Este RUC é exclusivamente documental.

R1 alterou `github_reader.py`, `sentinela_adapter.py`, `dag_engine.py`, `mission_service.py`, `dashboard.html`, `graph.html`, `missions.html`, `test_dag_engine.py`, `test_live_github_regression.py`, `test_routes_read_only.py`, o contrato técnico e este RUC. O contrato executivo da Sentinela e o Project #2 permaneceram intocados.

R2 alterou somente `apps/control-center/src/ch_control_center/graph/dag_engine.py`, `apps/control-center/tests/test_dag_engine.py`, `docs/control-center/CC-DAG-01-CONTRATO.md` e este RUC. A descrição da Draft PR será atualizada com o HEAD e o CI final.

## 8. Recomendação técnica

Encaminhar a Draft PR à auditoria independente do ChatGPT. O comportamento conservador pode ser auditado offline; não tratar o DAG como autorizador de execução. A liberação positiva de dependências requer contrato verificável de homologação definido pelo PO e implementação separada, sem inferência por campos visuais.

## 9. Decisão necessária do PO

Auditar e decidir sobre o aceite desta fatia e sobre o formato/fonte da prova de homologação humana vinculada à missão. O PO decide qualquer integração futura. Não houve merge, deploy, release nem alteração do Project #2.

## 10. Correção visual focalizada R3

- Gate expresso do PO: [comentário 6694005731 na Draft PR #60](https://github.com/hallanbrito/CHDevFlow/pull/60#issuecomment-6694005731). Baseline R3: `90f04a945279d938a9c9ce599e0b492c57d5ee5f`.
- Commit técnico R3: `4cea7d52c46d9b69cd47a46793018577132ae971`. O commit documental posterior deste RUC será o HEAD final da PR.
- P1-1: Dashboard mostra `BLOQUEADA_DADOS` como “Dados insuficientes”, igual a Missões; os estados e regras do DAG não foram alterados.
- P1-2: quarta raia do Grafo usa título numerado, tipografia compacta, diagnóstico e origem preservados, com rodapé Esteira/Autonomia CH.
- P1-3: tabelas, cartões e alertas mostram `#N` quando há número de Issue válido; o ID interno permanece no tooltip e no detalhe técnico. Sem número conhecido, o ID interno é exibido como fallback. Links e identificadores canônicos permanecem integrais.
- Arquivos alterados: `apps/control-center/src/ch_control_center/templates/{dashboard.html,missions.html,graph.html}` e `apps/control-center/tests/test_live_github_regression.py`. Nenhuma mudança de arquitetura, DAG, Sentinela, Project #2 ou outras frentes.

| Verificação R3 | Resultado observado | Limite |
|---|---|---|
| Testes offline novos de renderização | `2 passed, 22 deselected` na seleção R3 | Templates Jinja; não é inspeção visual em navegador. |
| Regressões locais selecionadas do Control Center | `60 passed, 4 deselected in 0.27s` | Quatro testes HTTP excluídos pelo timeout local já observado no baseline; CI completo os executa. |
| Sentinela offline | `Ran 73 tests`, `OK` | Nenhum contrato executivo foi alterado. |
| `git diff --check` | PASSOU | Sem erros de whitespace no diff R3. |
| [CI integral 42285089478](https://github.com/hallanbrito/CHDevFlow/actions/runs/42285089478) do commit técnico R3 | PASSOU | `success`: 290 testes raiz, 73 Sentinela e 90 Control Center, 453 aprovados; compilação e prévia offline também passaram. |

Estado formal da entrega R3: `AWAITING_PO`, sem homologação implícita. A reauditoria deve confirmar a apresentação visual em navegador se essa evidência for necessária ao aceite final.
