# STATUS — CHDevFlow

**Atualizado em:** 17/11/2026 (America/Fortaleza).  
**Último marco homologado pelo PO:** CC-DESPACHO-01 — ponte Control Center → F6, **somente funcional em laboratório** ([PR #123](https://github.com/hallanbrito/CHDevFlow/pull/123)).

## Estado integrado e marcos
- **Implementação homologada:** commit `9c509182dd74d003abc3a2cb7592a7b6db740d15`, branch `agy/cc-despacho-01`. PR **Draft**, **não integrada à main**.
- **CI:** [run 44137628819](https://github.com/hallanbrito/CHDevFlow/actions/runs/44137628819), `success`, `python-checks` e `f7-windows` passaram; dois jobs de custódia pulados.
- **Regressão local:** 142 testes do Control Center passaram (1 aviso); correção P1 mantém lock e devolve HTTP 409 em `crash → cancelar → despacho B`.
- **Primeiro piloto real pela interface:** missão `PILOTO-CC-123`, AGY 1 tentativa, 0 devoluções, testes Python **3/3**, Codex textual `APROVAR_LAB`, dossiê `APROVADO_AGUARDANDO_CH1`. SHA256 confirmado no arquivo pelo PO; apenas `calculadora.py` alterado.
- **Homologação PO:** concedida expressamente em 17/11/2026 para **escopo funcional de laboratório**; não substitui autorização específica para merge/deploy.

## Riscos e bloqueios
- `cost_verified=false`, `os_isolation_verified=false`, `test_execution=host`: custo R$0 e isolamento do sistema operacional **não verificados**.
- Codex auditou textualmente; não reexecutou testes nem validou hash/Git por conta própria.
- Crash preserva `active_execution.lock` (fail-closed); recuperação operacional manual. Cancelamento avançado via UI adiado.
- Nenhum merge na `main`, deploy, automação de produção ou escrita no Project #2 nesta entrega.

## Próxima decisão do PO
Autorizar ou não **merge em decisão separada**, após conferência da CI do HEAD documental e das proteções da branch. Isolamento e verificação de custo ficam fora desta homologação.

**Evidências:** [RUC do piloto](docs/control-center/RUC-CC-DESPACHO-01-PILOTO-20261117.md) · [PR #123](https://github.com/hallanbrito/CHDevFlow/pull/123).
