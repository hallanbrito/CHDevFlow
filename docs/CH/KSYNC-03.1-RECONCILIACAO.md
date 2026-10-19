# KSYNC-03.1 — Reconciliação inteligente de Etapa CH

**Missão:** [Issue #21](https://github.com/hallanbrito/CHDevFlow/issues/21) · **Autonomia:** CH-1 (branch isolada, Draft PR) · **RUC:** [v1.0](RELATORIO-UNIVERSAL-CH-v1.0.md).

## Contexto observado

A prévia real da KSYNC-03 mostrou Issues #8 e #19, OPEN e com status Todo, recebendo proposta indevida de Etapa CH = BACKLOG. O GitHub confirma PRs relacionados e integrados (#9 e #20). A condição OPEN + Todo não prova que a missão ainda é inédita. Tampouco PR merged prova homologação humana da missão.

## Contrato de consulta de evidência

O módulo scripts/ch_stage_evidence.py é usado por scripts/ch_project_sync.py (KSYNC-01) e scripts/ch_project_assist.py (KSYNC-03).

Comando de leitura de histórico: gh api -H 'Accept: application/vnd.github+json' --paginate --slurp repos/hallanbrito/CHDevFlow/issues/N/timeline?per_page=100.

- Consultar páginas completas da timeline com o gh autenticado no host. Verificar identidade do repositório e URL canônica da PR.
- Eventos cross-referenced com PR do mesmo repositório geram evidência WORK_FOUND. Eventos referenced/committed com SHA-40 também são sinais conservadores de trabalho.
- PR vinculado é indício de atividade, mas não prova que o PR implementou toda a Issue; um PR apenas mencionado pode bloquear uma sugestão e requerer atenção do PO. Estado merged_at é informativo, nunca uma decisão sobre HOMOLOGADA.
- CLEAR significa somente que a consulta válida não mostrou os indícios definidos. Não comprova inexistência de trabalho.
- Em erro de rede/API, JSON ou paginação inválida, identidade contraditória ou limite excedido, NÃO sugerir Etapa CH = BACKLOG.
- Limite de 30 páginas e 3.000 eventos. Limitações residuais: TOCTOU entre timeline e eventual escrita, e cobertura da timeline como fonte histórica.
- Nenhuma chamada para alterar Issue, PR, Project, credenciais ou agentes.

## Política de estágios

| Cenário | Esteira | Etapa CH |
|---|---|---|
| OPEN, Todo, timeline CLEAR, campos vazios | Proposta independente | Pode sugerir BACKLOG inicial |
| OPEN, Todo, PR ou commit relacionado | Proposta independente de Esteira | ETAPA_PENDENTE_PO, sem BACKLOG |
| OPEN, Todo, timeline indisponível | Proposta independente de Esteira | ETAPA_PENDENTE_PO, sem BACKLOG |
| CLOSED | Preservar demais regras conservadoras de cada ferramenta | Não inferir BACKLOG/HOMOLOGADA |
| Status diferente de Todo | Preservar regra anterior de cada ferramenta | Não propor BACKLOG |
| Executor ausente ou ambíguo | Nenhuma proposta | Nenhuma proposta |
| Etapa já preenchida | Não substituir Etapa | Nunca sobrescrever |

Observação: a KSYNC-03 pode gerar plano somente para Esteira mesmo quando ETAPA_PENDENTE_PO, sempre sujeito a futura autorização expressa do PO para qualquer escrita. As verificações de snapshot e confirmação humana da KSYNC-03 continuam obrigatórias. O script legado KSYNC-01 não ganhou automaticamente as mesmas salvaguardas nem autorização de execução.

## Critérios de aceite da Issue #21

1. As Issues #8 e #19 deixam de receber BACKLOG quando o histórico de PR #9/#20 for verificado.
2. Nunca converter merged/closed ou texto histórico em EM_EXECUCAO, EM_REVISAO ou HOMOLOGADA.
3. Em falha de consulta de histórico, bloquear apenas a proposta da etapa, sem permitir falsa homologação.
4. Identidade da PR, paginação e limites são verificados. Testes com mocks cobrem PR aberto/merged, falso vínculo, paginação e falha.
5. KSYNC-01 e KSYNC-03 compartilham o verificador; sem mudança em Autonomia CH e Decisao PO.
6. Testes offline/CI e revisão humana do Draft PR antes de merge.
7. Execução real do sincronizador, timers, deploy e acesso a HallanCraft estão fora de escopo.

## RUC/1.0 — nove seções

1. Identificação: KSYNC-03.1, Issue #21, CH-1, branch isolada e SHA.
2. Resumo: bloqueio de BACKLOG quando houver evidência de trabalho.
3. Consultas: Issue #8/#19, PR #9/#20, timelines e código.
4. Evidências: dados GitHub observados, prévia do PO declarada e mocks separados.
5. Verificações: testes offline, CI, nenhum item-edit no Project.
6. Riscos: vínculos indiretos, eventos incompletos, TOCTOU, legacy --apply.
7. Alterações: apenas arquivos versionados na branch, sem escrita remota em Project.
8. Recomendação: revisar PR e executar piloto futuro de leitura apenas, após gate.
9. Decisão PO: aceitar/revisar; merge e execução real exigem autorizações específicas.

**Não autorizado nesta fatia:** merge, --apply, --apply-plan, cron, deploy, workflow de escrita, dispatcher W2, execução Codex/AGY ou qualquer alteração em HallanCraft.
