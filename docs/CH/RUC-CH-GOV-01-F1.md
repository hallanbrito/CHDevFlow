# RUC/1.0 — CH-GOV-01 / F1

- Missão: https://github.com/hallanbrito/CHDevFlow/issues/63
- Autorização PO: "autorizado CH-GOV-01 — Gate Universal de Entrada conforme sua recomendação" (06/11/2026).
- Execução: F1 validador determinístico, testes e workflow de diagnóstico read-only.
- Fonte causal: timeline GitHub Issue #62, formulário atual, \`mission.py\` e \`ch_project_assist.py\`.
- Segurança: nenhum campo Project #2 editado; sem labels automáticas, API GraphQL de escrita, credenciais, execução de agentes, merge ou deploy.
- Proveniência: branch \`chatgpt/ch-gov-01-intake-f1\` baseada em \`main\` SHA \`f8eea14e03c687c4b2ba2a0f628c7c6948d7a6dd\`, sem empilhamento.
- Evidências de testes: conferir CI no HEAD da Draft PR; não declarar PASS até observar resultados.
- Aceite funcional: pendente de auditoria independente e PO.
- Próximo gate: PO decide F2 — alteração Auto-add, desenho de registro idempotente e escopo de escritas seguras. F1 não equivale a F2.
