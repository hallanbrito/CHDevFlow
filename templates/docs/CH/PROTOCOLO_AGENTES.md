# Protocolo de execução — C.H. DevFlow (experimental)

## Antes de agir
1. Consultar `docs/PROJETO.md`, `docs/STATUS.md`, `AGENTS.md` e Issue/W corrente.
2. Fixar base SHA e registrar modelo/executor, ambiente, autonomia e critérios de aceite.
3. Verificar dependências, exclusão de acesso simultâneo a arquivos, produção e segredos.

## Durante
- Executar somente no escopo concedido (CH-2 no piloto).
- Usar branch curta e, quando concorrer, worktree separada.
- Pausar e pedir decisão para qualquer desvio de escopo ou necessidade de elevação de autonomia.

## Ao entregar
- Commit e Draft PR, sem merge.
- Relatório: Issue, prompt versionado/sanitizado, branch, SHA, diff, testes, risco, pendências, rollback e custo conhecido.
- Etiquetar entrega `AGUARDANDO_PO` apenas após evidências e revisão, se aplicável.

## Aprovação
- Somente decisão autenticada do Owner Humano libera integração.
- Aprovação parcial exige fronteira de código verificável e W residual.
- Reprovação deve manter a trilha histórica sem alterar `main`.
