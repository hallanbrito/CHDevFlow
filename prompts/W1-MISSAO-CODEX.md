# W1 — Codex: provisionar o Kanban C.H. DevFlow

**Issue oficial:** https://github.com/hallanbrito/CHDevFlow/issues/2

Objetivo: executar, na máquina de Hallan com GitHub CLI autenticado, o instalador revisado da W1 para criar/reutilizar o GitHub Project, com quatro esteiras e um portão de decisão do PO.

## Regras de segurança

- Primeiro confira docs/W1-ESTEIRAS-KANBAN.md e scripts/w1_github_project.py na branch W1.
- Verifique a conta GitHub autorizada; não solicite tokens em mensagens, não os registre em logs, arquivos ou prompts.
- Não altere o HallanCraft, servidores, Docker, worlds, saves, .env ou infraestrutura.
- Não faça merge de branches nem habilite auto-merge.
- Se o GitHub solicitar novo consentimento de escopo project, o próprio humano deve autenticar localmente.

## Execução

1. Execute python scripts/w1_github_project.py (prévia).
2. Confira gh auth status e o escopo project. Caso necessário, peça ao PO para completar gh auth refresh -s project no próprio terminal.
3. Após a aprovação da configuração pelo PO, execute python scripts/w1_github_project.py --apply.
4. Se ocorrer falha parcial, não destrua Project ou campos. Diagnostique e execute novamente; o script foi desenhado para preservar objetos já criados.
5. Faça verificação visual dos agrupamentos por Etapa CH e ativação do Auto-add se a interface estiver disponível; caso contrário, documente as duas ações pendentes.
6. Informe URL do Project, campos e views existentes, GitHub Issue W1 vinculada e evidências reais. Não declare homologação sem inspeção final humana.

## Entrega

Relatório para Issue W1: comando, saída sem segredos, link do Project, tabelas/visualizações verificadas, pendências, riscos e próximos passos. Estado AGUARDANDO_PO.
