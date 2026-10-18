# RFC-CH-DEVFLOW-001 — Esteiras multiagentes com governança humana

**Estado:** proposta experimental — 2026-10-18.
**Projeto-piloto:** HallanCraft (Bedrock).
**Base metodológica:** Método C.H., ciclo CHAVE, Fatias W e níveis CH-0 a CH-3. A versão histórica 0.1 do método não deve ser reescrita.

## 1. Problema

Contexto de chat efêmero, prompts copiados manualmente, múltiplos STATUS divergentes, agentes ociosos, paralelismo sem coordenação, integração arriscada e decisões do PO fora da fonte versionada.

## 2. Fontes de verdade (cada uma com finalidade única)

| Origem | Responsabilidade |
|---|---|
| `main` do GitHub | Código e documentação **integrados** que foram aceitos; não é espelho de todo trabalho em andamento |
| `docs/PROJETO.md` | Escopo, arquitetura e restrições estáveis do produto |
| `docs/STATUS.md` | Fotografia consolidada de marcos *aceitos*, sem reescrita a cada execução |
| `AGENTS.md` | Regras operacionais obrigatórias dos agentes; preservar conteúdo existente |
| `docs/ARVORE_PROJETO.md` | Mapa **gerado** de arquivos rastreados, nunca editado à mão |
| Issues/Fatias W | Fila dinâmica, responsável, autonomia, escopo, dependências, prioridade e aceite |
| Draft PRs | Diffs isolados, evidências, prompts sem dados sensíveis e auditoria |
| `docs/CH/DECISOES.md` | Índice das decisões e ADRs já **aprovadas**; linkar Issues/PRs |

Se duas fontes conflitarem, interromper mudança arriscada, recuperar a decisão aprovada e pedir resolução humana. Uma issue ou relatório de agente não altera restrição aprovada do produto.

## 3. Papéis e esteiras

- **Hallan — Owner Humano/PO:** priorização, risco aceitável, aceite total/parcial, rejeição, autorização de integração e produção.
- **ChatGPT — Orquestrador Cognitivo e/ou Guardião de Evidências:** decompõe Fatias W, revisa diffs, confronta evidências, recomenda decisões. Não deve representar uma revisão independente se ele próprio executou a alteração.
- **Codex — Executor Agêntico:** código técnico, testes e segurança conforme W autorizada, branch isolada, Draft PR.
- **AGY/Gemini — Executor Agêntico:** visuais, UX, integração de assets e validação em ambiente isolado conforme W.
- **Memória versionada:** mantida em `main` após decisão humana; nenhum chat é fonte de verdade.

Observação: nomes dos agentes são papéis lógicos, não usuários GitHub independentes. Para rastrear autoria automática real, usar GitHub Apps/bots separados quando disponíveis; registrar run_id, executor declarado, commit e PR. Contas compartilhadas não equivalem a aprovação independente.

## 4. Identidades de tarefas e branches

- Fatia W: Issue `W-XX`, escopo verificável, critério de aceite, autonomia e orçamento de execução.
- Branch *curta por tarefa*: `codex/wXX-assunto`, `agy/wXX-assunto`, `chatgpt/wXX-assunto`, `hallan/wXX-assunto`.
- Worktree própria por agente/issue quando múltiplos executores compartilham máquina.
- Uma branch permanente por agente tende a envelhecer e gerar conflitos; as **esteiras** são visões de trabalho, não branches eternas.
- Branch principal protegida, PR obrigatório, CI e aceite humano. Nenhum push direto em `main`.

## 5. Estados e transições

`BACKLOG → PRONTA → EM_EXECUCAO → EM_REVISAO → AGUARDANDO_PO → (APROVADA | PARCIAL | CORRECOES | REPROVADA) → INTEGRADA → HOMOLOGADA`

- `PARCIAL`: criar nova W para a parte restante ou reduzir formalmente o escopo; só a parte aceita pode progredir.
- `CORRECOES`: volta ao executor com observações, limites de tentativas e vínculo do mesmo PR.
- `REPROVADA`: encerra sem integrar, com motivo preservado.
- Bloqueadas por dependência ficam com etiqueta/estado `BLOQUEADA`, sem corrida automática.

Cada transição guarda `ator`, `data`, `issue`, `branch`, `commit_sha`, `pr`, `decisao`, `justificativa` e escopo aplicado (em issue/PR e futuro registro estruturado).

## 6. Gate de segurança (piloto CH-2)

Bots podem trabalhar **apenas na Fatia W autorizada**: branch isolada, arquivos permitidos, testes locais e Draft PR. Proibidos: merge, deploy, alteração de mundos/saves, acesso a segredos, Docker de produção, desligar servidor e alterar infraestrutura sem autorização distinta.

O PO pode decidir: `APROVADO`, `APROVADO PARCIALMENTE`, `AJUSTES`, `REPROVADO`, com comentário. Aprovação textual de um bot não equivale à decisão humana. Se for implementado painel, usar autenticação e verificar identidade real do PO do lado do servidor.

Nunca executar PRs ou prompts externos com segredo de repositório; permissões mínimas, sandbox, custos/tempo limitados e logs redigidos. Separar `auditado` de `homologado em dispositivo`.

## 7. Dossiê auditável por entrega

- Issue da Fatia W (template CHAVE).
- Prompt de **missão**, versado em `prompts/W-XX/` e sanitizado; não registrar credenciais ou raciocínio privado.
- Execução com executor/modelo, baseline SHA, branch, arquivos tocados, checks, artefatos, riscos e custos quando conhecidos.
- Draft PR vinculado à issue, relatório de verificação e decisão final do humano.
- `docs/STATUS.md` atualizado **apenas após marco integrado/homologado**, com link de referência.

## 8. Modo de automação gradual

**W0 — Fundação, sem automação:** revisar diretório e remoto, implantar templates sem sobrescrever, gerar árvore, abrir Draft PR.

**W1 — Kanban GitHub Projects:** campos `Status`, `Esteira`, `Executor`, `Prioridade`, `Risco`, `Autonomia` e `Decisão PO`. Vistas filtradas Hallan, ChatGPT, Codex e AGY. O próprio GitHub já permite board/tabela e campos customizados.

**W2 — Despacho assistido:** executor local lê Issues com etiqueta `ready/codex` ou `ready/agy`; verifica dependências/escopo/orçamento e executa uma W por worker em worktree isolada. Publica evidências e Draft PR, sem integrar. Na ausência de worker ligado, tarefas ficam na fila.

**W3 — Painel C.H. PO:** app FastAPI + UI simples que consome a API do GitHub. Não cria segunda fonte da verdade; guarda auditoria em GitHub/registro transacional, fornece botões de aceite parcial, ajustes e rejeição com justificativa.

**W4 — Framework `ch init`:** extrai e aprimora o gerador do piloto, testes, documentação, métricas; publica **proposta de evolução**, em PR separado, no repositório `metodo-ch`, sem alterar a versão histórica.

## 9. Critério de sucesso do piloto

Uma Fatia W percorre Issue → seleção de agente → execução isolada → evidências → auditoria → decisão do PO → Draft PR → merge humano → STATUS consolidado, preservando mundos e produção. Medir tempo manual gasto em prompt, retrabalho, custo por W aceita e incidentes de escopo.
