# F7 E3-C3 — Ciclo F6 com executor Docker atestado (opt-in)

**Estado:** integração em Draft, sem agentes reais nesta rodada, sem publicação. E3-C3 não é produtor V1 e não homologa Gate 3.

## Objetivo realizado

O `generic_cycle.run_generic_cycle` (F6 experimental) pode executar seus testes
Python no **mesmo executor E3-B de TAR assinado** em vez da imagem genérica
`python:3.12-slim`. O modo novo é opt-in:

~~~bash
python -m chdevflow.core.generic_cycle \
  --manifest /caminho/manifesto_missao.json \
  --evidence-dir /caminho/novo-dossie \
  --i-accept-local-risk \
  --attested-executor-tar /caminho/f7-e3b-executor.tar
~~~

**Atenção:** executar o comando acima consumiria AGY/Codex reais se as CLIs
estivessem autenticadas; ele **NÃO foi usado** nas provas E3-C3. O laboratório
usou somente testes offline do ciclo e execução do mesmo Docker em GH Actions
**sem AGY ou Codex**. Uma missão real requer contrato e autorização de
Issue específica (#117), custo/credenciais e ambiente protegido.

## Política de admissão do TAR

`attested_executor.preflight` exige, antes de `_executables()` e AGY:

1. `gh` e Docker instalados, TAR não simbólico nem em ancestral simbólico.
2. SHA-256 **`b7b912afad6422f134501fd997eb13cc1bf70de8aa88de43e0988841a84b0242`**
   do TAR exato do build E3-B #43887485901, atestado Sigstore #68161760.
3. Cópia validada em diretório privado para prevenir substituição de arquivo
   entre SHA/atestação e `docker load`.
4. `gh attestation verify` exige repo `hallanbrito/CHDevFlow`, signer-workflow
   `f7-e3b-executor-attest.yml`, SHA produtor
   `389bcc61342cbcdd3183e291a18eef42ad78f488`, branch fonte e
   `--deny-self-hosted-runners`. Erro GH → fail-closed.
5. Docker Linux, `docker load` do TAR validado, image ID imutável
   `sha256:e0c1bddedb8763803370d0a02b9d05371a30d9c4c82f0fe0b8813bb3b5b9f7ed`,
   usuário `65534:65534` e label de revisão exata.
6. O comando de teste usa **image ID, não tag**, rootfs read-only, mount de
   worktree read-only, `--network=none`, `--cap-drop=ALL`, no-new-privileges,
   limite de memória/CPU/PIDs. A imagem E3-B é um runner real de `unittest`.
7. O retorno é JSON estrito (`CHDEVFLOW-F7-E3B-EXECUTOR/1`). O parser exige
   `TESTS_PASS`/exit 0 ou `TESTS_FAILED`/exit 12 e evidência de testes reais.
   Qualquer saída inesperada/erro de infraestrutura impede aprovação Codex.
   O campo `os_isolation_verified` só é marcado após prova consistente dos
   testes e rechecagem da worktree original.
8. `--isolated-tests` legado e `--attested-executor-tar` são mutuamente
   exclusivos. O modo legado **NÃO comprova proveniência Sigstore**.

## Provas possíveis nesta Draft

O workflow `f7-e3c3-attested-cycle-tests.yml`:

- Roda testes do adapter e do ciclo F6 com CLIs simuladas, sem rede ou tokens.
- Baixa o artifact GitHub E3-B por run/commit pinados, confere SHA256.
- Chama `attested_executor.preflight` com Sigstore GH **real**.
- Executa o contêiner E3-B para testes positivos e negativos independentes,
  verificando saída JSON, exit code e image ID.
- Recusa cópia adulterada do TAR. Não executa AGY/Codex.
- Trabalha numa branch separada, sem alterações em Project #2.

## Riscos que este modo NÃO resolve

- A atestação confirma **a proveniência do TAR executor**, não identifica
  as CLIs AGY/Codex, credenciais, prompts ou modelo de IA efetivamente usados.
- O runner Docker limita a exposição da worktree de testes, mas não representa
  isolamento hermético do agente, e não prova ausência de escape de contêiner.
- A imagem atestada do E3-B foi produzida uma vez; o artifact de transporte
  expira (retenção 7 dias), portanto pins e provas precisam de política de
  renovação do build com auditoria do novo SHA/digest.
- O F7 atual em `po_escalation_provenance.py` ainda exige string de origem
  de testes legada. O novo modo **não é automaticamente elegível para outbox
  V1**: o vínculo firmado entre dossiê da missão, artefato executor, actor
  protegido, run GH e atestador independente continua pendente.
- `REMOTE_PUBLICATION_ENABLED=False`; Gates 3/4/5 não homologados.
- A operação real AGY → testes → Codex precisa de autorização PO separada
  e CLIs autenticadas, sem chamadas pagas implícitas.
- Prova Sigstore não protege um host já comprometido. O modelo Solo segue
  tendo risco de poderes administrativos concentrados.

Referências: [PR #116](https://github.com/hallanbrito/CHDevFlow/pull/116),
[Issue #117](https://github.com/hallanbrito/CHDevFlow/issues/117),
[Issue #95](https://github.com/hallanbrito/CHDevFlow/issues/95).
