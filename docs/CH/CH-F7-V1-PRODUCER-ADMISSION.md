# F7 E3-C2 — Admissão de missão V1 no produtor protegido

**Estado em 16/11/2026: IMPLEMENTADO E TESTADO COMO GATE, NÃO EXECUTOR V1.**
Branch Draft empilhada em PR #115 → #114 → #113 → #94. Não há
integração autorizada à `main`, publicação remota ou segredo de agentes.

## O problema que este gate resolve

O E3-B construiu e assinou um TAR de executor Docker de testes.
O E3-C0 consumiu esse TAR em outro workflow e atestou o manifesto.
O E3-C1 provou que uma cadeia LAB assinada não vira autorização V1.
**Ainda não há evidência de uma missão AGY→testes→Codex real.**

O E3-C2 cria a primeira fronteira do futuro produtor:
a autorização específica do PO, vinculada ao commit auditado
e ao artefato executor, com consulta LIVE ao GitHub.

### Contrato obrigatório de missão

O futuro PO registrará no repositório protegido (commit auditado em `main`)
um arquivo `docs/CH/missions/<mission-id>.json` de acordo com o schema
`CHDEVFLOW-F7-V1-MISSION/1`, incluindo:

- `repository` = `hallanbrito/CHDevFlow` e `issue` aberta que não seja PR;
- `mission_id`, `producer_sha`, `baseline_sha`, SHA-256 do TAR executor;
- `allowed_path` com um único arquivo Python, `prompt_path` versionado;
- `timeout_seconds` de 120 a 900, `cost_brl` inteiro **zero**;
- `nonce` aleatório de 32 dígitos hexadecimais, exclusivo da missão.

O script `scripts/f7_v1_mission_gate.py` valida o contrato, serializa em
JSON canônico e calcula `MISSION_DIGEST` SHA-256. O PO, em uma Issue
específica, publicará um comentário **exato**:

~~~text
CH-F7-V1 AUTORIZAR ISSUE#<issue> MISSION#<mission_id> PRODUCER_SHA=<sha40> BASE_SHA=<sha40> EXECUTOR_TAR_SHA256=<sha256hex> MISSION_DIGEST=<sha256hex> COST_BRL=0 NONCE=<nonce32> ACTION=RUN_ONLY
~~~

O comentário precisa ser do login `hallanbrito` **e GitHub user.id 113695320**,
não editado, presente na lista completa de comentários da Issue aberta e
sem revogação posterior `CH-F7-V1 REVOGAR ISSUE#...` do mesmo PO.

O workflow `f7-v1-producer.yml` só poderá ser disparado manualmente na
`main`; a condição exige ator PO e o SHA aprovado na repo variable
`CH_F7_APPROVED_V1_PRODUCER_SHA`. O gate reconfere na API a origem
`workflow_dispatch`, branch, commit, identidade numérica de `actor` e
`triggering_actor`, repo ID, Issue e comentário. A variável ainda
**não está configurada** e não foi alterada por esta entrega.

**Crítico:** a identidade do `GITHUB_TOKEN` no runner é o bot de Actions,
não necessariamente o PO. Por isso a identificação do PO é obtida
do **run autenticado pelo GitHub API**, não de `gh api user`.

### O que acontece depois de passar a autorização?

**Nesta Draft:** o workflow registra o sucesso de admissão e **falha
propositalmente com exit 42**. Nenhuma outbox V1 é criada; não existe
artifact `f7-v1-evidence-*`, nenhuma chamada de agente e nenhum POST.
O script retorna `PO_APPROVAL_VERIFIED_ONLY`, com
`agents_executed=false` e `outbox_v1_created=false`.

Essa falha é uma barreira de segurança, não um defeito a contornar.
**NÃO trocar o `exit 42` por `exit 0` nem remover a proteção sem
revisão Codex do SHA final, homologação Gate 3 e aceite explícito PO.**

## Próxima implementação antes do piloto real

1. Criar missão real pequena, com testes independentes, issue específica,
   baseline SHA, nonce e orçamento verificável de R$0.
2. Prover AGY e Codex **autenticados** num ambiente protegido/efêmero,
   sem expor credenciais ao código gerado nem a jobs de PR.
3. Adaptar o motor real `generic_cycle.run_generic_cycle` para executar
   testes no **executor E3-B atestado**, não em Docker arbitrário,
   e corrigir a semântica de isolamento (não aceitar flag booleana sem prova).
4. Garantir que o produtor trabalhe com checkout isolado e paths
   permitidos, registre até três tentativas, Code SHA, falhas e
   feedback, Codex real e hash de cada prova; não permitir execução
   em `main` nem chamada de agente antes do gate.
5. Empacotar **outbox V1 verdadeira** e manifesto com digests, SHA
   do executor, run/tentativa e identidade de origem GH em ZIP,
   para assinatura **em outro job com Environment protegido**.
6. Fixar a política de trust/revogação, provar negativos entre hosts,
   reunir logs, pedir nova auditoria Codex e aceite formal do PO.
7. Gates 4 e 5 continuam separados: compromisso/revogação/POST real
   só após aprovação específica e testes de ponta a ponta.

## Custos e governança

CI de laboratório utiliza somente GitHub Actions com permissões de
leitura, sem acesso a segredos de AGY/Codex. Não há geração real de
código por LLM nem cobrança de API nesta PR. Operador Solo preserva
risco administrativo; o modelo multioperador deve ter revisores
distintos. Nenhuma alteração em Project #2, secrets, repo variables,
tag, deploy, merge, release ou F7 POST.

**Gate 3 segue BLOQUEADO; Gates 1 Solo e 2 = 2/5 aceitos operacionalmente.**
