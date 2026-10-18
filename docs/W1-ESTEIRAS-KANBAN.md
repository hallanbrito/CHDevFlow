# W1 — Kanban C.H. DevFlow (proposta de integração)

**Fatia W:** https://github.com/hallanbrito/CHDevFlow/issues/2  
**Estágio:** implantação parcial em Draft PR. Instância remota do GitHub Project ainda necessita execução do bootstrap autenticado.

## Um Project, quatro esteiras

As esteiras são visões de um único GitHub Project e não branches permanentes nem contas GitHub separadas.

| View | Filtro | Objetivo |
|---|---|---|
| 00 Geral | sem filtro | Visão geral |
| 01 Hallan | Esteira:Hallan | Atividades do Product Owner |
| 02 ChatGPT | Esteira:ChatGPT | Planejamento, auditoria, coordenação |
| 03 Codex | Esteira:Codex | Execução técnica |
| 04 AGY | Esteira:AGY | Execução visual/UX |
| 05 Aguardando PO | Etapa CH:AGUARDANDO_PO | Decisões pendentes, qualquer agente |

O status simplificado nativo do GitHub é preservado. O campo detalhado **Etapa CH** registra as transições C.H. (BACKLOG, PRONTA, EM_EXECUCAO, EM_REVISAO, AGUARDANDO_PO, APROVADA, PARCIAL, CORRECOES, REPROVADA, INTEGRADA, HOMOLOGADA).

**Campos novos:** Etapa CH, Esteira, Prioridade CH, Risco CH, Autonomia CH, Decisao PO.

## Portão de autorização

A aprovação do PO é um evento registrado em Issue/PR. Aprovação não significa merge automático; se parcial, dividir escopo e PR antes de integrar. O executor CH-2 só faz trabalho isolado e apresenta evidências.

## Execução controlada do instalador

O script inicia no modo **somente prévia** e não necessita de credenciais para mostrar o plano:

~~~bash
python scripts/w1_github_project.py
~~~

Depois de revisar o código e aprovar a configuração com sua sessão GitHub local:

~~~bash
gh auth status
gh auth refresh -s project
python scripts/w1_github_project.py --apply
~~~

A conta deve ter permissão de administração de Projects. O script verifica um Project de mesmo título antes de criar, preserva campos/views/labels já existentes, vincula o repositório e cadastra a Issue W1. Não apaga nada. Project novo é inicialmente privado; um Project existente não tem visibilidade alterada.

## Ajustes únicos pela interface (a validar)

1. Abrir o Project criado em sua conta e conferir **seis views**, incluindo as quatro esteiras.
2. Em cada board, escolher **agrupar por Etapa CH** (o instalador cria views e filtros, mas a personalização de agrupamento deve ser confirmada no navegador).
3. Em **Workflows**, ativar **Auto-add to project**, selecionar repositório hallanbrito/CHDevFlow e filtrar Issues com label ch:workflow. O GitHub não adiciona retroativamente todos os itens antigos, por isso a W1 é vinculada explicitamente.
4. Criar uma Issue de teste com a label e observar inclusão automática; registrar resultado na Issue W1.
5. Colar a **URL real do Project** na Issue W1 e neste arquivo, via novo PR, após verificação.

Documentação oficial do GitHub:
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/adding-items-automatically
- https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project

## Critérios de aceite W1

- [ ] Project real criado/vinculado com URL verificada.
- [ ] Views e campos configurados e testados.
- [ ] Issue W1 visível na esteira ChatGPT.
- [ ] Auto-add funcionando para Issue de teste nova.
- [ ] Aprovação do PO continua condição para merge.
- [ ] Nenhum acesso a produção, Docker, mundos ou saves do HallanCraft.

A instalação da instância remota não é executada automaticamente por este PR; exige a autenticação da conta GitHub para Projects. Automação Codex/AGY e painel PO continuam fora do escopo (W2/W3).
