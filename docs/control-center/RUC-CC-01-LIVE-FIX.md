# RUC/1.0 — CC-01: correção do formato nativo do Project

## 1. Identificação

- Data: 22/10/2026 (America/Fortaleza).
- Executor declarado: ChatGPT / Codex; revisão própria, sem alegação de auditoria independente.
- Origem: teste manual acompanhado do PO Hallan no Control Center integrado pelo PR #30.
- Baseline: `b192ebb6daa3798fce3620d56cfec44bc8d6b118`.
- Branch: `chatgpt/cc01-correcao-leitura-live`.

## 2. Resumo executivo

O PO observou 17 itens recebidos do GitHub e zero missões reconhecidas. A causa
foi a incompatibilidade entre o JSON nativo e a fixture: `labels` fica na raiz,
e os campos personalizados chamam-se `etapa CH` e `autonomia CH`.
A correção mantém o filtro exato `ch:workflow`, limita a Issues do repositório
canônico e preserva compatibilidade com a demonstração.

## 3. Consultas e atividades

Leitura do código, RFC e template de PR; clone isolado da baseline; reprodução
offline com 17 itens sintéticos na estrutura informada pelo PO; correção da
normalização, apresentação de dados insuficientes e aviso de falha de leitura.
Nenhum snapshot privado ou credencial do notebook foi copiado.

## 4. Evidências

- DECLARADO PELO PO: consulta local retornou 17 itens / 0 missões; nomes das
  chaves nativas foram apresentados na conversa.
- RETESTE VISUAL DO PO no head `14d7ed0`: as capturas
  `Captura_de_tela_20261022_103101.png` e `Captura_de_tela_20261022_103232.png`
  mostram LIVE_GITHUB com 17 missões reconhecidas, zero itens fora do filtro,
  12 com etapa de conclusão observada e 5 bloqueadas por dados insuficientes.
  O aviso de dependências não informadas permanece nas 17 missões.
- A captura `image(20261022-133315).png` revelou etiquetas saindo dos cartões
  do grafo devido aos IDs nativos longos. Ajustados quebra de linha, limites
  de largura e alinhamento dos cartões; legendas dos contadores agora dizem
  "Etapa de conclusão observada" e "Dependências ou dados insuficientes".
- OBSERVADO LOCALMENTE: o normalizador da baseline retorna 0 para os 17 itens
  sintéticos; o corrigido retorna 17, sem modificar o snapshot.
- Testes locais: **212 aprovados** (68 do painel, 67 da Sentinela, 77 da raiz),
  além de 11 subtestes; `git diff --check` limpo.
- Os 15 novos casos cobrem formato nativo, etiquetas string/objeto, exclusão
  de outros repositórios/DraftIssues/etiquetas parecidas, campos ausentes,
  dependências inválidas, bloqueios propagados, etapa homologada observada,
  renderização/filtros, erro sanitizado com HTTP 503, projeto vazio legítimo
  e renderização dos 11 cartões da demonstração.
- Após o ajuste de CSS/legendas: os 68 testes do painel passaram novamente.
  A tentativa de verificação visual automatizada não pôde ser concluída:
  o download do Chromium retornou um arquivo inválido. HTML com IDs longos
  foi renderizado via ASGI, mas não equivale a uma captura de navegador.
- O CI existente executa somente os testes da raiz. Os testes novos foram
  executados localmente; nenhuma alteração de workflow foi realizada.

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

## 6. Limitações e riscos

O reteste real confirmou que os 17 itens observados satisfazem o filtro
canônico e carregam na listagem/dashboard. O Project observado não oferece `dependencies`:
o grafo real fica explicitamente parcial até existir uma fonte estruturada
validada. Resolver essa fonte é trabalho posterior; não ler referências
genéricas no corpo da Issue como se fossem contratos de dependência.
O reteste do ajuste de layout no navegador do PO permanece pendente; o registro
das capturas recebidas acima se refere ao head anterior ao ajuste de layout.

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

Preparado para revisão em branch isolada / Draft PR #31. Sem merge.
Leitura real confirmada nas capturas do teste acompanhado; reteste de layout e decisão de integração pendentes. Não declarar
o modo ao vivo integralmente homologado enquanto faltarem o reteste e uma
fonte verificada das dependências.
