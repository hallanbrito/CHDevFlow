# ADR — FACTORY-001 B1: prova Docker do Copilot CLI

- **Data:** 2026-11-27
- **Estado:** aprovado com ressalvas para prova técnica; não libera runtime de produção.
- **Baseline:** `factory/v2`, `c07218498cd1d95b494aa94a9fe691a60f984b59`.

## Decisão

Usar a imagem oficial `ghcr.io/github/copilot-cli` na versão `1.0.117`, fixada pelos digests imutáveis para `linux/amd64` e `linux/arm64`. Sobrescrever o entrypoint documentado da imagem para executar `copilot --version` e `copilot --help`. Não autenticar, não chamar modelo e não montar credenciais.

Esta fatia demonstra somente o CLI e a fronteira do container. Não integra interface, runtime de produção, login, permissões de agente, egress para serviço Copilot ou cobrança. A documentação oficial posiciona a imagem primariamente como servidor para Copilot SDK; a invocação direta da CLI por entrypoint é uma prova específica desta fatia, não uma declaração de suporte de produção.

## Controles da prova

- Container efêmero por comando, daemon Docker Linux local e imagem oficial fixada por digest.
- UID/GID `10001:10001`; `--cap-drop=ALL`; seccomp padrão do daemon; `no-new-privileges`; rootfs somente leitura; rede `none`; limites de 1 CPU, 1 GiB e 64 PIDs; tmpfs `/tmp` limitado a 512 MiB, `nosuid,nodev,noexec`.
- Única montagem: workspace efêmero dedicado, somente leitura. Sem montagem de HOME, credenciais ou socket Docker. `COPILOT_HOME` aponta para temporário interno ao container.
- Cliente Docker usa diretório de configuração temporário e remove variáveis de credenciais conhecidas. Nenhum valor real é lido ou registrado.
- Timeout/cancelamento param o container, removem-no e verificam que não restou container com aquele ID. Qualquer falha de daemon, configuração ou cleanup termina como bloqueio, sem execução no host.

Docker compartilha o kernel com o host; esta prova reduz acesso, não demonstra isolamento absoluto. O daemon local desta auditoria não estava ativo, e ferramentas/endpoint rootless não estavam disponíveis. O job de CI reproduz a prova em runner Linux Docker; esse runner usa daemon gerenciado pelo CI e não certifica o ambiente local/rootless do PO.

## Critérios de aceite verificáveis

- Pré-verificação exige daemon Linux acessível, seccomp ativo e a imagem local correspondente ao digest fixado; daemon ausente resulta em `BLOQUEADO`, exit code 2.
- `docker inspect` confirma o digest, UID/GID não-root, remoção de capabilities, seccomp padrão, `no-new-privileges`, rootfs somente leitura, rede `none`, limites de CPU/memória/PIDs, bind exclusivo do workspace em `Mounts` e tmpfs exclusivo em `/tmp` via `HostConfig.Tmpfs`.
- `copilot --version` retorna `1.0.117` e `copilot --help` retorna uso dentro do container.
- Provas negativas confirmam canário externo inacessível, credenciais fictícias não encaminhadas, ausência de socket Docker, processo sem privilégios de escrita e conexão externa bloqueada.
- Timeout e cancelamento encerram e removem seus containers; o teste verifica que não restaram IDs.
- A prova reporta `status=PASS`, `credentials_used=false` e `model_calls=0`. O job de CI deve ficar verde para existir evidência real; testes unitários locais, isoladamente, não aprovam a fatia.

## Reprodução

Requisitos: Docker Engine Linux disponível; não requer Docker Compose, login Copilot ou dependências Python externas.

```bash
python3 scripts/factory_001_docker_sandbox.py pull
CH_FACTORY001_DOCKER_INTEGRATION=1 \
  python3 -m unittest discover -s tests -p 'test_factory_001_docker_sandbox.py' -v
```

O comando `pull` baixa apenas a imagem pública identificada pelo digest da arquitetura. A prova real imprime uma linha `FACTORY001_DOCKER_EVIDENCE` com versão, digest, controles e resultado de cleanup; não imprime transcript ou credencial. Se Docker/controles/imagem estiverem indisponíveis, o processo retorna falha e `BLOQUEADO`.

O job `factory-001-docker-sandbox.yml` executa os mesmos testes unitários e de integração em PR para `factory/v2`, com `contents: read`, sem secrets declarados; o checkout não persiste credenciais, e nenhum token é mapeado para os passos do sandbox.

## Evidência e limites

Evidência real requer conclusão verde do job dedicado. Verificação local: Docker CLI `29.10.1` e Compose `5.8.0` existem, mas `docker version` não alcança o daemon em `/var/run/docker.sock`; não foram encontrados `dockerd-rootless.sh`, `docker-rootless-setuptool.sh`, `rootlesskit` ou sockets rootless nos caminhos verificados. Portanto, esta estação não pode produzir evidência local de container. O primeiro ensaio de `--version` mostrou `ENOSPC` ao extrair o runtime no tmpfs de 128 MiB. O pacote Linux x64 oficial publicado para `1.0.117` tem 165,249,950 bytes comprimidos; os limites foram ajustados para 1 GiB de memória e tmpfs até 512 MiB, ainda finitos e inspecionados. A imagem pública `1.0.117` foi inspecionada em 27/11/2026; o índice publicado foi `sha256:b0c9fef096b841c0ed1ad121b8d389b09eaf1f7995b40b0383668f523cc09146`, com manifests por arquitetura fixados abaixo:

- `linux/amd64`: `sha256:6a816154086e00511cdc87563def1bb529dffef966288b0ce26677af7eb3ff1c`
- `linux/arm64`: `sha256:dcb3397e37c80f0a7edccd72d8af1ac78bf6086c37d1fe2772f1e5cbaebdb8e4`

Permanecem fora da prova: rootless local, contenção de egress para chamadas reais, autenticação oficial em container, limites/consumo de créditos, resistência a escape de kernel e avaliação independente da imagem/runtime.

## Fontes oficiais consultadas

- [GitHub Copilot CLI](https://docs.github.com/en/copilot/concepts/copilot-surfaces/copilot-cli)
- [Imagem oficial `ghcr.io/github/copilot-cli`](https://github.com/github/copilot-cli/pkgs/container/copilot-cli)
- [Guia oficial da imagem container](https://github.com/github/copilot-cli/blob/main/container/README.md) documenta a substituição do entrypoint para executar `copilot --version`.
