# CH-GOV-01 / W-F2.2 — Admissão assistida do GitHub Project #2

**Origem:** Issue [#63](https://github.com/hallanbrito/CHDevFlow/issues/63).  
**Baseline:** merge da W-F2.1, commit 724386124415b54c04e7aa7e4760d7d0caac3766 na main.  
**Autonomia da implementação:** CH-2; não houve autorização de registro real no Project #2.  
**Código:** scripts/ch_project_assist.py (lógica), src/chdevflow/cli.py (roteador), tests/test_ch_project_assist.py (fakes).

## Semântica e isolamento

A criação da Issue gera candidata ao Intake F1; CONTENT_VALID comprova **somente o conteúdo**. A admissão no Project exige **uma decisão separada do PO por Issue, Esteira, Etapa e Autonomia CH**, confirmada por comentário GitHub autenticado. O registro no Project **não autoriza executar agentes**.

O antigo KSYNC-03 não foi modificado. O comando com argumentos antigos continua consultivo por padrão; a allowlist legado permanece restrita a Esteira e Etapa CH=BACKLOG. A nova rotina usa funções com prefixo de admissão, separadas de inspect, make_plan, validate_plan e apply_plan.

## Entrada de linha de comando

O comando de primeira classe funciona em checkout do repositório ou instalação editável, onde scripts/ch_project_assist.py está presente. A CLI principal faz apenas roteamento para o script pelo Python atual; pacotes wheel sem scripts/ precisam de distribuição adicional antes de suportar esse roteamento.

**Prévia sem escrita, sem necessidade de aprovação:**

    ch project admit --issue 84 --dry-run

**Plano pinado (somente quando já existe autorização específica do PO):**

    ch project admit --issue 84 --approval-comment 9875 --plan-file /caminho/plan.json --dry-run

O arquivo de plano é criado uma única vez com permissão 0600; nunca será sobrescrito. A impressão da prévia não implica aprovação de execução.

**Contrato de aprovação do PO** (comentário GitHub do usuário hallanbrito na Issue #63 ou na própria Issue alvo; exatamente uma linha):

    CH-GOV-01 ADMIT PROJECT#2 ISSUE#84 ESTEIRA=ChatGPT ETAPA=BACKLOG AUTONOMIA=CH-0

A CLI lê e verifica autor, Issue de origem, texto exato e versão atual do comentário. A autonomia declarada na Issue permanece mera proposta; **CH-0 é o padrão obrigatório**, e CH-1/CH-2/CH-3 exigem aprovação correspondente, expressa na mesma linha.

**Modo de aplicação futura (não autorizado para uso no Project real por esta W-F2.2):**

    ch project admit --issue 84 --apply-plan /caminho/plan.json --confirm <digest-exato> --audit-file /caminho/audit.jsonl

Exige plano válido, digest íntegro, comentário do PO revalidado, terminal interativo com frase de aprovação e auditoria JSONL 0600 exclusiva. O modo de aplicação está implementado **somente para testes offline nesta missão**; **não executar contra o Project real** sem autorização operacional futura individualizada do PO.

## Operações exatas e prevenção de dívida

1. Consultar Issue (incluindo ID GraphQL), Project e seus campos, snapshot de itens completo e histórico de trabalho; exigir OPEN, F1=CONTENT_VALID, uma etiqueta válida de executor, atividade CLEAR para propor BACKLOG.
2. Identificar zero ou um cartão existente. Se já possui os três campos esperados, a operação é idempotente sem escrita. Cartão parcial, duplicado ou conflitante exige reconciliação manual; o comando não o conserta automaticamente.
3. Resolver Project ID, Field IDs e Option IDs reais dos campos Esteira, Etapa CH e Autonomia CH; exigir tipos SingleSelect e opções exatas.
4. Gerar plano canônico e SHA-256 de Issue, snapshot e decisão. Na aplicação, reconstruir o plano inteiro a partir do LIVE e exigir igualdade estrita antes de cada escrita; a versão do comentário do PO também deve coincidir.
5. Executar addProjectV2ItemById para incluir a Issue; exigir item ID. Ler novamente o cartão: ele deve existir, corresponder à Issue e não ter valores inesperados.
6. Executar updateProjectV2ItemFieldValue para Esteira, Etapa CH=BACKLOG e Autonomia CH, nessa ordem. Revalidar o estado antes e depois de cada mutation e novamente no fim.
7. Registrar COMPLETE somente após verificação integral. Não tocar Status, Decisao PO ou campos diferentes dos três previstos.

A API GitHub Projects não fornece uma transação atômica entre adição e edições. Falha após tentativa de mutation, timeout, resposta sem ID, alteração concorrente, leitura parcial ou valor divergente resulta em **ABORT** e possível estado indeterminado. **Nenhuma repetição automática nem reversão destrutiva** é permitida. O PO deve realizar nova avaliação/reconciliação, não tratar o registro como concluído.

## Testes e não-regressão

A suíte de tests/test_ch_project_assist.py mantém casos KSYNC-03 antigos e acrescenta testes W-F2.2 com contexto simulado:

- F1 válido mas sem aprovação é bloqueado antes da escrita.
- Autonomia CH-0 não é copiada do corpo e uma elevação sem texto do PO é rejeitada.
- Adição + três alterações + read-back em sequência; idempotência quando o cartão já está correto.
- Cartão parcial/duplicado, Field ID/Option ID ausentes, PO falso, digest alterado, snapshot obsoleto.
- Falha após add, falha após primeiro campo e read-back divergente sem repetição cega.
- Dry-run não invoca nenhum adaptador GraphQL; CLI ch project admit apenas despacha.
- Revisão CI do HEAD exato é obrigatória antes da homologação.

## Limites

Nenhum script nesta W-F2.2 foi utilizado contra o Project real. Não houve autorização para executar o caminho de aplicação LIVE, para deploy, para merge nem para ativar agentes. O Auto-add legado permanece OFF conforme F2-0. A entrega será por Draft PR e auditoria do PO.
