# Sentinela Python — CHDevFlow Bootstrap Engine

Módulo de observação, validação contratual e supervisão de tarefas do **CHDevFlow**, projetado segundo as diretrizes de governança do **Método C.H.**

A Sentinela atua como o primeiro elo automatizado entre o GitHub (fonte de verdade versionada) e os executores locais, reconhecendo tarefas elegíveis, conferindo contratos e acionando o supervisor local sem nunca iniciar agentes reais desgovernados ou realizar mutações desautorizadas.

> **Estado da missão BOOT-01:** Implementação funcional local com `FakeWorker` simulado e testes offline completos. Nenhum agente externo real (Codex, AGY, Gemini) foi iniciado nesta missão.

---

## 1. Princípios e Regras Irrevogáveis

1. **Disparo Manual e Observação Pontual (Decisão D05):** A Sentinela opera em modo de execução única (`watch --once`). É terminantemente proibido manter loop contínuo, daemon, cron ou polling 24/7 nesta fase.
2. **Custo Adicional Zero (Decisão D06):** Nenhuma chamada a APIs faturáveis, contratação de serviços ou uso de créditos pagos é permitida (R$ 0,00 obrigatório).
3. **Leitura Estrita e Imutabilidade:** O leitor GitHub (`LeitorGitHub`) executa somente operações de leitura. Comandos de mutação remota (`item-edit`, `create`, `merge`, `push`, etc.) são ativamente bloqueados.
4. **Portão Humano Inviolável:** A máquina de estados interrompe qualquer fluxo não autorizado em `AWAITING_AUTH`. Nenhuma label, coluna de Kanban ou texto livre na Issue pode ser interpretado como autorização de execução. O término ocorre em `AWAITING_PO`.
5. **Simulação Inofensiva (FakeWorker):** Todas as demonstrações utilizam o `FakeWorker`, um executor que não altera arquivos de projeto nem chama LLMs.

---

## 2. Arquitetura e Diagrama de Estados

O fluxo supervisionado percorre os seguintes estados rigorosos:

```text
DISCOVERED → PROPOSED → AWAITING_AUTH
                               │ Autorização do PO (apenas simulada em fixtures de teste)
                               ▼
PREFLIGHT_OK → CLAIMED → RUNNING → EVIDENCE_PENDING → AWAITING_PO
   │              │         │                 │
   └──────────────┴─────────┴─────────────────┴──→ BLOCKED
                                  ├──────────────→ CANCELLED
                                  ├──────────────→ TIMED_OUT
                                  └──────────────→ INDETERMINATE
```

- **DISCOVERED:** Tarefa candidata com `ch:workflow` encontrada no GitHub Project ou snapshot.
- **PROPOSED:** Contrato de Missão analisado e validado contra schema, repositório, baseline SHA e limites.
- **AWAITING_AUTH:** Portão de autorização humana. Em operação normal, o processo encerra aqui com segurança.
- **PREFLIGHT_OK:** Verificações de segurança e custo zero confirmadas.
- **CLAIMED:** Reserva exclusiva no `GerenciadorCheckpoint` garantindo concorrência máxima = 1 e idempotência.
- **RUNNING:** `FakeWorker` simula a execução gerando saída sintética em memória.
- **EVIDENCE_PENDING:** Coleta de evidências, validação de integridade e redação de segredos.
- **AWAITING_PO:** Dossiê RUC/1.0 gerado localmente; sistema aguarda decisão formal do PO.

---

## 3. Estrutura do Pacote

```text
apps/bootstrap/sentinela/
├── README.md               # Esta documentação
├── AGENTS.md               # Instruções delimitadas para agentes e IA
├── pyproject.toml          # Metadados e ponto de entrada da CLI
├── .env.example            # Exemplo de configuração de ambiente (sem segredos)
├── src/
│   └── ch_sentinela/
│       ├── __init__.py     # Pacote principal
│       ├── __main__.py     # Execução via `python -m ch_sentinela`
│       ├── cli.py          # Interface de linha de comando
│       ├── config.py       # Constantes e limites operacionais (D01-D07)
│       ├── contracts.py    # Contratos versionados (Mission, Worker, Supervisor)
│       ├── github_reader.py# Leitor gh estritamente seguro e somente leitura
│       ├── sentinel.py     # Observador pontual (watch --once)
│       ├── checkpoint.py   # Exclusão de concorrência e idempotência atômica
│       ├── supervisor.py   # Máquina de estados e orquestrador supervisionado
│       ├── audit.py        # Gravação de eventos append-only em JSONL (0o600)
│       ├── security/
│       │   ├── __init__.py
│       │   └── policies.py # Políticas de contenção, escopo e sanitização
│       └── workers/
│           ├── __init__.py
│           └── fake.py     # Simulador inofensivo com zero side-effects
├── tests/
│   ├── fixtures/           # Snapshots JSON offline
│   ├── test_contracts.py   # Testes dos contratos e digests
│   ├── test_github_reader.py # Testes de leitura e bloqueio de mutações
│   ├── test_sentinel.py    # Testes da observação pontual
│   ├── test_supervisor.py  # Testes do supervisor e máquina de estados
│   ├── test_security.py    # Testes das políticas de segurança e contenção
│   └── test_cli.py         # Testes da interface CLI
├── docs/
│   ├── PROJETO.md          # Visão geral e escopo do projeto
│   ├── STATUS.md           # Marco atual e entregas
│   ├── ARVORE_PROJETO.md   # Inventário detalhado de arquivos
│   ├── GUIA_DE_ESTUDO.md   # Guia progressivo de estudo para o PO com 3 exercícios
│   └── CH/
│       ├── DECISOES.md     # Registro de decisões arquiteturais
│       └── RUC-BOOT01.md   # Relatório Universal C.H. formal (v1.0)
└── prompts/
    └── README.md           # Diretrizes para prompts de missão
```

---

## 4. Como Executar

### 4.1 Ajuda dos comandos
```bash
python3 -m ch_sentinela --help
```

### 4.2 Observação pontual (watch --once --dry-run)
Executa uma única consulta ao GitHub (ou fallback offline caso não haja conexão), lista tarefas elegíveis e encerra imediatamente:
```bash
python3 -m ch_sentinela watch --once --dry-run
```

Para executar informando um arquivo de snapshot offline:
```bash
python3 -m ch_sentinela watch --once --dry-run --fixture tests/fixtures/projeto_snapshot_valido.json
```

### 4.3 Demonstração do ciclo supervisionado (demo --fake-worker)
Reproduz as duas etapas principais:
1. Execução sem autorização externa (pára com segurança em `AWAITING_AUTH`).
2. Ciclo supervisionado com autorização simulada de teste, culminando em `AWAITING_PO` e gerando o relatório local RUC/1.0:
```bash
python3 -m ch_sentinela demo --fake-worker
```

### 4.4 Consulta de status e checkpoints
Exibe o histórico de execuções persistidas e o último evento registrado na auditoria JSONL:
```bash
python3 -m ch_sentinela status
```

### 4.5 Visualização do relatório RUC gerado
Imprime o relatório RUC/1.0 da última execução:
```bash
python3 -m ch_sentinela report
```

---

## 5. Execução dos Testes

A suíte de testes unitários offline não requer pacotes externos nem conexão à internet:
```bash
python3 -m unittest discover apps/bootstrap/sentinela/tests
```

Para rodar em conjunto com os testes do repositório raiz:
```bash
python3 -m unittest discover tests
```
