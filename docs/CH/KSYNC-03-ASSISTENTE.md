# KSYNC-03 — Assistente de sincronização com gate humano

**Missão:** [Issue #19](https://github.com/hallanbrito/CHDevFlow/issues/19) · **Base:** KSYNC-01 [PR #17](https://github.com/hallanbrito/CHDevFlow/pull/17) · **Padrão:** [RUC/1.0](RELATORIO-UNIVERSAL-CH-v1.0.md).  
**Estado:** implementação proposta em branch isolada / Draft PR; **sem execução remota de escrita autorizada**.

## Escopo e separação de responsabilidades

O script \`scripts/ch_project_assist.py\` reduz a organização manual do Kanban, mas **não autoriza a si mesmo**. O PO concede autorizações específicas externas a esta ferramenta; etiquetas \`ch:*\`, Issue aberta, digitação de uma frase ou hash **não são prova de decisão do PO**. A aplicação real do plano não faz parte do gate que autorizou esta implementação.

Não despacha Codex/AGY, não toca HallanCraft, não executa merge/deploy, não inicia cron, daemon ou GitHub Action mutável e não transfere tokens. Usa apenas a instalação \`gh\` do host CachyOS.

## Comandos autorizados nesta fatia: leitura e plano local

Na raiz do repositório, com o \`gh\` do host autenticado:

\`\`\`bash
# Inspecionar o Project #2; leitura remota e saída local.
python scripts/ch_project_assist.py

# Limitar diagnóstico a determinadas Issues, sem escrita.
python scripts/ch_project_assist.py --issues 8,18

# Gerar plano imutável para lote explícito de até cinco Issues.
# Só funciona se todas estiverem OPEN, status Todo, labels inequívocas
# e houver preenchimentos elegíveis sem conflito.
python scripts/ch_project_assist.py --issues 19 --plan-file /tmp/ksync03-plano.json

# Testes unitários 100% offline, sem gh real.
python -m unittest discover -s tests -v
\`\`\`

O plano JSON contém escopo, os campos propostos, snapshots SHA256 da leitura e digest SHA256 da proposta. Não contém segredo. O arquivo não pode sobrescrever caminho existente. SHA256 aqui detecta divergências acidentais, **não é assinatura criptográfica do PO**.

## Aplicação futura: IMPLEMENTADA, mas **NÃO AUTORIZADA NESTA FATIA**

Após futura autorização PO por lote, a interface técnica prevista é:

\`\`\`text
python scripts/ch_project_assist.py --apply-plan CAMINHO --confirm SHA256_DO_PLANO
\`\`\`

**Não executar agora.** Antes de qualquer escrita, essa interface exige:
- Terminal interativo local (recusa cron/CI/pipe).
- Digest exato do plano e frase digitada no terminal.
- Releitura de todo o Project; \`totalCount\` íntegro, repositório/Issues corretos e *snapshots* idênticos.
- Até 5 Issues, 10 campos, OPEN, \`status=Todo\`, \`ch:workflow\` e exatamente um executor.
- Só preencher \`Esteira\` e \`Etapa CH=BACKLOG\` se vazios; jamais mexer em \`Autonomia CH\` e \`Decisao PO\`.
- Nova consulta antes **e depois** de cada campo; se o plano remanescente mudar, interrompe. Sem retry automático ou rollback implícito.
- Falha parcial claramente informada. Operações GitHub não constituem transação atômica; uma alteração simultânea entre leitura e escrita (**TOCTOU**) ainda é risco residual.

**Atenção:** KSYNC-01 continua existindo e seu \`--apply\` original não recebe automaticamente essas salvaguardas. Não tratar as duas ferramentas como equivalentes. O assistente acrescenta um fluxo novo; não altera o sincronizador legado.

## Quadro de critérios de aceite

| Critério | Expectativa |
|---|---|
| Leitura sem escrita por padrão | Obrigatório |
| CLOSED, labels conflitantes e status fora de Todo | Nunca propostos em lote de escrita |
| Repo diferente, JSON incompleto, duplicatas, URL errada | Falhar fechado |
| Plano alterado ou remoto divergente | Bloquear antes da escrita |
| Sem TTY e confirmação incorreta | Bloquear |
| Falha entre campos | Parar, indicar parcial, sem retry |
| Testes mocks offline | CI e local devem passar |
| Merge | Apenas decisão PO separada |
| Aplicação real | Outra autorização específica por lote |

## RUC/1.0 — nove seções de auditoria desta Fatia

1. **Identificação:** KSYNC-03 #19, executor ChatGPT, CH-1 de implementação autorizada, sem CH-2.
2. **Resumo executivo:** protótipo assistido; status de homologação pendente do PO.
3. **Consultas/atividades:** GitHub fonte remota para baseline; criação de código, testes e documentação em branch isolada.
4. **Evidências:** SHA de commit, arquivos do Draft PR e resultados dos testes, informados no parecer após CI.
5. **Verificações:** mocks offline; testes remotos com Project **NÃO_EXECUTADOS**.
6. **Riscos:** TOCTOU residual, falha parcial, administração do \`gh\` depende do host, confirmação digitada não equivale a identidade autenticada do PO.
7. **Alterações:** apenas três arquivos novos no repositório CHDevFlow (script, testes, documentação); nenhuma mutação de cards autorizada.
8. **Recomendação:** validar o Draft PR, CI e revisão de código; pilotar posteriormente com lote específico autorizado.
9. **Decisão necessária do PO:** revisar/homologar a implementação e **separadamente** decidir eventual merge e aplicação real.

**Registro semântico:** saída de testes é evidência de *simulação offline*, não demonstração de integração viva do Project nem autorização de operações futuras.
