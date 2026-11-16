# CHDevFlow — Inventário de testes, provas e componentes reutilizáveis

**Baseline revisada:** `main` = `ce939630363f8f762d0f0810a78735fe6975f7ff` em 16/11/2026.
**Finalidade:** impedir que uma funcionalidade já escrita/testada seja reinventada.

> Inventário consolidado das **famílias de provas e marcos relevantes identificados**, não um catálogo completo de todos os casos de teste/commits do projeto. Para contagem atual, executar CI no SHA exato. PR Draft ≠ código em `main`.

## 1. Escala obrigatória de evidência

| Código | Evidência | O que prova | O que não prova |
|---|---|---|---|
| **DOC** | Proposta, RFC, Issue, arquitetura | Intenção/decisão/escopo | Código funcional |
| **OFF** | Teste offline (mock/fake/fixtures), CI | Contrato e regressão de código naquele SHA | Invocação/autenticação de modelo real |
| **LOCAL** | Log/dossiê observado ou fornecido pelo PO no dispositivo | Comportamento daquele piloto local e data | Operação contínua, independência externa, universalidade |
| **LIVE** | GitHub API/Actions, imagem Docker/atestação executadas de verdade | Ação remota exata, origem/artefato/suite observados | AGY/Codex reais, se não foram chamados |
| **E2E** | UI real → AGY real → testes reais → Codex real → decisão PO | Fluxo de produto no ambiente e na revisão | Produção remota/auto-merge sem nova autorização |

**Regra:** CI `success` é evidência de **testes daquela execução**, não prova automática de missão real AGY/Codex. Nunca confundir `MockWorker`, `FakeWorker`, contrato ou `DRY_RUN` com execução de agentes.

## 2. Evolução comprovada e fontes primárias

| Marco | Tipo | Entrega/prova observada | Reutilização / fonte |
|---|---|---|---|
| W1 — GitHub Project #2, campos e Esteiras | LOCAL/LIVE históricos | Issues, Kanban e mutações via `gh`/GitHub usadas e conferidas pontualmente; a existência de cartão **não** concede CH-2 | [W1](../W1-ESTEIRAS-KANBAN.md), [Issue #7](https://github.com/hallanbrito/CHDevFlow/issues/7), [CH-GOV-01](CH-GOV-01-F2-2-ADMISSAO.md) |
| CLI `ch`, scaffolding `ch new/init`, verificação e RUC | OFF/LIVE | Codebase integrada na `main`; CI integral de referência verificada em [29/10 #40967464798](https://github.com/hallanbrito/CHDevFlow/actions/runs/40967464798) e [03/11 #41656696559](https://github.com/hallanbrito/CHDevFlow/actions/runs/41656696559) | [README](../../README.md), `src/chdevflow/cli.py`, testes `test_cli_*.py`, `test_verify_security_p04.py` |
| Sentinela BOOT-01 | OFF/LOCAL | Contratos, observação sob demanda e FakeWorker até etapa de decisão; **nenhum AGY/Codex real nesse modo** | [AGENTS Sentinela](../../apps/bootstrap/sentinela/AGENTS.md), `apps/bootstrap/sentinela/tests/` |
| W2-B dispatcher dry-run | OFF | `DryRunDispatcher`, `CodexExecFake` e `AgyPrintFake`, reserva simulada, casos positivos/negativos; `run_authorized=False` | [W2-B](../W2-B/README.md), `tests/test_w2b_dry_run_dispatcher.py` |
| Control Center CC-01 — painel e missões | OFF/LOCAL | FastAPI, `/missoes`, DAG, filtros, modos `DEMO_OFFLINE`/`LIVE_GITHUB`, CSRF e loopback; relatos de leitura LIVE e 28/28 itens após sync em 06/11. **Tela só lista/detalha; não despacha** | [Control Center](../../apps/control-center/README.md), `apps/control-center/src/ch_control_center/routes/missions.py`, `apps/control-center/tests/` |
| Integração CLI/Sentinela/CC, P0-03/P0-04 | OFF/LIVE | Suítes da raiz, Sentinela e CC testadas; CI integral [06/11 #42314423375](https://github.com/hallanbrito/CHDevFlow/actions/runs/42314423375) **success**; `ch verify` endurecido para execução e identidade | [P0 docs](CH-RUC-20261031-AUD-GERAL-P0-04.md), `.github/workflows/w1-checks.yml` |
| POC-01 (14/11, Windows 11) | LOCAL | Python consultou **31 itens** do Project #2 e chamou AGY para triagem; não gerou software naquela tentativa | [Issue #78](https://github.com/hallanbrito/CHDevFlow/issues/78) |
| POC-02 (14/11, Windows 11) | LOCAL | Python coordenou AGY → Codex → dossiê para mesmo snapshot; prova de comunicação entre ferramentas, **não** de código de missão produzido nem de revisão GitHub independente | [Issue #78](https://github.com/hallanbrito/CHDevFlow/issues/78) |
| POC-03 (14/11, Windows 11) | **LOCAL real** | AGY produziu `src/estoque.py` e testes; recheck executou **13 testes AGY + 9 de aceite**, AST/escopo PASS; parecer Codex `APROVAR_LAB`. Run local `RECHECK-20261114T183911Z-0b2838` (origem `20261114T182819Z-52dbd9`) | [Issue #78](https://github.com/hallanbrito/CHDevFlow/issues/78), [POC-03 doc](CH-PIPE-01-POC03.md) |
| F1 — inspeção de dossiê POC-03 | OFF | `ch pipeline inspect` valida arquivos, hashes, testes e veredito **sem chamar agentes**; não é nova POC real | [POC-03 doc](CH-PIPE-01-POC03.md), `tests/test_ch_pipe_01_manual_lab.py` |
| F2–F4 — manifesto, autorização e readiness | OFF | Contratos, gates, mocks de custo e segurança; execução default inativa | [F2](CH-PIPE-01-F2-MANUAL.md), [F3](CH-PIPE-01-F3-GATE.md), [F4](CH-PIPE-01-F4-READINESS.md) |
| F5 — `experimental_pilot.py` | OFF, LOCAL experimental | Já implementa AGY `--mode plan --output-format json --print` → JSON/código → validação/`unittest` → Codex read-only → `RELATORIO_COMPLETO_CH1.md`. Testes de CI com dublês não equivalem a AGY real no notebook | [F5](CH-PIPE-01-F5-LOCAL-PILOT.md), [executor](CH-PIPE-01-LOCAL-EXECUTOR.md), `tests/test_ch_pipe_01_f5_lab_pilot.py` |
| CCC-01 — `controlled_cycle.py` | OFF | **Até 3 AGY / 2 devoluções técnicas**; bloqueio de infraestrutura, resultado persistido, escalonamento local após terceira reprovação; suíte `test_ch_pipe_01_ccc01.py` | [Decisão CCC-01](CH-PIPE-01-CICLO-CORRECAO-CONTROLADA.md), [Issue #78](https://github.com/hallanbrito/CHDevFlow/issues/78) |
| F6 — `generic_cycle.py` | OFF, LOCAL experimental | Generaliza missão Python de um arquivo por manifesto, SHA/worktree/allowlist, testes independentes e Codex; referência de CI integral [15/11 #43710186781](https://github.com/hallanbrito/CHDevFlow/actions/runs/43710186781) `success` | [F6](CH-PIPE-01-F6-MISSOES-PYTHON.md), [Issue #85](https://github.com/hallanbrito/CHDevFlow/issues/85), `tests/test_ch_pipe_01_f6_generic_cycle.py` |
| F6 — incidente de auditoria frete (15/11) | LOCAL negativo | **15/15 testes por tentativa** não bastaram: Codex rejeitou três rodadas por evidência/diff insuficientes; gerou correções de contrato. Isso prova que **testes verdes não anulam auditoria** | [F6 — incidente](CH-PIPE-01-F6-MISSOES-PYTHON.md) |
| F7 — reserva/custódia/sincronização | LIVE parcial | Prova GitHub da reserva [#43746287761](https://github.com/hallanbrito/CHDevFlow/actions/runs/43746287761) `success`; gates 1 (Solo) e 2 aceitos operacionalmente, **2/5**. Não liberar publicador; ``REMOTE_PUBLICATION_ENABLED=False` | [F7](CH-PIPE-01-F7-CUSTODY.md), [Issue #95](https://github.com/hallanbrito/CHDevFlow/issues/95) |
| E3-B — Docker executor real **sem agentes** | LIVE | [Run #43887485901](https://github.com/hallanbrito/CHDevFlow/actions/runs/43887485901) `success` no SHA `389bcc61342cbcdd3183e291a18eef42ad78f488`; TAR com digest pinado, testes positivos/negativos Docker, assinatura [#68161760](https://github.com/hallanbrito/CHDevFlow/attestations/68161760) | [Draft PR #113](https://github.com/hallanbrito/CHDevFlow/pull/113) |
| E3-C0 — consumo do TAR assinado **sem agentes** | LIVE | [Run #43888441966](https://github.com/hallanbrito/CHDevFlow/actions/runs/43888441966) `success` no SHA `075ddbdb39bd32a824b212cd531461543d1307d9`; novo manifesto [Sigstore #68164164](https://github.com/hallanbrito/CHDevFlow/attestations/68164164), verificação em segundo job e rejeição de adulteração | [Draft PR #114](https://github.com/hallanbrito/CHDevFlow/pull/114) |
| E3-C1 — preflight fail-closed V1 | OFF/LIVE | [CI #43927134415](https://github.com/hallanbrito/CHDevFlow/actions/runs/43927134415) `success`; reconhece LAB atestado e o rejeita como execução/autorização V1 | [Draft PR #115](https://github.com/hallanbrito/CHDevFlow/pull/115) |
| E3-C2 — autorização futura de missão | OFF/LIVE negativa | [CI #43929136326](https://github.com/hallanbrito/CHDevFlow/actions/runs/43929136326) `success`; testes de autorização e run de `push` rejeitado como produtor V1 | [Draft PR #116](https://github.com/hallanbrito/CHDevFlow/pull/116) |
| E3-C3 — executor E3-B integrado ao ciclo, **AGY/Codex mockados** | OFF/LIVE Docker | [CI #43931274773](https://github.com/hallanbrito/CHDevFlow/actions/runs/43931274773) `success`; 9 testes de adaptador + 24 F6; Docker positivo/negativo e TAR adulterado rejeitado | [Draft PR #118](https://github.com/hallanbrito/CHDevFlow/pull/118) |
| E3-C4 — recibo externo da missão | OFF | [CI #43932915045](https://github.com/hallanbrito/CHDevFlow/actions/runs/43932915045) `success`; 117 testes de validador/publicação/identidade. **Recibo V1 real não existe; assinatura positiva só mockada** | [Draft PR #119](https://github.com/hallanbrito/CHDevFlow/pull/119) |
| E3-C5 — negar Docker legado para publicação F7 | OFF/LIVE negativa | [CI #43934169564](https://github.com/hallanbrito/CHDevFlow/actions/runs/43934169564) `success` em Linux/Windows, negativa GH LIVE; **atestador V1 real permanece sem assinatura**, pins vazios | [Draft PR #120](https://github.com/hallanbrito/CHDevFlow/pull/120) |
| CC-DESPACHO-01 — retomada do produto (16/11) | DOC/PREFLIGHT | [Issue #121](https://github.com/hallanbrito/CHDevFlow/issues/121) aberta. Notebook CachyOS: `agy` em `/home/hallan/.local/bin/agy` e `codex-cli 0.167.0` encontrados. Chamada AGY direta `--mode accept-edits --print --sandbox` foi **NEGADA pela permissão `command` no headless**; nenhuma implementação nessa tentativa. | [Issue #121](https://github.com/hallanbrito/CHDevFlow/issues/121) |

## 3. Quais módulos e testes NÃO devemos recriar

| Capacidade | Código que já existe na baseline | Família de testes |
|---|---|---|
| Descobrir AGY/Codex, ambiente local, executar subprocesso e encerrar em timeout | `src/chdevflow/core/local_executor.py` | `tests/test_ch_local_executor.py` |
| Chamar AGY por JSON em modo plan, recuperar código, validar AST e testar | `src/chdevflow/core/experimental_pilot.py` | `tests/test_ch_pipe_01_f5_lab_pilot.py` |
| Devolver falhas técnicas ao AGY e limitar 3 tentativas | `src/chdevflow/core/controlled_cycle.py` | `tests/test_ch_pipe_01_ccc01.py` |
| Reusar o ciclo para missões Python via manifesto e worktree | `src/chdevflow/core/generic_cycle.py` + `manual_pipeline_runner.py` | `tests/test_ch_pipe_01_f6_generic_cycle.py` |
| Testes Docker Linux opt-in | `src/chdevflow/core/docker_acceptance.py` | `tests/test_ch_pipe_01_f6_docker_acceptance.py` |
| W2-B simulação sem ferramentas reais | `src/chdevflow/core/dry_run_dispatcher.py` | `tests/test_w2b_dry_run_dispatcher.py` |
| Consultar Project/Sentinela e exibir missões | `apps/control-center/src/ch_control_center/` | `apps/control-center/tests/` |
| CI integral root + Sentinela + Control Center | `.github/workflows/w1-checks.yml` | `tests/` + `apps/bootstrap/sentinela/tests/` + `apps/control-center/tests/` |
| Documento de implantação e uso de executor | `docs/CH/CH-PIPE-01-LOCAL-EXECUTOR.md` | Histórico e riscos do laboratório |

**Não confundir `generic_cycle` na `main` com sua variante de teste E3-C3 na Draft PR #118**; cada PR tem base e HEAD próprios.

## 4. Como reproduzir **sem chamar modelos**

Na raiz de uma worktree do SHA que se deseja inspecionar:

~~~bash
PYTHONPATH=src:apps/bootstrap/sentinela/src python -m unittest discover -s tests -p 'test_ch_local_executor.py' -v
PYTHONPATH=src:apps/bootstrap/sentinela/src python -m unittest discover -s tests -p 'test_ch_pipe_01_ccc01.py' -v
PYTHONPATH=src:apps/bootstrap/sentinela/src python -m unittest discover -s tests -p 'test_ch_pipe_01_f5_lab_pilot.py' -v
PYTHONPATH=src:apps/bootstrap/sentinela/src python -m unittest discover -s tests -p 'test_ch_pipe_01_f6_generic_cycle.py' -v
PYTHONPATH=src:apps/bootstrap/sentinela/src:apps/control-center/src python -m pytest apps/control-center/tests -q
~~~

`python -m chdevflow.core.local_executor doctor` **só verifica descoberta de CLIs**, não logins.
`python -m chdevflow.core.local_executor run/cycle --i-accept-local-risk` **aciona agentes reais e NÃO é teste offline**. Nunca disparar essas entradas inadvertidamente em CI, codificação documental ou inspeção de contexto.

## 5. Falhas observadas que devem virar conhecimento, não retrabalho

1. **POC real não é homologação de produto:** dossiê POC-03 existe, mas ainda não há botão na UI nem mecanismo permanente de despacho.
2. **Erro `command` headless:** `--mode accept-edits --print` pode auto-negar ferramenta; evitar `--dangerously-skip-permissions`; reutilizar padrão `--mode plan --output-format json --print` que extrai código pela resposta, validando envelope/status e código antes de executar.
3. **Codex pode reprovar mesmo com testes PASS:** revisar patch contra baseline imutável, código efetivamente auditado e escopo; ver incidente frete F6.
4. **Win/Linux e credenciais:** CLIs encontradas não provam sessões autenticadas/custo. Modelo executado no host herda usuário local; não copiar tokens nem supor que ChatGPT Work compartilha cofre do notebook.
5. **Worktree não é sandbox de SO:** privilégios continuam do processo local. Executar só laboratório sem segredos e escopo restrito; não tocar repositório de produção.
6. **F7 tomou prioridade indevida:** muitos checks/provas Docker/Sigstore em Draft não concluíram a missão de produto. Congelar expansão, não apagar evidências. A régua do MVP deve ser **1 missão real via UI**.
7. **Testes unitários em milhares de linhas não substituem E2E:** registrar resultado, commit, ambiente, entradas, autor, saída, custo, risco e links. Falha ou execução não observada = PENDENTE.

## 6. Evidência obrigatória em qualquer relato futuro

Relate sempre `data`, `ambiente`, `repo/branch/HEAD`, `comando executado`, `AGY real ou fake`, `Python testes reais`, `Codex real ou mock`, `status`, `hashes/logs`, `limitações` e `decisão do PO`. Se não houver artefatos, dizer **não comprovado**. Atualizar este inventário **só depois de nova prova**; não reescrever história para parecer progresso.

**Fontes canônicas complementares:** [Projeto](../PROJETO.md) · [Decisões](DECISOES.md) · [STATUS](../STATUS.md) · [Issue #121](https://github.com/hallanbrito/CHDevFlow/issues/121).
