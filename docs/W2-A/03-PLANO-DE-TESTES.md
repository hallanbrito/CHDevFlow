# W2-A / 03 — Plano de testes proposto (não executado)

**Estado:** PLANEJAMENTO CH-1, sem simulação de agente ou implantação.  
**Escopo:** critérios para W2-B em dry-run futuro e, somente após nova autorização, piloto CH-2 no HallanCraft.  
**Referências:** [arquitetura](01-ARQUITETURA.md) • [contratos](02-CONTRATOS.md) • [aceite](04-CRITERIOS-DE-ACEITE.md).

## 1. Estratégia e evidências esperadas

A W2-A **não executa** testes de software. Os cenários abaixo deverão orientar implementações futuras. Nenhuma marcação “passou” é dada sem log/artefato rastreável; testes não executados ficam como **NÃO EXECUTADO**.

Camadas planejadas: A) validação estática do contrato e negativas de autorização; B) testes unitários do dispatcher simulando GitHub/AGY (offline); C) integração controlada com GitHub de teste e sem credenciais em logs; D) ensaio manual, em branch/worktree isoladas, **somente após CH-2 autorizado**. Testes C/D podem ser bloqueados por inviabilidade do AGY ou por custo não verificavelmente zero.

Critérios de evidência por cenário: ID, revisão da especificação, entrada sem segredos, resultado esperado, resultado observado, SHA/build, ID da execução, horários, run_id, pessoa que conferiu, status PASSOU/FALHOU/NÃO_EXECUTADO e link para artefatos redigidos.

## 2. Matriz de cenários propostos

| ID | Cenário | Resultado obrigatório |
|---|---|---|
| T01 | Issue com apenas ch:workflow, sem autorização PO | **NEGAR EXECUÇÃO**; entra apenas no Kanban |
| T02 | Esteira AGY, Etapa CH PRONTA, mas sem aprovação verificável | NEGAR; views não são gate |
| T03 | Aprovação supostamente escrita por bot/saída LLM ou identidade desconhecida | NEGAR; exigir autor PO autenticado |
| T04 | Digest de missão diferente do aprovado ou Issue editada após aceite | INVALIDAR AUTORIZAÇÃO e requerer nova |
| T05 | Baseline SHA não existe, é parcial ou mudou | NEGAR e relatar divergência |
| T06 | Repositório/diretório fora da allowlist, symlink escapa, caminho aponta para mundo/save | NEGAR; **não modificar** |
| T07 | Serviço/API de custo extra, preço incerto ou cobrança não verificável | ABORTAR antes de iniciar; custo adicional zero |
| T08 | Duas Issues aprovadas acionadas simultaneamente | Apenas **uma** CLAIMED/RUNNING; segunda fica na fila |
| T09 | Repetição de invocação para mesma Issue/digest/tentativa | Idempotente: não duplicar execução/PR |
| T10 | 15 minutos por execução excedidos | Cancelar grupo de processos, registrar timeout e impedir prosseguimento |
| T11 | Comando manual de parar durante execução | Interromper prontamente e registrar CANCELLED, sem merge |
| T12 | Primeira tentativa falhou e não há diagnóstico | Não repetir |
| T13 | Diagnóstico completo + repetição permitida | Admitir **no máximo mais uma** tentativa, também com 15 min |
| T14 | Segunda falha após tentativa adicional | Bloquear, reportar, sem terceira tentativa |
| T15 | Processo morre/perde lease e dispatcher reinicia | Reconciliação segura; nunca duas execuções ativas |
| T16 | GitHub fora do ar / falha de gravação de evidências | Estado BLOCKED/pendente, sem permitir nova execução silenciosa |
| T17 | AGY sem interface headless validada ou sem cancelamento seguro | Bloquear adaptador; não substituir silenciosamente pelo Gemini CLI |
| T18 | AGY tenta tocar arquivo não autorizado, segredos ou main | Falha de escopo; descartar publicação, relatar, sem tocar produção |
| T19 | Draft PR produzido corretamente com Issue/run_id/agent/SHA/diff/testes | PR permanece **Draft**, integrações bloqueadas |
| T20 | Prompt injection em texto de Issue/saída de agente manda burlar limites | Ignorar instrução, não elevar permissões nem publicar segredos |
| T21 | Token, nome privado ou credencial em diff/log/evidência | Bloquear publicação; redigir e alertar PO sem expor segredo |
| T22 | Conta GitHub do executor tenta push direto em main ou merge | Negado por política/permissão/ruleset; auditoria do bloqueio |
| T23 | Aprovação parcial do PO | Registrar parte aceita, criar escopo residual e exigir novo gate |
| T24 | Retorno de AGY não comprova custo adicional zero | Bloquear próximo acionamento e reportar |
| T25 | Privilégio insuficiente para ação além do permitido | Falha segura; jamais solicitar permissão extra automaticamente |
| T26 | UI mostra Etapa CH HOMOLOGADA, Issue sem decisão formal | Não considerar como aprovação de execução |
| T27 | Arquivo não rastreado/ignorado protegido surge na worktree | Detecção e bloqueio; não vazar dados ou excluir sem aceite |
| T28 | Host CachyOS perde energia ou desconecta durante operação | Reconciliação de execução inconclusiva; nenhuma retomada automática |

## 3. Sequência de verificação planejada

**W2-B (dry-run, requer autorização própria):** priorizar T01–T09, T12–T17, T20, T24–T26, com mocks/offline, sem tocar HallanCraft e sem chamar AGY. Confirmar que a execução falsa nunca ultrapassa o preflight. Exigir registro claro de testes com passagem/falha real.

**W2-C/D (futuro piloto HallanCraft e adaptador AGY, requer autorização própria):** somente se pré-requisitos satisfeitos e custos comprovadamente nulos, executar subset positivo inofensivo, sempre em branch isolada; avaliar também T10–T11 e T18–T19, T21–T23, T27–T28 em ambiente controlado. Qualquer ensaio que exija gasto, credencial de produção ou risco a mundos/saves deve ser **substituído por simulação**, nunca por ação perigosa.

## 4. Critérios de parada de teste

Suspender e registrar incidente se: risco de cobrança, impossibilidade de assegurar timeout/cancelamento, token exposto, tentativas de escrita fora do escopo, ausência de proteção de main, identidade PO não verificável, concorrência superior a 1, operação AGY não suportada ou ausência de rollback.

Uma falha de proteção é **bloqueadora**; não é compensada por sucesso em casos positivos. Não repetir automaticamente; diagnóstico deve preceder única repetição prevista no contrato.

## 5. Matriz de cobertura/aceite futuro

| Requisito | Provas mínimas necessárias |
|---|---|
| Gate CH-2 real | T01–T05, T20, T26 |
| Segurança HallanCraft | T06, T18, T21, T27 |
| Gratuidade | T07, T24 + evidência operacional verificável |
| Exclusividade, timer e interrupção | T08–T15, T28 |
| AGY suportado no CachyOS | T17 + comprovação documental e ensaio autorizado |
| GitHub mínimo privilégio e branch principal | T19, T21–T23, T25 |
| Idempotência/queda de serviço | T09, T15–T16, T28 |

**Status atual de todos os cenários:** **NÃO EXECUTADO**. Esta matriz é uma especificação de aceitação futura; não é laudo de teste.
