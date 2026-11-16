# E3-B — construção e atestação real do executor de testes F7

**Estado:** entrega E3-B isolada em Draft, empilhada sobre PR #94 (E3-A). Não libera o Gate 3.

## O que é executado de verdade

- `scripts/f7_executor_v1.py` é um programa Python real, stdlib-only, que verifica a
  identidade do processo e executa `unittest discover` em código de um diretório
  `/work` montado somente para leitura. Retorna JSON de resultado e digest do log.
- `docker/f7-e3b/Dockerfile` usa imagem Python 3.12 slim para Linux amd64 **fixada
  por manifest digest**:
  `python:3.12-slim@sha256:05a994d2344eb364cc186910f4fc8786a38215f39f00d0acc25bff33a08f4177`.
  Não instala pacotes externos; o código é copiado a partir do commit Git.
- O job `build` do workflow `f7-e3b-executor-attest.yml` não tem secrets e
  usa `--network=none` no build e no `docker run`, usuário `65534:65534`,
  rootfs de execução read-only, mount de entrada read-only, todas as capabilities
  descartadas, `no-new-privileges`, limite de CPU, memória e processos.
- O job executa `--self-check`, uma suíte real **positiva** e outra
  **negativa** (assertion errada). Exige exit code **12** no caso negativo.
- A imagem construída é salva como `dist/f7-e3b-executor.tar`, com SHA-256 dos
  bytes. `actions/attest` usa Sigstore/GitHub OIDC para publicar uma atestação
  SLSA de proveniência **do arquivo TAR**, e `upload-artifact` preserva TAR + checksum.
- O job `verify` roda em **outro runner**, baixa o artefato, confere SHA-256,
  exige assinatura válida por repo, workflow, SHA/ref do commit e origem GitHub,
  testa que um TAR adulterado é rejeitado e carrega a imagem para verificar
  o campo `org.opencontainers.image.revision` antes do smoke test.
- Todas as ações de terceiros estão referenciadas por SHA completo.
  O workflow só roda na branch E3-B própria do PO.

## O que essa atestação NÃO prova

**Não é uma outbox V1 real.** O executor não invoca AGY, Codex, GitHub Project,
GitHub CLI remoto, API paga ou publicador F7. Não contém credenciais.
Isso pertence ao E3-C, com autorização separada. A atestação de build do TAR
comprova a origem do artefato, **não o que uma futura missão efetivamente fez**,
e não é uma prova de que o host Docker seja inviolável.

O digest do TAR e o ID da imagem são identidades diferentes. `docker save`
não garante um TAR byte-a-byte reproduzível em todos os hosts: o hash atestado
é o hash **do TAR realmente produzido naquele run**. A imagem-base, por sua vez,
é fixada pelo digest do manifesto. O workflow não efetua push de imagem ao GHCR,
não faz release, não escreve tags nem ativa publicação.

## Verificação independente do build

No run, examinar `build` e `verify`. O job `verify` só será sucesso se a assinatura
for confirmada pelo GitHub CLI com os seguintes controles:

~~~bash
gh attestation verify dist/f7-e3b-executor.tar \
  -R hallanbrito/CHDevFlow \
  --signer-workflow hallanbrito/CHDevFlow/.github/workflows/f7-e3b-executor-attest.yml \
  --source-digest "$GITHUB_SHA" \
  --source-ref "$GITHUB_REF" \
  --deny-self-hosted-runners
~~~

A origem autenticada é o OIDC do job GitHub Actions. Para auditoria Po Solo:
inspecionar SHA/ref **reais** na resposta da CLI e no certificado.
A edição posterior desta branch altera o SHA e exige novo run/atestação.

## Condições restantes Gate 3

1. Conferir o run e a attestation ID/URL no GitHub, mais o digest SHA-256
   do TAR e o image ID observado no job independente.
2. Codex deve auditar **o commit final exato** e verificar se o artefato
   realmente corresponde ao código/versões esperados.
3. No E3-C, construir um produtor de missão **V1 real** que consuma um
   executor atestado e um ambiente com dependências pinadas; coletar evidências
   de AGY/Codex reais e assinar um manifesto ligado ao artefato/run.
4. Revisar Trust Policy, revogação, concorrência pré-POST e demais Gate 4/5.
5. PO decide explicitamente; nenhum dado deste build equivale a autorização de POST.

**Governança:** sem merge, deploy, release, GHCR push, tags, secrets, variáveis
repo, Project #2 ou habilitação do publicador. No modelo Multioperador, pelo
menos duas pessoas devem validar decisões sensíveis. Custo adicional alvo R$0
em GitHub Actions público, sujeito às políticas/cotas da conta.
