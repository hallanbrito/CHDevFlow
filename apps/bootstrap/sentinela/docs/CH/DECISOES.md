# Registro de Decisões Arquiteturais — Sentinela Python (BOOT-01)

Este documento consolida as decisões vigentes de governança e arquitetura técnica aplicadas na implementação da Sentinela Python.

---

## 1. Decisões Vinculantes D01 a D07 (Ratificadas pelo PO)

| ID | Decisão | Aplicação no Módulo da Sentinela |
|---|---|---|
| **D01** | Host Linux CachyOS | O ambiente de execução e testes é projetado para Linux com permissões POSIX restritas (0o600). |
| **D02** | AGY como executor prioritário do futuro piloto real | Na presente missão BOOT-01, opera exclusivamente com `FakeWorker` simulado; nenhum agente real foi acionado. |
| **D03** | CH-2 por missão com autorização individual | Exige contrato estruturado de autorização (`ContratoAutorizacao`) vinculado ao digest da missão; sem autoaprovação. |
| **D04** | Proteção absoluta de HallanCraft e produção | Caminhos `worlds`, `saves`, `.env` e repositórios de produção são ativamente bloqueados em `security/policies.py`. |
| **D05** | Disparo manual; proibido loop/cron/daemon | A Sentinela opera exclusivamente com `watch --once`. Proibido implementar polling contínuo nesta fatia. |
| **D06** | Limites operacionais: R$ 0,00, 1 run ativo, 900s timeout, 1 retry pós-diagnóstico, parada manual | Limites impostos e verificados ativamente em `config.py`, `checkpoint.py` e `supervisor.py`. |
| **D07** | Credenciais protegidas, privilégio mínimo e branch principal protegida | Leitor `LeitorGitHub` somente leitura, sanitização de segredos em logs e nenhum push/merge automático. |

---

## 2. Decisões Arquiteturais Específicas da Missão BOOT-01

### ADR-BOOT01-01: Padrão Didático Estrito em Português Brasileiro (pt-BR)
- **Decisão:** Todo o código, nomes de funções próprias, variáveis, docstrings, classes e comentários devem ser redigidos em português brasileiro claro, preservando termos técnicos externos apenas quando padronizados por contratos (`run_id`, `mission_digest`, `FakeWorker`).
- **Motivo:** O Product Owner humano deve conseguir auditar, estudar e compreender cada linha de código com rapidez e transparência.

### ADR-BOOT01-02: Dependência Exclusiva da Biblioteca Padrão do Python
- **Decisão:** Não utilizar pacotes de terceiros (`requests`, `pydantic`, `fastapi`, etc.) no núcleo do motor. A implementação baseia-se 100% na standard library do Python 3.12+ (`subprocess`, `json`, `hashlib`, `dataclasses`, `argparse`, `unittest`).
- **Motivo:** Garantir portabilidade imediata, zero vulnerabilidades de cadeia de suprimentos e custo de instalação zero no CachyOS.

### ADR-BOOT01-03: Separação entre Autoridade, Visão e Cache
- **Decisão:**
  - **Autoridade:** GitHub Issues e eventos de aprovação do PO humano.
  - **Visão:** GitHub Project #2 (rótulos e colunas não conferem autorização).
  - **Cache e Controle de Concorrência:** Checkpoint local em JSON (`checkpoint_estado.json`) com escrita atômica via `os.replace` e permissão `0o600`.
  - **Trilha de Auditoria:** Arquivo JSONL estritamente incremental (*append-only*).
- **Motivo:** Evitar fontes de verdade concorrentes e garantir que o Kanban nunca seja tratado como credencial de execução.

### ADR-BOOT01-04: Máquina de Estados com Parada Segura em AWAITING_AUTH
- **Decisão:** Sem uma autorização explicitamente identificada como simulação de teste (`is_simulation=True`), o supervisor encerra sua avaliação em `AWAITING_AUTH`.
- **Motivo:** *Fail-closed* absoluto: o sistema nunca presume autorização e nunca avança para execução de tarefas sem consentimento formal prévio.

### ADR-BOOT01-05: Proibição de Fallback Silencioso para Dados Sintéticos (AUD-01)
- **Decisão:** O comando `watch --once --dry-run` não pode, sob nenhuma hipótese, substituir uma falha de consulta ao vivo (`LIVE_GITHUB`) por dados sintéticos ou fixtures embutidas. Falhas de rede, subprocesso ou autenticação devem interromper a execução com código de saída não-zero (código 1) e mensagem explícita de erro (`LIVE_GITHUB FAILED`). Da mesma forma, argumentos `--fixture` apontando para caminhos inexistentes ou malformados devem falhar fechados imediatamente.
- **Motivo:** Auditoria independente AUD-01 (PR #26). Evitar que automações futuras ou operadores humanos confundam o sucesso de uma simulação interna com a leitura bem-sucedida do Project real no GitHub.
