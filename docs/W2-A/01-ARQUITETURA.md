# W2-A / 01 — Arquitetura proposta do despachante assistido

**Estado:** PROPOSTA DOCUMENTAL CH-1 • 18/10/2026 • não implementada.  
**Fatia:** [#8](https://github.com/hallanbrito/CHDevFlow/issues/8) • **Plano W2:** [#6](https://github.com/hallanbrito/CHDevFlow/issues/6) • **Decisões do PO:** [#7](https://github.com/hallanbrito/CHDevFlow/issues/7).  
**Repositório editado por esta fatia:** CHDevFlow, somente Markdown; **piloto futuro:** HallanCraft, sem alterações agora.

## 1. Requisitos irrevogáveis desta proposta

| ID | Regra aprovada pelo PO |
|---|---|
| D01 | Host do piloto: notebook Linux CachyOS |
| D02 | Executor pretendido: AGY/Antigravity; **interface não validada** |
| D03 | CH-2 **por missão**, com autorização nova e específica; sem merge automático |
| D04 | Primeira execução funcional futura no HallanCraft, isolada e sem tocar mundos/saves |
| D05 | Disparo **manual**, sem daemon, cron, polling nem execução 24/7 |
| D06 | **Custo adicional zero**, 1 tarefa ativa, 15 min por execução, 1 repetição só após diagnóstico, parada manual imediata |
| D07 | Autenticação segura no host, privilégio mínimo, segredos protegidos, autoria e run_id rastreáveis, branch principal protegida |

Custo zero significa **nenhuma aquisição, recarga, cobrança adicional ou uso de API potencialmente faturável**. Assinatura existente não é autorização para consumo adicional. Sem como comprovar gratuidade antes de iniciar? **Não executar** e relatar bloqueio ao PO. Custos de eletricidade/conectividade já disponíveis não são estimados aqui e não autorizam serviços pagos.

## 2. Diagrama lógico — futuro, NÃO em execução

~~~text
PO Hallan -- decisão autenticada da Fatia W --> GitHub Issue + trilha de aceite
                                      |
                             [Despacho manual CHDevFlow]
                                      |
                  [preflight / política de segurança / custo R$ 0]
                                      |
           [reserva exclusiva + timeout + parada + isolamento git]
                                      |
                      [adaptador AGY/Antigravity*]
                                      |
                     [worktree HallanCraft autorizada]
                                      |
                    [evidências + commits + Draft PR]
                                      |
                   [revisão independente, quando cabível]
                                      |
                         [gate humano: AGUARDANDO_PO]
                                      |
                      merge/deploy somente por novo aceite
* Interface programática ainda não comprovada.
~~~

**Componentes propostos:** (1) GitHub Issues/PRs como fonte da missão, autorização e auditoria; (2) GitHub Projects apenas como visualização (Esteira, Etapa CH etc.); (3) comando local de despacho **desligado por padrão**; (4) verificador fail-closed de autorização, ambiente, custo, arquivos e dependências; (5) reserva de execução exclusiva; (6) adaptador de AGY; (7) supervisor com temporizador e cancelamento; (8) coletor de evidências e publicador de Draft PR. Codex poderá ser outro adaptador **somente** se o PO autorizar uma Fatia W concreta.

Não criar banco de dados concorrente como fonte de verdade. Estado efêmero local e reserva de exclusão podem existir no futuro, desde que reconciliáveis com a Issue e que travas perdidas interrompam novas execuções.

## 3. Fluxo de ponta a ponta proposto

1. PO aprova explicitamente uma missão CH-2 individual, com revisão de escopo, baseline, orçamento e executor. Não basta a etiqueta ch:workflow, a view Codex/AGY, a etapa PRONTA ou uma mensagem escrita pelo próprio agente.
2. PO aciona manualmente um comando de **prévia**. Verificar identidade real do aprovador no GitHub, correspondência com o conteúdo aprovado, ausência de alterações posteriores, dependências, disponibilidade do host e modo sem custo adicional.
3. Supervisor assegura uma única missão ativa; resolve repositório e branch de partida autorizados, fixa SHA e prepara isolamento. Qualquer falha bloqueia antes de iniciar AGY.
4. Após confirmação humana de **executar esta missão**, o adaptador validado inicia apenas trabalho permitido na worktree. Contagem de 15 min por tentativa; ao exceder, solicitar interrupção/cancelar processo e registrar motivo.
5. Verificar mudanças: somente arquivos liberados; nenhum mundo/save, segredo, infraestrutura de produção, branch principal ou deploy. Falha de verificação impede publicação e exige avaliação.
6. Publicar relatório sanitizado e **Draft PR**, nunca merge. Associar Issue, identificador da execução, executor, baseline, commits, custos declarados/verificados, testes e alterações.
7. Marcar AGUARDANDO_PO somente após dossiê auditável. O PO pode aprovar, solicitar ajustes, aprovar parcialmente ou reprovar. Decisão registrada por identidade humana autenticada; um bot não vota pelo PO.

**Falha segura:** dados ausentes/incoerentes, política não verificável, custo incerto, bloqueio expirado, desligamento, mudança de SHA, ambiente inesperado, limite de tempo, conflito ou indisponibilidade do AGY => abortar/preservar evidências; jamais avançar sozinho.

## 4. Fronteiras de segurança

- **CHDevFlow** abriga documentação/contratos e eventual código futuro **em outra Fatia W**. Esta W2-A não cria executável.
- **HallanCraft** fica inacessível nesta W2-A. No piloto posterior, só clone/worktree permitida por caminho canônico, com verificação de symlinks, mount points e arquivos ignorados; **nunca** trabalhar na instalação/mundo ativo.
- **Sem autorização para** instalar dependências, abrir console interativo de agente com privilégios amplos, atualizar pacotes, consumir API paga, usar tokens em prompt, acessar arquivos externos à allowlist, fazer push em main, fazer merge ou deploy.
- Conteúdo de Issues/PRs, prompts externos e saídas de AGY é **entrada não confiável**: não pode ampliar direitos. Políticas e autorização devem ser verificadas fora do texto livre controlado pelos agentes.
- Nunca considerar identidade declarada em comentário como prova da identidade real. Diferenciar autor da ação GitHub, executor lógico e processo no host.
- Não assumir proteção de main: verificar branch protection/rulesets e possibilidade de bypass antes do primeiro piloto real.

## 5. Gate AGY/Antigravity (pendência técnica)

A escolha do PO pelo **AGY/Antigravity** é vinculante. Ainda faltam evidências de: suporte oficial/permitido a comando headless, interface para iniciar missão delimitada, disponibilizar exit code, capturar resultados, cancelar processo com segurança, limitar 15 minutos e impedir cobranças adicionais no CachyOS. **Não inferir** que a presença de AGY ou Gemini CLI fornece API para automação da interface Antigravity.

Se não houver forma suportada e segura de operar AGY, declarar **BLOQUEADO: ADAPTADOR AGY INVIÁVEL/INDETERMINADO** e solicitar decisão do PO. **Não** substituir silenciosamente por Gemini CLI, navegação por UI ou outro executor.

## 6. Separação dos gates de autorização

- **Gate A — planejamento:** W2-A CH-1 autorizada; somente Markdown neste repositório + Draft PR.
- **Gate B — implementação:** Fatia W específica e nova autorização do PO para desenvolver dispatcher/adaptadores.
- **Gate C — missão:** cada execução futura CH-2 exige consentimento individual, contexto e política.
- **Gate D — integração:** aprovação humana específica após diff e testes; a aprovação de arquitetura ou missão **não** significa merge.

## 7. Limites da especificação e próximo passo

Nenhuma ferramenta no notebook foi instalada, inspecionada ou acionada nesta entrega. Arquitetura é **proposta**, não confirmação de viabilidade da interface do AGY. O contrato detalhado está em [02-CONTRATOS.md](02-CONTRATOS.md), os testes projetados em [03-PLANO-DE-TESTES.md](03-PLANO-DE-TESTES.md), e os gates/aceite em [04-CRITERIOS-DE-ACEITE.md](04-CRITERIOS-DE-ACEITE.md).
