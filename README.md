# C.H. DevFlow

**Fundação experimental de esteiras de desenvolvimento humano–IA com governança do Método C.H.**

O **CHDevFlow** organiza o trabalho de Hallan (Product Owner), ChatGPT (orquestração e auditoria), Codex e AGY/Gemini (execução), usando GitHub como fonte de verdade versionada. O objetivo é evitar estados divergentes, registrar prompts e evidências, trabalhar por Fatias W e reservar as decisões de integração ao responsável humano.

> Estado: **MVP documental / piloto**, sem despachante autônomo nem painel em produção.

## Navegação

- [RFC de arquitetura](docs/RFC-CH-DEVFLOW.md)
- [W1 — Esteiras e Kanban (instalado e homologado)](docs/W1-ESTEIRAS-KANBAN.md)
- [GitHub Project W1 — esteiras](https://github.com/users/hallanbrito/projects/2)
- [W2-A — Arquitetura documental (proposta em revisão)](docs/W2-A/01-ARQUITETURA.md)
- [W2-A — Contratos de missão e autorização](docs/W2-A/02-CONTRATOS.md)
- [W2-A — Plano de testes proposto](docs/W2-A/03-PLANO-DE-TESTES.md)
- [W2-A — Critérios de aceite e riscos](docs/W2-A/04-CRITERIOS-DE-ACEITE.md)
- [W2-A — Missão autorizada CH-1](prompts/W2-A-MISSAO-DOCUMENTAL.md)
- [W1 — Missão de provisionamento para Codex](prompts/W1-MISSAO-CODEX.md)
- [W1 — Issue de rastreamento](https://github.com/hallanbrito/CHDevFlow/issues/2)
- [Gerador de projeto C.H.](scripts/ch_init.py)
- [Gerador da árvore do projeto](scripts/ch_tree.py)
- [Modelos de arquivos para novos projetos](templates/)
- [Missão do Codex no piloto HallanCraft](prompts/PROMPT_CODEX_PILOTO.md)
- [Método C.H. original](https://github.com/hallanbrito/metodo-ch)

## Uso inicial

O gerador funciona em **prévia por padrão**; somente `--apply` cria arquivos ausentes:

```bash
python scripts/ch_init.py --path /caminho/do/projeto --profile hallancraft
python scripts/ch_init.py --path /caminho/do/projeto --profile hallancraft --apply
python scripts/ch_tree.py --path /caminho/do/projeto
```

Para outros projetos, use `--profile generic`. O gerador **não sobrescreve** arquivos existentes. A árvore é um inventário dos nomes dos arquivos rastreados pelo Git, excluindo diretórios e nomes sensíveis conhecidos; revise antes de publicar.

### Regras do piloto

- Trabalhar em branches curtas/worktrees isoladas e abrir **Draft PR**.
- Codex e AGY não têm autorização implícita para fazer merge, deploy, modificar mundos/saves ou acessar segredos.
- `AGENTS.md`, `docs/PROJETO.md` e `docs/STATUS.md` de projetos existentes devem ser preservados.
- Issues representam trabalho corrente; `STATUS.md` representa apenas marcos aceitos.
- O **Product Owner** aprova ou reprova as entregas com evidências.

O primeiro experimento será no projeto **HallanCraft**, com implantação controlada. Este repositório é do **framework**, não contém o código ou os mundos do Minecraft.

## Próximas etapas

1. Integrar a fundação documental após revisão do PO.
2. **W1 homologada:** Project #2 com esteiras e auto-add de Issues `ch:workflow`.
3. **W2-A em revisão:** documentação do despachante assistido, sem executável, em Draft PR.
4. Futuramente, somente com autorização própria: validar AGY/Antigravity no CachyOS, construir despachante e ensaiar tarefa CH-2 isolada no HallanCraft.
5. Desenvolver painel de aprovação e evoluir o `ch init` para CLI reutilizável.

**Importante:** o **Kanban W1** já está instalado e homologado; **despachante Codex/AGY, automação permanente e painel PO não estão implementados**. As decisões da W2 definem limites futuros, mas não constituem autorização para executar ou fazer merge.
