# CHDevFlow — Documento do produto (fonte canônica de escopo)

> Estado de referência: 16/11/2026. Documento de arquitetura, não autorização de execução.
> **Primeira leitura obrigatória** de quem supervisiona ou implementa a fábrica.

## A alma do projeto

O **CHDevFlow** é uma fábrica de desenvolvimento humano–IA: transformar uma ideia/Issue em uma pequena entrega testada, revisada e decidida pelo PO, reduzindo o esforço manual a cada ciclo. A fábrica deve ajudar a construir a segunda ferramenta, que ajude a construir a terceira, até poder propor melhorias no próprio CHDevFlow (**bootstrap supervisionado**).

**A métrica de valor é software útil entregue com menos intervenção humana**, não o número de PRs, testes, relatórios, fases, atestações ou gates produzidos.

## Fluxo mínimo do produto

1. Hallan (PO) escolhe uma Issue ou missão de escopo pequeno e autoriza o disparo.
2. Control Center inicia **no host local autorizado** uma execução usando o motor Python **já existente**.
3. AGY/Antigravity gera código real, em espaço descartável, dentro do escopo permitido.
4. Python executa testes de aceitação previamente definidos e não editáveis pelo agente.
5. Codex revisa tecnicamente código, diff e testes, sem aprovar a própria implementação.
6. Se houver reprovação técnica, o motor pode devolver feedback ao AGY dentro do limite existente de três tentativas. Problemas de credenciais/quota/infraestrutura bloqueiam, não geram loop.
7. CH-1 confronta dossiê e parecer; Hallan aprova, pede correção ou reprova. **Nenhum merge/deploy automático.**

A primeira fatia de produto útil, **CC-DESPACHO-01 / Issue #121**, conecta a tela `/missoes` ao motor local. Não criar outro orquestrador. O piloto local precede qualquer publicação remota F7.

## Fronteiras estáveis

- **GitHub**: fonte versionada de Issues, PRs, commits, decisões e aceite. **Project #2** é visualização operacional, não autorização para executar agentes.
- **Core Python** (`src/chdevflow/core/`): contratos, CLI, validação, executor local, pipeline de tentativa/correção e relatórios.
- **Sentinela** (`apps/bootstrap/sentinela/`): consulta/governança e FakeWorker; suas simulações **não podem virar despacho real silenciosamente**.
- **Control Center** (`apps/control-center/`): FastAPI/UI local com `/missoes`; na baseline registrada ainda lê/observa, não faz despacho real.
- **AGY**: executor principal de implementação, conforme comando e sessão real; **Codex**: auditor independente; **ChatGPT CH-1**: arquitetura, delegação e supervisão, sem substituir automaticamente o executor.

## Decisões de produto

- Disparo manual, uma missão ativa no piloto; no máximo 15 minutos de orçamento total por execução local, custo incremental R$0 comprovado, sem daemon/cron/loop infinito.
- Branch/worktree própria, mudanças limitadas por allowlist; sem tokens em prompt/log; sem tocar `main`, outro projeto, produção, saves de jogos ou dados sensíveis.
- Worktree **não** é sandbox do SO. O AGY em `--mode plan` devolve código para Python validar/materializar; o AGY em `--mode accept-edits --print` pode exigir permissões de ferramentas e falhar em headless.
- Em reprovação **técnica**, a regra posterior do PO permite 1 implementação + até 2 devoluções (3 chamadas máximas ao AGY); problemas de infraestrutura e custo incerto não autorizam retries.
- Comprovar **uma missão real via interface**, com dossiê e decisão PO, antes de expandir a arquitetura.
- F7 (custódia/publicação remota) permanece uma evolução opcional futura, congelada como prioridade enquanto o MVP local não estiver funcional. Preservar trabalho já feito, sem promover evidências de laboratório a produção.

## Fontes e precedência

1. Aprovação específica e atual do PO na Issue/PR aplicável; em caso de conflito, não executar ação arriscada sem resolver a diferença.
2. Este documento e `docs/CH/DECISOES.md` para escopo e políticas; `docs/RFC-CH-DEVFLOW.md` para visão e papéis.
3. `docs/CH/CHDEVFLOW-CONTEXTO.md` para índice de leitura e `docs/CH/CHDEVFLOW-EVIDENCIAS.md` para o que foi realmente testado.
4. Código **da revisão/branch inspecionada**; `docs/STATUS.md` para snapshot da baseline, nunca para supor que uma Draft PR já está na `main`.
5. Issue/PR/RUC/evidência de execução para fatos de uma tarefa; docs históricos não substituem CI no SHA exato.

O RFC histórico tem trechos de desenho preliminar; documentos W2-A foram escritos em fase de proposta e seu estado de 18/10/2026 **não representa o estado atual do código**. Confrontar sempre com o HEAD real.

Links: [RFC](../docs/RFC-CH-DEVFLOW.md) · [Issue #121](https://github.com/hallanbrito/CHDevFlow/issues/121) · [W2-A](W2-A/01-ARQUITETURA.md).
