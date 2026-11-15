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
## Entrada integrada à CLI CHDevFlow

Além do módulo Python, a CLI `ch` oferece os comandos de execução local:

```shell
ch pipeline local-doctor
ch pipeline local-once --i-accept-local-risk
```

Para decidir onde guardar as pastas e mudar o timeout: `ch pipeline local-once --root CAMINHO --timeout 480 --i-accept-local-risk`.

O comando usa o pipeline F5 existente, sem nova autenticação e sem transferir a execução para o Work. Cada disparo opt-in executa uma única missão e retorna código 0 apenas com parecer `LAB_APROVADO_AGUARDANDO_CH1`. Incerteza de credencial do AGY é registrada como bloqueio com dossiê.

## Ciclo CCC-01 de correcao controlada (experimental)

Com AGY e Codex autenticados no **mesmo usuario** do Windows ou Linux:

```powershell
ch pipeline local-doctor
ch pipeline local-cycle --timeout 480 --i-accept-local-risk
```

O `local-cycle` é a nova entrada com **até 3 chamadas do AGY e 2 devoluções**, enquanto `local-once` e `lab-pilot` preservam a semântica anterior de apenas uma tentativa. O ciclo utiliza aceites independentes mais rigorosos (10 testes, incluindo objeto que simula string por `__eq__`). Se os testes falharem, não chama Codex naquela tentativa; devolve relatório ao AGY quando houver tentativas restantes. Após veto explícito do Codex, devolve o parecer ao AGY. Aprovou, encerrou sem rodadas extras.

O `--timeout` é **compartilhado pelo ciclo inteiro**, não multiplicado por tentativa. Cada execução cria pastas novas e dossiê `RELATORIO_COMPLETO_CH1.md`, estado `execucao.json` e subpastas `attempt-01` a `attempt-03`. Se houver três reprovações, grava também `escalonamento_po.json` para supervisão **local**. Não há cartão automático no GitHub Project #2 sem autorização de escrita.

A CI utiliza agentes simulados; **sem prova de integração real até executar a CLI autenticada no host**. Não há medição de custo/tokens nem isolamento completo do sistema. Sessões existentes são herdadas do terminal, sem copiar tokens. Após crash, o mesmo diretório não é reiniciado automaticamente, evitando duplicação de chamadas.
