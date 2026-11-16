# F7 Gate 3 — vincular autorização do PO ao commit F7 auditado

**Estado:** IMPLEMENTADO EM DRAFT / NÃO HOMOLOGADO / SEM PUBLICAÇÃO REAL.
**Origem:** Issue #86; Gate 1 Solo e Gate 2 aceitos operacionalmente em 16/11/2026 (2/5 gates).
**Escopo:** somente a ponte de confiança do **SHA do código F7 publicador**. O SHA base da missão e o SHA-256 do código produzido pelo AGY são identidades **diferentes** e não substituem o SHA auditado do publicador.

## Contrato de confiança (fail-closed)

O Gate 3 só admite um plano de publicação quando **todos** os elementos se referem ao mesmo SHA Git completo de 40 caracteres minúsculos:

1. **Auditoria independente:** executar a auditoria Codex em checkout limpo, com SHA completo, verificação dos blobs locais contra o commit e existência do commit no GitHub (script `scripts/Auditar_F7_Codex.ps1`). O relatório deve registrar o SHA e um parecer; o PO confere manualmente o resultado. **A variável, sozinha, não prova que a auditoria ocorreu.**
2. **Pin externo administrado pelo PO:** após conferir um parecer favorável e os riscos, fixar `CH_F7_AUDITED_COMMIT_SHA` em *Settings → Secrets and variables → Actions → Variables* do repositório, com **o SHA exato do checkout auditado**. O código da F7 consulta esse valor pela **API LIVE** do GitHub. Ausente, inválido ou não resolvível, o planejamento falha fechado.
3. **Checkout executado:** `git rev-parse --verify HEAD` deve igualar o pin. `git status --porcelain --untracked-files=all` deve estar vazio. Além disso, o verificador de identidade compara blobs Git de módulos F7 críticos com o commit auditado, suas origens de import e o bytecode das funções Python carregadas contra a fonte recompilada. Worktree modificada, módulo adulterado, import externo, código carregado antigo, commit diferente ou Git indisponível bloqueiam.
4. **Commit remoto:** `GET /repos/hallanbrito/CHDevFlow/git/commits/<SHA>` deve retornar `sha` exatamente igual ao pin e `tree.sha` Git completa. A comparação não aceita prefixos abreviados nem SHAs de outro repositório.
5. **Autorização LIVE individual do PO:** A autoria é conferida por **login + `user.id` fixo do PO** no comentário, no histórico e na sessão com ACL. A declaração exata na Issue de origem ou de governança inclui, além dos campos já exigidos, **`F7_AUDITED_SHA=<40-hex>`**, com o SHA aprovado. Sem campo, com SHA antigo, com outra pessoa ou com texto extra: rejeição.
6. **Plano pinado:** os campos `f7_audited_sha`, `f7_audited_tree` e `f7_runtime_digest` entram no plano e no digest; o comentário de escalonamento também expõe o SHA F7 para auditoria. A reconsulta LIVE nos snapshots de preflight, pré-reserva e pré-POST revalida a identidade, a política externa e a autorização. Política alterada ou checkout divergente: sem novo POST.
7. **Auditoria de tentativa:** o evento `ATTEMPT_POST` (somente em testes mockados enquanto o publicador está desligado) registra o SHA F7 auditado.

**Formato da declaração do PO (exemplo de contrato, NÃO é uma autorização):**

~~~text
CH-GOV-01 F7 PUBLICAR PROJECT#2 ISSUE#<ISSUE> EXECUTION#<32hex> CODE_SHA256=<64hex> BASE_SHA=<40hex> MISSION_DIGEST=<64hex> F7_AUDITED_SHA=<40hex> ACTION=COMMENT_ONLY
~~~

Não publique esse exemplo na Issue como se fosse autorização. O campo `BASE_SHA` identifica o repositório da **missão**; `F7_AUDITED_SHA` identifica o commit do **publicador**.

## Auditoria independente — primeira rodada BLOQUEADA (16/11/2026)

O Codex CLI auditou estaticamente o commit `32228452dcf2ad5f36b6e8dd8bedd2b0b18841f8` e retornou `VEREDITO: BLOQUEADO`, com 1 achado crítico, 6 altos e 3 médios. O auditor declarou que não executou testes nem consultou GitHub; seu parecer não invalida automaticamente as provas operacionais anteriores da sonda Gate 1 e da reserva Gate 2, mas **bloqueia o aceite do Gate 3**. Achados classificados e tarefas na [Issue #95](https://github.com/hallanbrito/CHDevFlow/issues/95).

Após o parecer, a PR foi atualizada para exigir também **ID GitHub numérico fixo do PO** (não apenas login) em aprovação, histórico e sessão, com negativas. O script de auditoria também passou a incluir os módulos de custódia, reserva, a sonda e os workflows do GitHub que não foram fornecidos na primeira execução. O achado #6 recebeu um controle adicional de **verificação de blobs + bytecode de módulos carregados**, com negativas para adulteração e alterações entre snapshots. **O risco continua parcialmente aberto:** um verificador executado no mesmo processo não prova a imutabilidade de um artefato isolado, das dependências externas, do binário Python ou do cliente `gh`. Não afirmar correção completa nem reutilizar o parecer para um HEAD diferente.

A próxima auditoria deve analisar o **novo commit exato** depois da CI e o mecanismo de identidade do artefato executado. A variável administrativa `CH_F7_AUDITED_COMMIT_SHA` **não deve ser cadastrada** antes de veredito e aprovação específica do PO.

## Segunda auditoria independente Codex — BLOQUEADO (16/11/2026)

O PO executou `scripts/Auditar_F7_Codex.ps1` em clone separado, checkout detached e worktree limpa no commit `d29021634f75e8680c3e9b3919c2e8639182d596`. O Codex CLI retornou **VEREDITO: BLOQUEADO**, com **3 achados ALTOS, 4 MÉDIOS e 1 BAIXO**; registro de origem local `CHDevFlow-Labs/CH-F7-Codex-Auditoria-d2902163.jsonl`. A avaliação foi **textual**: Codex não utilizou ferramentas, não verificou GitHub/runs nem executou testes diretamente. A CI anterior estava verde, mas isso não supera os bloqueios.

**Bloqueios altos:** (1) ausência de custódia/atestação em runner protegido compatível com uma outbox V1 real (a sonda de laboratório não serve como prova de produção); (2) verificação de identidade do executor somente *in-process*, sem binários/dependências/runner isolado e com lacuna para funções substituídas por objetos `callable`; (3) âncora de confiança da atestação entregue por variáveis do ambiente local, sem confrontação LIVE de run/workflow/artefato pelo publicador. A revisão também apontou janela de revogação antes do POST, ensaio multi-host ainda não coberto na própria auditoria, fraqueza do ID numérico no readback, integridade local diferente da custódia remota e vulnerabilidade residual de escrita de recibo em ancestrais.

**Resposta técnica sem aceite automático:** foram abertas correções na Draft PR #94 para exigir `user.id` do PO no reconhecimento de comentário e na reconciliação, além de negar exportações Python/métodos substituídos por objetos chamáveis opacos. A auditoria do SHA antigo não se estende ao novo HEAD; após CI verde será necessária nova avaliação, ainda mantendo o bloqueio dos riscos altos restantes.

A matriz completa está registrada na [PR #94](https://github.com/hallanbrito/CHDevFlow/pull/94#issuecomment-6918659143) e [Issue #95](https://github.com/hallanbrito/CHDevFlow/issues/95#issuecomment-6918661271). Não cadastrar `CH_F7_AUDITED_COMMIT_SHA`, não usar a sonda como autorização para outbox real, não ativar `REMOTE_PUBLICATION_ENABLED`.

## Evidência adicional de identidade de código carregado

O módulo `src/chdevflow/core/po_escalation_runtime.py` inspeciona a origem dos módulos críticos F7, compara cada blob com `git rev-parse SHA:caminho` e `git hash-object --path` (inclusive normalização Git/CRLF) e confere os `code objects` das funções Python presentes em memória contra a fonte recompilada. O digest `f7_runtime_digest` vincula essas observações ao plano, ao snapshot e ao readback.

A suíte `tests/test_f7_runtime_identity.py` cobre origem adulterada, arquivo editado após o commit, função trocada em memória, commit incompatível, módulo ausente e symlink (quando o sistema permite). O job Windows deve executar essa suíte além dos testes de publicação.

**Limites e risco residual:** verificação em processo **não é prova externa de execução hermética ou imutável**. Um atacante capaz de adulterar o intérprete, os módulos do verificador, a memória depois da última verificação, as ferramentas `git`/`gh`, ou as dependências externas poderá contornar este mecanismo. A homologação integral do achado #6 ainda requer um artefato executor versionado, um ambiente de execução isolado/imutável com identidade verificável (por exemplo, digest de imagem ou pacote), configuração de dependências fixada, e preservação desse vínculo até o ponto da escrita. **Nenhum dos novos testes concede autorização de publicação.**

## Hardenings E3-A — política LIVE + admissão de outbox V1 (Draft)

Implementadas na branch da PR #94, **ainda sem homologação**:

- O publicador consulta **repo Actions Variables pelo GitHub API LIVE**
  para obter chave pública de atestação, SHA do produtor, fingerprints revogados
  e IDs de workflow. Não usa o ambiente local como origem de confiança.
- Três **pins versionados** exigem fingerprint da chave, SHA do produtor e
  ID do workflow V1; **permanecem vazios/desabilitados** até auditoria e
  aprovação individual do PO. Repo Variables sozinhas não são imutáveis
  para um administrador Solo; essa segunda checagem dificulta trocar a
  política sem mudar o SHA do publicador auditado.
- A admissão V1 somente aceita recibo assinado com origem
  `github-actions:v1:<run>:<attempt>:<artifact>:sha256:<digest>` e
  verifica via GitHub API workflow, SHA, branch main, repo ID, tentativa,
  artefato, bytes do ZIP e SHA-256 e reconfere o run. A sonda
  `F7-CUSTODY-PROBE` não satisfaz esse contrato.
- Testes novos cobrem ausência/alteração dos pins, overrides de env,
  política inválida, workflow/repo/artefato trocados, ZIP adulterado,
  corrida no run e origem da sonda.

**Bloqueios importantes mantidos:** ainda não há workflow produtor V1, imagem
OCI/lock de dependências atestados, execução real AGY/Codex num runner
independente, nem assinatura de um manifesto de executor. O verificador
in-process continua apenas defesa adicional. O risco residual de conta
administrativa comprometida permanece.

O desenho executável, fases de implantação, Sigstore/SLSA e critérios de
aceite estão em [CH-PIPE-01-F7-EXECUTOR-V1-TRUST.md](CH-PIPE-01-F7-EXECUTOR-V1-TRUST.md).
O Gate 3 NÃO pode ser homologado com E3-A isoladamente.

## Evidências exigidas para homologar Gate 3

- Relatório de auditoria Codex com commit exato do publicador, parecer e achados resolvidos ou riscos aceitos explicitamente pelo PO, sem inferir homologação de um teste mockado.
- CI verde no HEAD da Draft PR e regressões negativas para pin ausente, SHA remoto divergente, worktree suja, declaração antiga, commit alterado entre snapshots e plano antigo.
- Registro da decisão de auditoria do PO com o SHA de 40 caracteres, identidade de revisor e referência do relatório. **Só então** criar ou atualizar a variável `CH_F7_AUDITED_COMMIT_SHA` pelo PO; jamais o AGY.
- Se o commit auditado deixar de ser o executado, **parar**. Um merge ou rebase altera o SHA; o pin precisa ser deliberadamente reavaliado após nova auditoria.

## Limitações

O método não autentica automaticamente a veracidade do parecer Codex: pressupõe que o PO examine o relatório e controle o pin. No modelo Solo, o próprio administrador controla GitHub, secrets, rulesets e a variável; isso não equivale a revisão humana independente. Em projetos com múltiplos operadores, recomenda-se **validação por pelo menos duas pessoas distintas** para mudanças e decisões sensíveis.

A F7 permanece com `REMOTE_PUBLICATION_ENABLED=False`. **Nenhuma decisão deste Gate 3 autoriza** merge, deploy, release, POST remoto, criação de tag, escrita no Project #2, execução real AGY/Codex ou consumo de provedor pago. Gates 4 e 5 são independentes.

## Execução futura (somente depois de uma auditoria aceita)

No PowerShell, em sessão administrativa do PO, consultar o valor (somente SHA público):

~~~powershell
$repo = "hallanbrito/CHDevFlow"
gh api "repos/$repo/actions/variables/CH_F7_AUDITED_COMMIT_SHA" --jq '.value'
~~~

Para fixar **após** conferir o SHA do parecer da auditoria:

~~~powershell
$repo = "hallanbrito/CHDevFlow"
$auditado = "<SHA_EXATO_40_HEX_DO_COMMIT_AUDITADO>"
if ($auditado -notmatch '^[0-9a-f]{40}$') { throw "SHA auditado invalido" }
gh variable set CH_F7_AUDITED_COMMIT_SHA --body $auditado --repo $repo
~~~

A criação do pin é um ato de confiança do PO, não uma permissão para publicação.
