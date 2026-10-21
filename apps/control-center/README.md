# CHDevFlow Control Center — MVP v0.2 (Fatia CC-01)

> **Primeira Interface Funcional de Supervisão e Governança de IA (Modo Somente Leitura)**
> **Conformidade Canônica:** Decisões D01, D05, D06, D07, RFC-CH-DEVFLOW-001, ADR-CC02-01, ADR-CC02-02, ADR-CC02-03.

---

## 1. Visão Geral

O **CHDevFlow Control Center** é a central de observabilidade, inteligência de missões e governança visual do ecossistema CHDevFlow.

Na presente fatia **CC-01**, o painel opera **estritamente em modo somente leitura (CH-1)**:
- **Zero Despacho Executivo:** Não inicia agentes autônomos nem executa scripts mutativos.
- **Segurança de Rede Local (RNF-01):** Conexão vinculada exclusivamente ao loopback (`127.0.0.1:8000`). Recusa formalmente vinculações externas como `0.0.0.0`.
- **Custo R$ 0,00 (D01):** Sem consumo de APIs comerciais faturáveis de IA.
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
7. **Suíte de Testes Automatizados (100% Offline):** 38 testes dedicados do Control Center cobrindo o motor DAG, serviços, fachada da Sentinela e rotas somente leitura, complementando os 77 testes do repositório raiz e os 67 testes do motor da Sentinela (total de 182 testes com 100% de aprovação).

---

## 3. Como Inicializar e Testar Localmente

### Pré-requisitos
- Python 3.10+ (Homologado em Python 3.14 no CachyOS/Linux).
- Virtualenv local com dependências instaladas (`fastapi`, `uvicorn`, `jinja2`).

### Inicialização Rápida

Na raiz do repositório ou da worktree:

```bash
# 1. Exportar os módulos no PYTHONPATH
export PYTHONPATH="apps/control-center/src:apps/bootstrap/sentinela/src"

# 2. Iniciar o servidor local (loopback 127.0.0.1:8000)
.venv/bin/python -m ch_control_center
```

Ou execute o script utilitário:

```bash
./scripts/iniciar_control_center.sh
```

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
export PYTHONPATH="apps/control-center/src:apps/bootstrap/sentinela/src"
.venv/bin/python -m pytest apps/control-center/tests -v
```

Para rodar a suíte completa de todo o repositório (Sentinela + Control Center):

```bash
export PYTHONPATH="apps/control-center/src:apps/bootstrap/sentinela/src"
.venv/bin/python -m pytest apps/control-center/tests apps/bootstrap/sentinela/tests tests -v
```

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
│       ├── app.py                     # Instância FastAPI e middlewares de segurança
│       ├── config.py                  # Parâmetros de rede (127.0.0.1) e caminhos
│       ├── dependencies.py            # Injeção de dependências
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
│           ├── missions.html          # Central de fatias W
│           ├── graph.html             # Grafo visual topológico
│           └── student.html           # Modo estudante
└── tests/
    ├── conftest.py                    # Cliente ASGI in-memory
    ├── test_dag_engine.py             # Testes topológicos e de ciclos
    ├── test_mission_service.py        # Testes de orquestração de missões
    ├── test_project_service.py        # Testes de isolamento multi-projeto
    ├── test_routes_read_only.py       # Testes de integridade HTTP e segurança
    ├── test_sentinela_adapter.py      # Testes da fachada da Sentinela
    └── test_server_security.py        # Testes de restrição a 127.0.0.1
```
