# CH-SEC-01 — Plano proposto para proteger a branch main

**Estado:** proposta documental CH-1 — **NÃO ATIVADA**.
**Repo:** [hallanbrito/CHDevFlow](https://github.com/hallanbrito/CHDevFlow) • **Issue:** [#10](https://github.com/hallanbrito/CHDevFlow/issues/10).
**Condição atual verificada em 18/10/2026:** `main` retornou `protected: false`; endpoint de rulesets retornou `[]`. A proteção exige ação nas configurações administrativas do GitHub, com autorização explícita do PO.

## Objetivo e ameaças cobertas

Impedir alterações diretas ou acidentais na `main`, force-push e exclusão; preservar o processo CH por Issue → branch → Draft PR → revisão humana → decisão PO → merge manual. **Não** tentar transformar comentário de bot, label ou campos de Kanban em aprovação humana autenticada.

## Configuração recomendada para dono único (proposta a validar na UI)

**Opção preferencial:** GitHub **Settings → Rules → Rulesets → New branch ruleset**, quando disponível para este repositório/plano. **Alternativa:** Settings → Branches → Add classic branch protection rule.

| Campo da regra | Valor proposto |
|---|---|
| Nome | `CHDevFlow — main protegida` |
| Target | Branch `main` exata, apenas CHDevFlow |
| Enforcement | `Active` **somente depois de aprovação**; durante preparação não criar regra ativa |
| Require a pull request before merging | **Sim**; sem bypass operacional automático |
| Required approving reviews | **0 / não ativar Require approvals** neste repositório de único mantenedor, para não exigir um segundo usuário; o aceite PO continua registrado explicitamente no PR/Issue |
| Block force pushes | **Sim** |
| Restrict deletions | **Sim** |
| Bypass de admins e apps | Preferir **nenhum**; verificar a capacidade real de bypass e o risco de auto-bloqueio antes de aplicar |
| Require status checks | **Não ainda**; corrigir e validar CI universal em Fatia W separada antes de torná-lo obrigatório |
| Require linear history / signed commits | **Não nesta fase**; exige revisão de estratégia de merge/assinatura |
| Restrict branch updates a bypass-only / lock branch | **Não**; poderia bloquear merges legítimos até por PR |

**Ponto fundamental:** o GitHub pode exigir PR sem obrigar revisão de segundo usuário. A permissão técnica para o titular fazer merge **não substitui a regra de negócio CH** de registrar aprovação humana com escopo, risco e justificativa. Em projeto pessoal o autor não pode suprir a revisão independente obrigatória da própria contribuição; não ativar 1 aprovação até haver outro revisor elegível.

## Porque o check atual NÃO deve ser obrigatório para todos

O workflow existente `.github/workflows/w1-checks.yml` dispara em `pull_request` somente para `scripts/**`, `tests/**` e o próprio workflow. PR documental, como o #9, **não dispara** o job `python-checks`. Se ele for selecionado como check requerido para todos os PRs, mudanças somente em Markdown podem ficar bloqueadas por check ausente/pendente.

**Proposta de melhoria futura (fora desta autorização):** criar e testar CI que rode em qualquer PR, ao menos uma checagem leve estável; **depois** considerar exigir seu job no branch ruleset. Isso exige uma nova Fatia W e autorização de alteração de código/workflow.

## Procedimento manual previsto (não realizar sem autorização)

1. PO revisa e aprova a configuração desta proposta na Issue #10.
2. Acessa [Settings do CHDevFlow](https://github.com/hallanbrito/CHDevFlow/settings/branches) (ou `Settings → Rules → Rulesets`).
3. Confirma disponibilidade e configura alvo `main`, PR obrigatório, força/exclusão bloqueadas, sem 1 review obrigatório, sem check required no momento, sem bypass inseguro. **Não usar `Lock branch`.**
4. Confere os efeitos e só então ativa a regra; documenta com captura sem credenciais, URL de rule/ruleset e horário.
5. Verifica pelo GitHub UI e leitura das regras efetivas (p.ex. `gh api repos/hallanbrito/CHDevFlow/rules/branches/main`, se API/autorização disponíveis), e abre um PR simples em branch isolada como **teste positivo**. Não fazer push direto nem tentativa destrutiva na `main` como teste.
6. Confirma que merge legítimo por PR continua permitido após decisão do PO e fecha #10 somente com evidência de regra **efetiva**.

Se o ruleset for indisponível, GitHub clássico é alternativa com regra para padrão literal `main`: habilitar PR obrigatório; não habilitar Required approvals; não permitir force-push/delete; considerar `Do not allow bypassing the above settings` só após revisar as consequências para o mantenedor.

## Critérios de aceite da implantação FUTURA

- [ ] PO aprovou configuração **e** autorizou ativá-la de modo separado deste documento.
- [ ] `main` abrangida por regra efetiva de PR obrigatório.
- [ ] Force-push e exclusão bloqueados.
- [ ] Nenhum bypass capaz de anular o gate sem registro foi mantido inadvertidamente.
- [ ] O titular ainda consegue abrir PR, revisar a própria evidência e integrar de forma legítima.
- [ ] Workflow de arquivos documentais não ficou preso por required check que não executa.
- [ ] Evidências registradas na Issue #10 (URL/captura/API), sem tokens.

## Fora de escopo e rollback

Esta proposta **não aplica** regras, não altera CI, não faz merge, não executa agentes e não toca HallanCraft. Se a proteção futura impedir o fluxo autorizado, **pausar merges e investigar**; modificar/desativar regra somente com aprovação do PO e registro do motivo, jamais por automatismo.

## Referências oficiais

- [GitHub — About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub — Managing a branch protection rule](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule)
- [GitHub — Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)