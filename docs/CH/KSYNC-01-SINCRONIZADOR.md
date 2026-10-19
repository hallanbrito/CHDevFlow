# KSYNC-01 — Sincronizador conservador do Kanban pelo `gh`

**Estado:** proposta de implementação mínima, em **Draft PR**, sem ativação remota.  
**Fatia:** [KSYNC-01 #16](https://github.com/hallanbrito/CHDevFlow/issues/16) · **Project:** [C.H. DevFlow #2](https://github.com/users/hallanbrito/projects/2) · **Relatórios:** [RUC v1.0](RELATORIO-UNIVERSAL-CH-v1.0.md).

## Objetivo

Após o auto-add do GitHub Project, preencher campos personalizados básicos sem arrastar cartões manualmente, mantendo **GitHub como fonte da verdade** e **Product Owner como único aprovador**.

Não é um despachante. Não executa Codex, AGY, chamadas de modelos, cron, GitHub Action de escrita, PRs ou merges.

## Requisitos

- Linux/CachyOS com Python 3.12+ e `gh` instalado.
- Autenticação **no terminal normal do host**: `gh auth status -h github.com` (não copiar token; nunca usar `--show-token`).
- Escopo do GitHub CLI para Projects, já validado no host pelo PO. Se for necessário renovar permissões, isso exige ação humana separada.
- Repositório CHDevFlow disponível localmente; executar na pasta raiz, depois de atualizar a branch autorizada.

**Atenção:** o sandbox do Codex no piloto P0 não conseguiu ler as credenciais do host. Rodar o script **no terminal autenticado do PO**, não no sandbox, e não afrouxar permissões para contornar isso.

## Comandos

```bash
# Apenas leitura e plano; NUNCA altera dados por padrão.
python scripts/ch_project_sync.py

# Prévia restrita à Issue 16:
python scripts/ch_project_sync.py --issue 16

# Aplicação real: SOMENTE após revisão do PR e autorização do PO.
python scripts/ch_project_sync.py --issue 16 --apply

# Quando homologado para uso amplo, opção manual (não agendada):
python scripts/ch_project_sync.py --apply

# Testes offline, sem gh nem credencial:
python -m unittest discover -s tests -v
```

O modo prévia **consulta o GitHub por leitura** (não é offline); não faz operações de escrita. No futuro, atualização recorrente precisará de nova autorização e nova fatia.

## Contrato de preenchimento

| Campo | Condição para preencher | Valor |
|---|---|---|
| `Esteira` | Vazio + `ch:workflow` + **exatamente uma** etiqueta de executor | `ch:po→Hallan`, `ch:chatgpt→ChatGPT`, `ch:codex→Codex`, `ch:agy→AGY` |
| `Etapa CH` | Vazio + executor inequívoco + `status=Todo` + `gh issue view` confirmou `state=OPEN` + timeline sem PR/commit relacionado, consulta íntegra | `BACKLOG` |
| `Autonomia CH` | Nunca por este utilitário | **Sem alteração** |
| `Decisao PO` | Nunca por este utilitário | **Sem alteração** |

Regras adicionais:
- Valores existentes **nunca** são sobrescritos. Divergência entre etiqueta e `Esteira` existente gera aviso, não correção automática.
- Issue `CLOSED` não vira `HOMOLOGADA`, mesmo se GitHub exibir `Done`. Homologação requer evento explícito do PO e tarefa separada.
- A ausência das chaves no JSON é tratada como não preenchida, **não** como inexistência dos campos no Project.
- O JSON é obtido por `gh project item-list <n> --owner ... --format json`, **sem `--field`**: essas opções são incompatíveis nessa versão do `gh`.
- O script valida `totalCount` contra o array `items`, número+repositório, URL canônica, etiquetas e dados esperados. Dados incompletos causam bloqueio.
- A KSYNC-03.1 bloqueia a proposta automática de `Etapa CH=BACKLOG` se há PR/commit associado ou falha de consulta da timeline. `Esteira` continua independente; PR merged não autoriza homologação. Ver [KSYNC-03.1](KSYNC-03.1-RECONCILIACAO.md).
- `--apply` só usa `gh project item-edit ... --field Esteira|Etapa CH --value ...`; sem permissão para escrever no repositório, comentar Issues ou executar agentes.
- Não há transação entre vários edits; se o serviço falhar no meio, haverá possibilidade de aplicação parcial, informada na saída. Conferir Project e repetir após diagnóstico. A reexecução é idempotente **quando o estado remoto reflete as operações concluídas**.
- O plano é calculado usando estado do momento da leitura, sem lock remoto; para evitar concorrência, execute um sincronizador por vez, manualmente.
- Ao sincronizar muitos itens, aplicar com cuidado; use `--issue N` primeiro e mantenha a conferência humana.
- Custo de modelos: R$ 0 adicional; o script não usa nenhuma API paga de modelos. Eventuais limites/quotas do GitHub são responsabilidade da conta.

## Exemplo ilustrativo

```text
C.H. DevFlow — sincronização conservadora do Kanban
Modo: PRÉVIA (sem escrita)
#16 | Esteira: (vazio) -> ChatGPT | https://github.com/hallanbrito/CHDevFlow/issues/16
#16 | Etapa CH: (vazio) -> BACKLOG | https://github.com/hallanbrito/CHDevFlow/issues/16
Total de campos previstos: 2
Prévia concluída. Para aplicar: repita incluindo --apply.
```

O exemplo não é log de uma execução real; os campos atuais podem ter mudado.

## Segurança, verificação e critérios de aceite

- O processo não publica tokens. Não colar resultados sensíveis do `gh auth status`.
- Não interpretar comentários, labels, status, `Decisao PO`, corpo da Issue ou campos manipuláveis como aprovação para executar CH-2.
- Sem cron/daemon/CI mutável, sem merge, sem integração ao HallanCraft, sem subprocessos de Codex/AGY.
- **Teste unitário offline** deve cobrir roteamento, múltiplas etiquetas, erro parcial, etapa já preenchida, Issue fechada, dados truncados e prévia sem escrita.
- **Primeira aplicação real no Project** só após autorização específica do PO, primeiro com `--issue 16`, e com verificação visual/novo `gh project item-list`.
- A execução do script não protege a `main`. A proteção da branch permanece na [Issue CH-SEC-01 #10](https://github.com/hallanbrito/CHDevFlow/issues/10).
- Nenhum merge do Draft PR sem autorização expressa do PO.

## Evolução futura, não autorizada aqui

Uma próxima fatia pode criar comando de transição de `Etapa CH` com verificação de decisão do PO, exportação compartilhada com agentes e execução automatizada agendada **somente se houver aprovação específica**. O primeiro marco é **tirar do PO a tarefa de preencher Esteira e BACKLOG**, sem automatizar governança.
