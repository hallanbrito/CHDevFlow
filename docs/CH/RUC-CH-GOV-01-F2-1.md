# RUC/1.0 — CH-GOV-01 / W-F2.1 (Draft)

- **Issue-mãe:** https://github.com/hallanbrito/CHDevFlow/issues/63
- **PO R2:** homologação conceitual e autorização CH-2 condicional, conforme comentário https://github.com/hallanbrito/CHDevFlow/issues/63#issuecomment-6707639771
- **F2-0:** evidência do PO https://github.com/hallanbrito/CHDevFlow/issues/63#issuecomment-6707694471 — filtro `is:issue label:ch:workflow` desativado.
- **Branch isolada:** `chatgpt/f2-1-mission-contract`, derivada de `main`; **não realizar merge sem novo gate**.
- **Fatia W:** emissores e contrato; alterações restritas a `src/chdevflow/core/mission.py`, `.github/ISSUE_TEMPLATE/fatia-w.yml`, `tests/test_cli_05.py`, `src/chdevflow/cli.py` (aditamento expresso do PO em 07/11/2026) e documentação de contrato/RUC.
- **Mudanças:** etiquetas de executor alinhadas ao F1; preflight `validate_issue` antes de criar Issue; campo explícito de evidências; formulário marcado para triagem.
- **Invariantes:** somente diagnóstico, nenhuma escrita no Project, `CONTENT_VALID` não significa autorização do PO, etiqueta não admite item, zero agentes reais.
- **Aditamento do PO:** autorizou exclusivamente `src/chdevflow/cli.py`; parser agora define `default=None` para `--executor` e `--autonomy`. Com `--remote`, um argumento omitido gera `stderr` explícito e exit code 1 sem invocar a criação; sem `--remote`, fallback local `AGY` / `CH-2` permanece. **Bloqueio de escopo anterior resolvido; auditoria final ainda pendente.**
- **Testes:** 3 testes novos do parser remoto (ausência de ambos/um argumento, sucesso explícito e defaults locais), mais regressões anteriores. **CI do novo HEAD a verificar.** Não declarar PASS sem logs.
- **Operação GraphQL:** nenhuma.
- **Custo incremental:** R$0 (nenhum serviço pago contratado).
- **Decisão final do PO:** PENDENTE.
- **Próximo gate:** CI integral no HEAD exato; então converter a PR #65 para Ready for review conforme autorização explícita do PO, sem merge. F2.2 segue bloqueada até integração autorizada da W-F2.1.

**Estado:** `W-F2.1_ADITAMENTO_IMPLEMENTADO / CI_PENDING / AWAITING_PO_FINAL_REVIEW`.
