# Arquitetura proposta — Factory v2

Estado: proposta de arquitetura, ainda não implementada nem homologada.

## Forma
Monólito modular local-first: Python/FastAPI, React/TypeScript, SQLite, WebSocket/eventos persistidos, Git/GitHub e Docker. Reaproveitamento seletivo da CLI ch, manifesto, Control Center, evidências e adaptadores após auditoria. Sem microsserviços/Redis/Kafka por padrão.

## Módulos
- Control Center: equipe, modelos, reuniões, tarefas, aprovações e evidências.
- Factory Core: projetos, agentes, sessões, mensagens, tarefas e artefatos; máquina de estados e limites determinísticos.
- Maestro: recomenda alocação por competências e capacidade; nunca amplia permissões ou ignora gates.
- Runtime: contratos discover, execute, status, cancel, resume; CLI/ACP adaptados; configuração por fornecedor, sem supor equivalência.
- Sandbox: broker restrito, containers efêmeros por missão, workspace dedicado e limites de recursos. O plano de controle não entrega o socket Docker aos agentes.
- Knowledge: persistência e recuperação contextual; RAG posterior.
- MCP: interface de ferramentas autorizadas; não substitui motor de tarefas nem política de acesso.
- Governance: aprovação humana, evidências, baseline Git, logs sanitizados e política de consumo.

## Fluxo
Humano → requisito → reunião limitada → plano e critérios de aceite → aprovação → tarefas isoladas → desenvolvimento → QA independente → correção limitada → dossiê → decisão humana. Cada tarefa tem ID, responsável, dependências, workspace, orçamento/limites e estado. Falha/cancelamento bloqueia avanço até recuperação explícita.

## Persistência e segurança
SQLite transacional inicialmente; eventos e artefatos vinculados ao projeto e à revisão Git. Worktree não é sandbox. Docker obrigatório para código não confiável; egress, montagem, credenciais e capacidades mínimas. Não executar no host silenciosamente quando sandbox indisponível. Ver SECURITY.md.

## ADRs pendentes
ADR-001: inventário/reuso do código; ADR-002: modelo de isolamento Docker e autenticação dos runtimes; ADR-003: CLI vs ACP; ADR-004: contratos e persistência; ADR-005: política MCP/RAG.
