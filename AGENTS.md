# Regras de trabalho dos agentes — CHDevFlow

Este arquivo na raiz é o ponto de entrada para ChatGPT CH-1, AGY, Codex e outros executores. **Não é autorização de execução.**

## Leia primeiro, antes de planejar ou editar

1. `docs/PROJETO.md` — o produto que queremos entregar.
2. `docs/STATUS.md` — o que está realmente integrado na `main`.
3. `docs/CH/DECISOES.md` — decisões do PO.
4. `docs/CH/CHDEVFLOW-CONTEXTO.md` e `docs/CH/CHDEVFLOW-EVIDENCIAS.md` — antirretrabalho e provas.
5. `.agents/skills/chdevflow/SKILL.md` — o papel do arquiteto especialista.
6. `docs/RFC-CH-DEVFLOW.md`, a Issue/PR atual, código real e testes específicos.

Não declarar leitura de arquivo/HEAD sem conferir. O README/RFC pode estar historicamente desatualizado: comparar com o código e o SHA atuais.

## Regras inegociáveis

- **PO Hallan** decide; **CH-1** supervisiona/delega; **AGY** implementa; **Codex** audita. Não autoaprovar a própria implementação.
- Reutilizar primeiro: `local_executor.py`, `experimental_pilot.py`, `controlled_cycle.py` e `generic_cycle.py` já contêm o ciclo AGY → testes Python → Codex. **Não construir outro motor** sem demonstrar lacuna com código e testes.
- Prioridade MVP: [Issue #121 — CC-DESPACHO-01](https://github.com/hallanbrito/CHDevFlow/issues/121): ligar a UI `/missoes` ao executor existente e provar uma missão REAL com dossiê e decisão humana. F7 em Draft não é pré-requisito desse laboratório local.
- Uma missão ativa, custo incremental R$0 verificável, timeout total até 15 minutos no piloto, branch/worktree descartável, allowlist e logs sanitizados. **Worktree não é sandbox de SO.**
- Em reprovação técnica, máximo 3 AGY/2 devoluções. Autenticação/quota/infraestrutura sem prova bloqueia sem retry. Não usar `--dangerously-skip-permissions` como solução padrão.
- Nunca fazer merge/deploy/editar Project #2/largar agentes em cron/acessar segredos/ativar F7 POST por iniciativa própria. Pedir autorização específica do PO.
- `FakeWorker`/`DRY_RUN` e CI de mocks **não** provam chamada de agentes reais. Comprovar run, SHA, comandos, logs, dossiê e Codex.
- Em `apps/bootstrap/sentinela/`, obedecer também ao [AGENTS.md próprio](apps/bootstrap/sentinela/AGENTS.md), mais restritivo.

**Ao receber uma tarefa:** diagnostique o que já existe, mostre a menor lacuna, delegue implementação ao executor correto, valide evidências, só então sugira evolução. Evite overengineering.
