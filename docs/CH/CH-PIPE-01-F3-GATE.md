# CH-PIPE-01/F3 — Gate operacional de piloto, ainda INATIVO

**Issue:** #78, dependência #69. Autorização PO em #78 (14/11/2026).  
**Branch:** `feat/ch-pipe-01-f3-operational-gate`, empilhada na F2 PR #80, que depende da F1 PR #79.

## O que esta fatia efetivamente entrega

- **`ch pipeline gate-check --mission ... --approval-comment N --json`**: verifica preflight Git local (HEAD, branch isolada, worktree limpa); busca um comentário específico via `gh api` em modo somente leitura; confronta identidade **do dono da conta GitHub** (ID e login), ID do comentário, URL da Issue, integridade, digest exato, SHA, escopo, timeout, nonce e data de expiração. Comentários editados são recusados; validado por consulta à API, não por texto digitado pelo agente.
- **`pilot_gate.py`**: contrato determinístico de decisão `chdevflow.pilot-approval/v1`, status explicitamente `BLOQUEADO_CUSTO` mesmo após conferência positiva de PO.
- **`pilot_claim.py`**: reserva local O_EXCL, lock único, histórico antirreplay e encerramento explícito. Fica **desconectada** de `ch pipeline run`; não coordena hosts diferentes. Lock órfão bloqueia futuras reservas até reconciliação humana.
- **`PilotCancellation`**: sinal cooperativo testável, **não** elimina processos OS ainda.
- O adaptador `ProcessAdapter._invoke_inactive` passou a recusar chamadas de maneira incondicional, inclusive por import direto, para evitar contorno de um sentinela Python. **Nenhum agente real é iniciado.**

## Estados e códigos

- `ch pipeline plan`: `PLANEJADO_AGUARDANDO_GATE` significa apenas plano consistente.
- `ch pipeline gate-check`: `BLOQUEADO` (comentário/contrato), `BLOQUEADO_GITHUB` (API), ou `BLOQUEADO_CUSTO` quando a decisão do PO é verificável mas falta prova independente de custo/licença, sandbox, controle de replay e novo gate do piloto. O código de saída permanece **não zero**.
- `ch pipeline run`: `BLOQUEADO_ATIVACAO`, sem lançar AGY/Codex; exit code 2.
- Nenhum desses estados aprova merge, deploy, custo, cron ou escrita no Project #2.

## Contrato de comentário (DOCUMENTAL, não publicar automaticamente)

Um comentário **novo, não editado e escrito pelo PO** na Issue da missão,
em corpo exatamente igual a:

~~~text
```ch-pilot-approval
{
  "schema": "chdevflow.pilot-approval/v1",
  "decision": "APPROVE_ONE_MANUAL_PILOT",
  "repository": "hallanbrito/CHDevFlow",
  "issue": 78,
  "mission_id": "PILOT-001",
  "mission_digest": "<64 hex correspondentes à missão>",
  "baseline_sha": "<40 hex da worktree>",
  "allowed_paths": ["src/lab.py", "tests/test_lab.py"],
  "timeout_seconds": 900,
  "max_extra_cost_brl": 0,
  "nonce": "<32 hex minúsculos, aleatórios e não reutilizados>",
  "expires_at": "2026-11-14T22:00:00Z"
}
```
~~~

**NÃO use esses placeholders nem a data antiga como autorização.** O
comentário deve ser emitido pelo PO com o digest e SHA observados na hora,
vale no máximo 24 horas desde a publicação e não pode ter sido editado.
É lido por `gh api repos/hallanbrito/CHDevFlow/issues/comments/N`; um
arquivo JSON local com `approved_by` não é aceito como fonte de identidade.

Mesmo se a decisão passar, o sistema retorna `BLOQUEADO_CUSTO` porque
**uma declaração de preço R$0 num comentário não é prova independente da
licença/conta nem garante não ocorrer cobrança**. Não há mecanismo de
liberação de execução nesta F3.

## Exemplo seguro Windows (PowerShell)

No checkout da F3 e com o CHDevFlow instalado em editable:

~~~powershell
ch pipeline plan --mission "$HOME\Downloads\missao-f2-teste.json" --json
ch pipeline gate-check --mission "$HOME\Downloads\missao-f2-teste.json" --approval-comment 123456 --json
ch pipeline run --mission "$HOME\Downloads\missao-f2-teste.json"
~~~

`123456` é apenas um exemplo **inexistente/não conferido**. O gate deve
retornar `BLOQUEADO_GITHUB` se a API não trouxer evidência válida.

## Testes offline e matriz de ameaça

~~~powershell
python -m unittest discover -s tests -p "test_ch_pipe_01_f3_gate.py" -v
~~~

Cobertura: autor GitHub divergente, ID/url incorretos, comentário editado,
formato/injeção, digest/paths/SHA divergentes, custo acima de zero, expiração
ou validade >24h, rede indisponível, plano desatualizado, reserva/replay,
lock órfão e chamada de `run` sem agentes.

## Antes de autorizar qualquer piloto real

1. Revisar e homologar F1/#79 e F2/#80, manter F3 Draft sem merge.
2. Verificar **ao vivo** as informações da conta/assinatura de AGY e Codex,
   com limites/quota sem custo incremental; sem prova, `BLOQUEADO_CUSTO`.
3. Criar execução em ambiente isolado de verdade (sandbox de SO, usuário
   não privilegiado, diretório descartável, **sem credenciais** ou arquivos
   externos) com controle dos subprocessos e encerramento da árvore de processos.
4. Registrar lock/idempotência persistente, reconciliação após queda, rollback
   dos arquivos, status Git/CI e revalidação do comentário imediatamente antes
   de cada ação — não basta validar uma vez no início.
5. Exigir **novo despacho específico do PO** para rodar uma única missão;
   nada de polling, Actions de execução, daemon, auto-merge/deploy.

**Limites:** a API `gh` fornece autoria da conta, não prova de que o PO
entendeu riscos financeiros. A partir deste ponto, não se deve tratar
`BLOQUEADO_CUSTO` como permissão de fazer teste real. Este F3 também não
oferece execução remota autorizada, apenas preparação auditável. Nenhum
processo AGY/Codex deve ser acionado no CI ou pelo novo comando.
