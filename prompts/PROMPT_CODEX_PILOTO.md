# Missão para Codex — W-DEVFLOW-00: fundação documental HallanCraft

Você é Executor Agêntico CH-2 no projeto HallanCraft, sob governança do Método C.H. e decisão final exclusiva do PO Hallan.

## Primeiro: diagnóstico somente leitura

1. Leia `AGENTS.md`, `docs/PROJETO.md` e `docs/STATUS.md` na pasta **real** do HallanCraft. Esses arquivos preexistentes prevalecem sobre qualquer template fornecido.
2. Execute `git status --short`, `git branch --show-current`, `git remote -v` e identifique o HEAD. Informe se há alterações locais, conflitos ou remotos; **não descarte nem faça stash/reset**.
3. Mapeie árvore de arquivos rastreados sem incluir conteúdos de mundos, backups, `.env`, credenciais ou tokens.
4. Verifique com `gh auth status` se a conta está autenticada. Antes de criar repositório, confirme que não há remoto existente nem projeto com o mesmo conteúdo. Se houver dúvida, NÃO crie repositório duplicado.
5. Preserve as entregas reportadas de Codex `feature/bedrock-core@94afd4d` e AGY `03.2@9efbae2`; não faça merge nem mova essas branches.

## Escopo autorizado desta Fatia W

- Preparar uma branch **curta e isolada** a partir de uma base estável, como `codex/w-devflow-00-bootstrap` (não tocar a árvore suja; use worktree se necessário).
- Consultar o kit `CH-DevFlow`: analisar, adequar e usar `scripts/ch_init.py` com `--profile hallancraft` e depois `scripts/ch_tree.py` para gerar `docs/ARVORE_PROJETO.md` com base nos arquivos reais.
- Criar **somente se ausentes**: `docs/CH/PROTOCOLO_AGENTES.md`, `docs/CH/DECISOES.md`, `docs/CH/PILOTO_HALLANCRAFT.md`, `prompts/README.md`, templates de Issue/PR.
- Se já existir uma implementação equivalente, preferir apontar para ela em vez de criar duplicata. Não substituir `AGENTS.md` por `AGENTE.md`.
- Produzir relatório com diferenças, testes, árvores, caminho do GitHub e Draft PR. Não dar status de integrado a nada.

## GitHub

O PO quer um repositório GitHub como fonte canônica. Se HallanCraft ainda for local e não tiver remote, preparar publicação privada (`hallanbrito/HallanCraft`) **apenas após auditoria de arquivos rastreados e `.gitignore`**; nunca subir mundos, saves, Docker de produção, chaves ou outras informações sensíveis. Caso a publicação exija permissão adicional ou haja qualquer ambiguidade, informar a pendência ao PO. Não realizar force-push nem push direto em branch principal.

## Proibições

- Não alterar funcionalidade de Minecraft/Bedrock, mundo, saves, packs em produção, containers ou serviços.
- Não alterar `docs/PROJETO.md`, `docs/STATUS.md`, `AGENTS.md` existentes sem necessidade justificada e autorização adicional.
- Não aprovar PR em nome do PO; não fazer merge, deploy, release ou checkout destrutivo.
- Não marcar a automação Codex/AGY ou painel como implementados; são propostas para próximas Fatias W.

## Saída exigida

Relatório `docs/CH/RELATORIO_W_DEVFLOW_00.md` com inventário, riscos, arquivos novos, arquivos preservados, branch e SHA, `git status`, comandos de verificação, resultados reais, URL de Issue/Draft PR (se criada), tarefas ainda pendentes e proposta da W seguinte. Inclua prompt sanitizado na trilha de auditoria. Finalize em `AGUARDANDO_PO`.
