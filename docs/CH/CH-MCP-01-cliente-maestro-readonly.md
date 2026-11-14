# CH-MCP-01 — Integracao local com Maestro MCP (F1 somente leitura)

**Issue:** #73 · **Status:** branch experimental / sem ativacao automatica.
**Servidor canonico:** Maestro Router Issue #70.

## Funcionalidade

O script `scripts/maestro_mcp_probe.py` usa o cliente MCP oficial (SDK v2) para iniciar o servidor **local stdio** do Maestro e consultar UMA das tres tools: `maestro_catalog`, `factory_issues`, `fallback_evidence`.

Nenhum caminho de escrita ou dispatch foi implementado. Esta integracao nao substitui o dispatcher, o Project #2, a supervisao horaria ou a F1 da Issue #72 do AGY.

## Pre-requisitos

- Python **>=3.11** no ambiente do experimento (o CHDevFlow core continua >=3.10).
- Repositorio `maestro-router` clonado localmente e com `src/maestro_router/factory_mcp.py`.
- SDK oficial `mcp>=2,<3` instalado SOMENTE no ambiente do experimento.
- Nao e preciso pagar API de modelo. Consultas publicas ao GitHub podem sofrer rate limit; token opcional do GitHub deve permanecer no ambiente.

Exemplo, estando no checkout CHDevFlow e com o venv MCP ativado:

~~~bash
python -m pip install "mcp>=2,<3"
python scripts/maestro_mcp_probe.py --maestro-repo ../maestro-router --tool factory_issues --project CHDevFlow --limit 5
python scripts/maestro_mcp_probe.py --maestro-repo ../maestro-router --tool fallback_evidence
python scripts/maestro_mcp_probe.py --maestro-repo ../maestro-router --tool maestro_catalog
~~~

Para a ultima consulta, inicie antes o Control Center local do Maestro. Se estiver indisponivel, o resultado correto e `status=unavailable`.

O script preserva o PYTHONPATH existente, adicionando apenas o `src` do Maestro no subprocesso. O stdout apresenta somente a resposta da tool, sem exportar variaveis de ambiente.

## Testes

~~~bash
python -m pytest -q tests/test_maestro_mcp_probe.py
~~~

Sao testes locais offline de validacao de checkout, configuracao do subprocesso e rejeicao de tool fora da allowlist. Nao atestam handshake real nem uso autenticado no ChatGPT.

## Proximos gates

1. Revisar PR do gateway Maestro MCP-01 e PR deste cliente separadamente; sem merge antes de auditoria independente.
2. Comprovar handshake e redacao em ambiente local.
3. Evoluir opcionalmente para servidor remoto autenticado (OAuth 2.1/HTTPS ou tunel seguro) somente com gate especifico do PO.
4. Tratar fallback real no Maestro [Issue #61](https://github.com/hallanbrito/maestro-router/issues/61): POC #51 nao e runtime homologado. Nao usar rota paga implicitamente.
