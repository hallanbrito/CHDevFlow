# CH-GOV-01 / W-F2.1 — Contrato de entrada (revisão inicial)

**Referência:** [Issue #63](https://github.com/hallanbrito/CHDevFlow/issues/63)  
**Pré-condição F2-0:** [evidência anexada pelo PO](https://github.com/hallanbrito/CHDevFlow/issues/63#issuecomment-6707694471) — Auto-add `is:issue label:ch:workflow` OFF.  
**Escopo:** emissores / contrato F1; **não inclui cadastro no Project #2**, mutation GraphQL, execução de agentes ou merge.

## Contrato de etiquetas

- `ch:workflow`: identifica Issue **candidata à triagem pela F1**, não admissão.
- `ch:po`, `ch:chatgpt`, `ch:codex`, `ch:agy`: exatamente uma etiqueta deve acompanhar as Issues criadas pela CLI; deve corresponder ao campo `Executor declarado`.
- `ch:admitted`: não usar para autorizar admissão; a F1 atual marca a presença como `ADMISSION_LABEL_UNVERIFIED`.
- A F1 não confere autorização do PO nem campos do Project. `CONTENT_VALID` é somente validação de conteúdo.

## Entrada pela CLI

`mission.py` produz uma Issue com `ch:workflow` + exatamente uma etiqueta de executor, usando a mesma nomenclatura já aceita por `intake.py`. Antes de chamar `gh issue create`, executa `validate_issue` sobre um payload sintético (número fictício somente para validação pura) e exige `CONTENT_VALID`. `--remote` preserva a geração prévia do artefato local.

O Markdown gerado contém explicitamente `Verificações e evidências exigidas` para evitar `EVIDENCE_PLAN_MISSING`. Esse texto apresenta um **plano proposto**, não evidência de testes aprovados.

Um baseline Git sem commit verificável não pode passar no Intake F1.

## Entrada pelo formulário Web

O template `fatia-w.yml` aplica apenas `ch:workflow`. O campo dropdown `Esteira` não aplica automaticamente uma etiqueta dinâmica. O primeiro evento `issues.opened` pode retornar `BLOCKED` por falta de etiqueta do executor. O PO ou triador aplica uma etiqueta de executor coerente, acionando `issues.labeled` para uma nova avaliação.

**Não** configurar `projects:` no template; não reativar Auto-add para compensar a ausência da etiqueta.

## Limites pendentes para auditoria

1. **CH-2 implícito no parser:** `src/chdevflow/cli.py` ainda define `default="CH-2"` e `default="AGY"` e os transmite diretamente a `create_mission`. **Não é tecnicamente possível distinguir os argumentos omitidos dos explicitamente fornecidos modificando apenas `mission.py`.** Esse arquivo está fora da allowlist W-F2.1. Necessário gate de alteração de escopo específico para cumprir integralmente o requisito de autonomia/executor explícitos; até lá a Draft PR NÃO deve ser homologada ou integrada.
2. O contrato F1 permanece intocado (fora do escopo). Seu check retorna 0 inclusive para `OUT_OF_SCOPE`; qualquer futura admissão F2.2 deverá conferir `content_status == CONTENT_VALID`, não apenas o código de saída.
3. O Auto-add foi desligado manualmente pelo PO; sua configuração continua recuperável e **não deve ser reativada** enquanto a entrada for insegura.
4. W-F2.2, `addProjectV2ItemById`, os três campos do Project e read-back são uma fatia separada, com gate posterior, após integração de W-F2.1.

## Validação prevista

- Testes offline `tests/test_cli_05.py` com `gh` simulado.
- Regressão do Intake F1 e demais checks configurados em CI.
- Revisão independente e homologação do PO com HEAD/CI verificados.
- **Sem escrita de Project, abertura de Issues de teste reais, merge ou execução de agentes.**

**Estado do contrato:** `DRAFT / AWAITING_CLI_PARSER_SCOPE_GATE`.
