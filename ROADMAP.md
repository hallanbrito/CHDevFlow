# Roadmap — nova direção CHDevFlow

Data: 27/11/2026. Planejamento por critérios de aceite, sem datas prometidas. Factory v2 é a geração arquitetural; as versões abaixo são marcos incrementais propostos, não releases publicadas.

| Marco | Escopo | Critério de aceite |
|---|---|---|
| v0.2 — Fundação | Inventário da base, ADRs, contratos de agentes, threat model, protótipo Docker rootless/restrito, testes negativos | Aprovação humana; isolamento validado em laboratório; decisão documentada de reuso/rewrite |
| v0.3 — Agent Runtime | Descoberta e configuração de Codex/AGY ou dois runtimes comprovados, CLI/ACP, sessões, timeout, cancelamento, cotas desconhecidas explícitas | Dois runtimes usam mesmo contrato; execução e cancelamento em sandbox verificados |
| v0.4 — Colaboração | Chat individual, reuniões limitadas, mensagens, tarefas, estados persistentes, aprovação | Agentes produzem plano e entregáveis rastreáveis; sem loops ilimitados |
| v0.5 — Factory MVP | Maestro, Arquiteto, Dev, QA; fluxo requisito → plano → aprovação → código → testes → revisão | Aplicação executável em projeto piloto, testes independentes e evidências; nenhuma publicação automática |
| v0.6 — MCP | Servidor com ferramentas de projeto, mensagens, tarefas e aprovações; integração externa autorizada | Autorização por agente, auditoria, testes negativos |
| v0.7 — RAG | SQLite FTS5, contexto versionado, embeddings locais opcionais, isolamento por projeto, avaliações | Recuperação de decisões relevantes com origem, versão e métricas |
| v0.8 — Maestro inteligente | Roteamento explicável por competências, qualidade, custo e cotas conhecidas | Recomendações avaliadas em benchmark; fallback explícito |
| v0.9 — Confiabilidade e pesquisa | Auditoria ampliada, recuperação, concorrência, avaliação; LoRA/QLoRA opcional com dados autorizados | Testes de segurança e confiabilidade; pesquisa não bloqueia produto |
| v1.0 — Release pública | Onboarding, empacotamento, documentação e suporte multiplataforma validado | Desenvolvedor externo instala e entrega uma fatia funcional sem assistência |

## Regras
- Segurança começa na v0.2, não na v0.9. Docker não substitui threat model.
- Apenas abrir issues da próxima fatia aprovada; não ressuscitar backlog antigo em massa.
- Cada marco exige evidências reproduzíveis e decisão humana. CI verde não equivale a homologação.
- Não afirmar compatibilidade, disponibilidade ou custos de CLIs sem teste e documentação oficial.
- A auditoria de reaproveitamento precede alterações funcionais.
