# CH-PIPE-01/F7 — E3-C5: encerrar caminho Docker legado e preparar atestador V1

**Estado em 16/11/2026: IMPLEMENTAÇÃO FAIL-CLOSED DE CONTRATO EM DRAFT.
NÃO EXISTE ATESTAÇÃO REAL DE UMA MISSÃO V1. GATE 3 BLOQUEADO.**

## Corrigido: o modo Docker legado não é mais publicável

O F6 mantém `docker-readonly-no-network:sha256:...` para diagnósticos
locais e regressões. A função `verify_provenance(...,require_isolation=True)`,
usada pelo F7, agora exige EXATAMENTE
`docker-attested-e3b-sigstore:sha256:e0c1bddedb8763803370d0a02b9d05371a30d9c4c82f0fe0b8813bb3b5b9f7ed`
além de `os_isolation_verified is True` **e** chamada a
`verify_runtime_receipt` para verificar assinatura independente do consumo
da missão, produtor e atestador GH LIVE.

Uma string local, booleano, assinatura apenas do build E3-B ou modo
`--isolated-tests` legado **não concedem autorização F7**. Sem
atestado externo V1, a validação falha. `REMOTE_PUBLICATION_ENABLED=False`.

Os testes de publicação que usam mocks de recibo continuam testando governança
isoladamente, **não representam uma missão assinada**. Uma regressão explícita
confere que uma outbox legada é rejeitada mesmo com flag True. Os testes F6
mantêm apenas o `verify_provenance(...,require_isolation=False)`.

## Novo atestador independente, AINDA NÃO ATIVADO

Foram versionados:

- `.github/workflows/f7-v1-attestor.yml` — trigger `workflow_run:
  completed`, para o futuro produtor V1 na `main`. Só prevê iniciar
  job caso produtor conclua `success`, a branch seja `main`,
  e a variável `CH_F7_V1_ATTESTOR_READY` seja `true`.
- Job de leitura mínima (`contents:read`, `actions:read`), sem
  `id-token:write`, `attestations:write` ou segredos de assinatura.
- `environment: f7-attestor` **previsto, mas sem configuração de regras
  realizada nesta entrega**. O PO precisa criar/validar aprovadores,
  proteção de branch e ausência de bypass antes de qualquer ativação.
- `scripts/f7_v1_attestor_preflight.py` confere o evento GitHub recebido
  com o readback GH LIVE do run produtor, incluindo repo ID, nome
  completo, branch, SHA exato, workflow ID e path, evento manual,
  tentativa, conclusão e ID numérico do PO como actor/triggering_actor.
- `PRODUCER_SHA_PIN=""`, `PRODUCER_WORKFLOW_ID_PIN=0` e
  `ATTESTOR_SIGNING_ENABLED=False` são constantes **não provisionadas**.
  Mesmo um run com origem válida acaba com exit **42** para não assinar
  evidências que ainda não foram verificadas integralmente.

O workflow só será reconhecido para `workflow_run` na branch default
quando o arquivo estiver presente na `main`. Como todas as PRs permanecem
Draft e a `main` inalterada, **não há atestador de produção operacional**
nem workflow de atestação V1 autorizado nesta entrega.

## Provas e limitações

O workflow de laboratório `f7-e3c5-attestor-guard-tests.yml` executa
negativas do verificador de origem (incluindo fork, outro ator, SHA,
tentativa, workflow e evento falsos) e prova que um run GitHub LIVE de
`push` da branch de teste não pode ser reconhecido como produtor.
Testes de publicação em Linux/Windows devem continuar verdes no SHA final.

**Não existe** nesta entrega: AGY/Codex reais em runner protegido, prova
autenticada de identidade/custo dos agentes, outbox de três tentativas reais,
conferência independente da origem e do conteúdo da outbox, assinatura
Sigstore V1 da missão, pins confiáveis provisionados, teste real de
revogação/concorrência Gate 4 ou piloto Gate 5.

## Próximo estágio para assinatura autêntica

1. Auditoria independente Codex no SHA final de cada mudança e CI integral.
2. PO cria regras e revisa proteção do Environment, política de
   trust e pins. Nada deve ser ativado somente por uma variável remota.
3. Consumir **o mesmo executor atestado por digest** para testes em missão
   AGY/Codex reais autenticados em ambiente protegido, com custo confirmado.
4. O atestador deve recuperar diretamente o ZIP da outbox e seu digest
   GH LIVE, verificar run/tentativa, inventário e hashes dos arquivos,
   logs dos agentes e do Docker, políticas de escopo e autorização PO
   separada. Só depois disso emitir atestação de consumo da missão.
5. Um verificador distinto sem acesso à chave confere assinatura e
   origem antes de eventualmente solicitar homologação ao PO.
6. Gates 3, 4 e 5 permanecem etapas de aceitação distintas.

**Guardrails:** sem merge, deploy, release, tags, secrets, variables,
pin real, Project #2, POST, AGY/Codex pago ou missão V1 real.
