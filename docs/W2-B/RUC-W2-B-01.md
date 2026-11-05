# RUC/1.0 — W2-B Dispatcher DRY_RUN — tentativa 1 / correção R1

> Formato documental do CHDevFlow; este relatório é parecer do executor, não auditoria independente nem aceite do PO.

**Cabeçalho:** missão/Issue: [#56](https://github.com/hallanbrito/CHDevFlow/issues/56) | executor declarado: Codex | coordenação/PO: Hallan | autonomia e prova: CH-2 delimitada pelo [gate inicial](https://github.com/hallanbrito/CHDevFlow/issues/6#issuecomment-6666762269) e pelo [gate corretivo R1](https://github.com/hallanbrito/CHDevFlow/issues/56#issuecomment-6667473112) | ambiente: cópia Git isolada `/tmp/chdevflow-w2b-56`, Linux | fontes: `LIVE_GITHUB` + `LOCAL_REPO` | registro inicial: 2026-11-05 19:19:08 UTC; atualização R1: 2026-11-05 19:55:55 UTC | run_id: NÃO_APLICÁVEL (produto não iniciou run real) | baseline: `ffadabed95a3d4d55284135c574e741f9c9bd61b`, branch `codex/w2b-dispatcher-dryrun`, [Draft PR #57](https://github.com/hallanbrito/CHDevFlow/pull/57) | resultado técnico: **PARCIAL** até nova auditoria independente.

## 1. Identificação

Implementação W2-B autorizada para código, testes offline e Draft PR. A R1 foi autorizada pelo PO somente para os três achados do [parecer CH-AUD-W2B-01](https://github.com/hallanbrito/CHDevFlow/pull/57#pullrequestreview-5790852194). D01–D07 foram lidas na [Issue #7](https://github.com/hallanbrito/CHDevFlow/issues/7). Contratos W2-A e Sentinela foram consultados na cópia local. O despacho de agentes reais permanece fora do gate.

## 2. Resumo executivo

O módulo só produz prévia de simulação, reserva em memória e normalização de eventos de fixtures. A R1 vincula a reserva à prévia validada e registra falhas de normalização como `INDETERMINATE`, liberando a reserva ativa. `run_authorized=False` em toda prévia. Adaptadores fake `codex_exec` e `agy_print` não têm interface para abrir processos ou chamar modelos. Estado desta entrega: `R1_IMPLEMENTADA / AGUARDANDO_AUDITORIA_INDEPENDENTE_CHATGPT / AGUARDANDO_PO / SEM_MERGE`.

## 3. Consultas/atividades realizadas

1. Consultei as Issues #56, #7 e o gate do PO na #6 via conector GitHub; li `docs/W2-A` e contratos/políticas/FakeWorker da Sentinela no repositório.
2. Conferi `main` remota em `ffadabe`. O checkout local estava em `185d3df`; a comparação remota indicou apenas `src/chdevflow/core/mission.py` e `tests/test_cli_05.py` diferentes. Reconstituí esses dois arquivos na cópia isolada e confirmei os blobs `11b41dc59f5b24dec8093584d44bdb570cce52a2` e `fc22f562122f0a084aca70c4f94ae303a9bc72df` contra o GitHub. A branch remota foi criada diretamente de `ffadabe`.
3. Implementei código, testes e documentação W2-B. Rodei os comandos da seção 5. Abri Draft PR #57 sem merge.
4. Na R1, li o gate corretivo da Issue #56 e a revisão/threads da PR #57; confirmei HEAD remoto `88552fa` e `main` em `ffadabe`. Corrigi vínculo da prévia e estado após exceção, acrescentei cinco testes regressivos e atualizei a interface documental. O primeiro ensaio dos 21 testes detectou uma comparação por valor no replay; corrigi para comparação por identidade e repeti a suíte com `OK`.

## 4. Evidências verificáveis

| ID | Classe | Fonte/ref | Fato observado e limite |
|---|---|---|---|
| E01 | OBSERVADO | LIVE_GITHUB: Issues #56, #7 e comentário #6 citado | Gate CH-2 limitado à implementação W2-B; D01–D07 ratificadas. |
| E02 | OBSERVADO | LIVE_GITHUB: comparação `185d3df..ffadabe` e blobs dos dois arquivos | Base remota reconciliada por conteúdo; nenhum commit foi escrito na `main`. |
| E03 | OBSERVADO | LOCAL_REPO: `/tmp/chdevflow-w2b-root-tests-offline.log` e `/tmp/chdevflow-w2b-root-tests-final.log` | Suíte raiz terminou `Ran 285 tests`, `OK (skipped=1)` nas duas rodadas offline; a segunda foi após a última alteração de código. |
| E04 | OBSERVADO | LOCAL_REPO: execução da suíte Sentinela | `Ran 69 tests`, `OK`. |
| E05 | OBSERVADO | LOCAL_REPO: testes W2-B e código | 16 casos W2-B passaram; interceptação de `subprocess.run`, `Popen` e `socket.socket` não detectou chamada pelo simulador. Prova limitada ao caminho testado. |
| E06 | OBSERVADO | LIVE_GITHUB: Draft PR #57 | PR draft aberto sobre `main`, branch `codex/w2b-dispatcher-dryrun`, sem merge. |
| E07 | NÃO_VERIFICADO | Sessão/licença do host | Custo incremental da sessão Codex e de futuros agentes não foi medido/comprovado aqui; o produto não faz chamadas a modelos. |
| E08 | OBSERVADO | [CI Integral run 42093052181](https://github.com/hallanbrito/CHDevFlow/actions/runs/42093052181), HEAD `86a8808ba46c762be4d3af9c6e6b8512a8e75242` | Workflow `completed/success`; job `python-checks` e as três etapas de testes concluíram com `success`. Este registro documental cria HEAD posterior, sujeito à própria CI. |
| E09 | OBSERVADO | [CI Integral run 42093359872](https://github.com/hallanbrito/CHDevFlow/actions/runs/42093359872), HEAD `88552fa74a4f9b9d76608d752736a0c59cd5f1d9` | CI final da entrega inicial `completed/success`; substitui o antigo campo `NÃO_EXECUTADO` para esse HEAD histórico. |
| E10 | OBSERVADO | [Review CH-AUD-W2B-01](https://github.com/hallanbrito/CHDevFlow/pull/57#pullrequestreview-5790852194) e [gate R1](https://github.com/hallanbrito/CHDevFlow/issues/56#issuecomment-6667473112) | Três correções autorizadas: vínculo da reserva, estado após exceção, RUC/CI. |
| E11 | OBSERVADO | LOCAL_REPO: `/tmp/chdevflow-w2b-r1-root.log`, `/tmp/chdevflow-w2b-r1-sentinela.log` e suíte W2-B | R1: 21 testes W2-B `OK`; raiz 290 `OK (skipped=1)`; Sentinela 69 `OK`; `compileall` e `git diff --check` sem erro. |
| E12 | OBSERVADO | [CI Integral run 42098399116](https://github.com/hallanbrito/CHDevFlow/actions/runs/42098399116), HEAD `cb4d45c3dd93b2d17310bbe3b0c691d369ecd163` | CI da R1 de código `completed/success`; etapas raiz, Sentinela e Control Center com `success`. O commit posterior deste RUC exige reconferência própria, registrada externamente na PR. |

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
| CI Integral da implementação | Workflow `CHDevFlow CI Integral` no HEAD `86a8808` | PASSOU | E08; run 42093052181 |
| CI final da entrega inicial | Workflow no HEAD `88552fa` | PASSOU | E09; run 42093359872 |
| Regressões R1 | Relatório forjado, Issue divergente, executor adulterado, replay, exceções e diagnóstico | PASSOU | E11; 21 testes W2-B no total |
| Suítes locais R1 | Raiz, Sentinela, `compileall`, `git diff --check` | PASSOU | E11; raiz 290 `OK (skipped=1)`, Sentinela 69 `OK` |
| CI da R1 de código | Workflow no HEAD `cb4d45c` | PASSOU | E12; run 42098399116 |
| Agentes reais, custo operacional e GitHub Project #2 | Execução/alteração fora do escopo | NÃO_APLICÁVEL | Nenhum agente real despachado pelo produto; custo real NÃO_VERIFICADO |

Na primeira rodada da suíte raiz, dois testes de wheel falharam porque `uv` tentou escrever em `/home/hallan/.cache/uv`, somente leitura no sandbox. O cache foi copiado para `/tmp` e a suíte inteira foi repetida offline com `OK`. O log da primeira rodada permanece em `/tmp/chdevflow-w2b-root-tests.log`; não é uma falha de código concluída como PASS sem reteste.

## 6. Riscos e bloqueios

- Autorização GitHub autenticada, identidade do PO, licença e custo adicional R$ 0 **não são implementados nem verificados** no produto. A fixture serve apenas à simulação.
- Reserva em memória não é lock atômico entre processos nem persiste após crash. Um adaptador operacional futuro requer nova Fatia e novo gate.
- O teste local de Control Center não rodou por falta de `pytest`; as CI dos HEADs `88552fa` e `cb4d45c` cobriram a suíte (E09, E12). O resultado da CI do commit deste RUC será registrado no corpo da PR após confirmação, pois o próprio relatório não pode antecipar a verificação de seu SHA.
- Sanitização cobre padrões conhecidos; saída não confiável precisa de revisão antes de publicação fora da fixture.

## 7. Alterações realizadas

- `src/chdevflow/core/dry_run_dispatcher.py`: núcleo e adaptadores fake.
- `tests/test_w2b_dry_run_dispatcher.py`: matriz offline.
- `docs/W2-B/README.md`: interface e fronteiras.
- `docs/W2-B/RUC-W2-B-01.md`: este relatório.

R1: alterações restritas aos quatro caminhos acima, sem novo arquivo. O diff incremental R1 antes da atualização do RUC foi `+52/-12` no dispatcher, `+68/-6` nos testes e `+1/-1` no README, conforme comparação GitHub `88552fa..cb4d45c`.

Publicação: branch e Draft PR #57. Nenhum merge, deploy, release, mudança em `main`, Project #2, ruleset CH-SEC-01 ou outros repositórios. Custo adicional real da sessão: **NÃO_VERIFICADO**; custo declarado pelo resultado fake: zero, com `verified=False`.

## 8. Recomendação técnica

**PARCIAL** no momento do registro: os testes offline e a CI da R1 de código passaram; a CI do commit deste RUC e a nova auditoria independente ainda precisam ser conferidas. Recomendo revisão do diff e dos limites antes de qualquer decisão de integração. Não recomendo habilitar execução real neste gate.

## 9. Decisão necessária do PO

**PENDENTE** — Após auditoria independente e CI do HEAD final, aceitar, pedir ajustes ou reprovar a entrega; eventual merge exige despacho separado do PO. Nenhuma decisão `Decisao PO` foi alterada pelo executor.
