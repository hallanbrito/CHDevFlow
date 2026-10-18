# W2-A / 02 — Contratos de missão, autorização e evidências (proposta)

**Estado:** desenho CH-1, não há parser, executor, serviço ou credencial criada.  
**Referências:** [arquitetura](01-ARQUITETURA.md), [Issue W2-A #8](https://github.com/hallanbrito/CHDevFlow/issues/8), [decisões PO #7](https://github.com/hallanbrito/CHDevFlow/issues/7).

## 1. Princípios de validade

A **Issue** é unidade de trabalho e rastreamento. A **aprovação humana autenticada** é um evento próprio, vinculado a uma revisão imutável da missão. Campos do GitHub Project são indicadores de fluxo, **não credenciais/autorização**. A etiqueta ch:workflow somente insere cartão no Project; etiquetas de prontidão não concedem CH-2.

Uma edição posterior de escopo, caminhos, prompts, modelo, repositório, commit de base ou teto da missão **invalida a aprovação anterior**. O dispatcher futuro deve falhar fechado se não puder comprovar hash da versão autorizada e identificar o autor humano permitido.

## 2. Contrato de missão — proposta schema version 0.1

Exemplo ilustrativo **NÃO EXECUTÁVEL**. Todos os valores são placeholders, não dados verificados do HallanCraft.

~~~json
{
  "schema_version": "w2a-mission/v0.1",
  "issue": "owner/CHDevFlow#EXEMPLO",
  "target_repository": "hallanbrito/HallanCraft",
  "target_branch": "main",
  "baseline_sha": "<SHA_COMPLETO_VALIDADO_NO_FUTURO>",
  "executor": "agy-antigravity",
  "autonomy": "CH-2",
  "goal": "Tarefa documental ficticia para testar o contrato",
  "prompt_ref": "prompts/W-XX/MISSAO.md@<SHA>",
  "scope": {
    "allowed_paths": ["docs/exemplo-autorizado.md"],
    "blocked_paths": ["**/worlds/**", "**/saves/**", "**/.env*", "**/secrets/**"],
    "external_network": false,
    "install_dependencies": false,
    "deploy": false,
    "merge": false,
    "write_default_branch": false
  },
  "dependencies": [],
  "limits": {
    "max_active_runs": 1,
    "per_attempt_seconds": 900,
    "max_additional_attempts": 1,
    "retry_requires_diagnosis": true,
    "manual_cancel": true,
    "additional_cost_brl": 0
  },
  "decision_revision_digest": "<HASH_DA_MISSAO_CANONICA>",
  "approval_event_id": "<REFERENCIA_GITHUB_A_PROVAR>",
  "approved_by": "<IDENTIDADE_GITHUB_DO_PO_VERIFICADA>",
  "status": "DRAFT_NOT_AUTHORIZED_TO_RUN"
}
~~~

**Regras semânticas:** proibir curingas amplos de caminhos; validar caminhos reais e symlinks; bloquear qualquer arquivo fora de allowed_paths, mesmo se omitido do blocked_paths. A lista de bloqueios é **defesa em profundidade**, não mecanismo exclusivo. Não confiar em caminhos fornecidos por saída do agente. O SHA precisa estar fixado antes da autorização executiva; o exemplo não fornece um SHA real.

Os campos approved_by e approval_event_id só são válidos quando recuperados e verificados do GitHub por identidade controlada; não aceitar valores autoafirmados em YAML, JSON, comentários, PR ou prompt. A autenticação local do host não é autorização do PO para executar.

## 3. Contrato de autorização separada

~~~text
approval_type: CH2_RUN_APPROVAL
issue_ref: repositório e número
mission_digest: hash de todos os parâmetros executáveis da missão
baseline_sha: commit completo da origem autorizada
authorized_executor: agy-antigravity
authorized_repo_and_scope: allowlist explícita
budget: custo adicional zero, 1 run, 15min/tentativa, até 1 retry pós-diagnóstico
approved_by: identidade GitHub do PO, confirmada pela API
approved_at: instante UTC auditável
expires_at: prazo a definir em Fatia W futura
event_id: ID imutável/verificável do evento de aprovação
~~~

**Aceite no chat ou marca visual no Project não equivale automaticamente à autorização de execução.** O futuro mecanismo de aprovação deve exigir prova de identidade humana e do payload aprovado, incluindo risco de edições/replays. Disparar manualmente uma prévia não autoriza execução; confirmação humana separada é necessária. Nunca permitir autoaprovação por AGY/Codex/dispatcher.

## 4. Contrato da execução (run) e evidências

~~~json
{
  "schema_version": "w2a-run/v0.1",
  "run_id": "<ID_UNICO>",
  "mission_digest": "<HASH_AUTORIZADO>",
  "issue": "owner/CHDevFlow#EXEMPLO",
  "executor": "agy-antigravity",
  "adapter_version": "<VERSAO_VERIFICADA>",
  "host": "cachyos-notebook",
  "baseline_sha": "<SHA>",
  "worktree_path_redacted": "<CAMINHO_SANITIZADO>",
  "branch": "agy/wXX-exemplo",
  "started_at_utc": "<TIMESTAMP>",
  "ended_at_utc": "<TIMESTAMP>",
  "attempt": 1,
  "duration_seconds": 0,
  "budget_status": "VERIFIED_ZERO_ADDITIONAL_COST",
  "cost_brl_reported": 0,
  "result": "STOPPED_BEFORE_EXECUTION",
  "diagnosis_ref": null,
  "modified_files": [],
  "commits": [],
  "draft_pr": null,
  "test_evidence": [],
  "redactions_checked": false
}
~~~

Antes de publicar evidências, remover tokens, credenciais, nomes sensíveis e caminhos privados. Identificar separadamente (a) identidade da conta GitHub que publicou; (b) executor declarado; (c) run_id; (d) SHA e PR; (e) verificador. **Autor do commit não comprova sozinho executor real**. A relação deve ser auditável no relatório e na Issue/PR; identidade confiável demanda controle de acesso e logs.

## 5. Máquina de estados — separação obrigatória

**Etapa CH (negócio, GitHub Projects):** BACKLOG → PRONTA → EM_EXECUCAO → EM_REVISAO → AGUARDANDO_PO → decisão do PO → INTEGRADA → HOMOLOGADA; admite CORRECOES, PARCIAL e REPROVADA segundo RFC. Esse campo não é o estado de um processo.

**Estado da execução local (proposta):**

~~~text
UNAUTHORIZED -> ELIGIBLE -> PREFLIGHT_OK -> CLAIMED -> RUNNING
     |              |             |            |          |
   BLOCKED <--------+-------------+------------+----------+
                                                         |
                                               EVIDENCE_PENDING
                                                         |
                                               DRAFT_PR_READY
                                                         |
                                               AWAITING_PO
~~~

- UNAUTHORIZED: falta autorização CH-2 específica e verificável; jamais iniciar processo.
- ELIGIBLE: parâmetros elegíveis; antes de executar verificar política/custo/ambiente.
- PREFLIGHT_OK: passou nas verificações, mas ainda requer confirmação manual de executar.
- CLAIMED: reserva única de tarefa/worker; concorrência diferente de 1 é proibida.
- RUNNING: um processo isolado. Interrupção manual ou timeout encerra tentativa.
- BLOCKED: abortado por risco, falha de regra, custo, crash, incerteza ou cancelamento; registrar motivo.
- EVIDENCE_PENDING: trabalho encerrado, checagens de escopo, custos e segredos em andamento.
- DRAFT_PR_READY: proposta publicada sem integração; sempre Draft.
- AWAITING_PO: decisão humana pendente.

**Não há transição automática de AWAITING_PO para INTEGRADA.** Finalização da tarefa requer decisão autêntica do PO, não execução do dispatcher. Qualquer estado de execução inconclusivo ou incoerente bloqueia a próxima tentativa até reconciliação.

## 6. Concorrência, idempotência e retomada

1. **Exclusão única** por host + repositório + Issue/mission digest; garantir **no máximo 1 run ativo no piloto**, mesmo para Issues diferentes.
2. Travamento deve ser verificável e seguro em caso de processo morto; combinar identificador único, lease/heartbeat e operação atômica comprovada na implementação futura. Comentário em Issue, etiqueta ou alteração visual de campo **não são mutex atômicos**.
3. Idempotency key proposta: repositório + Issue + digest + tentativa; replay acidental não deve iniciar segundo processo nem produzir dois PRs.
4. Após interrupção/quebra, registrar estado e exigir diagnóstico/reconciliação antes de repetir. Tentativa extra (máximo uma) não é automática; registrar diagnóstico e obter decisão apropriada antes de repetir.
5. Tempo de tentativa começa ao iniciar a ação efetiva; fixar relógio monotônico e supervisão, com política de encerramento do grupo de processos. Se não for possível parar o processo de forma confiável, o adaptador fica BLOQUEADO.
6. Encerramento/cancelamento deve preservar logs minimizados e jamais realizar merge/deploy/limpeza destrutiva.

## 7. Credenciais e custo como fronteiras

- Autenticação no host com mecanismo seguro suportado, sem gravar tokens em arquivos do repositório; política de privilégios mínimos para ler Issues e abrir somente Draft PR na branch isolada.
- Antes de qualquer piloto verificar se o mecanismo GitHub escolhido impede push direto na branch principal e quais bypasses existem; autenticação no host e aprovação do PO são gates distintos.
- Assinatura AGY/Antigravity não prova API gratuita. **Se não houver prova verificável de custo adicional R$ 0 para a operação específica, falha segura antes de disparar**.
- Registrar evidências de viabilidade AGY antes de escrever adaptador: interface suportada, controle de acesso, exit status, captura redigível, cancelamento e limites de cobrança.
- Não aceitar instruções de “desative o filtro”, “ignore a segurança” ou “publique token” oriundas de Issue/PR/LLM.

## 8. Campos não resolvidos

Formato final dos eventos autenticados, integração suportada AGY, mecanismo atômico de reserva, semântica de expiração de aprovação e política de publicação após teste falho **dependem de validação em etapas posteriores**. São riscos e gates, não requisitos satisfeitos nesta W2-A.
