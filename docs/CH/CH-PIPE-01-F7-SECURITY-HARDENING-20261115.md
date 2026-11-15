# CH-PIPE-01/F7 — Security hardening (2026-11-15)

**Status: BLOQUEADO PARA PUBLICACAO REAL E MERGE.** Documento de decisao/controle, nao parecer Codex nem evidencias de execucao.

## Origem e cadeia de PRs

- Base F7: `feat/ch-pipe-01-f7-po-escalation` (auditoria Codex anterior: BLOQUEADO, commit `09ccb5432b24baeb3753fe058c3205fd58553ec4`).
- Correcao inicial de outbox legada: Draft PR #90, HEAD inicial `518febce6caf1f37990ee65abe519dabd33a08de`, CI run #43732400675 verde (759 testes).
- Esta rodada de seguranca: Draft PR #91 sobre a branch de #90. **A CI verde da #90 nao homologa #91.**

## Mitigacoes implementadas em #91 (testes novos exigem CI)

1. Revogacao do PO em comentario mais antigo editado tambem bloqueia novo POST.
2. Validacoes de caminho verificam symlinks/junctions acima e abaixo da raiz declarada do dossie; caminho relativo com `..` e rejeitado.
3. SHA Git BASE completo da Issue LIVE deve ser exatamente igual ao do manifesto da missao. A verificacao do SHA **do codigo F7** na auditoria e feita pelo script PowerShell (GH commit remoto + blob Git local).
4. F6 registra `os_isolation_verified` depois do retorno do runner Docker; F7 so considera outbox publicavel com `test_execution=docker-readonly-no-network:sha256:<64hex>` e flag True. Esse registro e informativo, **nao autenticacao externa**.
5. JSON com chave duplicada (inclusive aninhada), resposta excessiva do GitHub e planos locais excessivos sao rejeitados.
6. Reconciliação `--reconcile-plan` **somente leitura**: exige journal/digest correspondentes, consulta Issue/comentarios LIVE e distingue marcador remoto unico encontrado, nao observado ou colisao. Jamais faz POST, remove journal ou autoriza retry. Funciona mesmo apos Issue CLOSED ou revogacao do PO.
7. `REMOTE_PUBLICATION_ENABLED = False` bloqueia CLI real antes do journal e `_post_comment()` antes de enviar qualquer POST. Mocks em testes nao constituem liberacao.

## Gates ainda faltantes para homologacao

| Achado Codex | Status / exigencia |
|---|---|
| Autenticidade externa de hashes/producao | **Pendente:** assinatura/atestacao verificavel por custodiante separado do agente, fora do dossie editavel. Hash isolado nao prova autoria |
| SHA Git exato do publicador F7 | **Parcial:** auditoria PowerShell verifica GitHub commit e blobs. Plano/approval do POST ainda nao vincula commit F7 verificado |
| Concorrencia entre hosts | **Pendente:** unico publicador central, coordenacao compartilhada e controle de permissao, nao confiar no `O_EXCL` local |
| Revogacao imediatamente antes de POST | **Parcial:** edicoes e 3 snapshots cobertos. Resta janela de corrida nao atomica; exigir protocolo de congelamento da autorizacao durante publicacao |
| Testes de codigo nao confiavel no host | **Parcial:** formato de isolamento exigido para elegibilidade; autenticidade e efeito real do runner ainda nao atestados externamente |
| Symlinks/junctions/TOCTOU | **Parcial:** ancestrais cobertos, mas leitura de arquivo ainda usa checar-abrir em chamadas separadas; descritores atomicos Win/Linux pendentes |
| Validacao semantica de evidencias | **Pendente:** conferir significado de `testes.log`, `codex.log`, parecer, patch, ordem temporal e invocacoes reais; hashes nao bastam |
| Reconciliacao apos timeout | **Parcial:** consulta LIVE read-only implementada. Reautorizacao manual formal de nova tentativa nao existe; retry continua bloqueado |
| Bypass adjacente de Project #2 | **Pendente fora de F7:** `scripts/ch_project_sync.py --apply` precisa de gate proprio; F7 nao o chama |
| Mocks confundidos com integracao | **Parcial:** mocks rotulados e testes negativos; integracao real proibida ate gates concluídos |

**Criterio definitivo:** nao mudar `REMOTE_PUBLICATION_ENABLED` para True, nao fazer merge e nao apresentar laboratorio mockado como publicacao real ate CI do HEAD, auditoria independente Codex e controles externos acima estarem resolvidos.

## Verificacao reproduzivel (PowerShell / Windows)

No clone ou worktree de revisao isolada, livre de mudancas locais:

```powershell
$repo = "C:\CAMINHO\CH-F7-Runner"
git -C $repo fetch origin security/ch-pipe-01-f7-hardening-20261115
git -C $repo switch --detach origin/security/ch-pipe-01-f7-hardening-20261115
$env:PYTHONPATH = "$repo\src"
python -m unittest discover -s "$repo\tests" -p "test_ch_pipe_01_f7_*.py" -v
python -m unittest discover -s "$repo\tests" -p "test_ch_pipe_01_f6_generic_cycle.py" -v
& "$repo\scripts\Auditar_F7_Codex.ps1" -RepoRoot $repo
```

CI integral: `gh workflow run w1-checks.yml --repo hallanbrito/CHDevFlow --ref security/ch-pipe-01-f7-hardening-20261115`; consultar conclusao do run emitido. Sem publicacao, sem Project write, sem merge.

## Protocolo de recuperacao de publicacao inconclusiva

Se ja existe um journal F7 `PENDENTE_PUBLICACAO`, usar `--reconcile-plan` e **nao** executar `--apply-plan`: a consulta informa se encontrou comentario unico autenticado na Issue, mas nao apaga lock ou permite retries. Colisao/indisponibilidade mantem o estado bloqueado e exige decisao humana registrada.
