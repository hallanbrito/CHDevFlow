# CH-PIPE-01 / F5 — Piloto local opt-in AGY → testes → Codex

**F5 é experimental** e depende de F4/#82 → F3/#81 → F2/#80 → F1/#79. Este comando não integra o dispatcher de produção. Só testa o fluxo com uma tarefa fixa e pastas locais descartáveis.

## O que faz, de verdade

- Cria uma pasta NOVA com missão fixa de estoque Python, src e testes de aceite independentes.
- Com opt-in explícito, chama AGY em modo `plan` com `--sandbox` e lê a resposta do envelope JSON do modo headless. O CHDevFlow pode materializar apenas o módulo solicitado.
- Confere que só src/estoque.py foi produzido; não deixa passar mudanças nos testes de aceite, arquivos extras, symlink, código malformado.
- Executa os 9 testes de aceite Python escritos pelo CHDevFlow, **no Windows hospedeiro**, não em sandbox do SO.
- Se os testes passarem, envia o diff e os resultados ao Codex em modo somente leitura. O pipeline exige que a primeira linha da última mensagem de um turno concluído contenha o veredito.
- Salva dossiê em pasta separada da tarefa: execucao.json, resposta_agy.md, logs_testes.txt, alteracoes.patch, codex_processo.log, auditoria_codex.md, RELATORIO_COMPLETO_CH1.md. Em falhas, o dossiê guarda os logs das etapas alcançadas e marca as demais como `NAO_EXECUTADO`.
- Não envia GitHub PR, não dá push/merge, não toca no Project #2, não agendará nada. O comando oficial ch pipeline run permanece bloqueado.

## Riscos expressamente aceitos pelo operador para esta tarefa experimental

A conta ChatGPT está autenticada no Codex; o AGY existe na máquina. **Nenhum provedor foi auditado quanto a custo/cotas, e a existência da opção --sandbox do AGY não prova isolamento de SO.** Programas gerados por agentes têm risco de acessar arquivos externos, rede ou executar código. Mesmo com timeout, não se garante encerramento de todos os descendentes em todas as situações. Não executar no host de produção nem com segredos sensíveis.

## Windows PowerShell

Execute a partir da cópia de trabalho da correção, com o Python e a resolução de módulos apontando para essa cópia.

~~~powershell
cd "$HOME\Downloads\CHDevFlow-F2-Teste"
gh pr checkout 83
$env:PYTHONPATH = "$PWD\src;$PWD\apps\bootstrap\sentinela\src"
python -m unittest discover -s tests -p "test_ch_pipe_01_f5_lab_pilot.py" -v
~~~

Somente se os testes passarem e você quiser acionar as CLIs reais nessa tarefa simples:

~~~powershell
$id = Get-Date -Format "yyyyMMdd-HHmmss"
$lab = "$HOME\Downloads\CH-Lab-$id"
$dossie = "$HOME\Downloads\CH-Dossie-$id"

python -m chdevflow pipeline lab-pilot --workspace $lab --evidence-dir $dossie --timeout 480 --i-accept-local-risk

Get-Content "$dossie\RELATORIO_COMPLETO_CH1.md"
~~~

Essas duas pastas NÃO podem existir nem ser aninhadas; para repetir use novo id. Não forneça a pasta do próprio repositório como workspace. O comando imprime o resumo em JSON. Se falhar, envia detalhes ao dossiê e mantém as fontes para auditoria.

**Resultado positivo:** LAB_APROVADO_AGUARDANDO_CH1 (somente laboratório, não produção).

**Resultado negativo:** LAB_BLOQUEADO, ou erro prévio se faltou o aceite, executável, ou caminho novo.

**Custo R$0 e isolamento real:** não foram verificados. Esse comando não deve ser ativado em cron/CI. O modo oficial permanece BLOQUEADO_ATIVACAO.

## Testes de F5

~~~powershell
python -m unittest discover -s tests -p "test_ch_pipe_01_f5_lab_pilot.py" -v
~~~

Esses testes usam mocks de subprocessos: nunca fazem chamadas reais de modelos.

## Diagnóstico sem gastar novas chamadas de IA — falhas 18:06:31 e 18:06:53

Para inspecionar a tentativa anterior pelo inventário local, use os diretórios já criados:

~~~powershell
ch pipeline lab-diagnose --workspace "$HOME\Downloads\CH-Lab-20261114-180631" --evidence-dir "$HOME\Downloads\CH-Dossie-20261114-180631" --json
ch pipeline lab-diagnose --workspace "$HOME\Downloads\CH-Lab-20261114-180653" --evidence-dir "$HOME\Downloads\CH-Dossie-20261114-180653" --json
~~~

O comando só lista nomes de arquivos esperados/presentes/ausentes/extras, além da presença e tamanho do log AGY. **Não inicia subprocessos nem lê o conteúdo da resposta de IA.**

Consulte localmente o log real de AGY, somente se necessário:

~~~powershell
Get-Content "$HOME\Downloads\CH-Dossie-20261114-180653\resposta_agy.md" -Tail 35
~~~

**Oculte tokens e dados privados antes de compartilhar.** Código de saída zero do AGY não prova que o arquivo de implementação foi gravado. Se src/estoque.py estiver ausente, investigue o output real da CLI antes de alterar suas opções.

O piloto agora informa ausentes=[...] e extras=[...] e corrige estados de falha, sem afrouxar as regras de escopo. Testes dessa melhoria utilizam apenas fixtures; não houve novo piloto real.

## Diagnóstico por etapa

- `resposta_agy.md` contém código de saída, indicador de timeout, envelope JSON do AGY e diagnósticos sanitizados. O adaptador exige `status=SUCCESS` e extrai apenas a resposta desse envelope. Ele cria `src/estoque.py` após conferir os arquivos independentes e validar o subconjunto Python da missão.
- `AGY_TEXT_ADAPTER: PASS` indica que o CHDevFlow escreveu o código devolvido pelo AGY no laboratório.
- `codex_processo.log` contém os eventos do subprocesso e os diagnósticos. `auditoria_codex.md` contém o parecer final quando houve turno concluído. Mensagens intermediárias e processos interrompidos não aprovam a missão.
- `authentication failed or timed out` com zero turnos indica que esta execução ficou sem acesso à sessão do Antigravity. O laboratório reutiliza credenciais da sessão local e registra a falha antes de executar Python ou Codex.
