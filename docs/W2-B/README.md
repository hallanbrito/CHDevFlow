# W2-B — Dispatcher de prévia simulada

**Issue:** [#56](https://github.com/hallanbrito/CHDevFlow/issues/56) · **Autonomia de implementação:** CH-2 · **Estado do produto:** somente `DRY_RUN`.

O módulo `chdevflow.core.dry_run_dispatcher` recebe um contrato de missão da Sentinela, uma aprovação **de fixture** (`ContratoAutorizacao.is_simulation=True`), um SHA observado e uma raiz local. Ele devolve elegibilidade da **simulação**, motivo, digest, executor e plano. `run_authorized` é sempre `False`. Não há comando CLI ou método de execução real.

## Interface interna

- `DryRunDispatcher.preview(...)`: valida schema/digest por `validar_contrato_missao`, autorização de fixture por `ContratoAutorizacao.validar_contra_missao`, limites D06 exatos, SHA observado, escopo e symlinks. Custo e interface são parâmetros **de fixture**, sem valor probatório para uma missão real.
- `reserve_simulation(...)`, `finish_simulation(...)`, `cancel_simulation(...)`, `simulation_status(...)`: reserva e idempotência somente em memória. A reserva exige a mesma instância de relatório elegível produzida pela prévia deste dispatcher, com Issue, digest e executor originais; relatório fabricado ou replay com parâmetros diferentes é recusado. Uma reserva ativa por instância; replay idêntico devolve a mesma chave. A segunda tentativa exige diagnóstico e nova aprovação **simulada**. Crash ou exceção de normalização gera `INDETERMINATE` com diagnóstico consultável e libera a reserva ativa; a reserva não é persistente nem adequada a múltiplos processos.
- `CodexExecFake` e `AgyPrintFake`: normalizam linhas JSONL/stream-json já presentes em `FixtureTrace`. O primeiro reconhece `turn.completed`; o segundo, `result`. Erro, JSON parcial, stderr, permissão negada e saída sem marcador terminal bloqueiam mesmo com `exit_code=0`. Ambos devolvem `ContratoWorkerResultado` da Sentinela, com custo real `verified=False` e nenhum artefato.

Os adaptadores não importam nem chamam `subprocess`, rede, CLIs, modelos ou APIs. Os nomes `codex_exec` e `agy_print` descrevem apenas formatos de fixture. Nenhuma flag ou variável de ambiente ativa execução. A saída de eventos é tratada como dado não confiável e passa por `sanitize_output`; não é interpretada como instrução. A simulação não altera GitHub Project, branch, arquivos do alvo nem `Decisao PO`.

## Fronteira para etapa futura

Uma futura execução real exige outra Fatia W e novo gate humano: prova de identidade/autorização GitHub vinculada à revisão exata, custo adicional R$ 0 verificável, licença, sandbox/menor privilégio, cancelamento confiável, lock atômico entre processos, controle de mudanças no escopo e proteção de `main`. Esta entrega **não** fornece esses componentes nem valida a interface operacional das CLIs. A aprovação de fixture jamais pode ser promovida a autorização real.

## Verificação offline

Na raiz do repositório, com as dependências de desenvolvimento já disponíveis:

```sh
PYTHONPATH=src:apps/bootstrap/sentinela/src python3 -m unittest discover -s tests -p 'test_w2b_dry_run_dispatcher.py' -v
PYTHONPATH=src:apps/bootstrap/sentinela/src python3 -m unittest discover -s tests -v
PYTHONPATH=src:apps/bootstrap/sentinela/src python3 -m unittest discover -s apps/bootstrap/sentinela/tests -v
PYTHONPATH=src:apps/bootstrap/sentinela/src:apps/control-center/src python3 -m pytest apps/control-center/tests -q
python3 -m compileall -q src scripts apps
```

Os testes W2-B interceptam `subprocess.run`, `subprocess.Popen` e `socket.socket` e falham se o simulador os chamar. A CI integral do repositório executa as três suítes em PRs para `main`. A matriz de referência permanece em [W2-A/03](../W2-A/03-PLANO-DE-TESTES.md); casos que exigem agente, host ou GitHub reais continuam não executados.
