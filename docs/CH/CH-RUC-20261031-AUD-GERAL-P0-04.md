# Relatório Técnico de Auditoria e Implementação C.H. — Protocolo RUC/1.0

**Cabeçalho:** missão/Issue: [#51](https://github.com/hallanbrito/CHDevFlow/issues/51) | Épico: [#40](https://github.com/hallanbrito/CHDevFlow/issues/40) | Draft PR: [#52](https://github.com/hallanbrito/CHDevFlow/pull/52) | executor declarado: Google Antigravity (AGY) | auditoria independente: ChatGPT | PO: Hallan de Sousa Brito | autonomia e prova: CH-2 restrita à implementação, testes e Draft PR autorizada pelo PO em 31/10/2026 e ratificada em 02/11/2026 para ciclo R2 na Issue #51 | ambiente: Linux x86_64 / Python 3.14 (local) / Python 3.12 (CI) / GitHub CLI (gh) 2.67.0 | fonte: LIVE_GITHUB / WORKTREE_LOCAL | timestamp ISO 8601: 2026-11-02T14:45:00Z | baseline SHA: `f589da98f0ab50961c655b035816a776a56e1c9c` | reauditoria R2 SHA: `33dfe0994fc247539d294bc80c6e32cad3719ad2` | branch: `agy/p0-04-safe-verify-model` | resultado técnico: IMPLEMENTADO_AGUARDANDO_REAUDITORIA_CHATGPT_E_DECISAO_PO.

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
- **Estado Final:** `AGUARDANDO_REAUDITORIA_CHATGPT_E_DECISAO_PO`.

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

### 4.1 Módulo `src/chdevflow/core/trust.py` (Novo e Corrigido em R1)

Implementa o ciclo de vida da governança de confiança:
- `compute_project_fingerprint(project_root)`: Gera digest SHA-256 combinando `chdevflow.yaml`, arquivos de build (`package.json`, `pyproject.toml`, `requirements.txt`, etc.) e estado Git local relevante (`get_git_state`). Opera em modo fail-closed caso arquivos do manifesto ou build não possam ser lidos (`TrustIntegrityError`).
- `get_git_state(project_root)`: Captura o HEAD commit e inspeciona `git status --porcelain=v1 -uall`. Para cada arquivo relevante modificado ou não rastreado, calcula o hash SHA-256 de conteúdo (`code:path:content_hash`), falhando fechado caso ocorra erro de I/O (`TrustIntegrityError`). Garante que modificações sucessivas sob o mesmo código de status Git (ex: ` M core.py`) invalidem imediatamente a confiança.
- `grant_trust(project_root, declaration)`: Grava `.ch/trust.json` com permissões `0600` e notice explícito de consentimento e não-sandbox.
- `check_trust(project_root)`: Valida existência, integridade estrutural e correspondência exata do fingerprint. Retorna `(False, motivo)` caso arquivos tenham sido alterados, o registro tenha sido violado ou ocorra `TrustIntegrityError`.
- `invalidate_trust(project_root)`: Remove conscientemente o registro local de confiança.

### 4.2 Módulo `src/chdevflow/core/evidence.py` (Hardening Integral e Correção R1)

- `ALLOWED_VERIFICATION_BINARIES`: Allowlists de binários: `ch`, `python`, `python3`, `pytest`, `npm`, `pnpm`, `yarn`, `dotnet`, `mvn`, `gradle`, `cargo`, `go`, `echo`, `true`, `false`, `exit`.
- `ALLOWED_SUBCOMMANDS`: Restrição granular de subcomandos para cada adaptador.
- `ALLOWED_LIFECYCLE_SCRIPTS`: Restrição para `npm run`: apenas `test`, `test:unit`, `test:ci`, `lint`, `check`, `typecheck`, `build`.
- `sanitize_subprocess_env(source_env, project_root)`: Expurgador de variáveis de ambiente. Restringe a allowlist (`PATH`, `HOME`, `USER`, `LANG`, `LC_ALL`, `TMPDIR`, `PYTHONPATH`, `NODE_ENV`, `TERM`).
- Validação e confinamento de `PATH`: Rejeita caminhos relativos antes da canonicalização, remove diretórios graváveis por terceiros (`st.st_mode & 0o002`), diretórios dentro de `project_root` (anti-hijacking de binários) e pastas temporárias mundiais (`/tmp`, `/dev/shm`).
- `safe_resolve_executable(bin_name, sanitized_path, project_root)`: Localiza binário via `shutil.which` no PATH estritamente higienizado e valida permissões físicas de execução (`os.X_OK`) e integridade de origem.
- `parse_and_validate_command(cmd_str, project_root, sanitized_path)`: Parser defensivo sem shell, impedindo metacaracteres e bypasses.
- Leitura com teto real via threads (`_read_pipe_bounded`): Aloca no máximo 5 MB por pipe durante a leitura contínua, anexando aviso de segurança em caso de truncamento.
- Encerramento de grupo de processos em dois estágios com persistência de grupo (Correção R1 P0-03): Executa sob `start_new_session=True` em POSIX, definindo PGID isolado. Dispara `os.killpg(pgid, SIGTERM)` e monitora ativamente se qualquer processo do grupo sobrevive via `os.killpg(pgid, 0)` durante a carência de 2.0s (mesmo se o processo líder finalizar antes). Se remanescentes persistirem, emite `os.killpg(pgid, SIGKILL)` estritamente confinado ao PGID alvo.
- `run_verification(...)`: Suporte a `--trust`, `--dry-run`, `--timeout` e fail-closed em caso de erro no manifesto.

### 4.3 Módulo `src/chdevflow/core/submit.py`

- Validação rigorosa: `validate_and_submit` invoca `run_verification(target, trust=False)` para garantir que nenhum bypass de confiança seja concedido pelo pipeline de submissão.
- Se o projeto for untrusted ou se checks falharem, a operação é terminada imediatamente com `SubmitError`, sem interações remotas (`git push` / `gh pr`).

### 4.4 Módulos `cli.py`, `config.py` e `project.py` (Correção R1 P0-01)

- `cli.py`: Adicionadas as flags `--trust`, `--dry-run` e `--timeout` ao subcomando `ch verify`.
- `config.py`: Removido integralmente o parâmetro `auto_trust=True` de `save_manifest()`. A persistência do manifesto nunca concede confiança implícita.
- `project.py`: `create_project()` desacoplado de `grant_trust()`. Criar ou modificar um projeto nunca manifesta consentimento automático de confiança. Inclusão obrigatória de `.ch/trust.json` e `.ch/evidence/` no `.gitignore` padrão na inicialização do projeto.

### 4.5 Correções da Reauditoria Independente R2 (R2-01, R2-02, R2-03)

Sob autorização explícita CH-2 concedida pelo PO em 02/11/2026 (Issue [#51](https://github.com/hallanbrito/CHDevFlow/issues/51)), foram implementadas as seguintes correções pontuais e defensivas:

1. **R2-01 (P0) — Isolamento de execução e proteção contra Shadowing de `chdevflow`:**
   - Comandos internos confiáveis (`ch status`, `ch tree`) agora são executados diretamente in-process no ambiente controlado do verificador via `_run_internal_ch_command`.
   - Remove temporariamente qualquer caminho da raiz do projeto (`project_root`) ou de subpastas locais (`src/`) do `sys.path`, capturando stdout/stderr via `io.StringIO` sem spawnar subprocesso com `cwd=project_root`.
   - Impede que arquivos locais maliciosos (`chdevflow.py` ou pasta `chdevflow/`) na raiz do projeto analisado sobrescrevam ou façam hijacking dos módulos confiáveis da biblioteca `chdevflow`.

2. **R2-02 (P1) — Rastreamento abrangente de alvos e integridade de scripts do runner:**
   - Adicionada a função `_extract_explicit_targets` que analisa o manifesto `chdevflow.yaml` para registrar qualquer arquivo referenciado pelos comandos do runner, independentemente de sua extensão (ex.: scripts `.txt` ou executáveis sem extensão como `run`).
   - `_is_relevant_for_trust` agora classifica como relevante: arquivos de código (`CODE_EXTENSIONS`), executáveis com bit `+x`, arquivos sem extensão, arquivos de configuração/build e qualquer alvo explícito do runner (inclusive sob `docs/` ou subpastas).
   - Documentação estritamente textual/visual (`.md`, `.png`, etc.) não referenciada por comandos de execução é excluída do fingerprint, evitando falsos positivos durante o ciclo C.H. (ex.: geração de `docs/CH/*.md` em `ch mission new`).
   - Preservada a auto-exclusão segura de `.ch/trust.json` e `.ch/evidence/` para não invalidar a confiança com a persistência de relatórios.

3. **R2-03 (P1) — Gramática estrita e fail-closed de comandos Python:**
   - O parser léxico/sintático de Python agora opera com gramática estrita em estágios sequenciais:
     a) Rejeição imediata de stdin (`-`), flags proibidas (`-c`, `-i`, `-e`, `--command`) e qualquer forma compacta/anexada (`-cprint(42)`, `-uc`, etc.).
     b) Processamento de opções seguras do interpretador (`-u`, `-B`, `-v`, `-W`, etc.) exclusivamente antes da definição do alvo.
     c) Reconhecimento e validação estrita do alvo: módulo `-m <mod>` (restrito a `unittest` e `pytest`) ou script relativo contido no projeto.
     d) Validação física do arquivo de script via `.is_file()`, rejeitando scripts inexistentes ou diretórios.
     e) Argumentos subsequentes ao módulo ou script são preservados intactos como parâmetros da rotina de teste, evitando falsos positivos com flags legítimas (ex.: `-k test_smoke`, `-v`).

---

## 5. Matriz Completa de Testes de Segurança

Criada suíte dedicada em `tests/test_verify_security_p04.py` cobrindo **54 cenários automatizados** (11 positivos e 43 negativos/regressivos):

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
| **TN-31** | Auto-trust desabilitado (P0-01) | Negativo | `save_manifest` e `create_project` sem trust prévio | Nunca geram `.ch/trust.json`; manifestação separada | `APROVADO` |
| **TN-32** | Alterações sucessivas com mesmo status Git (P0-02) | Negativo | Modifica `core.py`, concede trust, modifica novamente com mesmo status ` M` | Hash de conteúdo SHA-256 altera; confiança invalidada | `APROVADO` |
| **TN-33** | Falha fechada em arquivo ilegível (P0-02) | Negativo | Arquivo em working tree ilegível sem permissão de leitura | Dispara `TrustIntegrityError` fail-closed, confiança negada | `APROVADO` |
| **TN-34** | Timeout com término precoce do líder (P0-03) | Negativo | Processo pai finaliza mas filho persistente continua | Varredura ativa de PGID envia `SIGKILL` confinado ao grupo | `APROVADO` |
| **TN-35** | Shadowing de pacote `chdevflow` por pasta local (R2-01) | Negativo | Pasta maliciosa `chdevflow/` na raiz do projeto | Pacote confiável não é sobrescrito; execução in-process isolada de `sys.path` | `APROVADO` |
| **TN-36** | Shadowing de pacote `chdevflow` por módulo local (R2-01) | Negativo | Arquivo malicioso `chdevflow.py` na raiz do projeto | Módulo confiável executado sem importação do arquivo local | `APROVADO` |
| **TN-37** | Alteração em script sob `docs/` invalida trust (R2-02) | Negativo | `docs/probe.py` referenciado no runner | Modificação detectada; invalida fingerprint e revoga confiança | `APROVADO` |
| **TN-38** | Script com extensão documental `.txt` invalida trust (R2-02) | Negativo | `python3 docs/probe.txt` referenciado no runner | Modificação detectada; rastreado por `_extract_explicit_targets` | `APROVADO` |
| **TN-39** | Script sem extensão invalida trust (R2-02) | Negativo | Script executável sem extensão referenciado no runner | Rastreamento ativo; invalida confiança | `APROVADO` |
| **TN-40** | Persistência sob `.ch/` preserva trust (R2-02) | Positivo | Relatório de evidência gerado em `.ch/evidence/` | Ignorado pelo fingerprint; trust preservado | `APROVADO` |
| **TN-41** | Workspace fora do Git detecta alterações (R2-02) | Negativo | Modificação de script em workspace sem `.git` | Fingerprint sem Git recalcula e invalida confiança | `APROVADO` |
| **TN-42** | Flags compactas proibidas em Python (R2-03) | Negativo | `-cprint(42)`, `-uc`, `-i tests/t.py` | Rejeição fail-closed com `VerificationSecurityError` | `APROVADO` |
| **TN-43** | Execução via stdin rejeitada (R2-03) | Negativo | `python3 -` | Rejeição fail-closed imediata | `APROVADO` |
| **TN-44** | Alvo inexistente ou diretório rejeitado (R2-03) | Negativo | `python3 nonexistent.py` ou `python3 docs` | Rejeitado fail-closed com `VerificationSecurityError` | `APROVADO` |

---

## 6. Resultados de Testes e Integração Contínua

- **Testes de Segurança Locais (`test_verify_security_p04.py`):** 54/54 aprovados (100%).
- **Suíte Completa Raiz (`tests/`):** 253 testes aprovados, 1 pulado (pytest opcional localmente), 0 falhas, 0 erros.
- **Suíte Sentinela (`apps/bootstrap/sentinela/tests/`):** 69/69 testes aprovados (100%).
- **Suíte Control Center (`apps/control-center/tests/`):** 53/53 testes aprovados (100%).
- **Total Local Executado:** 375 testes automatizados aprovados, 0 falhas, 0 erros.
- **Checagem de Diff (`git diff --check`):** 100% limpo, sem erros de whitespace ou formatação.
- **Integração Contínua (GitHub Actions):**
  - **Run ID:** [41261101918](https://github.com/hallanbrito/CHDevFlow/actions/runs/41261101918)
  - **Job:** `python-checks`
  - **Status:** `completed` / `conclusion: success` (Tempo de execução: 51s).
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

**Estado Final Obrigatório:** `AGUARDANDO_REAUDITORIA_CHATGPT_E_DECISAO_PO`.
