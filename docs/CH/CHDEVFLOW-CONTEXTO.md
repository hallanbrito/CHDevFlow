# CHDevFlow — Janela de contexto e protocolo antirretrabalho

**Versão:** 2026-11-16 / `main` de referência `ce939630363f8f762d0f0810a78735fe6975f7ff`.
**Entrada para ChatGPT CH-1, AGY, Codex e futuros agentes especialistas.**
**Visão:** o CHDevFlow é uma fábrica de apps que, gradualmente, deve conseguir ajudar a desenvolver o próprio CHDevFlow. O primeiro resultado procurado é **software útil executado**, não mais infraestrutura para “um dia” executá-lo.

## Ordem obrigatória de leitura (antes de proposta técnica, autorização ou código)

| Ordem | Arquivo | Pergunta respondida |
|---|---|---|
| 1 | [`docs/PROJETO.md`](../PROJETO.md) | Por que existe a fábrica e qual MVP importa? |
| 2 | [`docs/STATUS.md`](../STATUS.md) | O que está mesmo na `main` e o que continua bloqueado? |
| 3 | [`docs/CH/DECISOES.md`](DECISOES.md) | Quais decisões do PO e precedências são vinculantes? |
| 4 | [`docs/CH/CHDEVFLOW-EVIDENCIAS.md`](CHDEVFLOW-EVIDENCIAS.md) | O que já foi testado, com qual tipo de evidência? |
| 5 | [`docs/CH/CHDEVFLOW-MAPA-TESTES.md`](CHDEVFLOW-MAPA-TESTES.md) | Onde estão as suítes já existentes e os workflows? |
| 6 | [`docs/RFC-CH-DEVFLOW.md`](../RFC-CH-DEVFLOW.md) | Papéis, contrato de governança, fonte de verdade e objetivo bootstrap |
| 7 | [`.agents/skills/chdevflow/SKILL.md`](../../.agents/skills/chdevflow/SKILL.md) | Como agir como arquiteto especialista sem reinventar componentes |

Em seguida, ler a **Issue atual e comentários**, a PR e seu HEAD exato, os **arquivos de código que implementam o comportamento**, os testes correspondentes e a documentação da fatia específica. Documentos antigos podem conter status de “proposta” que foi superado por merges posteriores. Não inferir implementação do nome da Issue.

## Mapa da fábrica: reutilizar, nunca reconstruir sem demonstrar lacuna

| Se a demanda envolver... | Procurar primeiro... |
|---|---|
| Invocação de AGY/Codex, identificação local e timeout | `src/chdevflow/core/local_executor.py` |
| AGY devolvendo código em JSON modo plan, AST, testes, Codex | `src/chdevflow/core/experimental_pilot.py` |
| Correção automática controlada, 3 tentativas | `src/chdevflow/core/controlled_cycle.py` |
| Missão Python genérica, manifesto, SHA, allowlist, dossiê | `src/chdevflow/core/generic_cycle.py` e `manual_pipeline_runner.py` |
| Lista, consulta, filtro, layout e CSRF da UI | `apps/control-center/src/ch_control_center/routes/missions.py`, `templates/missions.html`, `security.py` |
| GitHub Projects, DAG e cache | `apps/control-center/` + `apps/bootstrap/sentinela/` |
| Execução mockada, FakeWorker e dry-run | `src/chdevflow/core/dry_run_dispatcher.py` + `apps/bootstrap/sentinela/` |
| Teste de proveniência, gates remotos F7 | `docs/CH/CH-PIPE-01-F7-*.md` e PRs #94/#113–#120 — **não puxar para o MVP local** |

## Decisão de arquitetura: protocolo de oito passos

1. **Intenção do PO:** definir resultado de usuário observável (ex.: “clicar Executar missão em `/missoes` e receber veredito”), não uma “fase” técnica.
2. **Estado real:** confirmar `main`, branch/HEAD, Issue, PRs e se há diferenças entre notebook e GitHub.
3. **Inventário e provas:** consultar tabela anterior, código, testes e links; separar executado LIVE/LOCAL de MOCK/DOC. **Mostrar o que já existe ao PO antes de sugerir novo componente.**
4. **Mínima mudança:** preferir conexão de componentes existentes, um endpoint e uma tela; propor uma única Issue/PR curta. Justificar por que um método existente não basta antes de criar serviço novo.
5. **Responsabilidades:** PO decide; CH-1 desenha/coordena/audita evidências; AGY implementa, testa e devolve diff; Codex revisa de forma independente. CH-1 não deve escrever todo código da feature e depois “homologar” a própria alteração.
6. **Critérios e riscos proporcionais:** um resultado e2e real, permissões mínimas, custo incremental R$0, branch/worktree separada, testes independentes, timeout/cancelamento e logs sanitizados. Não chamar Docker/Sigstore/ambientes protegidos como pré-condição para um piloto local se a decisão não exigir isso.
7. **Execução e evidência:** registrar SHA/branch, AGY real ou fake, testes, Codex real ou fake, RUC, duração, bloqueios e links. Sem resultado real, escrever “não demonstrado”.
8. **Aceite e evolução:** apresentar ao PO para decidir; só após homologação perguntar “o que este ciclo ensinou para automatizar o próximo?”, preservando autonomia humana.

## Anti-padrões a evitar

- **Recomeçar do zero:** construir novo runner quando `local_executor`, `controlled_cycle` e `generic_cycle` já fazem o fluxo.
- **Overengineering:** gastar uma semana em F7/F8, trust policy, pin ou assinaturas antes de ter um botão que chama o motor já implementado.
- **CI como produto:** comemorar 1.000 testes de mocks sem 1 missão real de usuário.
- **Autoria confundida:** AGY implementou ≠ ChatGPT auditou ≠ Codex aprovou ≠ PO homologou.
- **Regras por estilo:** criar mais um relatório/gate/Issue para uma dúvida que requer só executar ou inspecionar código existente.
- **Permissão irrestrita por conveniência:** jamais sugerir `--dangerously-skip-permissions` como solução automática; o erro headless do AGY exige preflight/reuso do modo plan ou permissões específicas.
- **Usar histórico como autorização:** a POC-03 comprovou um fluxo local, mas não habilitou publicação, acesso a segredos ou execução em produção.

## Contexto técnico mais recente (16/11/2026)

- O notebook Linux CachyOS tem `agy` localizado em `/home/hallan/.local/bin/agy` e `codex-cli 0.167.0`. Descoberta **não atesta login, cota ou sandbox**.
- O AGY chamado diretamente em `--mode accept-edits --print --sandbox` bloqueou: ferramenta `command` exigia permissão que o headless não podia solicitar. **Não foi falha do pipeline Python POC-03**.
- O pipeline F5/F6 em `main` chama AGY em `--mode plan --output-format json --print`, materializa o resultado validado, executa testes, audita com Codex; precisa ser consumido pela UI em vez de duplicado.
- O Control Center já expõe `/missoes` apenas como listagem/detalhe. [#121 — CC-DESPACHO-01](https://github.com/hallanbrito/CHDevFlow/issues/121) é prioridade; [#78](https://github.com/hallanbrito/CHDevFlow/issues/78)/[#85](https://github.com/hallanbrito/CHDevFlow/issues/85) guardam histórico técnico.
- F7: PRs #94, #113, #114, #115, #116, #118, #119, #120 continuam Draft. Trabalho valioso em proveniência/assinaturas, porém **não é prioridade para uma missão local**; Gates 1 Solo e 2 aceitos operacionalmente (2/5), Gate 3 não homologado, publicação desativada.

## Saída mínima de qualquer sessão CH-1

Antes de executar alterações relevantes, produzir:

- **Leitura confirmada:** links dos documentos/Issue/arquivos e HEAD vistos.
- **Já existe e funciona:** componentes e evidências com qualificação real vs mock.
- **Lacuna verdadeira:** diferença exata entre comportamento existente e aceite do PO.
- **Próxima menor entrega:** implementador, auditor, um PR, testes/evidência E2E, risco/custo e bloqueios.
- **Operações não autorizadas:** dizer explicitamente caso envolvam agente real, merge, deploy, Project #2, segredo, cron ou F7 POST.

Não alegar acesso ao notebook nem leitura de arquivo que não foi de fato consultado. Se ferramenta não puder ler a fonte, deixar a lacuna explícita. Se houver conflito de políticas, solicitar decisão de PO antes de operações de risco.

**Prompt reutilizável:** [CHDEVFLOW-PROMPT-RETOMADA.md](CHDEVFLOW-PROMPT-RETOMADA.md).
