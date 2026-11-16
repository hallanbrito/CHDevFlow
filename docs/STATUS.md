# CHDevFlow — Snapshot de estado integrado (baseline)

**Verificado em:** 16/11/2026, na origem `hallanbrito/CHDevFlow`.
**HEAD da `main` conferido:** `ce939630363f8f762d0f0810a78735fe6975f7ff`.
**Não atualizar este documento só porque abriu uma Draft PR.** Atualizar após integração/homologação verificáveis.

## Já presente na main (código real)

- CLI `ch`, comandos de scaffolding, governança e verificação; Sentinela (FakeWorker e consultas de workflow); Control Center FastAPI em `127.0.0.1:8000`, dashboard e `/missoes` em leitura.
- `src/chdevflow/core/local_executor.py`: descobre CLIs e executa subprocessos locais com timeout.
- `experimental_pilot.py`: piloto fixo AGY → Python/unittest → Codex → dossiê.
- `controlled_cycle.py`: ciclo de até 3 tentativas AGY / 2 devoluções técnicas.
- `generic_cycle.py`: missões Python por manifesto, validação de escopo/worktree, testes e Codex, ainda sem UI.
- F7 de governança/custódia integrado em fases anteriores; **`REMOTE_PUBLICATION_ENABLED=False`**. Gate 3 de publicação V1 continua não homologado.

## Operação demonstrada vs. não demonstrada

| Camada | Estado no snapshot |
|---|---|
| POC-03 AGY real + Python + Codex, Windows (14/11) | Evidência local comunicada pelo PO e registrada em #78; **não** equivale a serviço contínuo |
| Pipeline de laboratório F5/F6 | Implementado no código; regressões CI usam dublês; execuções reais devem ser avaliadas pelo dossiê exato |
| Control Center `/missoes` | **Somente leitura**, falta botão/serviço de despacho |
| Notebook 16/11 | `agy` e `codex` encontrados; `accept-edits --print` bloqueou pela permissão `command` headless |
| Uso de `--mode plan` para obter fonte sem ferramentas de edição | Já implementado em `experimental_pilot.py` e `generic_cycle.py` |
| F7 E3-B a E3-C5 | Provas reais de Docker/Sigstore e testes de rejeição, **em Draft PRs**, não integrados |
| Missão V1 real via painel com AGY/Codex + decisão PO | **PENDENTE** |
| Publicação F7 externa | **DESATIVADA** |

## Workstream prioritário

- [Issue #121 — CC-DESPACHO-01](https://github.com/hallanbrito/CHDevFlow/issues/121): **prioridade do MVP**. Implementador AGY; Codex auditor; CH-1 arquiteto/supervisor; PO aprova. Reusar motores existentes; objetivo é uma missão real iniciada na UI local.
- [Issue #78](https://github.com/hallanbrito/CHDevFlow/issues/78), [#85](https://github.com/hallanbrito/CHDevFlow/issues/85): histórico de provas/ciclo local.
- [Issue #95](https://github.com/hallanbrito/CHDevFlow/issues/95), [#117](https://github.com/hallanbrito/CHDevFlow/issues/117): governança F7 e futuro piloto V1, não prioridades operacionais do MVP local.

## F7 congelada para expansão — não apagar

Draft PRs encadeadas: [#94](https://github.com/hallanbrito/CHDevFlow/pull/94), [#113](https://github.com/hallanbrito/CHDevFlow/pull/113), [#114](https://github.com/hallanbrito/CHDevFlow/pull/114), [#115](https://github.com/hallanbrito/CHDevFlow/pull/115), [#116](https://github.com/hallanbrito/CHDevFlow/pull/116), [#118](https://github.com/hallanbrito/CHDevFlow/pull/118), [#119](https://github.com/hallanbrito/CHDevFlow/pull/119), [#120](https://github.com/hallanbrito/CHDevFlow/pull/120). **Não presumir merge; verificar cada PR.**
Na F7, Gate 1 (Solo) e Gate 2 estavam aceitos *operacionalmente*: **2/5 (40%)**; Gate 3 bloqueado; Gates 4/5 pendentes. Esses gates NÃO medem progresso da fábrica local.

> Para links de CI, distinção entre provas reais e mocks, versões e limitações, ler [CHDEVFLOW-EVIDENCIAS](CH/CHDEVFLOW-EVIDENCIAS.md). Não converter contagens históricas de testes em promessa de estado atual.
