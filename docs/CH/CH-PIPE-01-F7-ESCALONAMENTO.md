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

## Incidente real Intake F1 / Issue #85 (15/11/2026)

Em Windows 11, a consulta somente leitura `ch_project_assist.py admit --issue 85
--dry-run --autonomy CH-0` falhou inicialmente por leitura cp1252 em subprocess
GitHub CLI. Corrigido em `scripts/ch_project_sync.py` com captura de bytes e
decode UTF-8 estrito; regressões incluem caracteres Unicode, resposta inválida
e não divulgação de tokens no stderr.

Após fix de codificação, o Intake F1 respondeu
`OUT_OF_SCOPE NOT_ENROLLED`: **a Issue #85 não está matriculada na esteira**.
Isso não é permissão para adicionar `ch:workflow` automaticamente, alterar
o corpo da Issue ou pular critérios do KSYNC-03. O corpo atual de #85 descreve
um contrato de implementação, não os campos específicos de intake necessários
para admissão. A revisão da F7 passou a consultar LIVE o Intake somente quando
não há cartão no Project #2, e retorna `EXIGE_TRIAGEM_INTAKE` mais
`intake_status` e `intake_reasons` em vez de recomendar admissão inelegível.
Se a Issue for elegível, `EXIGE_ADMISSAO_PO` continua exigindo histórico
CLEAR, autorização individual do PO, plano pinado e readback. A consulta
`gh issue view` é estritamente leitura e não altera rótulos/campos.

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

## Publicacao por comentario F7 — desenvolvimento opt-in, nao liberado

Modulo novo: `src/chdevflow/core/po_escalation_publication.py`.
Nao roda AGY ou Codex; a unica operacao de escrita que contem e **POST de
comentario na Issue de origem**. Nunca altera cartoes, etiquetas, Esteira,
Etapa CH, Autonomia, merge ou deploy. A admissao permanece responsabilidade
separada do `scripts/ch_project_assist.py admit` (KSYNC-03).

**Gate obrigatorio para gerar plano** (sem qualquer escrita):
- Outbox **V1 completa**, com hash do codigo e evidencias locais validas;
  outbox historica/legada da F6 so permite preview.
- Issue LIVE aberta, numero/URL corretos, Intake F1 `CONTENT_VALID`;
  a Issue #85 historica retorna `OUT_OF_SCOPE / NOT_ENROLLED` e portanto
  **NAO permite geracao de plano de publicacao**. Nao forcar rótulos ou
  alterar corpo para burlar isso.
- Sessao `gh api user` pertence ao PO; permissao LIVE no repositorio
  deve indicar `push`, `maintain` ou `admin` explicitamente.
- Comentario de aprovacao LIVE, escrito pelo login do PO, vinculado a
  propria Issue ou a Issue de governanca #63. Precisa conter linha exata
  para a execucao e SHA avaliados (sem inferir autorizacao por labels):

      CH-GOV-01 F7 PUBLICAR PROJECT#2 ISSUE#<issue>
      EXECUTION#<execution_id> SHA256=<code_sha256> ACTION=COMMENT_ONLY

  Essa declaracao e uma unica linha no comentario real do PO, nao duas.
- Snapshot completo e coerente do Project #2. Cartao existente e preservado;
  cartao ausente nao e criado. Autorizacao para comentario nao e autorizacao
  de admissao de cartao.
- Nenhum comentario com o mesmo marcador e corpo divergente, autoria invalida
  ou marcador duplicado; idempotencia por execution_id.

**Operacao local apos homologacao adicional e autorizacao nova do PO**:

    python -m chdevflow.core.po_escalation_publication --outbox <OUTBOX_V1>

Mostra somente preview local e `writes=0` (sem consulta remota). Para
preparar um plano, usar `--approval-comment <ID_REAL_DO_PO> --plan-file
<ARQUIVO_NOVO>`; o plano contem digest de issue, Project, comentarios,
aprovacao/ACL, corpo sanitizado e escopo COMMENT_ONLY. Sem aprovar/aplicar,
essa etapa e exclusivamente leitura.

A aplicacao remota permanece desativada (`REMOTE_PUBLICATION_ENABLED=False`).
O caminho abaixo e exercitado somente por testes offline e, apos futura homologacao, exige
`--apply-plan <PLANO> --confirm <DIGEST_COMPLETO> --audit-file
<ARQUIVO_NOVO>`, mais confirmacao humana interativa especifica
`APROVO F7 PUBLICAR <12primeirosdigitosdigest>`. Revalida estado LIVE
duas vezes, usa lock exclusivo duravel no dossie e realiza NO MAXIMO um
POST. Readback confere comentario unico e exato; falha/timeout de POST ou
readback grava auditoria e recibo local `PENDENTE_PUBLICACAO` com
`remote_effect=INDETERMINADO`. **Nao repetir automaticamente**: e
obrigatorio reconciliar o comentario LIVE e registrar novo gate do PO.

**Limite de idempotencia:** lock exclui concorrencia no *mesmo dossie local*
e marcador detecta comentarios existentes; a API de comentarios GitHub
nao oferece chave de idempotencia atomica entre hosts distintos. Por isso
frota multi-host deve usar escritor unico/serializacao externa antes de
ligar publicacao autonoma. Autorizacoes e readback evitam duplicatas normais,
mas **nao garantem exactly-once distribuido**.

A implementacao e os testes offline nao constituem autorizacao para usar
a funcao de aplicacao na Issue #85 nem para habilita-la em producao.
A CI do novo HEAD e revisao independente permanecem gates obrigatorios.

## Segurança D-3 — veto independente do Codex e remediação

Auditoria Codex real do PO em 15/11/2026 sobre HEAD `d7aa472`:
**VEREDITO: BLOQUEADO**, com cinco achados ALTOS e quatro MÉDIOS.
Evidência local `CH-F7-Codex-Auditoria-d7aa472a.jsonl`.
A CI `#43728084714` ficou verde com 746 testes **no HEAD antigo**;
isso NÃO revoga o veto do Codex.

Correções posteriores à auditoria (exigem nova CI e novo parecer):
- terceira reprovação por **testes** não requer `auditoria_codex.md`,
  pois Codex não foi chamado; V1 identifica `third_attempt_status`;
- a outbox V1 agora carrega `provenance`, com digest do manifesto
  canônico, SHA Git **base da missão** e hashes de TODOS os artefatos
  exigidos pelas três tentativas (`execucao.json`, relatório, código,
  patch, log de testes e log/parecer Codex quando realmente houve);
  publicação falha fechado se faltarem provas, qualquer arquivo for
  adulterado ou manifesto/execução divergirem;
- aprovação individual exige uma única linha EXATA e vigente, com
  `CODE_SHA256` (código AGY), `BASE_SHA` (commit base da missão),
  `MISSION_DIGEST` (manifesto), Issue e execution ID:
  
      CH-GOV-01 F7 PUBLICAR PROJECT#2 ISSUE#<issue> EXECUTION#<id> CODE_SHA256=<sha64> BASE_SHA=<gitsha40> MISSION_DIGEST=<sha64> ACTION=COMMENT_ONLY

- aprovação no comentário da Issue de origem ou #63 é conferida em
  histórico LIVE (inclusive edições). Revogação posterior por comentário
  PO com prefixo `CH-GOV-01 F7 REVOGAR PROJECT#2 ISSUE#<issue>
  EXECUTION#<id>` em qualquer um desses dois tópicos bloqueia POST;
- nova consulta LIVE depois de adquirir lock e antes de tentar POST;
- `f7-publicacao-<id>.lock` é um journal local **durável e pendente ANTES
  do POST**, `remote_effect=INDETERMINADO`, sem retry; apenas readback
  muda o status local para `PUBLICADO_VERIFICADO`.

**Limitações importantes que continuam BLOQUEANDO a liberação real:**
1. A prova local por hashes é **consistência dos artefatos**, não
   assinatura externa independente nem proteção contra quem pode
   substituir o dossiê inteiro por dados coerentes.
2. Não há exclusão distribuída atômica entre HOSTS distintos: GitHub
   Issues Comments não tem chave de idempotência global. Exige escritor
   único e um protocolo operacional/teste auditável antes de liberar.
3. Revogação e mudanças de estado podem ocorrer imediatamente após a
   última releitura LIVE; coordenação/atomicidade global não demonstrada.
4. Filesystem reparse/TOCTOU em Windows/Linux não foi ensaiado em
   condições concorrentes reais. Não declarar prova resistente a
   substituição atômica maliciosa de paths.
5. `PYTHONUTF8` não é requisito após fix de bytes/UTF-8, mas a nova
   versão requer a execução novamente da suíte Windows e CI Linux.

**Status de governança:** PR #88 Draft; sem chamada de publicação real,
sem admissão/escrita de cartão Project #2, sem merge/deploy; a F7 segue
BLOQUEADA por auditoria até nova evidência e correção de riscos residuais.

## Próxima frente: Control Center visual (depois dos gates Python)

Após F7 e homologação dos gates: expandir o Control Center já existente
(FastAPI + React), em vez de iniciar uma segunda aplicação desconectada.
Planejar dashboard com timeline AGY → Docker → Codex → CH-1, status legível,
contadores e cotas, dossiê clicável, fila de aprovações PO e alertas de
bloqueio. Priorizar interface responsiva, visual marcante, acessibilidade,
segurança e padrão **somente leitura por default**. Ações remotas devem
exigir confirmação explícita, plano pinado e readback, nunca inferir aprovação.
A UI não integra o escopo funcional da F7 nem autoriza merge/deploy.
