# CH-PIPE-01 / F6 — Missões Python reais por manifesto (experimental)

**Status:** implementação em Draft, homologação real PENDENTE. Relacionado a Issue #85 e PR #83.
**Esta fatia NÃO ativa o comando de produção ch pipeline run.**

## O que foi generalizado

- AGY recebe os requisitos via prompt_ref e produz o conteúdo completo do arquivo definido em allowed_paths; não depende do laboratório fixo estoque.py.
- Reutiliza Mission e plan_manual_mission: valida SHA Git live, branch não protegida, worktree limpa, allowlist, prompt e timeout.
- Inicialmente, cada missão altera **apenas um arquivo Python** fora de tests/. Os testes independentes usam unittest discover na pasta tests/.
- AGY executa via CLI local autenticada, em modo plan sem ferramentas; Python verifica e grava o único arquivo autorizado; Codex audita o patch e os testes de forma somente leitura.
- Aprovação termina imediatamente; reprovação técnica gera feedback, com limite absoluto de 3 chamadas ao AGY e 2 devoluções.
- Erros de autenticação, quota, timeout, execução inconclusiva e violação do escopo bloqueiam sem retry.
- Registros por attempt-01, attempt-02, attempt-03, SHA, patch, logs sanitizados, parecer Codex, execucao.json e RELATORIO_COMPLETO_CH1.md.
- Na terceira reprovação, gera escalonamento_po.json **LOCAL**, com publicação remota PENDENTE_DE_AUTORIZACAO (Issue #86).

## Requisitos para execução manual

1. Preparar uma Git worktree **descartável** cujo nome comece com CH-Lab-. Não usar o clone principal nem diretórios pessoais.
2. Incluir prompt.txt e testes/test_*.py independentes, commitar tudo e deixar a worktree limpa.
3. Capturar o SHA do commit com git rev-parse HEAD.
4. Criar o manifesto JSON **FORA** da worktree, sem modificá-la, com o SHA, caminhos relativos, issue verdadeira e um único alvo Python.
5. Usar pasta de evidência NOVA fora da worktree.

Exemplo de manifesto (substituir pelos seus dados reais; base_sha precisa ter 40 caracteres hexadecimais):

    {
      "schema": "chdevflow.pipeline.manual/v1",
      "mission_id": "F6-PY-001",
      "repository": "hallanbrito/CHDevFlow",
      "issue": 85,
      "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "worktree": "C:\\CHDevFlow-Labs\\CH-Lab-001",
      "allowed_paths": ["src/exemplo.py"],
      "prompt_ref": "prompt.txt",
      "timeout_seconds": 480
    }

Execução experimental em PowerShell (exemplo, não executar em ambiente importante):

    python -m chdevflow.core.generic_cycle --manifest C:\CHDevFlow-Labs\missao-001.json --evidence-dir C:\CHDevFlow-Labs\CH-Dossie-001 --timeout 480 --i-accept-local-risk

**Aviso:** a execução de código gerado por IA dentro dos testes Python permite ações sob o usuário do host. NÃO HÁ sandbox de SO comprovado. O custo e as cotas não foram atestados. O uso das sessões autenticadas é voluntário; não usar informações privadas, segredos nem repositórios reais nesta fatia.

## Verificação offline

    python -m unittest discover -s tests -p "test_ch_pipe_01_f6_generic_cycle.py" -v

Os testes offline utilizam AGY e Codex simulados: não são prova de integração real. F6 não faz merge, deploy, cron nem escrita no Project #2.

## Limites ainda pendentes

- Arquivos múltiplos, stacks .NET, Java, Angular/TypeScript e comandos de teste não-Python.
- Readback/escalonamento remoto na esteira Project #2 (Issue #86) e idempotência remota.
- Recuperação de execução após crash: reutilização do dossiê é bloqueada para evitar chamadas duplicadas.
- Auditoria e validação de isolamento real no host Windows/Linux.
- Liberação de execução de produção, que continua proibida.
