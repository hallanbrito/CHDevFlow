# CH-PIPE-01 — Ponte POC-03 para o CHDevFlow (F1, manual/inativa)

**Issue:** #78 — https://github.com/hallanbrito/CHDevFlow/issues/78  
**Dependências:** #56 (DryRunDispatcher W2-B), #69 (adaptador real com gate), #72 (turnos)  
**Estado:** Draft, somente leitura, sem ativação do runner de agentes.

## Objetivo

Integrar os **dossiês reais de laboratório** da POC-03 (Python → AGY → testes → Codex → CH-1)
à interface canônica `ch`, preservando a separação entre:

- **W2-B:** `DryRunDispatcher` com autorização sintética e fixtures; nunca inicia agentes.
- **CH-PIPE-01/F1:** importação/inspeção read-only de evidências de execução manual externa já concluída.
- **CH-AUTO-01/#69:** execução CLI real **ainda não liberada no produto**; exige gate próprio e prova de custo/ambiente.
- **PO:** validação humana, merges, deploy, agendamento ou transição Project #2.

Esta fatia **não copia** o dispatcher W2-B, não instala daemon, não altera suas políticas,
não declara permissão de execução para um cartão de Kanban e não usa APIs faturáveis.

## Comando

Com o CHDevFlow instalado em editable (`python -m pip install -e .`) ou via
`PYTHONPATH=src`, no mini-PC Windows 11:

~~~powershell
ch pipeline inspect --run-dir "$HOME\Downloads\CHDevFlow-POC03\20261114T182819Z-52dbd9\RECHECK-20261114T183911Z-0b2838"
ch pipeline inspect --run-dir "$HOME\Downloads\CHDevFlow-POC03\20261114T182819Z-52dbd9\RECHECK-20261114T183911Z-0b2838" --json
~~~

No Linux, a mesma interface recebe um caminho `--run-dir` para um diretório
copiado com os artefatos e a execução original como diretório pai.

`0` significa **consistência offline do dossiê para análise CH-1**.
`1` indica bloqueio, arquivos faltantes, hashes divergentes, testes falhos,
veredito não positivo ou ausência da origem AGY reconciliada. Não representa
autorização de uma missão real, CI verde ou homologação de produção.

## Evidências avaliadas

1. `execucao.json`: schema `chdevflow-poc03/v1`, modo real, estado por etapa,
   erros, escopo e veredito.
2. `resposta_agy.md`, `alteracoes.patch`, `auditoria_codex.md`: existência
   e SHA256 comparados com o `RELATORIO_COMPLETO_CH1.md`.
3. `logs_testes.txt`: blocos `testes_agy` e `aceite_independente`, contagem
   e `OK` de execução; os `exit_code` também devem ser zero.
4. Recheck: recuperar o `execucao.json` do **pai do diretório do recheck**,
   nunca seguir cegamente um caminho absoluto contido em dados recebidos.
   Confrontar `recheck_source_run`, `agy=SUCESSO` e `github=SUCESSO`.
5. Falha segura em symlink de artefato, conteúdo acima de 1 MB, JSON inválido,
   saída Codex negativa, hash inconsistente e suíte com falha.

O inspector não abre subprocessos, rede, AGY, Codex ou GitHub. É possível usá-lo
com cópias locais e comparar verificações sem consumir cotas de modelo.

## Limites e pendências reais

- **Integridade não é autenticidade:** SHA256 interno a arquivos fornecidos pelo mesmo
  operador não comprova origem GitHub nem autoria dos agentes.
- O status `SUCESSO` das etapas é declaração do orquestrador, não atestado
  independente. CH-1 deve revisar o diff e o CI separadamente.
- AST é uma análise sintática, **não** isolamento do Windows. A POC-03 anterior
  usou `agy --mode accept-edits`, que não constitui sandbox segura.
- Esta F1 ainda **não executa** AGY/Codex diretamente. A interface declarativa
  para os dois agentes prepara integração futura sem reabrir o gate #69.
- Lock interprocesso, reserva de missão, idempotência de produção, autorização
  autenticada por digest e rollback da execução real permanecem em #69/#53.
- Não utilizar um status de Kanban/label ou este relatório para liberar execução,
  merge, deploy ou agendamento.

## Testes

~~~text
python -m unittest tests/test_ch_pipe_01_manual_lab.py -v
~~~

Teste positivo e cenários negativos: recheck normal, veto do Codex, divergência
de parecer, falha de testes, escopo extra, origem não comprovada, hash adulterado,
artefato ausente, simulação, symlink e **nenhuma chamada de subprocesso**.

## Próxima fatia, após revisão

F2: adaptar o runner manual POC-03 em `#69` com gate autenticado e comprovável,
limites D01–D07, worktree isolada, kill/cancel, monitoramento de processos,
custos e sanitização, idempotência e testes com executáveis *fake* antes de qualquer
teste real. **Precisa de liberação específica do PO para acionar agentes pelo produto**.

**Não fazer merge/ativação a partir desta documentação.**
