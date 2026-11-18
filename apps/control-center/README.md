# CHDevFlow Control Center — MVP v0.2 (Fatia CC-01)

> **CC-01: supervisão somente leitura; PR #123: despacho local experimental opt-in (CC-DESPACHO-01)**
> **Conformidade Canônica:** Decisões D01, D05, D06, D07, RFC-CH-DEVFLOW-001, ADR-CC02-01, ADR-CC02-02, ADR-CC02-03.

---

## 1. Visão Geral

O **CHDevFlow Control Center** é a central de observabilidade, inteligência de missões e governança visual do ecossistema CHDevFlow.

Na fatia original **CC-01**, a supervisão permanece somente leitura. A [PR #123](https://github.com/hallanbrito/CHDevFlow/pull/123) adiciona **despacho local experimental opt-in por manifesto pré-preparado**, com confirmação individual do PO:
- **Despacho não automático:** a interface invoca F6 (AGY → testes → Codex) somente em laboratório descartável, com trava exclusiva persistente.
- **Segurança de Rede Local (RNF-01):** Conexão vinculada exclusivamente ao loopback (`127.0.0.1:8000`). Recusa formalmente vinculações externas como `0.0.0.0`.
- **Custo e isolamento da execução real NÃO verificados:** o piloto utilizou AGY/Codex autenticados, `cost_verified=false`, `os_isolation_verified=false`, testes no host; o modo consulta não comprova custo zero de agentes.
- **Decisão D05 Preservada:** Inicialização manual sob demanda, sem daemons permanentes e sem polling contínuo da rede.
- **Princípio Fail-Closed (D06):** Qualquer ciclo, dependência órfã ou dado corrompido bloqueia a tarefa em vez de tentar adivinhar a intenção do desenvolvedor.

---

## 2. As 7 Entregas Obrigatórias da Fatia CC-01

1. **Dashboard em Português Brasileiro:** Menu lateral responsivo, alternância de tema claro/escuro (`localStorage`), cartões métricos de Fatias W e tabela de monitoramento.
2. **Integração Somente Leitura via Composição:** Reutilização dos contratos canônicos e validadores da Sentinela Python (`ch_sentinela`) via `SentinelFacade`, sem duplicação de regras.
3. **Grafo Visual de Dependências (DAG Read-Only):** Ordenação topológica (Algoritmo de Kahn), classificação em raias/níveis, detecção de ciclos circulares (`BLOQUEADA_CICLO`) e identificação de dependências inexistentes (`BLOQUEADA_ORFA`).
4. **Central de Missões e Fatias W:** Tabela com busca textual instantânea, filtros por status e esteira (AGY, Codex, ChatGPT) e modal de inspeção detalhada.
5. **Modo Estudante Didático (ADR-CC02-03):** Glossário contextual do Método C.H., diagrama explicativo dos 9 estados da máquina de governança e detalhamento das 5 invariantes inegociáveis.
6. **Modo Demonstração Offline (RF-06):** Alternância transparente com um clique entre o snapshot de demonstração offline (`DEMO_OFFLINE`) e o GitHub Project #2 (`LIVE_GITHUB`), com banner de aviso explícito.
7. **Testes da versão atual:** suíte Control Center **153 passed, 1 warning** em 17/11/2026, incluindo a preparação guiada de missões e preflight F6 (Issue #124 / Fatia A); regressão P1 aprovada; piloto real CC-123 com **3/3** testes independentes, Codex textual `APROVAR_LAB`.

---

## 3. Como Inicializar e Testar Localmente

### Pré-requisitos
- Python 3.12+ (Homologado em Python 3.14 no CachyOS/Linux).
- Virtualenv local com dependências instaladas (`fastapi`, `uvicorn`, `jinja2`).

### Inicialização Rápida

Na raiz do repositório ou da worktree:

```bash
# 1. Exportar os módulos no PYTHONPATH
export PYTHONPATH="$PWD/src:$PWD/apps/control-center/src:$PWD/apps/bootstrap/sentinela/src"

# 2. Iniciar o servidor local (loopback 127.0.0.1:8000)
python -m ch_control_center
```

Utilize um ambiente Python em que as dependências do Control Center estejam instaladas. O script utilitário legado `./scripts/iniciar_control_center.sh` pode exigir ajuste do `PYTHONPATH`. **Não executar missão com segredos, dados pessoais ou código de produção.** [Relatório de homologação do piloto](../../docs/control-center/RUC-CC-DESPACHO-01-PILOTO-20261117.md).

### Acesso no Navegador (Firefox / Chromium)

Abra no seu navegador:
```
http://127.0.0.1:8000
```

Rotas navegáveis:
- `/` — Dashboard de supervisão com métricas e fatias recentes.
- `/missoes` — Central de missões com filtros e modais de inspeção.
- `/grafo` — Grafo visual DAG com níveis topológicos e alertas de circularidade.
- `/estudante` — Modo Estudante com glossário e estados da máquina C.H.
- `/health` — Sonda de integridade somente leitura (`status: ok`).

---

## 4. Execução dos Testes Automatizados

Para rodar toda a suíte de testes do Control Center em modo 100% offline:

```bash
export PYTHONPATH="$PWD/src:$PWD/apps/control-center/src:$PWD/apps/bootstrap/sentinela/src"
.venv/bin/python -m pytest apps/control-center/tests -v
```

Para rodar a suíte completa de todo o repositório (Sentinela + Control Center):

```bash
export PYTHONPATH="$PWD/src:$PWD/apps/control-center/src:$PWD/apps/bootstrap/sentinela/src"
.venv/bin/python -m pytest apps/control-center/tests apps/bootstrap/sentinela/tests tests -v
```

> **Evidências recentes (17/11/2026):** 142 testes do Control Center passaram localmente (1 aviso Starlette), inclusive regressão `crash → cancelar → despacho B`; piloto real com 3/3 testes Python e Codex `APROVAR_LAB` **textual**. [GitHub Actions #44137628819](https://github.com/hallanbrito/CHDevFlow/actions/runs/44137628819) — `success` (`python-checks` e `f7-windows` passaram; 2 jobs de custódia pulados). Isso não atesta custo R$0 nem isolamento de SO.

---

## 5. Estrutura do Pacote `ch_control_center`

```
apps/control-center/
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
├── fixtures/
│   └── demo_project_snapshot.json     # Fixture de demonstração com 11 tarefas
├── profiles/
│   ├── chdevflow.json                 # Perfil do repositório de meta-governança
│   └── hallancraft.json               # Perfil do servidor de jogo (proteção de saves)
├── src/
│   └── ch_control_center/
│       ├── __init__.py
│       ├── __main__.py                # CLI runner manual (D05)
│       ├── app.py                     # Instância FastAPI e middlewares de segurança (CSP defensiva inicial/local)
│       ├── config.py                  # Parâmetros de rede (127.0.0.1 estrito) e caminhos
│       ├── dependencies.py            # Injeção de dependências
│       ├── security.py                # Validação de Host, Origin/Referer, Token CSRF obrigatório e redirect seguro (AUD-02.1)
│       ├── adapters/
│       │   └── sentinela_adapter.py   # SentinelFacade (ADR-CC02-01)
│       ├── graph/
│       │   └── dag_engine.py          # Algoritmo de Kahn, detecção de ciclos e órfãs
│       ├── routes/
│       │   ├── dashboard.py           # GET /
│       │   ├── missions.py            # GET /missoes e GET /api/missoes/{id}
│       │   ├── graph.py               # GET /grafo e GET /api/grafo
│       │   ├── student.py             # GET /estudante e GET /api/estudante/glossario
│       │   ├── demo.py                # POST /demo/alternar e GET /api/demo/status
│       │   └── projects.py            # POST /projetos/alternar e GET /api/projetos
│       ├── services/
│       │   ├── execution_service.py    # Despacho, lock e dossiê (PR #123)
│       │   ├── mission_preparation_service.py # Preparação guiada e preflight F6 (Issue #124)
│       │   ├── mission_service.py     # Orquestrador de missões e estados
│       │   └── project_service.py     # Gerenciador de perfis multi-projeto
│       ├── static/
│       │   ├── css/styles.css         # Tema escuro/claro, badges e layout responsivo
│       │   └── js/app.js              # Alternância de tema e controle de modais
│       ├── student/
│       │   └── glossary.py            # Conceitos do Método C.H. e estados da máquina
│       └── templates/
│           ├── base.html              # Layout mestre com sidebar e banners
│           ├── dashboard.html         # Página inicial
│           ├── missions.html          # Central de missões, preparação guiada e preflight
│           ├── graph.html             # Grafo visual topológico
│           └── student.html           # Modo estudante
└── tests/
    ├── conftest.py                    # Cliente ASGI in-memory
    ├── test_dag_engine.py             # Testes topológicos e de ciclos
    ├── test_mission_execution_bridge.py # Testes de despacho e ciclo F6 (PR #123)
    ├── test_mission_preparation_bridge.py # Testes de preparação guiada e preflight (Issue #124)
    ├── test_mission_service.py        # Testes de orquestração de missões
    ├── test_project_service.py        # Testes de isolamento multi-projeto
    ├── test_routes_read_only.py       # Testes de integridade HTTP e segurança
    ├── test_sentinela_adapter.py      # Testes da fachada da Sentinela
    └── test_server_security.py        # Testes de restrição a 127.0.0.1
```
