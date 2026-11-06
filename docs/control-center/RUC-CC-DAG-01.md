# RUC — CC-DAG-01 — Implementação CH-2

## 1. Identificação

- Missão: [Issue #59](https://github.com/hallanbrito/CHDevFlow/issues/59), gate do PO [comentário 6691485065](https://github.com/hallanbrito/CHDevFlow/issues/59#issuecomment-6691485065).
- Executor declarado: Codex. Coordenação e auditoria independente: ChatGPT. Decisão final: PO Hallan.
- Fonte: repositório local isolado `/tmp/chdevflow-cc-dag-01`, branch `codex/cc-dag-01`; consultas GitHub apenas de leitura para gate/baseline.
- Baseline `origin/main` e `main` remota verificados: `f8eea14e03c687c4b2ba2a0f628c7c6948d7a6dd`.
- SHA da implementação verificada: `f98b59cd890c87d4961bf3ab309f6b0f678fe664`. O commit documental deste RUC será o HEAD apresentado na Draft PR.
- Observação: 06/11/2026, 18:04 UTC. Estado formal: `AWAITING_PO`.

## 2. Resumo executivo

O Control Center passou a consultar `blocked_by` nativo e distinguir lista vazia verificada de dados indisponíveis. A regra do DAG deixa de satisfazer dependências por `INTEGRADA`, `DONE`, `CLOSED`, `PROD_OK` ou `HOMOLOGADA` visual isolada. Não há prova de homologação humana autenticada e vinculada à missão disponível nos contratos atuais; por segurança, a leitura ao vivo fornece `homologacao_verificada=False` e bloqueia essas dependências. Nenhum agente real foi despachado.

## 3. Consultas e atividades

Issue #59 e gate do PO lidos pelo conector GitHub. `origin/main` confirmado por `git ls-remote` e pela API de branch; ambos permaneceram no baseline. Criado worktree isolado e implementados leitor, fachada, normalização, DAG, apresentação mínima, testes e contrato em `CC-DAG-01-CONTRATO.md`. Nenhum campo/cartão do Project #2 foi alterado.

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

## 5. Verificações e resultados

| Critério | Resultado | Evidência / limite |
|---|---|---|
| `blocked_by` paginado, identidade, vazio verificado e falhas | PASSOU | Testes offline do leitor na suíte Sentinela. |
| Dependência externa, falha parcial, 403, JSON inválido e resolução para item | PASSOU | Testes offline LIVE_GITHUB selecionados. |
| `INTEGRADA`/`DONE`/`CLOSED`/`PROD_OK` sem homologação não desbloqueiam | PASSOU | Testes do DAG, inclusive ciclo e autodependência. |
| Suíte Sentinela | PASSOU | E04. |
| Testes selecionados Control Center | PASSOU | E05. |
| Rotas web via ASGI/TestClient | FALHOU | Timeout reproduzido no baseline; quatro testes excluídos da rodada selecionada. E07. |
| Homologação humana real verificável | NÃO_EXECUTADO | Contrato atual não oferece fonte autenticada e vinculada à missão; permanece bloqueada. |
| CI remoto da Draft PR | NÃO_EXECUTADO | Aguardando criação da PR e execução do workflow. |

## 6. Riscos e bloqueios

1. Não há verificador de prova de homologação real; qualquer dependência, mesmo com `Etapa CH=HOMOLOGADA`, permanece bloqueada na leitura ao vivo. Esta é a limitação funcional deliberada do gate conservador.
2. Project e Issues não são consultados em transação atômica. As respostas pertencem à mesma requisição do painel e recebem horário, mas mudanças simultâneas podem ocorrer entre consultas.
3. `gh api --paginate` segue os links de paginação; uma omissão silenciosa desses links pelo servidor não é detectável apenas pelo payload.
4. A credencial local do `gh` não autenticou a consulta ao vivo nesta sessão. Nenhum teste dependente da rede foi declarado aprovado.
5. A instalação local de FastAPI/Starlette mantém o travamento de TestClient também no baseline; testes HTTP completos exigem ambiente corrigido/auditoria independente.

## 7. Alterações realizadas

`apps/bootstrap/sentinela/src/ch_sentinela/github_reader.py`, `apps/bootstrap/sentinela/tests/test_github_reader.py`, `apps/control-center/src/ch_control_center/{adapters/sentinela_adapter.py,graph/dag_engine.py,services/mission_service.py,templates/graph.html,templates/missions.html}`, `apps/control-center/tests/{test_dag_engine.py,test_live_github_regression.py,test_mission_service.py}` e `docs/control-center/CC-DAG-01-CONTRATO.md`. Este RUC é exclusivamente documental.

## 8. Recomendação técnica

Encaminhar a Draft PR à auditoria independente do ChatGPT. O comportamento conservador pode ser auditado offline; não tratar o DAG como autorizador de execução. A liberação positiva de dependências requer contrato verificável de homologação definido pelo PO e implementação separada, sem inferência por campos visuais.

## 9. Decisão necessária do PO

Auditar e decidir sobre o aceite desta fatia e sobre o formato/fonte da prova de homologação humana vinculada à missão. O PO decide qualquer integração futura. Não houve merge, deploy, release nem alteração do Project #2.
