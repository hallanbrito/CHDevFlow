# CH-PIPE-01 / F2 — Planejamento manual e adaptadores CLI inativos

**Issue:** #78 — https://github.com/hallanbrito/CHDevFlow/issues/78  
**Dependência:** F1 na Draft PR #79. A F2 usa branch empilhada enquanto #79 não for integrada.
**Contrato vinculante:** Issue #69 (CH-AUTO-01), D01–D07 e W2-B #56.

## O que funciona nesta fatia

- `ch pipeline plan --mission caminho/mission.json [--json]`: lê um manifesto
  local, consulta **somente** `git rev-parse HEAD` e devolve digest de missão,
  etapas e bloqueios, sem iniciar AGY/Codex. Com todos os requisitos estáticos
  válidos, o status é `PLANEJADO_AGUARDANDO_GATE`, **não autorização**.
- `ch pipeline run --mission caminho/mission.json`: **falha intencionalmente**
  com `BLOQUEADO_ATIVACAO` e código de saída 2. Nenhuma CLI AGY/Codex é iniciada.
- `ProcessAdapter.command("agy"|"codex")`: catálogo exato de CLIs para
  Windows e Linux, com o Codex em `read-only`. O método interno
  `_invoke_inactive` modela captura de exit_code/stderr, sanitização e timeout,
  **não está conectado à CLI** e só deve ser ativado após gate específico #69.
- `SimulatedPipeline.run_fixture`: encadeamento **100% offline**, a partir de
  respostas pré-gravadas (não aceita funções executoras), com estado de falha
  segura, veto Codex, falha de testes e idempotência in-memory. Não gera
  autorização falsa nem registra trabalhos reais.
- F1 `ch pipeline inspect --run-dir ...` permanece preservada; W2-B
  `DryRunDispatcher` não foi alterado.

## Exemplo de manifesto

Crie uma worktree **isolada e limpa**, com branch que não seja `main`, e
um arquivo `missions/mission.md` contendo a missão aprovada. Exemplo JSON
ilustrativo (troque SHA e caminho, não use este texto como autorização):

~~~json
{
  "schema": "chdevflow.pipeline.manual/v1",
  "mission_id": "LAB-F2-001",
  "repository": "hallanbrito/CHDevFlow",
  "issue": 78,
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "worktree": "C:/Users/USUARIO/CHDevFlow-lab",
  "allowed_paths": ["src/lab_f2.py", "tests/test_lab_f2.py"],
  "prompt_ref": "missions/mission.md",
  "timeout_seconds": 900
}
~~~

No Windows 11 PowerShell:

~~~powershell
ch pipeline plan --mission .\mission.json --json
ch pipeline run --mission .\mission.json
# BLOQUEADO_ATIVACAO — isso é esperado na F2
~~~

No Linux:

~~~bash
ch pipeline plan --mission ./mission.json --json
~~~

## Segurança e validações

- Fail-closed para manifesto/schemas/campos inesperados, SHA de 40 hex,
  timeout superior a 900 s, path traversal, glob, symlink, prompt não encontrado,
  worktree ausente, escopo vazio e baseline divergente.
- O planejamento **não** valida identidade PO, decisão autenticada do GitHub,
  licença/custo incremental R$0, ambiente de execução, lock entre processos,
  git status limpo, branch protegida ou idempotência entre máquinas. Sem esses
  gates **não pode iniciar agente real**.
- O pipeline de fixtures opera com apenas uma tarefa por instância; idempotência
  em memória não resolve concorrência multiprocesso.
- Não exibir segredos em logs; sanitização do adaptador é uma proteção parcial,
  não substitui isolamento de processos nem revisão de prompts.
- Não ativar Sidecar, agendamento Python, cron, Actions de despacho, merges,
  deploys ou alterações no Project #2.

## Testes CI

`python -m unittest discover -s tests -p "test_ch_pipe_01_f2_manual_runner.py" -v`

Matriz F2: contrato válido, missing fields, timeout, baseline, traversal,
symlink, saída negativa Codex, falha testes, replay, inclusão de callback
malicioso como dado, zero subprocessos reais em fixtures e bloqueio explícito
do comando `run`.

## F3 — Gate para execução real em missão específica

Para conectar `ch pipeline run` aos adaptadores reais, será necessária uma
prova externa **verificável** de autorização do PO (comentário autenticado
vinculado ao digest, SHA e Issue), custo/licença comprovados, ambiente/sandbox,
lock interprocesso/timeout/cancelamento e prevenção de novas execuções após
falhas. Só então implementar e testar `run` com executáveis fake e liberar
um piloto real de escopo controlado. A existência da F2 **não** substitui
esse novo gate nem demonstra custo R$0.

**RUC resumido:** F2 = código/contrato/manual/fixtures; execução real = NÃO
REALIZADA; custos dos modelos = NÃO VERIFICADOS (nenhuma CLI de modelo foi
chamada por este incremento); merge/deploy/timers = NÃO REALIZADOS.
