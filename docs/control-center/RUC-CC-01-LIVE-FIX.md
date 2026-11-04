# RUC/1.0 — CC-01: correção do formato nativo do Project

## 1. Identificação

- Data inicial: 22/10/2026 (America/Fortaleza).
- Executor declarado inicial: ChatGPT / Codex; revisão própria, sem alegação de auditoria independente.
- Reauditoria técnica: 03/11/2026 por AGY (Antigravity), autonomia CH-2, autorizada pelo PO em 03/11/2026 ([PR #31](https://github.com/hallanbrito/CHDevFlow/pull/31#issuecomment-6614342106) / [Issue #53](https://github.com/hallanbrito/CHDevFlow/issues/53#issuecomment-6614350576)).
- Correção documental de CI: 04/11/2026 por AGY (Antigravity), Missão AGY-CC01-R2, autorizada pelo PO Hallan no parecer CH-AUD-CC01-R1.
- Origem: teste manual acompanhado do PO Hallan no Control Center integrado pelo PR #30.
- Baseline histórica da branch: `b192ebb6daa3798fce3620d56cfec44bc8d6b118`.
- Baseline canônica de alinhamento (`main`): `a1aa3935ce3e5a34cd12dbf79c54dd211c02887e`.
- Branch: `chatgpt/cc01-correcao-leitura-live`.
- HEAD inicial da reauditoria: `ffb38d74805594e60970b61944b60296a074c342`.
- HEAD da reauditoria R1: `64456b63e394c42152fbe77b715ceeeb73a26920`.

## 2. Resumo executivo

O PO observou 17 itens recebidos do GitHub e zero missões reconhecidas em 22/10. A causa
foi a incompatibilidade entre o JSON nativo do GitHub Project e a fixture legada: `labels` fica na raiz,
e os campos personalizados chamam-se `etapa CH` e `autonomia CH`.
A correção mantém o filtro exato `ch:workflow`, limita a Issues do repositório
canônico e preserva compatibilidade com a demonstração.
Na reauditoria de 03/11/2026 (Missão AGY-CC01-R1), a leitura ao vivo contra o snapshot
atual do Project #2 foi retestada em modo estritamente somente leitura, comprovando
26 itens recebidos, 26 missões reconhecidas, 0 itens fora do filtro, 20 com etapa de conclusão observada,
6 bloqueadas por dados insuficientes e 0 elegíveis (sem invenção de dependências fictícias).
Na correção documental de 04/11/2026 (Missão AGY-CC01-R2), as evidências de CI remota foram
atualizadas com base no parecer CH-AUD-CC01-R1, registrando a aprovação com sucesso do workflow
`CHDevFlow CI Integral` (run 41711753771, 399 testes PASS no total), distinguindo os 212 testes
locais históricos da suíte completa integrada no CI.

## 3. Consultas e atividades

Leitura do código, RFC e template de PR; inspeção do clone isolado da baseline; reprodução
offline com 17 itens sintéticos na estrutura informada pelo PO; correção da
normalização, apresentação de dados insuficientes e aviso de falha de leitura.
Reconciliação estrutural contra a `main` atual (`a1aa3935ce3e5a34cd12dbf79c54dd211c02887e`)
comprovando compatibilidade total (zero conflitos via `git merge-tree`).
Verificação da execução remota do workflow `CHDevFlow CI Integral` no GitHub Actions
(run 41711753771, job 126181306959) e coleta dos logs de execução de testes.
Nenhum snapshot privado ou credencial do notebook foi copiado.

## 4. Evidências

### 4.1 DECLARADO PELO PO (Histórico de 22/10/2026)
- Consulta local no notebook retornou 17 itens / 0 missões; nomes das chaves nativas foram apresentados na conversa.
- Reteste visual no head `14d7ed0`: capturas `Captura_de_tela_20261022_103101.png` e `Captura_de_tela_20261022_103232.png` mostraram LIVE_GITHUB com 17 missões reconhecidas, zero itens fora do filtro, 12 com etapa de conclusão observada e 5 bloqueadas por dados insuficientes.
- Captura `image(20261022-133315).png` revelou etiquetas saindo dos cartões do grafo devido aos IDs nativos longos. Ajustados quebra de linha, limites de largura e alinhamento dos cartões; legendas dos contadores agora dizem "Etapa de conclusão observada" e "Dependências ou dados insuficientes".

### 4.2 LIVE_GITHUB (Observado ao vivo em 03/11/2026)
- Consulta somente leitura realizada via `SentinelFacade().obter_snapshot_ao_vivo()` sobre o GitHub Project #2 (`hallanbrito/CHDevFlow`):
  - Total recebidos (`total_recebidos` / `totalCount`): **26 itens**.
  - Total de missões reconhecidas com `ch:workflow` e `repository == 'hallanbrito/CHDevFlow'`: **26 missões**.
  - Total fora do filtro (`total_ignorados`): **0 itens**.
  - Total com etapa de conclusão observada (`INTEGRADA` ou `HOMOLOGADA`): **20 missões**.
  - Total bloqueadas por dados insuficientes (`BLOQUEADA_DADOS`): **6 missões** (#5, #6, #10, #24, #32, #40).
  - Total elegíveis (`ELEGIVEL`): **0 missões**.
  - Total de ciclos detectados: **0**.
  - Total de dependências órfãs: **0**.
  - Total com dados insuficientes (`total_dados_insuficientes`): **26 missões** (ausência de campo estruturado de dependências no Project nativo; grafo mantido parcial sem inventar arestas ou elegibilidade falsa).

### 4.3 FIXTURE_OFFLINE (Testes locais executados em 03/11/2026)
- Suíte do Control Center (`apps/control-center/tests/`): **68 testes PASS** (1.57s).
  - `test_live_github_regression.py`: 15 testes aprovados cobrindo formato nativo, etiquetas string/objeto, exclusão de repositórios externos/DraftIssues, campos ausentes, dependências inválidas, bloqueios propagados, etapa homologada observada, erro 503 sanitizado, projeto vazio e 11 cartões demo.
  - `test_dag_engine.py`: 10 testes aprovados.
  - `test_mission_service.py`: 6 testes aprovados.
  - `test_project_service.py`: 5 testes aprovados.
  - `test_routes_read_only.py`: 22 testes aprovados.
  - `test_sentinela_adapter.py`: 6 testes aprovados (com isolamento de credencial).
  - `test_server_security.py`: 4 testes aprovados.
- Suíte da Sentinela Python (`apps/bootstrap/sentinela/tests/`): **67 testes PASS** (0.32s).
- Suíte do repositório raiz (`tests/`): **77 testes PASS** (0.097s).
- **Total consolidado de testes locais históricos da branch: 212 testes PASS** (execução isolada em 03/11/2026).

### 4.4 CI_INTEGRAL_GITHUB (Execução remota no GitHub Actions — 03/11/2026)
- Workflow: `CHDevFlow CI Integral` (disparado via `pull_request` no HEAD `64456b63e394c42152fbe77b715ceeeb73a26920`).
- Run ID: `41711753771` ([Acessar Run 41711753771](https://github.com/hallanbrito/CHDevFlow/actions/runs/41711753771)).
- Job ID: `126181306959` (`python-checks`).
- Resultado: `success` (concluído em 1m18s).
- Testes executados no CI integral:
  - Testes do repositório raiz (`tests/`): **262 PASS** (`Ran 262 tests in 41.087s`).
  - Testes da Sentinela (`apps/bootstrap/sentinela/tests/`): **69 PASS** (`Ran 69 tests in 0.053s`).
  - Testes do Control Center (`apps/control-center/tests/`): **68 PASS** (`68 passed in 0.47s`).
  - **Total consolidado do CI integral: 399 testes PASS.**

### 4.5 DISTINÇÃO METODOLÓGICA ENTRE SUÍTES DE TESTE
- **212 testes locais históricos (Seção 4.3):** executados localmente em 03/11/2026 no ambiente isolado da branch `chatgpt/cc01-correcao-leitura-live` cobrindo o escopo restrito da fatia (77 raiz + 67 Sentinela + 68 Control Center).
- **399 testes do CI integral (Seção 4.4):** executados remotamente pelo GitHub Actions no commit `64456b63e394c42152fbe77b715ceeeb73a26920`, validando a integração completa da branch contra a `main` canônica atualizada (262 raiz + 69 Sentinela + 68 Control Center).

### 4.6 NÃO_EXECUTADO / LIMITAÇÕES VERIFICADAS
- Captura de tela visual automatizada via navegador headless não pôde ser executada localmente devido à ausência de binário do navegador no ambiente (permanece dependente da validação visual humana nas capturas fornecidas pelo PO).

## 5. Alterações

- Mapear os campos nativos sem presumir BACKLOG, AGY, CH-1 ou homologação por
  `Status=Done` quando os campos de governança não foram informados.
- Distinguir `dependencies=[]` de campo ausente/inválido: exibir informação
  pendente e `BLOQUEADA_DADOS` para missões ainda não concluídas; não gerar
  arestas fictícias nem inferir dependências a partir de menções no texto.
- Preservar etapas concluídas explicitamente observadas, mantendo o aviso
  de que as dependências dessas missões não foram verificadas.
- Mostrar contagem de recebidos/reconhecidos/fora do filtro e grafo parcial.
- Em falha de consulta, mostrar erro sanitizado e escapado com HTTP 503,
  ocultar indicadores indisponíveis e preservar LIVE_GITHUB sem fallback demo.
- Corrigir escopo Jinja da variável que ocultava os três cartões de anomalias
  no grafo demo: `namespace` preserva o resultado fora do laço.
- Ignorar `*.egg-info/`, gerado pela instalação editável. Nenhum arquivo
  do notebook do PO foi removido ou alterado por esta execução.
- Atualizar documentalmente o RUC para registrar as evidências de aprovação do workflow
  remoto `CHDevFlow CI Integral` (run 41711753771, 399 testes PASS), removendo a alegação
  desatualizada de `CI_NAO_VERIFICADA`.

## 6. Limitações e riscos

O reteste real confirmou que os itens observados satisfazem o filtro
canônico e carregam na listagem/dashboard. O Project observado não oferece `dependencies`:
o grafo real fica explicitamente parcial até existir uma fonte estruturada
validada. Resolver essa fonte é trabalho posterior; não ler referências
genéricas no corpo da Issue como se fossem contratos de dependência.
O reteste do ajuste de layout no navegador do PO permanece dependente de conferência visual humana.

## 7. Segurança, custo e exclusões

Somente o módulo do painel, seus testes e este relatório foram modificados.
Sentinela, contratos normativos, workflow CI, campos/itens do Project e Issues
permanecem inalterados. Sem worker, loop, timer, deploy, merge, API de IA
faturável ou acesso a HallanCraft/Maestro. Custo adicional de chamadas de IA:
R$ 0,00. As operações GitHub desta entrega limitam-se a leitura e publicação
da branch/Draft PR da correção.

## 8. Reteste e recuperação

No notebook, interromper o servidor com Ctrl+C, buscar a branch publicada,
alternar para ela e executar `bash scripts/iniciar_control_center.sh` usando
a `.venv` já instalada. Alternar explicitamente para AO VIVO, conferir as
contagens, as etapas/autonomias e os avisos de dados insuficientes.
Para recuperar a versão anterior, interromper o servidor, retornar a `main`
e iniciar novamente; nenhum dado remoto precisa ser restaurado.

## 9. Estado e decisões do PO

- **Estado:** `AGUARDANDO_AUDITORIA_CHATGPT / AGUARDANDO_PO / SEM_MERGE`.
- Preparado para revisão em branch isolada / Draft PR #31. Sem merge.
- Leitura real confirmada com 26 itens; zero conflitos com a `main` canônica (`a1aa3935ce3e5a34cd12dbf79c54dd211c02887e`).
- CI integral comprovado com resultado `success` (run 41711753771, job 126181306959, 399 testes PASS).
- Nenhuma auto-homologação declarada. Decisão final de integração cabe exclusivamente ao PO Hallan.
