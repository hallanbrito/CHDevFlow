# CH-GOV-01 — Gate Universal de Entrada — F1 consultiva

**Issue:** https://github.com/hallanbrito/CHDevFlow/issues/63
**Escopo F1:** código e testes offline; evento GitHub Actions de **somente leitura**. **Não** há filtro Auto-add alterado, nem cadastro automático Project #2.

## O que foi comprovado
1. O timeline GitHub da Issue #62 mostrou `ch:workflow` aplicado, seguida da inclusão no Project por `github-project-automation[bot]`; não foi um GitHub Actions do repositório. O `Status` nativo não equivale aos campos CH.
2. Issue forms (`.github/ISSUE_TEMPLATE/fatia-w.yml`) capturam informações, mas `gh issue create` e a integração direta não são obrigados a usar o formulário.
3. `ch mission new --remote` publica `ch:workflow` sem reconciliar campos Project. Seu default `CH-2` **é proposto, não autorizado**; a correção dessa CLI é F3 futura.
4. `scripts/ch_project_assist.py` oferece mecanismo de aplicação assistida, auditável, mas não tem permissão genérica para `Autonomia CH`. Não ampliar allowlist nem contornar gates nesta F1.

## F1 — contrato do validador

`python scripts/ch_intake_check.py --event-json /caminho/event.json --enforce --json`

- Entrada: arquivo JSON de evento GitHub contendo `issue`, **sem rede**.
- `CONTENT_VALID`: somente metadados explícitos completos e consistentes (objetivo, Executor/Esteira, Autonomia **proposta**, escopo/aceite, baseline Git e plano de evidências). **Não** autoriza executar nem comprova cadastro Project.
- `BLOCKED`: campos incompletos, etiquetas conflitantes, proposta inconsistente ou etiqueta prematura `ch:admitted`.
- `OUT_OF_SCOPE`: Issue não etiquetada `ch:workflow` (triagem); não implica autorização.
- `ERROR`: JSON/evento inválido.
- Campos invariantes em qualquer saída: `project_fields_verified=false`, `po_authorized=false`, `execution_allowed=false`, `mutation_performed=false`.
- `--enforce`: retorna 2 para `BLOCKED`, 3 para `ERROR`, 0 para `CONTENT_VALID` ou `OUT_OF_SCOPE`. Não ecoa body nem tokens.
- Labels do executor: exatamente uma dentre `ch:po/ch:chatgpt/ch:codex/ch:agy`, alinhada com texto do formulário. `ch:workflow` é a etiqueta de escopo legada; **não é o novo gate**.

### Teste de regressão sem GitHub
`python -m unittest discover -s tests -p 'test_ch_intake_check.py' -v`

Fixture sintética fiel ao tipo de entrada incompleta da #62 em `tests/fixtures/ch_intake/issue62_incomplete.json`, sem credenciais. O conteúdo da Issue não é executado.

## Restrições e próximos gates (F2, não autorizado nesta fase)

**Importante:** a F1 **detecta** problemas, mas **não impede o Auto-add existente**. Logo a prevenção efetiva da entrada incompleta depende de decisão de migração F2.

1. PO confere a configuração real de **Project #2 → Workflows → Auto-add**; antes de alterar, exportar filtro atual, registrar rollback.
2. **Preferir eliminar o Auto-add geral e usar um registrador controlado e idempotente** que só adicione a Issue após validação e autorização específica de cadastro. Filtrar o Auto-add por `label:ch:admitted` é alternativa de roteamento, **não uma barreira de segurança**, pois uma etiqueta pode ser aplicada manualmente por alguém com permissão. Mesmo quando presente, `ch:admitted` não comprova cadastro nem autorização e nunca libera a Sentinela.
3. O item deve permanecer fora do Project enquanto estiver em triagem. Na admissão, `add item → preencher campos → read-back` não é uma transação atômica em Projects. Até prova de preenchimento, o estado é `PENDING_REGISTRATION`, **não elegível para execução**.
4. Em caso de falha, não produzir falsa conformidade nem apagar registros/decisões anteriores; notificar, abortar e permitir reparo idempotente com autorização humana.
5. Uma POC n8n pode futuramente executar notificações e diagnósticos somente leitura; não substitui a validação, não recebe credenciais de escrita nesta fase.

## Proteção desta Issue
A Issue #63 CH-GOV-01 foi criada sem `ch:workflow` de propósito, para não reproduzir a dívida antes de existir um gate real. Não adicionar a etiqueta para “arrumar o board” antes de F2.
