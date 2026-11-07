# RUC/1.0 — W-DATA-01-A / Aplicador Autonomia CH — CH-2 isolado

> **Missão:** [CH-DATA-01 / Issue #62](https://github.com/hallanbrito/CHDevFlow/issues/62)  
> **PO:** Hallan · **Executor:** ChatGPT · **Base:** `main` (`d99f7176d3335bd5426a479fe05b5840848822bd`)  
> **Branch:** `chatgpt/ch-data-01-autonomy-reconciler` · **PR:** Draft, não integrada  
> **Gate:** CH-2 **somente código isolado e testes fakes**. Sem autorização de mutation no Project #2.

## 1. Objetivo / referências pinadas

Desenvolver ferramenta isolada `scripts/ch_project_autonomy.py` para futura regularização estrita do campo `Autonomia CH` em cinco cartões já existentes. Não modificar as rotinas do KSYNC-03 nem a CLI principal.

- **Plano documental CH-1 homologado (SHA-256):** `68bcb20520d315853acd8073a548f2ec3dcabf02b3e766c3992a1197b4a2f88f`.
- **Snapshot histórico LIVE (SHA-256):** `7460350916057bd5f14bf0934560fff247f548d03dc0e531e5e6ebbb486f41c6` (31 itens/19 campos; 2026-11-07T16:41:54Z; reportado pelo terminal do PO).
- **Matriz:** #8→CH-1; #10→CH-1; #12→CH-0; #13→CH-0; #24→CH-1.
- O digest e o snapshot históricos são provas, **não** autorização de mudança de dados.

## 2. Arquitetura/implementação

1. Novo arquivo em `scripts/` com **dry-run** padrão: valida o contrato CH-1; somente `--plan-output` consulta o Project via adaptador existente para preparar um **plano executável de esquema separado**, sem escrita.
2. A aplicação futura exigirá `--apply-plan`, SHA completo em `--confirm`, `--approval-comment` da Issue #62, `--audit-file` inédito e terminal humano TTY com frase específica.
3. A identidade de aprovação é conferida contra a API GitHub: comentário do PO `hallanbrito` com digest **do plano executável**, cinco valores, autorização de apenas um campo e aceitação expressa do risco sem CAS atômico. O plano consultivo CH-1, isoladamente, **não autoriza escrita**.
4. Mutation reutiliza `ch_project_assist._admit_graphql("set", params)` da W-F2.2. Não há operação `add` no reconciliador; a allowlist existente `validate_plan/apply_plan` do KSYNC-03 permanece intocada.
5. Verificação de Project/Field/Option/Card IDs em leitura LIVE, `Autonomia CH` ainda vazia, preservação de `Etapa CH`, `Esteira`, `Status`, `Decisao PO`, `Prioridade CH`, `Risco CH`. Um cartão por vez; confirmar resposta GraphQL e read-back de todos os cinco.
6. Log JSONL `O_EXCL`/`0600`, `flush/fsync` por evento; `ATTEMPT` precede a mutation; falhas/timeout após tentativa ficam `UNCERTAIN` e impedem repetição automática ou rollback cego.

**Limitação explícita:** GitHub `updateProjectV2ItemFieldValue` não possui compare-and-swap atômico de campo nulo. Uma alteração externa entre a leitura e a mutation permanece possível. O PO deve aceitar esse risco no eventual gate de aplicação (não concedido).

**Desvio deliberado da proposta R0:** a prova de autorização é um comentário externo, obtido **depois** da geração e digest do plano executável. Incorporar o ID ou fingerprint da autorização no próprio digest criaria dependência circular. O comentário e seu fingerprint são vinculados em tempo de aplicação e registrados no JSONL, com revalidação antes de cada tentativa.

## 3. Contratos de segurança

- Nenhuma escrita remota está autorizada por este PR e nenhum teste pode chegar à API real.
- Sem alterações de `Etapa CH`, `Esteira`, campos opcionais, `Decisão PO`, status ou homologações humanas.
- Sem inclusão de novos cartões, deploy, release, execução real de agentes, merge ou promoção de Draft.
- Não confiar em snapshot global como guarda imutável: verificar os cinco cartões antes de cada tentativa, sem invalidar por novas Issues fora do lote.
- Plano gerado para execução tem validade curta (24 h) e demanda **autorização específica posterior do PO**, assinada pelo comentário GitHub.

## 4. Testes e evidências

Teste local somente com `unittest` (sem rede):

```bash
python -m unittest discover -s tests -p 'test_ch_project_autonomy.py' -v
python -m py_compile scripts/ch_project_autonomy.py
```

**Execução local isolada durante preparação:** 25 testes de casos normais/adversários, todos verdes. Incluem adulteração de SHA, esquema consultivo recusado, TTY/PO inválidos, mudanças no lote, alterações em campos preservados, opções incorretas, timeout antes/depois da mutation fake, falha no 3º cartão, reexecução parcial, JSONL exclusivo/0600 e operação GraphQL exclusivamente `set`.

**Suíte legada/CI:** conferir no HEAD publicado. O baseline `main` do dia 07/11 tem CI pós-merge `42391671744` concluída com `success`; a contagem de **465 testes** citada no gate é uma referência do PO e não foi presumida como total atual. Registrar nova contagem efetiva e jobs no comentário da Draft PR.

## 5. Estado da entrega

`CH2_ISOLATED_IMPLEMENTATION / OFFLINE_TESTS_ONLY / PROJECT_WRITES_ZERO / DRAFT_PR / AWAITING_INDEPENDENT_REVIEW_AND_PO`

**Gates futuros separados:** (1) homologação técnica da PR; (2) geração de plano executável atualizado; (3) decisão expressa de escrita no Project #2, com verificação do risco concorrente. **Nenhum desses gates de aplicação foi concedido.**