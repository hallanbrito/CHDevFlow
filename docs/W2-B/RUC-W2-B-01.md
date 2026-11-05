# RUC/1.0 — W2-B Dispatcher DRY_RUN — tentativa 1

> Formato documental do CHDevFlow; este relatório é parecer do executor, não auditoria independente nem aceite do PO.

**Cabeçalho:** missão/Issue: [#56](https://github.com/hallanbrito/CHDevFlow/issues/56) | executor declarado: Codex | coordenação/PO: Hallan | autonomia e prova: CH-2 delimitada pelo [gate do PO na #6](https://github.com/hallanbrito/CHDevFlow/issues/6#issuecomment-6666762269) e pela #56 | ambiente: cópia Git isolada `/tmp/chdevflow-w2b-56`, Linux | fontes: `LIVE_GITHUB` + `LOCAL_REPO` | timestamp: 2026-11-05 19:19:08 UTC | run_id: NÃO_APLICÁVEL (produto não iniciou run real) | baseline: `ffadabed95a3d4d55284135c574e741f9c9bd61b`, branch `codex/w2b-dispatcher-dryrun`, [Draft PR #57](https://github.com/hallanbrito/CHDevFlow/pull/57) | resultado técnico: **PARCIAL** até CI e auditoria independente.

## 1. Identificação

Implementação W2-B autorizada para código, testes offline e Draft PR. D01–D07 foram lidas na [Issue #7](https://github.com/hallanbrito/CHDevFlow/issues/7). Contratos W2-A e Sentinela foram consultados na cópia local. O despacho de agentes reais permanece fora do gate.

## 2. Resumo executivo

O módulo novo só produz prévia de simulação, reserva em memória e normalização de eventos de fixtures. `run_authorized=False` em toda prévia. Adaptadores fake `codex_exec` e `agy_print` não têm interface para abrir processos ou chamar modelos. Estado desta entrega: `DRY_RUN_VERIFICADO / NENHUM_EXECUTOR_REAL_INICIADO / AGUARDANDO_AUDITORIA_CHATGPT / AGUARDANDO_PO`.

## 3. Consultas/atividades realizadas

1. Consultei as Issues #56, #7 e o gate do PO na #6 via conector GitHub; li `docs/W2-A` e contratos/políticas/FakeWorker da Sentinela no repositório.
2. Conferi `main` remota em `ffadabe`. O checkout local estava em `185d3df`; a comparação remota indicou apenas `src/chdevflow/core/mission.py` e `tests/test_cli_05.py` diferentes. Reconstituí esses dois arquivos na cópia isolada e confirmei os blobs `11b41dc59f5b24dec8093584d44bdb570cce52a2` e `fc22f562122f0a084aca70c4f94ae303a9bc72df` contra o GitHub. A branch remota foi criada diretamente de `ffadabe`.
3. Implementei código, testes e documentação W2-B. Rodei os comandos da seção 5. Abri Draft PR #57 sem merge.

## 4. Evidências verificáveis

| ID | Classe | Fonte/ref | Fato observado e limite |
|---|---|---|---|
| E01 | OBSERVADO | LIVE_GITHUB: Issues #56, #7 e comentário #6 citado | Gate CH-2 limitado à implementação W2-B; D01–D07 ratificadas. |
| E02 | OBSERVADO | LIVE_GITHUB: comparação `185d3df..ffadabe` e blobs dos dois arquivos | Base remota reconciliada por conteúdo; nenhum commit foi escrito na `main`. |
| E03 | OBSERVADO | LOCAL_REPO: `/tmp/chdevflow-w2b-root-tests-offline.log` | Suíte raiz terminou `Ran 285 tests`, `OK (skipped=1)` com cache `uv` em `/tmp` e `UV_OFFLINE=1`. |
| E04 | OBSERVADO | LOCAL_REPO: execução da suíte Sentinela | `Ran 69 tests`, `OK`. |
| E05 | OBSERVADO | LOCAL_REPO: testes W2-B e código | 16 casos W2-B passaram; interceptação de `subprocess.run`, `Popen` e `socket.socket` não detectou chamada pelo simulador. Prova limitada ao caminho testado. |
| E06 | OBSERVADO | LIVE_GITHUB: Draft PR #57 | PR draft aberto sobre `main`, branch `codex/w2b-dispatcher-dryrun`, sem merge. |
| E07 | NÃO_VERIFICADO | Sessão/licença do host | Custo incremental da sessão Codex e de futuros agentes não foi medido/comprovado aqui; o produto não faz chamadas a modelos. |

## 5. Verificações e resultados

| Teste | Critério | Resultado | Evidência |
|---|---|---|---|
| T01–T07, T24–T26 | Gate, digest, SHA, escopo, custo e privilégios em fixture | PASSOU | E05; `tests/test_w2b_dry_run_dispatcher.py` |
| T08–T15 | Concorrência, replay, timeout, cancelamento, retry e crash simulados | PASSOU | E05 |
| T16–T17, T20–T21 | Falha segura, prompt e sanitização em fixture | PASSOU | E05 |
| JSONL Codex/AGY | Válido, inválido, parcial, erro e `exit=0` com permissão negada | PASSOU | E05 |
| Sem invocação real | Interceptar subprocessos e rede nos caminhos W2-B testados | PASSOU | E05 |
| Suíte raiz | `UV_CACHE_DIR=/tmp/chdevflow-w2b-uv-cache UV_OFFLINE=1 PYTHONPATH=src:apps/bootstrap/sentinela/src python3 -m unittest discover -s tests -q` | PASSOU | E03; 285 testes, 1 salto por ausência de `pytest` local |
| Sentinela | `PYTHONPATH=src:apps/bootstrap/sentinela/src python3 -m unittest discover -s apps/bootstrap/sentinela/tests -v` | PASSOU | E04; 69 testes |
| Sintaxe e prévia W1 | `python3 -m compileall -q src scripts apps`; `python3 scripts/w1_github_project.py` | PASSOU | saída local; prévia sem ações remotas |
| Control Center local | `python3 -m pytest apps/control-center/tests -q` | NÃO_EXECUTADO | `No module named pytest`; sem instalação no host |
| CI Integral da PR | Workflow `CHDevFlow CI Integral` | NÃO_EXECUTADO | Pendente de resultado no HEAD final da PR no momento deste RUC |
| Agentes reais, custo operacional e GitHub Project #2 | Execução/alteração fora do escopo | NÃO_APLICÁVEL | Nenhum agente real despachado pelo produto; custo real NÃO_VERIFICADO |

Na primeira rodada da suíte raiz, dois testes de wheel falharam porque `uv` tentou escrever em `/home/hallan/.cache/uv`, somente leitura no sandbox. O cache foi copiado para `/tmp` e a suíte inteira foi repetida offline com `OK`. O log da primeira rodada permanece em `/tmp/chdevflow-w2b-root-tests.log`; não é uma falha de código concluída como PASS sem reteste.

## 6. Riscos e bloqueios

- Autorização GitHub autenticada, identidade do PO, licença e custo adicional R$ 0 **não são implementados nem verificados** no produto. A fixture serve apenas à simulação.
- Reserva em memória não é lock atômico entre processos nem persiste após crash. Um adaptador operacional futuro requer nova Fatia e novo gate.
- O teste local de Control Center não rodou por falta de `pytest`; a CI deve cobrir a suíte antes de decisão de integração.
- Sanitização cobre padrões conhecidos; saída não confiável precisa de revisão antes de publicação fora da fixture.

## 7. Alterações realizadas

- `src/chdevflow/core/dry_run_dispatcher.py`: núcleo e adaptadores fake.
- `tests/test_w2b_dry_run_dispatcher.py`: matriz offline.
- `docs/W2-B/README.md`: interface e fronteiras.
- `docs/W2-B/RUC-W2-B-01.md`: este relatório.

Publicação: branch e Draft PR #57. Nenhum merge, deploy, release, mudança em `main`, Project #2, ruleset CH-SEC-01 ou outros repositórios. Custo adicional real da sessão: **NÃO_VERIFICADO**; custo declarado pelo resultado fake: zero, com `verified=False`.

## 8. Recomendação técnica

**PARCIAL** no momento do registro: os testes offline executados passaram, mas a CI e a auditoria independente ainda precisam ser conferidas. Recomendo revisão do diff e dos limites antes de qualquer decisão de integração. Não recomendo habilitar execução real neste gate.

## 9. Decisão necessária do PO

**PENDENTE** — Após auditoria independente e CI do HEAD final, aceitar, pedir ajustes ou reprovar a entrega; eventual merge exige despacho separado do PO. Nenhuma decisão `Decisao PO` foi alterada pelo executor.
