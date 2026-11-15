# F7 — Ponte de escalonamento CCC-01 → Project #2

Status: Draft / prévia somente leitura. Relacionada à Issue #86; empilhada sobre F6 (#87).

## Gate F6 homologado e integração real F7

A F6 foi homologada em 15/11/2026 no host Windows do PO com duas missões
automáticas (`AGY -> Docker 15/15 -> Codex APROVAR_LAB -> CH-1`).
O merge de sincronização da F7 incorpora o executor F6, incluindo
`--isolated-tests` e `docker_acceptance.py`, sem voltar a executar
código gerado diretamente no host quando Docker é solicitado.

A F7 estende SOMENTE o caso de terceira reprovação (3 tentativas AGY,
2 devoluções). Emite `escalonamento_po.json` por escrita atômica com
`schema=CHDEVFLOW-F7-OUTBOX/1`, `code_sha256`, ID, issue, status
`AGUARDANDO_PO`, `publication_status=PENDENTE_DE_AUTORIZACAO` e
`evidence_files` estritamente relativos à pasta do dossiê:
`attempt-03/codigo.py`, `attempt-03/alteracoes.patch`,
`attempt-03/testes.log`, `attempt-03/auditoria_codex.md`,
`RELATORIO_COMPLETO_CH1.md`.
Nenhum caminho absoluto do usuário/host, token, prompt secreto ou log bruto
entra no plano de publicação. A ponte valida a presença das evidências e
o SHA do código antes de solicitar um snapshot remoto. Outboxes legadas
permanecem aceitas somente para consulta, sem permissão de escrita.

A F7 nunca chama AGY ou Codex no retry de uma falha GitHub. Erro ao consultar
Project #2 não modifica a outbox original. Com `--receipt <arquivo-novo>`,
o CLI grava um recibo LOCAL exclusivo com `PENDENTE_PUBLICACAO`,
`remote_writes=0` e indicação da necessidade de autorização live do PO.
Esse recibo não publica comentário ou cartão e não é uma autorização.

### Teste manual somente leitura (não reinicia agentes)

```powershell
$env:PYTHONPATH = "src"
python -m chdevflow.core.po_escalation --outbox "$HOME\CHDevFlow-Labs\CH-Dossie-Frete-29d75943ef\escalonamento_po.json" --json --receipt "$HOME\CHDevFlow-Labs\F7-pendente-publicacao.json"
```

No exemplo acima, a outbox é legada da F6 e deve ser preservada.
Se a consulta falhar, o recibo será emitido somente se o caminho não
existir. A consulta `gh project item-list` é read-only; para executar
em host real, revisar autenticação e ACL de leitura antes.

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

## Próxima frente: Control Center visual (depois dos gates Python)

Após F7 e homologação dos gates: expandir o Control Center já existente
(FastAPI + React), em vez de iniciar uma segunda aplicação desconectada.
Planejar dashboard com timeline AGY → Docker → Codex → CH-1, status legível,
contadores e cotas, dossiê clicável, fila de aprovações PO e alertas de
bloqueio. Priorizar interface responsiva, visual marcante, acessibilidade,
segurança e padrão **somente leitura por default**. Ações remotas devem
exigir confirmação explícita, plano pinado e readback, nunca inferir aprovação.
A UI não integra o escopo funcional da F7 nem autoriza merge/deploy.
