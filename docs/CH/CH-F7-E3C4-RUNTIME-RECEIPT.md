# CH-PIPE-01 / F7 E3-C4 — Recibo de consumo assinado da missão

**Estado: CONTRATO IMPLEMENTADO EM DRAFT. NÃO EXISTE RECIBO REAL V1 NESTA ENTREGA.**
Gate 1 Solo + Gate 2 = 2/5 aceitos operacionalmente; Gate 3 BLOQUEADO.

## Por que este controle existe

O E3-B atestou **o build** de um executor Docker com SHA-256 e Sigstore.
O E3-C0 consumiu essa imagem em laboratório, gerando um manifesto atestado
por GitHub OIDC. O E3-C3 conectou a imagem ao modo experimental F6.

Isso **não prova**, por si só, que determinada missão AGY→testes→Codex
executou no mesmo contêiner. O registro local `os_isolation_verified=True`
e a string `docker-attested-e3b-sigstore:sha256:...` podem ser forjados
por quem controla a worktree. O E3-C4 separa esses conceitos.

## Admissão do modo E3-B no publicador F7

`verify_provenance(root, outbox, require_isolation=True)` agora reconhece
a identidade do executor E3-B, mas **recusa a missão** sem um recibo
`f7-runtime-receipt.json` produzido e assinado por atestador externo.

A exigência aplica-se somente ao modo `docker-attested-e3b-sigstore:...`.
O modo legado `docker-readonly-no-network:...` mantém a compatibilidade
anterior e **não é uma prova de build atestado**. Esta exceção legada
permanece risco residual para a auditoria Gate 3 e precisa de política
de descontinuação antes de produção real.

## Contrato do recibo protegido

Schema: `CHDEVFLOW-F7-E3C4-RUNTIME-RECEIPT/1`.
O arquivo precisa vincular os seguintes campos:

- Repositório nome e ID numérico, `mission_id`, `execution_id` e
  `mission_digest` da mesma outbox/manifesto.
- `outbox_sha256` calculado sobre **bytes exatos** de
  `escalonamento_po.json`; `files_sha256` **igual ao mapa completo**
  dos artefatos da proveniência local (incluindo testes de cada tentativa).
- `executor_build_sha`, `executor_image_id` e
  `executor_tar_sha256` exatamente iguais aos pins E3-B versionados.
- `producer_run_id` e tentativa; `attestor_run_id` e tentativa, com
  identificadores inteiros positivos.
- Modo `docker-attested-e3b-sigstore` e autorização explícita
  `V1_ATTESTOR_RUN_ONLY_NO_POST`, sem poderes de publicação.

O publicador recusa arquivos simbólicos, JSON com chaves duplicadas,
campos extras ou ausentes, divergência de digest ou outbox alterada.
Depois da validação local, exige:

1. Pins versionados de SHA e ID de **ambos** os workflows de produção:
   `ATTESTOR_SHA_PIN`, `ATTESTOR_WORKFLOW_ID_PIN`,
   `PRODUCER_SHA_PIN` e `PRODUCER_WORKFLOW_ID_PIN`, todos ainda
   **não configurados**. Sem os quatro valores, rejeita antes da API.
2. GitHub REST LIVE confirmando o run **produtor V1** concluído com
   sucesso na `main`, por `workflow_dispatch`, com workflow, SHA,
   repo ID e tentativa iguais ao recibo e aos pins.
3. GitHub REST LIVE confirmando o run **atestador V1** concluído com
   sucesso na `main`, workflow correto, SHA, tentativa e repo ID.
4. `gh attestation verify` de uma **cópia privada dos mesmos bytes do
   recibo**, exigindo `--signer-workflow` do futuro
   `f7-v1-attestor.yml`, `--source-digest` pinado, `--source-ref
   refs/heads/main` e `--deny-self-hosted-runners`.

**O atestador V1 ainda não está implantado; pins vazios fazem o
publicador falhar fechado por padrão.** Assinatura mockada nos testes
não é prova real de custódia.

## Próxima integração real E3-C5 / E3-D

1. Definir o workflow de **atestador V1 independente** com proteção de
   Environment e origem de evidências da execução realmente ocorrida.
   Não basta simplesmente assinar JSON arbitrário vindo do executor.
2. Verificar no atestador o **run produtor V1**, controles de executor
   e autenticação dos agentes, SHA da missão, log e todos os resultados,
   com vínculo do TAR atestado a **cada tentativa real**.
3. Emitir e atestar `f7-runtime-receipt.json` numa sessão sem acesso
   ao segredo/chave de publicação; revisar o código e pins com PO.
4. Auditar Codex no HEAD exato; executar negativas GH LIVE com recibo
   adulterado, fork/workflow errado, revogação e artefato expirado.
5. Não habilitar `REMOTE_PUBLICATION_ENABLED` e não reservar/taguear
   nem escrever no Project #2 sem Gates 3/4/5 e autorização PO.

**E3-C4 é verificação preparada, não homologação nem execução V1 real.**
