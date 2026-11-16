# CHDevFlow — Índice de decisões e precedência

**Índice de referências**, não uma autorização adicional nem substituto de decisões por Issue/PR.

| Tema | Decisão / interpretação vigente | Fonte |
|---|---|---|
| Papel do PO | Hallan decide prioridade, risco, disparo real e integração; agente não se autoaprova | [RFC](../RFC-CH-DEVFLOW.md), [Issue #7](https://github.com/hallanbrito/CHDevFlow/issues/7) |
| CH-1 vs executores | ChatGPT arquiteta/delega/revisa; AGY implementa; Codex audita de forma independente; separar implementador de revisor | [RFC](../RFC-CH-DEVFLOW.md), [Issue #121](https://github.com/hallanbrito/CHDevFlow/issues/121) |
| D01–D07 | Notebook CachyOS no piloto inicial, AGY, missão autorizada individualmente, disparo manual, sem merge automático, custo adicional R$0 e proteção de credenciais/`main` | [W2-A](../W2-A/01-ARQUITETURA.md), [Issue #7](https://github.com/hallanbrito/CHDevFlow/issues/7) |
| Concorrência/tempo | Uma missão ativa; limite 15 min para execução local; timeout/cancelamento precisam de comprovação | [W2-A](../W2-A/01-ARQUITETURA.md), [executor local](CH-PIPE-01-LOCAL-EXECUTOR.md) |
| Reprovação técnica | Regra posterior aprovada em 14/11: máximo 3 chamadas AGY (1 inicial + até 2 devoluções); aprovação encerra cedo; falha de credencial/quota/infraestrutura bloqueia sem retry | [CCC-01](CH-PIPE-01-CICLO-CORRECAO-CONTROLADA.md), [Issue #78](https://github.com/hallanbrito/CHDevFlow/issues/78) |
| W2-B | `DryRunDispatcher` e `FakeWorker` são **simulações**, não chamadas de agente | [W2-B](../W2-B/README.md), [Sentinela](../../apps/bootstrap/sentinela/AGENTS.md) |
| F5/F6 | AGY em `--mode plan` + fonte/JSON → Python materializa e testa → Codex somente leitura; inspeção de artefatos por SHA; dossiês por tentativa | [F5](CH-PIPE-01-F5-LOCAL-PILOT.md), [F6](CH-PIPE-01-F6-MISSOES-PYTHON.md) |
| Escrita no Project #2 | Campos do Project são **indicadores**, não autorização de execução; operação de admissão exige decisão independente por Issue | [CH-GOV-01 F2.2](CH-GOV-01-F2-2-ADMISSAO.md) |
| Publicação F7 | Governança avançada permanece com publicação remota desabilitada; provas LAB não autorizam POST/merge; não seguir criando fases antes do MVP local | [F7 Security](CH-PIPE-01-F7-SECURITY-HARDENING-20261115.md), [Issue #121](https://github.com/hallanbrito/CHDevFlow/issues/121) |
| Prioridade restaurada — 16/11 | Construir o **despacho real pela UI existente** antes de novas camadas E3/F7; aproveitar código e decisões existentes. A mudança de foco não suspende guardrails de custo/segredos/PO | [Issue #121](https://github.com/hallanbrito/CHDevFlow/issues/121) |

## Como resolver conflitos

1. Distinguir **proposta histórica** de implementação atual e de aprovação humana efetiva.
2. Inspecionar a Issue/PR de decisão no GitHub e o commit; não “atualizar” as regras silenciosamente em função de um chat ou de um relatório de IA.
3. A regra de três tentativas altera **somente** a política de devoluções técnicas, não autoriza loop por erro de infraestrutura ou custo incerto.
4. Se uma política local do módulo for mais restritiva (ex.: Sentinela FakeWorker), preservá-la; alteração requer decisão específica.
5. Se a ação envolver agente real, créditos, merge, deploy, segredos, Project #2 ou F7 POST sem autorização exata, **não executar**; apresentar o bloqueio objetivo.

Mantenha aqui **links para decisões verificadas**, não declarações de homologação baseadas só em uma CI verde.
