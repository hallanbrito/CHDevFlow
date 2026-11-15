# F7 — Ponte de escalonamento CCC-01 → Project #2

Status: Draft / prévia somente leitura. Relacionada à Issue #86; empilhada sobre F6 (#87).

## Fluxo atual implementado

1. CCC-01/F5 ou F6 persiste um arquivo escalonamento_po.json local após 3 rejeições e 2 devoluções.
2. O módulo po_escalation.py exige status AGUARDANDO_PO, limites corretos, execution_id e URL/Issue válidos.
3. Consulta ao vivo o Project #2 exclusivamente por gh project item-list (somente leitura).
4. Valida totalCount, número real de itens, Issue URL e duplicações.
5. Se o cartão já existe, reporta JA_EXISTE_NO_PROJECT e NÃO modifica Status, Esteira nem Etapa CH.
6. Se não existe, reporta EXIGE_ADMISSAO_PO e orienta o fluxo EXISTENTE de aprovação KSYNC-03 (scripts/ch_project_assist.py admit), com autorização autenticada do PO, plano pinado e readback.
7. Nunca transforma veredito AGY/Codex, rótulo ou outbox em permissão automática para alterar o Project #2.

Exemplo de consulta em terminal com sessão gh autenticada:

    python -m chdevflow.core.po_escalation --outbox C:\CHDevFlow-Labs\CH-Dossie-001\escalonamento_po.json --json

O comando acima é exclusivamente leitura, não cria cartão nem publica comentário. Para publicação remota real, a integração com KSYNC-03 exigirá uma segunda fatia após validação da aprovação e idempotência. Isso não deve ser apresentado como concluído.

Testes offline:

    python -m unittest discover -s tests -p "test_ch_pipe_01_f7_po_escalation.py" -v

Sem merge, deploy, cron, escrita em Project #2 ou liberação de execução de produção.
