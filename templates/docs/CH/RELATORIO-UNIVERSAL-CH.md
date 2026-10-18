# RELATÓRIO UNIVERSAL C.H. — [EXECUTOR] — [MISSÃO]

> **Protocolo:** `RUC/1.0`  
> **Natureza:** modelo de relatório, **não uma autorização de execução**.  
> **Norma de referência:** [RUC v1.0](../../../docs/CH/RELATORIO-UNIVERSAL-CH-v1.0.md)

**Como usar:** substituir os valores em colchetes por dados comprovados. Se não puder comprovar, escrever **NÃO_VERIFICADO**; se não se aplicar, **NÃO_APLICÁVEL**. Remover instruções auxiliares antes de publicar. Não reproduzir segredos, tokens ou dados privados.

## 1. Identificação da missão

| Campo | Valor |
|---|---|
| Identificador | [repositório#issue e URL] |
| Executor declarado | [Codex / AGY / outro] |
| Coordenador / PO | [responsáveis] |
| Nível CH autorizado | [CH-0/CH-1/CH-2 + referência da autorização] |
| Ambiente | [host/sandbox, sem dado sensível] |
| Fonte da consulta | [SNAPSHOT_OFFLINE/LIVE_GITHUB/LOCAL_REPO/OUTRA] |
| Horário da execução | [ISO 8601 com fuso ou NÃO_VERIFICADO] |
| `run_id` / tentativa | [id/tentativa ou NÃO_APLICÁVEL] |
| Baseline / branch / PR | [SHA/URL ou NÃO_APLICÁVEL] |
| Parecer técnico | [APROVADO_TECNICAMENTE/PARCIAL/BLOQUEADO] |

## 2. Resumo executivo

**Parecer:** [resultado técnico restrito ao objetivo autorizado].

[Em **até cinco linhas**: objetivo, resultado observado, principal limitação/bloqueio, mudanças realizadas ou não e decisão pendente. Não usar “100% de sucesso” fora do escopo testado.]

## 3. Consultas/atividades realizadas

| ID | Ação de fato executada | Resultado |
|---|---|---|
| A01 | [comando ou atividade sem credenciais] | [PASSOU/FALHOU/…] |
| A02 | [atividade adicional ou NÃO_EXECUTADO] | [motivo] |

**Fonte consultada:** [ex.: `project.json`, com data/hora de exportação conhecida ou DESCONHECIDA, tamanho, contagem e validade; OU URL e hora da consulta online].

**Fora do escopo:** [ações expressamente proibidas que não foram feitas].

## 4. Evidências verificáveis

| ID | Fato e classe | Fonte / limite |
|---|---|---|
| E01 | [OBSERVADO: campo ou resultado] | [comando, trecho, SHA ou arquivo] |
| E02 | [DECLARADO: informação do PO/executor] | [referência; não auditado] |
| E03 | [INFERIDO ou NÃO_VERIFICADO] | [premissas/impedimento] |

**Identidade da Issue (se aplicável):**
- `content.repository`: [valor observado / NÃO_VERIFICADO]
- `content.number`: [valor observado / NÃO_VERIFICADO]
- Estado GitHub `state`: [OPEN/CLOSED/… ou NÃO_VERIFICADO]
- Status nativo do Project `status`: [Todo/In Progress/Done/… ou NÃO_VERIFICADO]
- `labels`: [lista efetivamente observada]
- `esteira`: [PRESENTE valor / NULO / AUSENTE NO SNAPSHOT / NÃO CONSULTADO]
- `etapa CH`: [PRESENTE valor / NULO / AUSENTE NO SNAPSHOT / NÃO CONSULTADO]
- `autonomia CH`: [PRESENTE valor / NULO / AUSENTE NO SNAPSHOT / NÃO CONSULTADO]
- **Somente no corpo textual:** [ex.: `BACKLOG`, `CH-0`; nunca apresentar como campo preenchido]

**Limites de verificação:** [snapshot não confirma estado atual; relatório do agente não é auditoria independente; arquivos/etiquetas não autorizam trabalho CH-2].

## 5. Verificações e resultados

| Teste | Critério | Estado | Evidência |
|---|---|---|---|
| T01 | [critério mensurável] | [PASSOU/FALHOU/NÃO_EXECUTADO/NÃO_APLICÁVEL] | [E01 ou motivo] |
| T02 | [critério mensurável] | [estado] | [E02 ou motivo] |
| T03 | [controle de escopo e segurança] | [estado] | [fonte] |

**Observação:** teste não realizado permanece **NÃO_EXECUTADO**; não contar como êxito.

## 6. Riscos e bloqueios

| Risco | Impacto | Condição / mitigação |
|---|---|---|
| [ex.: snapshot desatualizado] | [Baixo/Médio/Alto + consequência] | [nova exportação autorizada] |
| [ex.: autenticação indisponível] | [bloqueia leitura online] | [retornar ao PO] |

**Condição de parada:** [se houver bloqueio de custo, permissão, segurança ou escopo, declarar parada imediata].

## 7. Alterações realizadas

**Declaração do executor:** [NENHUMA / listar alterações].  
**Escopo efetivamente verificado:** [sessão, diretório, repo ou remoto; se não houve auditoria independente, declarar].

| Item | Resultado |
|---|---|
| Arquivos modificados | [nenhum / paths autorizados / NÃO_VERIFICADO] |
| Commit(s) / branch | [SHA/URL / NÃO_APLICÁVEL] |
| Issue/Project/PR modificados | [nenhum / URLs / NÃO_VERIFICADO] |
| Deploy / merge | [não executado / fato observado] |
| Credenciais expostas | [não observado na sessão / requer auditoria] |
| Custo adicional | [R$ 0 **declarado** / auditoria indisponível / valor verificado, se houver prova] |

**Se CH-0:** todas as mutações devem ser `NENHUMA`. Se não for possível garantir, relatar desvio e bloquear homologação até investigação.

## 8. Recomendação técnica

**Parecer:** [APROVADO_TECNICAMENTE/PARCIAL/BLOQUEADO] **apenas para [escopo]**.

**Fundamento:** [2–4 frases que liguem a conclusão às evidências T01/E01].  
**Ajustes propostos:** [nenhum / mudanças futuras de escopo, explicitamente **não autorizadas**].  
**Capacidades não demonstradas:** [acesso vivo, execução CH-2, publicação automática, outros testes, quando aplicável].

## 9. Decisão necessária do Product Owner

**Decisão registrada:** **PENDENTE** (até evento expresso do PO com escopo).

| Opção do PO | Efeito permitido |
|---|---|
| **APROVAR relatório/ensaio** | [homologar somente o escopo avaliado] |
| **SOLICITAR AJUSTES** | [listar correções a propor] |
| **REPROVAR** | [encerrar sem homologação / justificar] |
| **AUTORIZAR NOVA ETAPA** | [**nova autorização separada** com Issue, escopo, nível e limites] |

**Atenção:** parecer do executor não equivale a aceite do coordenador; aceite do coordenador não equivale a homologação do PO; homologação documental não equivale a autorização CH-2, merge, deploy ou custo.

---

*Fim do modelo RUC/1.0. Preferir tabelas curtas e evidências fortes; organização visual inspirada no AGY e rigor factual inspirado no Codex. Não criar evidências, aprovações nem resultados que não existam.*
