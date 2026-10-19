# Estado do Módulo — Sentinela Python (BOOT-01)

**Última atualização:** 19/10/2026
**Missão:** AGY-BOOT01-LAB
**Estado atual:** `AWAITING_PO` (Aguardando Decisão do Product Owner)

---

## 1. Funcionalidades Concluídas (Prontas e Testadas)

- [x] **LeitorGitHub (`github_reader.py`):**
  - Consultas seguras somente leitura via `subprocess` sem `shell=True`.
  - Suporte completo a fixtures offline e mocks de dados.
  - Bloqueio rigoroso de subcomandos mutáveis (`item-edit`, `create`, `merge`, `push`, etc.).
  - Sanitização automática de tokens em stderr e saídas de erro.
- [x] **Contratos Versionados (`contracts.py`):**
  - Implementação de `ContratoMissao`, `ContratoAutorizacao`, `ContratoWorkerResultado` e `ContratoSupervisorResultado`.
  - Serialização canônica determinística e cálculo de `mission_digest` via SHA-256.
  - Validação de repositório, baseline SHA (40 chars hex), escopos e limites.
  - Rejeição expressa de autoaprovação por agentes ou bots.
- [x] **Sentinela (`sentinel.py`):**
  - Observação de execução única (`watch --once --dry-run`).
  - Reconhecimento de tarefas elegíveis com `ch:workflow`.
  - Detecção e descarte de duplicatas e itens corrompidos.
  - Término imediato sem loops em segundo plano (respeito a D05).
- [x] **Gerenciador de Checkpoint (`checkpoint.py`):**
  - Controle atômico de concorrência garantindo no máximo 1 execução ativa (D06).
  - Idempotência estrita: bloqueio de replay acidental da mesma missão e tentativa.
  - Gravação com permissão restrita 0o600.
- [x] **Supervisor (`supervisor.py`):**
  - Máquina de estados: `DISCOVERED → PROPOSED → AWAITING_AUTH → PREFLIGHT_OK → CLAIMED → RUNNING → EVIDENCE_PENDING → AWAITING_PO`.
  - Estados de falha segura: `BLOCKED`, `CANCELLED`, `TIMED_OUT`, `INDETERMINATE`.
  - Interrupção segura em `AWAITING_AUTH` quando não há autorização do PO.
  - Geração local de Relatório Universal C.H. (RUC/1.0) em Markdown.
- [x] **Auditoria Local (`audit.py`):**
  - Gravação estritamente incremental (*append-only*) em arquivo JSONL.
  - Sanitização de segredos antes da persistência.
  - Permissões seguras 0o600 no disco.
- [x] **Políticas de Segurança (`security/policies.py`):**
  - Bloqueio de *path traversal* (`..`), caminhos absolutos e curingas amplos (`*`).
  - Proteção de mundos, saves, segredos, credenciais e `.env`.
  - Garantia de custo adicional R$ 0,00 obrigatório.
- [x] **FakeWorker (`workers/fake.py`):**
  - Simulador inofensivo com zero side-effects.
  - Cobertura de cenários de sucesso, erro, timeout e cancelamento.
- [x] **Interface CLI (`cli.py` e `__main__.py`):**
  - Comandos: `watch --once --dry-run`, `demo --fake-worker`, `status` e `report`.
  - **Correção AUD-01 (Fail-Closed Estrito):** Remoção de qualquer substituição silenciosa de fixtures em caso de falha de consulta ao vivo ou arquivo inexistente. Erros reais ou de fixtures ausentes retornam código 1 e mensagem explícita (`LIVE_GITHUB FAILED` / `ERRO CRÍTICO`).
- [x] **Testes Automatizados:**
  - 50 testes unitários cobrindo todos os fluxos positivos, negativos e regressões AUD-01 offline.

---

## 2. Funcionalidades Incompletas ou Deliberadamente Postergadas

As seguintes funcionalidades **NÃO** foram implementadas nesta missão por estarem expressamente fora de escopo ou sujeitas a autorizações e decisões futuras:

1. **Sentinela em Loop Contínuo (`--loop`):** Permanece desativada em cumprimento à Decisão D05 vigente (disparo manual). Sua eventual adoção depende de decisão formal do PO (D05-v2).
2. **Adaptadores de Agentes Reais (`AgyWorker`, `CodexWorker`):** Proibidos nesta missão. Apenas o `FakeWorker` foi construído e autorizado.
3. **Mutações Remotas no GitHub:** Não há publicação automática de PRs, criação de comentários remotos ou modificações de campos no Project #2.
4. **Painel Web (Control Center):** Nenhuma interface gráfica foi implementada para não duplicar o trabalho em andamento no branch `hallan/cc00-fundacao-control-center`.

---

## 3. Próximo Passo

Submeter o relatório formal **RUC-BOOT01.md** e as evidências ao Product Owner para revisão humana e homologação técnica da Fatia BOOT-01.
