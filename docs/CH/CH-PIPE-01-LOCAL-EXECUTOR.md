# CHDevFlow — executor local multiplataforma

Decisão do PO na Issue #78: **não exigir Docker, WSL ou VM** para o piloto local. A execução deve usar **o próprio usuário do sistema operacional**, no Windows 11 ou Linux, com AGY e Codex já autenticados. O operador pode optar por isolamento reforçado separadamente.

## Instalação de desenvolvimento

O pacote `chdevflow` deve estar instalado no Python usado pelo terminal (normalmente com `python -m pip install -e .`, feito uma única vez no clone). O comando do executor não inicia serviços, agentes remotos ou temporizadores.

## Fluxo de uso — Windows 11 PowerShell ou Linux

Diagnóstico somente leitura (não acessa tokens nem executa agentes):

```shell
python -m chdevflow.core.local_executor doctor
```

Uma missão de laboratório real, voluntária e descartável, com duas CLIs existentes:

```shell
python -m chdevflow.core.local_executor run --i-accept-local-risk
```

O comando cria um diretório de laboratório e outro de evidências em `~/CHDevFlow-Labs`, com ID novo por execução; imprime caminho do dossiê. Para escolher uma pasta, passe `--root CAMINHO`. Timeout padrão 480 segundos (`--timeout 120..900`). Nenhum comando de `git push`, merge, cron, Project #2 ou deploy é executado por esta entrada.

**Saída `LAB_APROVADO_AGUARDANDO_CH1` exige AGY real, nove testes independentes Python e revisão real Codex.** Quando o AGY falhar no acesso às credenciais do Windows ou Linux, a execução bloqueia, guarda log e não chama o Codex. Não copie tokens de uma conta para outra ou para o Work. Reabra o terminal na sessão do mesmo usuário que autenticou ambas as CLIs.

## Limitações e responsabilidades

- O diagnóstico de CLIs não comprova que o login headless funcione nem que créditos sejam gratuitos.
- As CLIs são iniciadas pelo subprocesso filho da **sessão local corrente**; não utilize Windows Service, `runas`, tarefas agendadas em outra conta, SSH com outro usuário ou o ambiente Work para acessar o cofre de credenciais do computador.
- Worktree e diretório descartável são isolamento lógico, **não sandbox do sistema operacional**. Código gerado pelo agente é executado pelo Python hospedeiro após validações. A instalação e o isolamento reforçado são opções/responsabilidade de quem executar o repositório.
- Windows e Linux usam resolução própria dos binários no PATH, com herança do ambiente da conta; não expõem o conteúdo de arquivos de login.
- O comando oficial de produção `ch pipeline run` permanece bloqueado. Este recurso não ativa agendamento ou execução autônoma.

## Arquivos

`src/chdevflow/core/local_executor.py` oferece CLI nativa; `experimental_pilot.py` mantém pipeline real e dossiê; `tests/test_ch_local_executor.py` valida a entrada sem chamar modelos. A suíte F5 conserva teste de subprocessos reais com CLIs falsas e nove aceites independentes.

Uma execução ponta a ponta com **AGY/Codex reais** só estará demonstrada com dossiê gerado por terminal local autenticado; CI com dublês não substitui essa evidência.