# Segurança — Factory v2

Política proposta para implementação desde v0.2. Não representa segurança já comprovada. A versão legada teve execução de testes no host e isolamento/custo não verificados; não está liberada para produção.

## Docker obrigatório para execução autônoma
- Container efêmero por tarefa/missão e workspace dedicado; preferir Docker rootless ou user namespace com usuário não-root, cap-drop ALL, no-new-privileges, seccomp/AppArmor conforme plataforma.
- Sem privileged, sem socket Docker exposto aos agentes, sem montagem do home, SSH agent, chaves, credenciais ou diretórios externos indiscriminadamente.
- Root filesystem somente leitura quando viável; escrita restrita ao workspace e temporários; limites CPU, RAM, PIDs, disco, timeout; cleanup e cancelamento testados.
- Rede bloqueada por padrão para testes; para CLIs remotas, egress restrito e autenticado conforme endpoints necessários. Credenciais mínimas e específicas, nunca embutidas na imagem/logs. Se autenticação oficial não for compatível, marcar runtime bloqueado; não degradar silenciosamente ao host.
- Imagens fixadas por digest, revisão de dependências, scans/SBOM e atualizações; avaliar atestação/Sigstore conforme risco. Docker compartilha kernel: isolamento não equivale a VM ou garantia absoluta.

## Governança
Aprovação humana de escopo, execução, consumo adicional, publicação, merge e deploy; permissões e rede mínimas por papel. Prompt injection e conteúdo externo tratados como dados não confiáveis. Logs redigidos, trilha de auditoria, persistência separada por projeto, validação de paths/symlinks e artefatos. MCP não concede privilégios por si.

## Gate de aceite
Testes negativos de acesso a arquivos e segredos do host, rede, socket Docker, escape de workspace, escalada, limite de processos/recursos, cancelamento, crash e recuperação. Execução bloqueada se sandbox ou política não puderem ser verificados. Auditoria independente antes de declarar produção.

## Histórico que merece revisão
Issue #95 (achados de auditoria), #10 (proteção main), PRs #113–#120 (executor e atestação), #123 (piloto com isolamento não verificado). Encerramento de backlog não resolve achados. Reavaliar antes de liberar o novo runtime.

## Reportar vulnerabilidade
Preferir reporte privado por recurso de segurança do GitHub, se habilitado. Não publicar segredos ou detalhes exploráveis em issues públicas.
