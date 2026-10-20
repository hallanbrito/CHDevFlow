# Árvore do Projeto — Módulo Sentinela Python

Inventário completo e descrição de cada arquivo que compõe a implementação da Sentinela Python dentro de `apps/bootstrap/sentinela/`.

```text
apps/bootstrap/sentinela/
├── README.md                           # Documentação principal, arquitetura e instruções de uso
├── AGENTS.md                           # Protocolo de governança e restrições para agentes de IA
├── pyproject.toml                      # Configuração de build e ponto de entrada CLI
├── .env.example                        # Exemplo de variáveis de ambiente sem dados sensíveis
├── src/
│   └── ch_sentinela/
│       ├── __init__.py                 # Inicialização do pacote Python
│       ├── __main__.py                 # Ponto de entrada para python -m ch_sentinela
│       ├── cli.py                      # Interface de linha de comando (watch, demo, status, report)
│       ├── config.py                   # Constantes, limites de governança (D01-D07) e caminhos
│       ├── contracts.py                # Contratos versionados e cálculo de digest canônico SHA-256
│       ├── github_reader.py            # Leitor seguro somente leitura via GitHub CLI (gh)
│       ├── sentinel.py                 # Observador pontual (watch --once) e emissor de eventos
│       ├── checkpoint.py               # Persistência de estado local, exclusão mútua e idempotência
│       ├── supervisor.py               # Máquina de estados completa e gerador de dossiê RUC
│       ├── audit.py                    # Trilha imutável em JSONL append-only com permissão 0o600
│       ├── security/
│       │   ├── __init__.py             # Exportações do subpacote de segurança
│       │   └── policies.py             # Validações fail-closed: caminhos, custo zero, SHA e segredos
│       └── workers/
│           ├── __init__.py             # Exportações do subpacote de workers
│           └── fake.py                 # Simulador inofensivo FakeWorker com zero efeitos colaterais
├── tests/
│   ├── fixtures/
│   │   ├── missao_valida.json          # Fixture de missão elegível válida
│   │   ├── missao_adulterada.json      # Fixture de missão com digest divergente
│   │   ├── autorizacao_valida.json     # Fixture de autorização simulada de teste
│   │   ├── projeto_snapshot_valido.json # Snapshot de itens do GitHub Project
│   │   ├── projeto_snapshot_duplicado.json # Snapshot contendo itens duplicados para teste
│   │   ├── projeto_snapshot_incompleto.json # Snapshot corrompido (totalCount divergente)
│   │   └── issue_valida.json           # Fixture de dados individuais de Issue
│   ├── test_contracts.py               # Testes de schema, imutabilidade e integridade dos contratos
│   ├── test_github_reader.py           # Testes de leitura segura, mocks e bloqueio de mutações
│   ├── test_sentinel.py                # Testes de observação pontual, duplicatas e filtros
│   ├── test_supervisor.py              # Testes da máquina de estados, timeout, cancelamento e idempotência
│   ├── test_security.py                # Testes de contenção de diretório, custo zero e sanitização
│   └── test_cli.py                     # Testes de integração dos comandos CLI
├── docs/
│   ├── PROJETO.md                      # Visão do projeto, arquitetura e requisitos
│   ├── STATUS.md                       # Status detalhado das funcionalidades prontas e pendentes
│   ├── ARVORE_PROJETO.md               # Este inventário estrutural detalhado
│   ├── GUIA_DE_ESTUDO.md               # Guia didático progressivo para o PO com 3 exercícios
│   └── CH/
│       ├── DECISOES.md                 # Registro formal de decisões arquiteturais e governança
│       └── RUC-BOOT01.md               # Relatório Universal C.H. oficial (v1.0) em 9 seções
└── prompts/
    └── README.md                       # Diretrizes de imutabilidade e vinculação de prompts
```
