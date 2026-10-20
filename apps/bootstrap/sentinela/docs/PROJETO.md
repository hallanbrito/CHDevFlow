# Projeto — Sentinela Python (CHDevFlow Bootstrap Engine)

## 1. Visão Geral e Finalidade

O projeto **Sentinela Python** é o componente de observação e supervisão autônoma inicial do **CHDevFlow Bootstrap Engine**.

Sua missão é eliminar a necessidade de transporte manual de prompts, comandos e logs entre ferramentas e agentes (ChatGPT, Codex, AGY/Antigravity), fornecendo uma esteira estruturada em que o GitHub atua como fonte de verdade versionada e o Product Owner humano permanece com o poder exclusivo de autorização e integração.

---

## 2. O Problema Resolvido

No modelo experimental anterior, as tarefas sofriam riscos de:
1. Estados divergentes entre o que constava na Issue e o que o agente executava localmente.
2. Incerteza sobre a imutabilidade do escopo autorizado.
3. Risco de autoaprovação indevida por agentes de IA ou agentes executando ações sem consentimento prévio do PO.
4. Falta de registros locais imutáveis e auditáveis com cálculo de integridade criptográfica (digest).

A Sentinela Python introduz:
- Leitura automatizada e segura do GitHub CLI.
- Validação estrita de contratos de missão imutáveis.
- Controle atômico de concorrência e idempotência via checkpoints locais.
- Auditoria append-only em JSONL com permissões restritas.
- Portão de autorização intransponível sem decisão explícita do PO humano.

---

## 3. Módulos e Responsabilidades

| Módulo | Responsabilidade Principal |
|---|---|
| `contracts.py` | Modela e valida os contratos versionados (Mission, Worker, Supervisor) e gera o `mission_digest` via SHA-256 canônico. |
| `github_reader.py` | Executa consultas estritamente de leitura via `gh` com sanitização de credenciais e proteção contra subcomandos de escrita. |
| `sentinel.py` | Observa fotografias do GitHub Project (`watch --once`), detecta duplicatas e emite eventos estruturados sem disparar workers. |
| `checkpoint.py` | Garante concorrência máxima de 1 execução ativa (D06) e idempotência para evitar replays indesejados. |
| `supervisor.py` | Orquestra a máquina de estados completa e impede avanço além de `AWAITING_AUTH` sem consentimento humano. |
| `audit.py` | Persiste eventos de execução em formato JSONL estritamente incremental (append-only) com permissão 0o600. |
| `security/policies.py` | Implementa regras *fail-closed* contra path traversal, proteção de mundos/saves e garantia de custo adicional R$ 0,00. |
| `workers/fake.py` | Fornece um executor simulado inofensivo para ensaios e validações sem efeitos colaterais. |
| `cli.py` | Interface de linha de comando ergonômica em português com comandos `watch`, `demo`, `status` e `report`. |

---

## 4. Requisitos Não Funcionais

- **Linguagem:** Python 3.12+ (compatível com Python 3.14+).
- **Dependências:** Biblioteca padrão do Python (Zero dependências externas obrigatórias).
- **Ambiente Host:** Linux (CachyOS) com isolamento de worktree.
- **Segurança:** Sanitização de segredos e bloqueio preventivo de qualquer caminho fora de `allowed_paths`.
- **Custo:** R$ 0,00 adicional garantido antes de qualquer disparo.
