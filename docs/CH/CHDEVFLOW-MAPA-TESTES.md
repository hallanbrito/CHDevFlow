# CHDevFlow — Mapa de testes existentes (onde encontrar cada prova)

**Inventário estrutural do commit `ce939630363f8f762d0f0810a78735fe6975f7ff` (`main`, 16/11/2026):**
**31** arquivos `tests/test_*.py` na raiz, **6** da Sentinela, **8** do Control Center = **45 módulos de testes**. Há ainda `browser_smoke.py`, `conftest.py` e **5 workflows Actions**. Esses números são **arquivos**, **não contagem de casos PASS**.

**Como interpretar:** estas referências comprovam que **há código de teste** para cada domínio, não que todos rodaram com sucesso em qualquer HEAD. Resultados reais da CI/POC, com links e diferenças entre AGY real/mock, estão em [CHDEVFLOW-EVIDENCIAS.md](CHDEVFLOW-EVIDENCIAS.md).

## 1. CLI, inicialização, verificação e empacotamento (raiz)

- [`tests/test_cli_01.py`](../../tests/test_cli_01.py), [`test_cli_02.py`](../../tests/test_cli_02.py), [`test_cli_03.py`](../../tests/test_cli_03.py), [`test_cli_04.py`](../../tests/test_cli_04.py), [`test_cli_05.py`](../../tests/test_cli_05.py), [`test_cli_06.py`](../../tests/test_cli_06.py) — suíte CLI por fatia.
- [`tests/test_cli_audit_fixes.py`](../../tests/test_cli_audit_fixes.py) e [`test_cli_strict_status.py`](../../tests/test_cli_strict_status.py) — correções de CLI e estado estrito.
- [`tests/test_verify_security_p04.py`](../../tests/test_verify_security_p04.py) — segurança do `ch verify`.
- [`tests/test_packaging_wheel_audit.py`](../../tests/test_packaging_wheel_audit.py) — distribuição/instalação.
- [`tests/test_ci_integral_audit.py`](../../tests/test_ci_integral_audit.py) — garantias da CI integral.

## 2. Sentinela, Project #2, governança e sincronização (raiz)

- [`tests/test_ch_intake_check.py`](../../tests/test_ch_intake_check.py) — check de intake.
- [`tests/test_w1_github_project.py`](../../tests/test_w1_github_project.py) — regras de W1/Project.
- [`tests/test_project_export.py`](../../tests/test_project_export.py) — exportação Project.
- [`tests/test_ch_project_sync.py`](../../tests/test_ch_project_sync.py) — sincronização Project.
- [`tests/test_ch_project_assist.py`](../../tests/test_ch_project_assist.py) — assistente/admissão Project.
- [`tests/test_ch_project_autonomy.py`](../../tests/test_ch_project_autonomy.py) — política de autonomia.
- [`tests/test_ch_stage_evidence.py`](../../tests/test_ch_stage_evidence.py) — estágios/evidências.

## 3. Pipeline AGY → Python → Codex e F7 (raiz)

- [`tests/test_w2b_dry_run_dispatcher.py`](../../tests/test_w2b_dry_run_dispatcher.py) — simulação W2-B; NÃO chama agente real.
- [`tests/test_ch_pipe_01_manual_lab.py`](../../tests/test_ch_pipe_01_manual_lab.py) — inspeção do laboratório/POC.
- [`tests/test_ch_local_executor.py`](../../tests/test_ch_local_executor.py) — processo local, entrada e descoberta de CLIs, com dublês na CI.
- [`tests/test_ch_pipe_01_f2_manual_runner.py`](../../tests/test_ch_pipe_01_f2_manual_runner.py) — plano manual.
- [`tests/test_ch_pipe_01_f3_gate.py`](../../tests/test_ch_pipe_01_f3_gate.py) — gate de autorização.
- [`tests/test_ch_pipe_01_f4_readiness.py`](../../tests/test_ch_pipe_01_f4_readiness.py) — readiness de execução.
- [`tests/test_ch_pipe_01_f5_lab_pilot.py`](../../tests/test_ch_pipe_01_f5_lab_pilot.py) — AGY/Python/Codex em piloto de laboratório, **testes de unidade não são chamada real de modelos**.
- [`tests/test_ch_pipe_01_ccc01.py`](../../tests/test_ch_pipe_01_ccc01.py) — até 3 tentativas AGY / 2 devoluções.
- [`tests/test_ch_pipe_01_f6_generic_cycle.py`](../../tests/test_ch_pipe_01_f6_generic_cycle.py) — missão Python genérica por manifesto.
- [`tests/test_ch_pipe_01_f6_docker_acceptance.py`](../../tests/test_ch_pipe_01_f6_docker_acceptance.py) — testes com Docker/aceitação.
- [`tests/test_ch_pipe_01_f7_po_escalation.py`](../../tests/test_ch_pipe_01_f7_po_escalation.py) — escalonamento para PO.
- [`tests/test_ch_pipe_01_f7_publication.py`](../../tests/test_ch_pipe_01_f7_publication.py) — contrato/gates de publicação F7, **não pressupõe POST real**.
- [`tests/test_f7_custody_live.py`](../../tests/test_f7_custody_live.py) — contrato da prova de custódia F7.

## 4. Sentinela (módulo separado)

- [`test_cli.py`](../../apps/bootstrap/sentinela/tests/test_cli.py)
- [`test_contracts.py`](../../apps/bootstrap/sentinela/tests/test_contracts.py)
- [`test_github_reader.py`](../../apps/bootstrap/sentinela/tests/test_github_reader.py)
- [`test_security.py`](../../apps/bootstrap/sentinela/tests/test_security.py)
- [`test_sentinel.py`](../../apps/bootstrap/sentinela/tests/test_sentinel.py)
- [`test_supervisor.py`](../../apps/bootstrap/sentinela/tests/test_supervisor.py)

**Alerta:** a Sentinela mantém `FakeWorker` e não deve despachar AGY/Codex reais sem projeto/decisão separada. Ler seu [AGENTS](../../apps/bootstrap/sentinela/AGENTS.md).

## 5. Control Center (módulo separado)

- [`test_cc_quality_recovery.py`](../../apps/control-center/tests/test_cc_quality_recovery.py)
- [`test_dag_engine.py`](../../apps/control-center/tests/test_dag_engine.py)
- [`test_live_github_regression.py`](../../apps/control-center/tests/test_live_github_regression.py)
- [`test_mission_service.py`](../../apps/control-center/tests/test_mission_service.py)
- [`test_project_service.py`](../../apps/control-center/tests/test_project_service.py)
- [`test_routes_read_only.py`](../../apps/control-center/tests/test_routes_read_only.py)
- [`test_sentinela_adapter.py`](../../apps/control-center/tests/test_sentinela_adapter.py)
- [`test_server_security.py`](../../apps/control-center/tests/test_server_security.py)

**Suporte, não contados como módulos `test_*.py`:** [`browser_smoke.py`](../../apps/control-center/tests/browser_smoke.py) e [`conftest.py`](../../apps/control-center/tests/conftest.py). A rota `/missoes` da baseline ainda não possui despacho real.

## 6. Workflows na baseline integrada

- [`w1-checks.yml`](../../.github/workflows/w1-checks.yml) — CI integral.
- [`ch-intake-readonly.yml`](../../.github/workflows/ch-intake-readonly.yml) — Intake consultivo.
- [`f7-custody-producer.yml`](../../.github/workflows/f7-custody-producer.yml) — qualificação do produtor F7.
- [`f7-custody-attestor.yml`](../../.github/workflows/f7-custody-attestor.yml) — custódia F7 protegida.
- [`f7-reservation-live-proof.yml`](../../.github/workflows/f7-reservation-live-proof.yml) — reserva F7 LIVE.

**Workflows E3-B–E3-C5 pertencem a Draft PRs** #113–#120, não aparecem neste inventário de `main`. Seus resultados foram registrados separadamente em [CHDEVFLOW-EVIDENCIAS.md](CHDEVFLOW-EVIDENCIAS.md).

## 7. Comandos de regressão antes de propor mudança

~~~bash
# Todos os testes da raiz (não chamar modelos reais):
PYTHONPATH=src:apps/bootstrap/sentinela/src python -m unittest discover -s tests -p 'test_*.py' -v

# Contratos e FakeWorker da Sentinela:
PYTHONPATH=apps/bootstrap/sentinela/src python -m unittest discover -s apps/bootstrap/sentinela/tests -p 'test_*.py' -v

# Control Center, requer dependências locais de desenvolvimento:
PYTHONPATH=src:apps/bootstrap/sentinela/src:apps/control-center/src python -m pytest apps/control-center/tests -q
~~~

Antes de dizer que “passou”, registrar **qual comando realmente foi executado, no HEAD exato, com seu código de saída, total/skip e plataforma**. Caso não execute, marque apenas “comandos disponíveis” e cite a CI histórica separadamente.

**Condição para encerrar o inventário:** todas as famílias listadas são descobertas na árvore de `main` em 16/11; a quantidade de testes dentro de cada módulo e o status por HEAD exigem leitura/execução específica. A skill CHDevFlow deve consultar também o código produtivo antes de propor substituir qualquer componente.
