# CH-PIPE-01/F7 — Contrato de executor isolado e confiança LIVE da outbox V1

**Estado (16/11/2026): DESIGN DE SEGURANÇA + ADMISSÃO FAIL-CLOSED EM DRAFT. NÃO HOMOLOGADO.**
Gate 1 Solo e Gate 2 aceitos operacionalmente (2/5). Gate 3 bloqueado pela segunda auditoria Codex (3 achados altos, 4 médios, 1 baixo). `REMOTE_PUBLICATION_ENABLED=False`.

## Princípio fundamental

Uma igualdade entre `git HEAD`, blobs Git e bytecode no processo de publicação **não prova um executor imutável**. A identidade deve ser medida e assinada **fora do processo capaz de publicar**. O executor não pode emitir sua própria atestação confiável, escolher sua chave pública ou validar sozinho seu próprio digest.

A cadeia pretendida, **ainda não implementada ponta a ponta**, é:

~~~text
PO aprova SHA do produtor + SHA do publicador + digest da imagem/dependências
    ↓
GitHub Actions main protegida: produtor V1 sem credenciais de publicação
    ├─ checkout no commit exato; dependências e binários por hashes fixos
    ├─ execução isolada F6/AGY + testes Docker + revisão Codex REAL
    ├─ três rejeições reais (sem fabricar isolamento por campos JSON)
    └─ ZIP SHA-256 com outbox e manifesto do executor
    ↓
Job de custódia independente: Environment f7-attestor (sem bypass)
    ├─ baixa o ZIP via GitHub API e confere o digest
    ├─ compara workflow, run, tentativa, repo ID, SHA e branch main
    ├─ compara manifesto de imagem/dependências com pins autorizados
    ├─ assina statement contendo outbox + executor + origem ZIP
    └─ outro job verifica assinatura sem acessar a chave privada
    ↓
Publicador F7 em commit auditado, sem segredo de assinatura
    ├─ busca política LIVE e confere origem do produtor via GitHub API
    ├─ verifica assinatura, executor, artifact e ZIP do run real
    ├─ confere autorização individual PO e SHA exato do publicador
    └─ POST continua proibido até Gates 3, 4 e 5 e nova autorização PO
~~~

## O que o código Draft já faz

1. **Política remota:** `po_escalation_publication._f7_remote_trust_policy` consulta pela API GH autenticada e host `github.com` o repo ID oficial `1424359000` e as repo Actions Variables:
   `CH_F7_TRUSTED_RUNNER_PUBKEY`, `CH_F7_TRUSTED_RUNNER_SHA`,
   `CH_F7_REVOKED_RUNNER_FINGERPRINTS`, `CH_F7_PRODUCER_WORKFLOW_ID` e
   `CH_F7_V1_PRODUCER_WORKFLOW_ID`. Ausência, SHA incorreto, revogação
   ou valores inválidos bloqueiam. **Variáveis locais `CH_F7_TRUSTED_*`
   não fornecem mais a âncora da verificação do publicador.**
   A variável `CH_F7_V1_PRODUCER_WORKFLOW_ID` ainda não está provisionada;
   somente o PO pode cadastrá-la após validar o workflow V1.
   **Pins versionados, vazios por design:** `F7_TRUST_KEY_FINGERPRINT_PIN`,
   `F7_TRUSTED_PRODUCER_SHA_PIN` e `F7_TRUSTED_V1_WORKFLOW_ID_PIN` no
   publicador. A comparação GH LIVE só autorizará a política se chave,
   SHA e workflow também coincidirem com esses valores auditados. O PO
   precisará fornecer os três dados reais após o produtor V1 existir,
   aprovar o commit que os fixa e reauditar o HEAD. Não editar a variável
   sem revisão nem preencher os pins com valores fictícios.
2. **Origem LIVE:** `po_escalation_origin.verify_v1_producer_origin` só admite
   `github-actions:v1:<run_id>:<attempt>:<artifact_id>:sha256:<digest>`
   e consulta GH LIVE para verificar repo ID, workflow V1, branch `main`,
   SHA confiável, status `completed/success`, tentativa, artifact não expirado,
   metadados do artefato, download real de ZIP e SHA-256 dos bytes.
   Repete a consulta do run após obter o ZIP. Rejeita as origens
   `github-actions:probe:*`, `github-actions:custody:*` e origens locais.
3. **Assinatura:** continua usando `ssh-keygen -Y verify`, com chave pública
   obtida da política GH. Assinatura sem vínculo GH V1 não passa. Esse é
   um **contrato de admissibilidade**, não prova de que já exista produtor V1.
4. **Identidade em processo:** `po_escalation_runtime` continua verificando
   arquivos, blobs e código Python carregado como defesa adicional.

## Garantias que ainda NÃO existem

- O workflow `.github/workflows/f7-v1-producer.yml` **não existe nem executou**
  nesta entrega. Nenhuma outbox V1 real pode passar esta admissão.
- Repo Variables são mais confiáveis que ambiente local, mas **não são imutáveis
  contra administrador único**. Os três pins compilados exigem revisão do SHA
  para troca de chave, produtor ou workflow, mas **não eliminam o risco de
  comprometimento da conta administrativa nem atestam o host consumidor**.
  Avaliar também prova de atestação independente de ambiente/repositório.
- Metadados e ZIP não demonstram automaticamente o que aconteceu no runner.
  Manifesto e assinatura independente precisam comprovar testes/execução reais.
- A sonda Gate 1 não atesta missão V1 real. Nenhum run ou recibo de sonda pode
  ser promovido a prova de produção.
- O próprio `gh`, `git`, `ssh-keygen`, Python e credenciais GitHub no host
  consumidor ainda não têm raiz externa de confiança.
- Nenhum isolamento/imutabilidade completo foi demonstrado por Docker, OCI
  ou executor remoto nesta PR. CI das funções de admissão não substitui a
  prova de runner real.

## Contrato do artefato executor, a implementar

O produtor V1 deve construir/usar imagem OCI **referenciada exclusivamente por
digest `sha256:<64 hex>`**, com base e dependências fixadas e verificadas
(sem `latest`, `pip install` sem hash ou download sem digest). Manifesto mínimo:

- Repo ID, commit do produtor, tree SHA e SHA do publicador auditado.
- Workflow ID, run ID, tentativa e IDs GitHub de imagem/artefato.
- Digest OCI, OS/arquitetura, versão e digest de Python, Git, GH e OpenSSH.
- Hash do lock de dependências e lista fechada de módulos carregados.
- Digest canônico da missão, baseline e provas de cada tentativa real.
- Digest ZIP e identidade do job atestador protegido.

A assinatura do Environment deve cobrir **todos esses campos**, não apenas
código gerado e outbox. O publicador não pode reescrever o manifesto confiável.
Terceiro job, sem chave privada, deve validar assinatura e origem LIVE.

## Plano de homologação incremental

**E3-A — Política de confiança e origem (Draft agora):**
CI Windows/Linux de negativas: variável ausente, chave revogada, repo errado,
workflow de sonda, SHA/tentativa/artefato divergentes e ZIP adulterado. Sem POST.

**E3-B — Manifesto e ambiente isolado (pendente):**
criar produtor V1 sem segredo de publicação, construir pacote/imagem por digest
e lock reproduzível, verificar binários e dependências em job independente,
provar rejeição de alterações de código/manifesto. Nenhum segredo F7 no produtor.

**E3-C — Piloto protegido, depende de aceite PO:**
executar missão pequena real em runner protegido com AGY/Codex reais, três
tentativas e evidências. Atestador independente verifica artefato/manifesto
e faz assinatura. Testar negativa de run de outra branch e ZIP alterado.

**E3-D — Auditoria e aceite:** CI verde no HEAD exato, auditoria Codex
independente no mesmo SHA, verificação LIVE de política, runner e logs.
PO decide explicitamente; se HEAD mudar, repetir. Gates 4/5 são independentes.

## Governança e proibições

- **Solo:** risco residual de administrador único permanece explícito.
- **Multioperador:** ideal pelo menos duas pessoas distintas validando
  mudanças e aprovações sensíveis.
- Sem autorização, não criar segredos, não alterar repo Variables, não executar
  missão real, não escrever no Project #2, não reservar tags, não fazer merge,
  deploy, release ou POST. Publicação fica **desativada**.

Este documento especifica **critérios de futuro aceite**, não concede aceite.
