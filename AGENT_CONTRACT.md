# Contrato de agentes — proposta

Cada agente é uma identidade lógica estável, distinta do modelo, fornecedor e sessão. O usuário pode fixar runtime/modelo ou autorizar recomendação do Maestro.

| Papel inicial | Responsabilidade | Entregável |
|---|---|---|
| Maestro | Coordenar e recomendar alocação | Plano de tarefas e justificativas |
| Arquiteto | Requisitos com humano, desenho técnico e critérios | Plano/ADRs |
| Desenvolvedor | Implementar escopo aprovado | Patch, código, evidências |
| QA | Validar de modo independente | Testes, resultados e parecer |

Futuro: PO, Tech Lead, UX/UI, frontend, backend, Security, DevOps, documentação. Nenhum agente assume aprovação humana.

Campos mínimos: agent_id, role, project_id, runtime_id, model (opcional), effort (quando suportado), permissions, tools, session_id, task_id, limits, workspace_id. Mensagens: sender, recipient/channel, correlation_id, payload, timestamp. Entregáveis: artifact_id, path/hash, source revision, status, evidence. Segredos nunca em mensagens.

Estados: pending, awaiting_approval, running, succeeded, failed, cancelled, blocked. Transições validadas pelo núcleo. Limite de rodadas, tempo e concorrência. Não repetir indefinidamente. QA não altera implementação nem critérios aprovados sem nova autorização. O runtime pode declarar capacidades indisponíveis e cotas desconhecidas.
