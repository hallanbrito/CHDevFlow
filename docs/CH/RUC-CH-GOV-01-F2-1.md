# RUC/1.0 — CH-GOV-01 / W-F2.1 (Draft)

- **Issue-mãe:** https://github.com/hallanbrito/CHDevFlow/issues/63
- **PO R2:** homologação conceitual e autorização CH-2 condicional, conforme comentário https://github.com/hallanbrito/CHDevFlow/issues/63#issuecomment-6707639771
- **F2-0:** evidência do PO https://github.com/hallanbrito/CHDevFlow/issues/63#issuecomment-6707694471 — filtro `is:issue label:ch:workflow` desativado.
- **Branch isolada:** `chatgpt/f2-1-mission-contract`, derivada de `main`; **não realizar merge sem novo gate**.
- **Fatia W:** emissores e contrato; alterações restritas a `src/chdevflow/core/mission.py`, `.github/ISSUE_TEMPLATE/fatia-w.yml`, `tests/test_cli_05.py` e documentação de contrato/RUC.
- **Mudanças:** etiquetas de executor alinhadas ao F1; preflight `validate_issue` antes de criar Issue; campo explícito de evidências; formulário marcado para triagem.
- **Invariantes:** somente diagnóstico, nenhuma escrita no Project, `CONTENT_VALID` não significa autorização do PO, etiqueta não admite item, zero agentes reais.
- **Pendência bloqueante:** `src/chdevflow/cli.py` (fora da allowlist) define defaults `--autonomy=CH-2` e `--executor=AGY`. A exigência de parâmetros explícitos no modo remoto não pode ser satisfeita integralmente sem autorização para alterar o parser. **Não homologar/integrar a W-F2.1 enquanto não resolvida.**
- **Testes:** unidade local/CI e validação de HEAD **a verificar**. Não afirmar PASS sem logs verificáveis.
- **Operação GraphQL:** nenhuma.
- **Custo incremental:** R$0 (nenhum serviço pago contratado).
- **Decisão final do PO:** PENDENTE.
- **Próximo gate:** autorização mínima para `src/chdevflow/cli.py` e avaliação da Draft PR; F2.2 segue bloqueada.

**Estado:** `W-F2.1_DRAFT / SCOPE_BLOCKER_CLI_DEFAULT / AWAITING_PO`.
