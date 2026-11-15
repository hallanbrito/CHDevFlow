# CH-PIPE-01 / F4 — Evidência de custo e projeto de isolamento (SEM ativação)

**Issue:** #78 • **Governança:** #69 • **Dependências:** F1/#79 → F2/#80 → F3/#81 → F4.  
**Modo:** offline/read-only, exceto *processos Git usados apenas para diagnosticar a worktree*. **Sem execução de AGY/Codex/Docker, deploy, merge, cron ou escrita Project #2.**

## Objetivo e entrega

O PO solicitou fechar o preparo do piloto antes de liberar agentes reais. Esta fatia entrega:

1. **\`ch pipeline readiness --mission ... --json\`**: retoma o preflight do plano (Git HEAD, branch isolada, clean worktree), indica riscos de chave API **sem imprimir valores**, identifica presença das CLIs \`docker\`/\`podman\` com \`shutil.which\` e lista provas faltantes. **Sempre** \`BLOQUEADO_CUSTO\` quando a missão está estática/documentalmente elegível; se nem isso estiver, \`BLOQUEADO\`. Não há caminho para \`can_execute_agents=true\`.
2. **\`ch pipeline sandbox-plan --lab-dir ... --runtime docker|podman --image IMAGE@sha256:... --json\`**: prepara apenas uma **lista de argumentos** para um futuro ensaio de fakes em container, sem executá-la. Exige uma pasta minúscula que contenha somente a fixture fake allowlisted e marcador canônico.
3. **\`examples/ch-pipe-01-fake-lab/\`**: testes \`unittest\` sem agentes, segredos, APIs, dependências ou rede.
4. **Testes negativos:** sem PIN de imagem, \`.env\`, \`.git\`, caminhos extras, symlinks, arquivos grandes, falta de Docker/Podman, variáveis com API key, comprovante autodeclarado, CLI que não deve acionar agentes.

## Modos de autenticação e custo

As **páginas públicas** dos provedores indicam elegibilidade geral, **não provam o estado da sua conta**:

- OpenAI — Codex CLI pode entrar com **ChatGPT** (uso incluído sujeito a franquias/limites/créditos), ou com **API key** (cobrança padrão de API). Consulte o modo de autenticação **no próprio Codex**, sem imprimir segredo: https://learn.chatgpt.com/docs/auth?surface=cli e https://help.openai.com/pt-br/articles/11369540-using-codex-with-your-chatgpt-plan
- Google — Antigravity tem acesso individual de entrada e planos com cotas diferentes; caminhos empresariais/API podem cobrar consumo: https://antigravity.google/pricing e https://antigravity.google/docs/extensions

**Nenhum dado de autenticação, assinatura, cota, cobrança, crédito ou licença do PO foi consultado ao vivo nesta F4.** Não existe fonte autenticada de *conta* conectada ao preflight; assim, sempre retorna \`BLOQUEADO_CUSTO\`. Um arquivo local com \`{"verified": true}\` ou uma declaração no GitHub **não altera** esse status.

O diagnóstico inspeciona **apenas a existência** de nomes de variáveis de chave API em memória. Não registra valores. Chave presente é alerta, não prova de que a CLI esteja usando aquela chave; ausência também não prova autenticação ChatGPT/individual.

## Plano restrito de sandbox para FAKE

Apenas para um laboratório de testes que não chame modelos:

- Imagem com digest \`sha256\` pinado, já presente localmente (\`--pull=never\`).
- \`--network=none\`: sem chamadas externas, **incompatível com execução AGY/Codex real**.
- \`--read-only\`; montagem da **fixture fake somente leitura**; \`--cap-drop=ALL\`; \`--security-opt=no-new-privileges:true\`.
- Limites: \`--pids-limit=32\`, \`--memory=256m\`, \`--cpus=1\`; usuário 65534; tmpfs \`/tmp\` 32 MB.
- Comando permitido fixo: \`python -B -m unittest discover -s tests -p test_fake_agent.py -v\`; sem \`shell=True\` ou argumentos arbitrários.
- Allowlist: \`.chdevflow-fake-lab.json\`, \`tests/test_fake_agent.py\`, \`README.md\`; recusar \`.git\`, \`.env\`, arquivos extras, reparse points/symlinks, arquivos >16 KiB e pasta com muitos objetos.

**Limitações não resolvidas:** o blueprint não verifica se Docker/Podman está rodando, se engine opera em modo rootless, se a imagem pinada é confiável, se há acesso indevido a outros mounts, se o host Windows/WSL2 possui proteções adequadas ou se existe capacidade real de matar toda a árvore de processos. Nem mesmo Docker é garantia absoluta contra exploração do kernel. Ainda não há código que execute containers.

## Comandos PowerShell — Windows 11

Depois de abrir a F4 (empilhada, Draft) e instalar o projeto em editable:

~~~powershell
# Se $arquivo ainda aponta SHA antigo da F2/F3, readiness deve BLOQUEAR;
# replanejar a missão na branch correta antes de tentar nova avaliação.
ch pipeline readiness --mission $arquivo --json

# Exemplo somente de sintaxe — use um digest REAL e confiável da imagem local.
$imagem = "docker.io/library/python@sha256:" + ("a" * 64)
ch pipeline sandbox-plan --lab-dir ".\examples\ch-pipe-01-fake-lab" --runtime docker --image $imagem --json

# Continua INATIVO — nunca deve iniciar agentes.
ch pipeline run --mission $arquivo
~~~

**Nota:** o digest \`aaaa...\` acima é **placeholder sintático**, não uma imagem existente/validada. O comando pode gerar um plano, mas não tenta puxar nem executar a imagem. A execução de qualquer imagem precisa de revisão e aceite separado.

## Teste específico

~~~powershell
python -m unittest discover -s tests -p "test_ch_pipe_01_f4_readiness.py" -v
~~~

## Gate seguinte antes do piloto operacional

Faltam, independentemente deste código:
- Verificação de **conta e cobrança** via fonte autenticada do Codex e AGY, vinculada à sessão usada na CLI, comprovando que não há cobrança automática ou uso de créditos pagos;
- Avaliação do mecanismo de sandbox efetivo e da worktree descartável, sem secrets/host files, com isolamento, métricas, kill-tree e testes de falha;
- Aprovação do PO de **uma missão real** vinculada ao digest/base_sha, host, executor, modo de autenticação e orçamento;
- Runner real que revalide tudo no momento do disparo, com idempotência e falha segura.

Até lá: \`F4_IMPLEMENTADA\` (somente quando CI comprovar) / \`BLOQUEADO_CUSTO\` / \`BLOQUEADO_ISOLAMENTO\` / \`RUN_REAL_NAO_AUTORIZADO\`.

**RUC F4:** somente implementação, documentação e testes de fixtures offline; nenhuma comprovação de custo de conta; nenhuma execução de modelo/container; custo incremental do trabalho local declarado zero apenas no sentido de **nenhuma chamada faturável realizada por este código**, sem garantir despesas do ambiente do usuário.
