# Relatório Técnico de Auditoria e Implementação C.H. — Protocolo RUC/1.0

**Cabeçalho:** missão/Issue: [#51](https://github.com/hallanbrito/CHDevFlow/issues/51) | Épico: [#40](https://github.com/hallanbrito/CHDevFlow/issues/40) | Draft PR: [#52](https://github.com/hallanbrito/CHDevFlow/pull/52) | executor declarado: Google Antigravity (AGY) | auditoria independente: ChatGPT | PO: Hallan de Sousa Brito | autonomia e prova: CH-2 restrita à implementação, testes e Draft PR autorizada pelo PO em 31/10/2026 na Issue #51 | ambiente: Linux x86_64 / Python 3.14 (local) / Python 3.12 (CI) / GitHub CLI (gh) 2.67.0 | fonte: LIVE_GITHUB / WORKTREE_LOCAL | timestamp ISO 8601: 2026-11-01T01:00:00Z | run_id atual: [41259002591](https://github.com/hallanbrito/CHDevFlow/actions/runs/41259002591) (SUCCESS) | baseline SHA: `f589da98f0ab50961c655b035816a776a56e1c9c` | HEAD SHA: `26395685cbdf6b3f204949cec9007eb18bd300f9` | branch: `agy/p0-04-safe-verify-model` | resultado técnico: IMPLEMENTADO_AGUARDANDO_AUDITORIA_CHATGPT_E_HOMOLOGACAO_PO.

---

## 1. Identificação

- **Missão:** AUD-GERAL-P0-04 — Implementação do Modelo de Execução Segura do `ch verify`
- **Issue Oficial:** https://github.com/hallanbrito/CHDevFlow/issues/51
- **Épico:** https://github.com/hallanbrito/CHDevFlow/issues/40
- **Draft PR:** https://github.com/hallanbrito/CHDevFlow/pull/52
- **Repositório:** `hallanbrito/CHDevFlow`
- **Branch de Trabalho:** `agy/p0-04-safe-verify-model`
- **Worktree Isolada:** `/home/hallan/.gemini/antigravity/worktrees/CHDevFlow/auditoria_seguranca_ch_verify`
- **Baseline de Origem:** `f589da98f0ab50961c655b035816a776a56e1c9c` (`origin/main`)
- **Autonomia Autorizada:** CH-2 estritamente restrita a branch, commits, testes automatizados e abertura de Draft PR. Proibido merge em `main` ou encerramento de issue.
- **Papel do Executor:** AGY em execução especializada CH-2.
- **Auditor Independente:** ChatGPT (auditorias prévias CH-1 e homologação final).
- **Product Owner (PO):** Hallan de Sousa Brito.
- **Custo Adicional:** R$ 0,00 (Nenhum serviço faturável ou pacote pago utilizado).
- **Estado Final:** `AGUARDANDO_AUDITORIA_CHATGPT_E_HOMOLOGACAO_PO`.

---

## 2. Resumo Executivo

O `ch verify` é o gate central de verificação automatizada de conformidade documental e qualidade de código no ecossistema C.H. DevFlow. Na baseline histórica, a execução de comandos definidos em `chdevflow.yaml` operava sob `shell=True` sem validação estruturada, sem sanitização compulsória de variáveis de ambiente, com carregamento fail-open de manifestos e sem governança de consentimento para código não confiável.

Sob autonomia CH-2 autorizada pelo PO, foi implementada a arquitetura de execução defensiva e governança formal:

1. **Eliminação do interpretador de shell (`shell=False`):** Substituição integral por despacho direto via lista de argumentos estruturados (`tokens`), bloqueio de metacaracteres de shell (`;`, `&&`, `||`, `|`, `&`, `>`, `<`, `$()`, ``` ` ```), allowlist estrita de executáveis (`ALLOWED_VERIFICATION_BINARIES`) e subcomandos (`ALLOWED_SUBCOMMANDS`).
2. **Fechamento de bypasses de interpretadores:** Bloqueio de injeção por flags arbitrárias (`python -c`, `-i`, `-e`), restrição de módulos autorizados para execução sob Python (`unittest`, `pytest`) e restrição de scripts de ciclo de vida em Node (`npm run <script>`), impedindo bypasses como `npm run publish` ou `npm run deploy`.
3. **Confinamento de ambiente e resolução segura de PATH:**
   - Higienização compulsória de variáveis de ambiente (`sanitize_subprocess_env`), despojando ativamente tokens de acesso (`GITHUB_TOKEN`, credenciais de nuvem, strings de banco de dados).
   - Validação prévia de PATH antes de qualquer canonicalização: rejeição de entradas relativas (`.` ou `./bin`), diretórios permissivos a terceiros (*world-writable* sem sticky bit), diretórios situados dentro da raiz do projeto (`project_root`) para evitar binary hijacking local, e pastas temporárias mundiais (`/tmp`, `/dev/shm`).
   - Resolução física direta de `ch status --strict` pelo próprio interpretador Python ativo (`sys.executable -m chdevflow.cli`), eliminando dependência do binário global `ch` no PATH.
4. **Governança de Confiança Explícita (Project Trust):**
   - Criação de `src/chdevflow/core/trust.py` com registro de consentimento em `.ch/trust.json` sob modo POSIX `0600`.
   - Impressão digital composta (fingerprint SHA-256) atrelando o manifesto `chdevflow.yaml`, manifestos de build conhecidos e o estado Git local da working tree.
   - Detecção e invalidação automática diante de código modificado ou não rastreado (untracked code). Documentos (`docs/`), metadados (`.ch/`) e relatórios são categorizados adequadamente para permitir o ciclo natural de desenvolvimento sem falsos bloqueios.
   - O comando `ch submit` e agentes nunca concedem confiança automaticamente. Consentimento explícito exige `--trust`.
   - Documentação expressa de que o consentimento humano não substitui nem constitui sandbox de sistema operacional.
5. **Eliminação de comportamento Fail-Open:**
   - Carregamento de manifesto em modo fail-closed: erros de sintaxe YAML, tipos de dados inválidos ou comandos maliciosos abortam imediatamente a verificação com código de erro, sem fallback para comandos arbitrários.
   - Tratamento explícito de `ManifestSecurityError` distinguindo presença de segredos/tokens de erros comuns de schema.
   - Bloqueio rigoroso em `ch submit`: qualquer falha de verificação ou check reprovado aborta a submissão, impedindo push remoto (`git push`) ou criação/atualização de PR (`gh pr create`).
6. **Contenção de recursos e isolamento de processos:**
   - Leitura de saídas (`stdout`/`stderr`) com teto real de 5 MB mantido em memória durante a leitura contínua dos pipes, evitando truncamento meramente a posteriori.
   - Timeout com encerramento de grupo de processos em dois estágios (`SIGTERM` $\rightarrow$ carência 2.0s $\rightarrow$ `SIGKILL`), prevenindo processos zumbis ou órfãos em POSIX.

---

## 3. Evidências Factuais e Diagnóstico

Classificação rigorosa das evidências levantadas e verificadas no código:

| Código | Evidência / Fato | Status | Localização / Justificativa |
|---|---|---|---|
| **EV-01** | `ch verify` executava subprocessos com `shell=True` | `VERIFICADO` | Código original em `src/chdevflow/core/evidence.py` linha 68 invocava `subprocess.run(cmd, shell=True)`. |
| **EV-02** | Manifesto falhava aberto em caso de erro de YAML | `VERIFICADO` | Bloco `except ManifestError: pass` silenciava exceções e permitia fallback arbitrário. |
| **EV-03** | Variáveis de ambiente eram herdadas integralmente | `VERIFICADO` | `subprocess.run` sem argumento `env` herdava `os.environ` completo com `GITHUB_TOKEN`. |
| **EV-04** | Resolução de `ch` dependia do PATH global | `VERIFICADO` | Comando `ch status --strict` falhava se o pacote não estivesse instalado no PATH do SO. |
| **EV-05** | Memória ilimitada na captura de stdout | `VERIFICADO` | `capture_output=True` acumulava bytes indefinidamente na memória do processo pai. |
| **EV-06** | `shell=False` impede injeção de shell mas não limita chamadas de sistema | `VERIFICADO` | Processo filho compartilha o UID do operador; controle exige sandbox em nível de kernel (isolamento de contêiner). |

---

## 4. Módulos Implementados e Alterações

### 4.1 Módulo `src/chdevflow/core/trust.py` (Novo)

Implementa o ciclo de vida da governança de confiança:
- `compute_project_fingerprint(project_root)`: Gera digest SHA-256 combinando `chdevflow.yaml`, arquivos de build (`package.json`, `pyproject.toml`, `requirements.txt`, etc.) e estado Git local relevante (`get_git_state`).
- `get_git_state(project_root)`: Captura o HEAD commit e inspeciona `git status --porcelain=v1`, filtrando arquivos de código e scripts e ignorando modificações puramente documentais (`docs/`, `.ch/`, `.github/`, `*.md`).
- `grant_trust(project_root, declaration)`: Grava `.ch/trust.json` com permissões `0600` e notice explícito de consentimento e não-sandbox.
- `check_trust(project_root)`: Valida existência, integridade estrutural e correspondência do fingerprint. Retorna `(False, motivo)` caso arquivos tenham sido alterados ou o registro tenha sido violado.
- `invalidate_trust(project_root)`: Remove conscientemente o registro local de confiança.

### 4.2 Módulo `src/chdevflow/core/evidence.py` (Hardening Integral)

- `ALLOWED_VERIFICATION_BINARIES`: Allowlists de binários: `ch`, `python`, `python3`, `pytest`, `npm`, `pnpm`, `yarn`, `dotnet`, `mvn`, `gradle`, `cargo`, `go`, `echo`, `true`, `false`, `exit`.
- `ALLOWED_SUBCOMMANDS`: Restrição granular de subcomandos para cada adaptador.
- `ALLOWED_LIFECYCLE_SCRIPTS`: Restrição para `npm run`: apenas `test`, `test:unit`, `test:ci`, `lint`, `check`, `typecheck`, `build`.
- `sanitize_subprocess_env(source_env, project_root)`: Expurgador de variáveis de ambiente. Restringe a allowlist (`PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TMPDIR`, `PYTHONPATH`, `NODE_ENV`, `TERM`).
- Validação e confinamento de `PATH`: Rejeita caminhos relativos antes da canonicalização, remove diretórios graváveis por terceiros (`st.st_mode & 0o002`), diretórios dentro de `project_root` (anti-hijacking de binários) e pastas temporárias mundiais (`/tmp`, `/dev/shm`).
- `safe_resolve_executable(bin_name, sanitized_path, project_root)`: Localiza binário via `shutil.which` no PATH estritamente higienizado e valida permissões físicas de execução (`os.X_OK`) e integridade de origem.
- `parse_and_validate_command(cmd_str, project_root, sanitized_path)`: Parser defensivo sem shell, impedindo metacaracteres e bypasses.
- Leitura com teto real via threads (`_read_pipe_bounded`): Aloca no máximo 5 MB por pipe durante a leitura contínua, anexando aviso de segurança em caso de truncamento.
- Encerramento de grupo de processos em dois estágios: `start_new_session=True` em POSIX, disparando `os.killpg(pid, SIGTERM)` com carência de 2.0s antes de `os.killpg(pid, SIGKILL)`.
- `run_verification(...)`: Suporte a `--trust`, `--dry-run`, `--timeout` e fail-closed em caso de erro no manifesto.

### 4.3 Módulo `src/chdevflow/core/submit.py`

- Validação rigorosa: `validate_and_submit` invoca `run_verification(target, trust=False)` para garantir que nenhum bypass de confiança seja concedido pelo pipeline de submissão.
- Se o projeto for untrusted ou se checks falharem, a operação é terminada imediatamente com `SubmitError`, sem interações remotas (`git push` / `gh pr`).

### 4.4 Módulos `cli.py`, `config.py` e `project.py`

- `cli.py`: Adicionadas as flags `--trust`, `--dry-run` e `--timeout` ao subcomando `ch verify`.
- `config.py`: Validação de sintaxe estrita no manifesto (`verification.commands` não pode conter caracteres de controle ou metacaracteres de shell).
- `project.py`: Inclusão obrigatória de `.ch/trust.json` e `.ch/evidence/` no `.gitignore` padrão na inicialização do projeto.

---

## 5. Matriz Completa de Testes de Segurança

Criada suíte dedicada em `tests/test_verify_security_p04.py` cobrindo **40 cenários automatizados** (10 positivos e 30 negativos/regressivos):

| ID | Cenário | Tipo | Entrada Testada | Comportamento Observado | Resultado |
|---|---|---|---|---|---|
| **TP-01** | Comando direto simples | Positivo | `"echo 'validacao ok'"` | Executado sem shell (`shell=False`), state `PASS` | `APROVADO` |
| **TP-02** | Resolução segura de `ch` | Positivo | `"ch status --strict"` | Converte para `sys.executable -m chdevflow.cli`, state `PASS` | `APROVADO` |
| **TP-03** | Python módulo unittest | Positivo | `"python3 -m unittest"` | Permitido pela allowlist, executa sem shell | `APROVADO` |
| **TP-04** | Python script interno | Positivo | `"python3 tests/test_smoke.py"` | Valida caminho interno à raiz do projeto | `APROVADO` |
| **TP-05** | Adaptador npm e lifecycle | Positivo | `"npm test"`, `"npm run test:ci"` | Permitidos por `ALLOWED_LIFECYCLE_SCRIPTS` | `APROVADO` |
| **TP-06** | Fail-fast preservado | Positivo | `["exit 1", "echo 'segundo'"]` | Primeiro falha, segundo fica `SKIPPED`, overall `FAIL` | `APROVADO` |
| **TP-07** | Inspeção `--dry-run` | Positivo | `ch verify --dry-run` | Valida sintaxe sem disparar subprocessos, state `PASS` | `APROVADO` |
| **TP-08** | Subcomandos de adaptadores | Positivo | `"dotnet test"`, `"cargo test"`, `"go test"` | Subcomandos autorizados validados | `APROVADO` |
| **TP-09** | Simulação exit segura | Positivo | `"exit 0"` | Traduzido para código seguro de encerramento Python | `APROVADO` |
| **TP-10** | Permissões de trust | Positivo | `grant_trust` | Grava `.ch/trust.json` com `0600` e aviso não-sandbox | `APROVADO` |
| **TN-01** | Injeção de shell com `;` | Negativo | `"echo ok ; id"` | Rejeitado léxica/estruturalmente com `VerificationSecurityError` | `APROVADO` |
| **TN-02** | Injeção de shell com `&&` | Negativo | `"echo ok && whoami"` | Rejeitado léxica/estruturalmente com `VerificationSecurityError` | `APROVADO` |
| **TN-03** | Injeção com pipe `\|` | Negativo | `"echo dado \| cat"` | Rejeitado léxica/estruturalmente com `VerificationSecurityError` | `APROVADO` |
| **TN-04** | Expansão `$()` e crases | Negativo | `"echo $(uname -a)"` | Rejeitado léxica/estruturalmente com `VerificationSecurityError` | `APROVADO` |
| **TN-05** | Redirecionamento `>` / `<` | Negativo | `"echo evil > output.txt"` | Rejeitado léxica/estruturalmente com `VerificationSecurityError` | `APROVADO` |
| **TN-06** | Python com flag `-c` | Negativo | `"python3 -c 'print(1)'"` | Bloqueado: flag `-c` proibida em interpretador Python | `APROVADO` |
| **TN-07** | Python com flag interativa | Negativo | `"python3 -i tests/t.py"` | Bloqueado: flags interativas `-i`/`-e` proibidas | `APROVADO` |
| **TN-08** | Python módulo perigoso | Negativo | `"python3 -m http.server 8080"` | Bloqueado: módulo `http.server` não autorizado | `APROVADO` |
| **TN-09** | Path traversal em script | Negativo | `"python3 ../../outside.py"` | Bloqueado: script reside fora da raiz do projeto | `APROVADO` |
| **TN-10** | Script absoluto fora da raiz | Negativo | `"python3 /tmp/malicious.py"` | Bloqueado: caminho absoluto não autorizado | `APROVADO` |
| **TN-11** | Subcomando npm perigoso | Negativo | `"npm install"`, `"npm run deploy"` | Bloqueado por allowlist de subcomandos e scripts | `APROVADO` |
| **TN-12** | Injeção no prefixo `ch` | Negativo | `"ch status && echo hacked"` | Rejeitado por metacaractere proibido | `APROVADO` |
| **TN-13** | Binário perigoso do SO | Negativo | `"rm -rf ."`, `"curl http://..."` | Bloqueado: executáveis fora da allowlist | `APROVADO` |
| **TN-14** | Higienização de ambiente | Negativo | Ambiente com `GITHUB_TOKEN`, AWS | Tokens sensíveis expurgados do subprocesso | `APROVADO` |
| **TN-15** | Timeout com isolamento | Negativo | Script em loop infinito com timeout 0.5s | Grupo encerrado em 2 estágios sem zumbis, `TIMEOUT` | `APROVADO` |
| **TN-16** | Manifesto YAML quebrado | Negativo | `chdevflow.yaml` com sintaxe corrompida | Fail-closed imediato, overall `FAIL`, saída 1 | `APROVADO` |
| **TN-17** | Comandos não sendo lista | Negativo | `commands: "echo ok"` | Fail-closed: rejeita manifesto com erro estrito | `APROVADO` |
| **TN-18** | Item não-string na lista | Negativo | `commands: [123]` | Fail-closed: rejeita tipo de elemento inválido | `APROVADO` |
| **TN-19** | Comando em branco | Negativo | `commands: ["   "]` | Fail-closed: rejeita comando vazio | `APROVADO` |
| **TN-20** | `ch submit` em repo inseguro | Negativo | Submissão com comando fora da allowlist | Bloqueia submissão sem chamadas remotas (`SubmitError`) | `APROVADO` |
| **TN-21** | Entrada relativa em PATH | Negativo | `PATH=".:bin:/usr/bin"` | Entradas `.` e `bin` expurgadas antes de canonicalizar | `APROVADO` |
| **TN-22** | PATH world-writable | Negativo | Diretório com modo `0777` em PATH | Expurgado fail-closed da variável PATH | `APROVADO` |
| **TN-23** | PATH interno ao projeto | Negativo | Subpasta `local_bin` em PATH | Expurgado fail-closed (anti-hijacking de binários) | `APROVADO` |
| **TN-24** | Binário falso de `ch` | Negativo | Script falso `ch` no PATH | Ignorado; `ch` sempre resolve via `sys.executable` | `APROVADO` |
| **TN-25** | Modificação local de código | Negativo | Código novo não commitado com HEAD fixo | Trust invalidado automaticamente (`Confiança invalidada`) | `APROVADO` |
| **TN-26** | Adulteração de trust | Negativo | `.ch/trust.json` corrompido ou editado | Fail-closed: trust rejeitado | `APROVADO` |
| **TN-27** | Auto-trust no `ch submit` | Negativo | `ch submit` em projeto sem trust prévio | Bloqueio imediato; nunca concede confiança implícita | `APROVADO` |
| **TN-28** | Teto de 5 MB de saída | Negativo | Script gerando ~6 MB de texto | Truncado na leitura contínua com aviso de segurança | `APROVADO` |
| **TN-29** | Segredo no manifesto | Negativo | Manifesto contendo token `ghp_...` | Gera `ManifestSecurityError` distinto de erro de schema | `APROVADO` |
| **TN-30** | Declaração não-sandbox | Negativo | Inspeciona registro emitido | Contém aviso de consentimento e não-sandbox de SO | `APROVADO` |

---

## 6. Resultados de Testes e Integração Contínua

- **Testes de Segurança Locais (`test_verify_security_p04.py`):** 40/40 aprovados (100%).
- **Suíte Completa do Repositório (`tests/`):** 238 testes aprovados, 1 pulado (pytest opcional localmente), 0 falhas, 0 erros.
- **Checagem de Diff (`git diff --check`):** 100% limpo, sem erros de whitespace ou formatação.
- **Integração Contínua (GitHub Actions):**
  - **Run ID:** [41259002591](https://github.com/hallanbrito/CHDevFlow/actions/runs/41259002591)
  - **Job:** `python-checks`
  - **Status:** `completed` / `conclusion: success` (Tempo de execução: 37s).
  - Cobriu integralmente: Compilação sintática de todos os componentes, testes de governança W1, testes da raiz CLI (`tests/`), testes do Sentinela (`apps/bootstrap/sentinela/tests/`) e testes do Control Center (`apps/control-center/tests/`).

---

## 7. Limitações Técnicas e Fronteira de Segurança

> [!IMPORTANT]
> **Fronteira Defensiva e Limites do Não-Sandbox:**
> 1. O modelo implementado impede a injeção acidental ou proposital de operadores de shell, bloqueia a invocação de binários e subcomandos perigosos e protege as variáveis de ambiente ativas.
> 2. Contudo, **nenhum subprocesso em Python com `shell=False` constitui sandbox de sistema operacional**. O processo de teste/build executado pelo adaptador roda com as mesmas credenciais e UID do usuário do sistema operacional.
> 3. Projetos desconhecidos ou recebidos de fontes não confiáveis exigem inspeção humana prévia do código-fonte antes da concessão de confiança via `--trust`, ou execução em contêineres/VMs descartáveis isolados em nível de kernel.

---

## 8. Plano de Reversão (Rollback) e Condições de Parada

### 8.1 Condições de Parada
Caso seja identificada falha de segurança residual de severidade P0 ou necessidade de alterações fora do escopo autorizado pela Issue #51, a execução é interrompida imediatamente com estado fail-closed.

### 8.2 Procedimento de Reversão
Como o trabalho foi isolado na branch `agy/p0-04-safe-verify-model` e submetido exclusivamente como Draft PR [#52](https://github.com/hallanbrito/CHDevFlow/pull/52), o rollback é direto:
```bash
git checkout main
git branch -D agy/p0-04-safe-verify-model
# Opcional: fechar o Draft PR #52 sem merge
gh pr close 52
```

---

## 9. Parecer Final e Próximos Passos

A implementação CH-2 atende com precisão a todos os requisitos da Issue [#51](https://github.com/hallanbrito/CHDevFlow/issues/51), às diretrizes do Épico [#40](https://github.com/hallanbrito/CHDevFlow/issues/40) e aos apontamentos da auditoria independente prévia do ChatGPT.

Nenhuma alteração foi realizada na branch `main`. Nenhum merge foi executado. A vulnerabilidade não é declarada resolvida unilateralmente.

**Estado Final Obrigatório:** `AGUARDANDO_AUDITORIA_CHATGPT_E_HOMOLOGACAO_PO`.
