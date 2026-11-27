# Equipe de desenvolvimento — CHDevFlow

Aprovada pelo PO em 27/11/2026. Esta é a equipe que desenvolve o CHDevFlow, não o catálogo de papéis do produto. Alocação pode mudar conforme disponibilidade e autorização.

| Responsável | Papel | Limites |
|---|---|---|
| Humano (PO) | Direção, prioridades, autorização e homologação | Decisão final |
| ChatGPT | Arquitetura, planejamento, contratos, critérios de aceite | Não substitui aprovação humana |
| GitHub Copilot | Desenvolvimento principal, testes e PRs | Escopo aprovado, sem merge/deploy autônomo |
| Codex | Auditoria técnica independente e segurança | Revisão por evidências; não homologar a própria implementação |
| Gemini | Pesquisa externa e análise | Não consultar repositório; fornecer contexto selecionado |
| Groq (GPT-OSS 20B) | Triagem, classificação e resumos experimentais | API remota; sem execução, aprovação ou acesso autônomo a repositórios; fora do runtime inicial |
| AGY | Reserva operacional | Acionamento pontual autorizado |

Grok está fora da equipe. Não confundir Grok com Groq. Priorizar economia de recursos, evitando convocar todas as IAs para toda tarefa. Consumo adicional e envio de dados a fornecedores exigem autorização conforme política.

Fluxo: PO → arquitetura → pesquisa externa se necessária → Copilot → Codex → PO. Primeira missão: [FACTORY-001 #127](https://github.com/hallanbrito/CHDevFlow/issues/127). A Groq teve teste de conectividade, conversa e triagem; não foi homologada como componente da fábrica.
