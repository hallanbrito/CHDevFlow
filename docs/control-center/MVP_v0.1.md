# CHDevFlow Control Center — Proposta de Arquitetura MVP v0.1

**Data:** 19/10/2026
**Classificação:** CH-1 — proposta documental, sem autorização de implementação ou execução
**Product Owner:** Hallan
**Repositório de referência:** https://github.com/hallanbrito/CHDevFlow
**Piloto futuro:** HallanCraft, exclusivamente em clone/worktree autorizada
**Estado do documento:** PARA REVISÃO DO PO

## 1. Objetivo e fronteira da proposta

Construir **futuramente**, em Python, um painel web local para visualizar e preparar Fatias W e operar — somente depois de gates próprios — adaptadores do **Codex CLI** e do **AGY/Antigravity CLI**, com branches/worktrees isoladas, evidências, cancelamento e decisão humana.

O painel **não** substitui GitHub Issues/Projects/PRs como fonte de verdade, nem altera o método C.H. histórico. Não cria um segundo Kanban autoritativo. Não expõe API pública de execução, não opera 24/7 e não habilita acesso pago a modelos.

**Nesta etapa:** nenhum arquivo do repositório, branch, serviço, permissão, credencial, processo, Docker, mundo/save ou ambiente de produção foi alterado. A arquitetura não confere CH-2.

## 2. Fontes canônicas e decisões preservadas

Referências verificadas:
- [RFC-CH-DEVFLOW-001](https://github.com/hallanbrito/CHDevFlow/blob/main/docs/RFC-CH-DEVFLOW.md)
- [W2-A / arquitetura](https://github.com/hallanbrito/CHDevFlow/blob/main/docs/W2-A/01-ARQUITETURA.md)
- [W2-A / contratos](https://github.com/hallanbrito/CHDevFlow/blob/main/docs/W2-A/02-CONTRATOS.md)
- [W2-A / plano de testes](https://github.com/hallanbrito/CHDevFlow/blob/main/docs/W2-A/03-PLANO-DE-TESTES.md)
- [Issue #7 / decisões PO D01–D07](https://github.com/hallanbrito/CHDevFlow/issues/7)
- [Issue #8 / W2-A em revisão, PR #9](https://github.com/hallanbrito/CHDevFlow/issues/8)
- [KSYNC-03 / assistente com gate humano](https://github.com/hallanbrito/CHDevFlow/blob/main/docs/CH/KSYNC-03-ASSISTENTE.md)

**D01–D07 preservadas:** (D01) notebook CachyOS; (D02) AGY/Antigravity é executor prioritário do piloto, interface ainda exige homologação no host; Gemini CLI não é substituto tácito; (D03) CH-2 por missão, sem merge automático; (D04) HallanCraft é piloto futuro sem qualquer toque na produção; (D05) disparo manual, sem daemon/cron/polling; (D06) R$ 0 de custo adicional, uma missão ativa, 900 segundos por tentativa, no máximo um retry depois de diagnóstico, parada manual; (D07) autenticação segura no host, privilégio mínimo, trilha de autoria/run_id e proteção da branch principal.

Restrições adicionais: `main` protegido; PR Draft; aceite do PO é distinto de aprovação de executar; `STATUS.md` registra apenas marcos aceitos; `AGENTS.md`/`docs/PROJETO.md`/`docs/STATUS.md` preservados; nenhuma integração ou deploy sem autorização separada. `git worktree` é isolamento de checkout, **não sandbox de segurança**.

## 3. Decisão arquitetural proposta

### 3.1 Stack do MVP

| Camada | Proposta | Motivação |
|---|---|---|
| Linguagem | Python 3.12+ | Alinhamento com scripts existentes e CachyOS |
| Servidor | FastAPI + Uvicorn iniciado manualmente | Respeita RFC W3 e dá separação HTTP/worker |
| UI | Jinja2 + HTMX/JS mínimo + SSE | Interface leve no notebook, atualização de eventos sem SPA pesada |
| Tipos/contratos | Pydantic + JSON Schema versionado | Aplicação validável do contrato W2-A v0.1 |
| Git | `git` via subprocesso de argumentos fixos | Worktrees e validações explícitas, sem `shell=True` |
| GitHub | `gh` autenticado no host, inicialmente somente leitura | Reutiliza a fonte canônica e evita nova credencial de IA |
| Persistência local | JSONL 0600 + SQLite apenas para índice/cache opcional | Eventos e reserva/retomada locais; GitHub continua canônico |
| Executor | Supervisor de subprocesso com `run_id`, lock, timeout e cancelamento | Uma tarefa por vez, sem worker permanente |
| Agentes | Adaptadores `codex_cli` e `agy_cli` separados | Versões, flags, formatos e permissões diferentes |
| Testes | unittest/pytest com mocks, sem autenticação ou modelos nos testes básicos | Falhas e guardrails testados sem gastar créditos |

### 3.2 Desenho lógico

```text
Navegador local (127.0.0.1; sessão iniciada manualmente)
       │
       ▼
FastAPI — UI do PO (leitura / prévia / cancelamento)
       │
       ├── GitHubReader: Issue/PR/Project + decisão canônica
       ├── MissionValidator: schema/digest/SHA/escopo/risco/limites
       ├── AuthorizationGate: prova autenticada do PO, fora do texto de prompt
       ├── CostGate: modo sem API faturável + evidência de elegibilidade
       ├── GitWorktreeManager: allowlist, paths, branch por missão
       ├── RunSupervisor: um run, lock, 900s, kill do grupo, auditoria
       │      ├── CodexAdapter (versão/flags verificadas no host)
       │      └── AGYAdapter (versão/flags verificadas no host)
       └── EvidenceCollector: diff, testes, logs redigidos, RUC/1.0
                     │
                     ▼
         GitHub Issue + Draft PR + decisão humana
```

**MVP local somente:** `127.0.0.1` e sem proxy público. Uma aprovação de UI não autentica sozinha a identidade do PO: o fluxo de autorização CH-2 exigirá uma prova externa, verificável e vinculada ao *digest* exato da missão, por identidade GitHub do PO e credenciais segregadas da execução. Até isso ser projetado e testado, o botão de **Executar** ficará desabilitado.

### 3.3 Distribuição dos adaptadores

- **AGY / Antigravity:** continua sendo o executor prioritário do primeiro piloto operacional aprovado. Adaptador com prévia, execução não interativa com `agy -p` e `--output-format stream-json` *sujeitos à versão instalada e teste de permissões no CachyOS*. Verificar exit code **e** evento `result/status`, stderr e negações de ferramenta, pois exit code 0 pode não significar todas as ações realizadas. Nunca usar `--dangerously-skip-permissions`. No início, revisão/diagnóstico somente leitura.
- **Codex:** `codex exec --json --sandbox read-only -C <worktree> -` (prompt por stdin) no diagnóstico; modo de escrita `workspace-write` só com CH-2 individual. Nunca usar `--yolo` nem bypass de sandbox. Leitura de eventos NDJSON, verificação do resultado e supervisão de processo. `app-server` pode ser avaliado depois para aprovações ricas/continuidade, não no primeiro MVP.
- **Gemini CLI:** não substituir AGY automaticamente. Exige decisão do PO se futuramente entrar como terceiro adaptador.

A documentação pública de CLI prova que modos não interativos existem, mas **não comprova que o notebook local tem a mesma versão, autenticação, limites de uso ou sandbox adequado**. O diagnóstico inicial consulta versões e ajuda, sem consumir modelo.

## 4. Execução sequencial e isolamento

O MVP **não** libera duas missões simultâneas. O uso combinado dos agentes será inicialmente **sequencial**:

1. A Issue/W no GitHub descreve trabalho e escopo; o painel lê os campos, sem elevar permissões.
2. O PO vê prévia/diff da missão, baseline SHA completo, pastas permitidas e proibições.
3. Depois de autorização CH-2 comprovada para a *execução concreta*, um adaptador pode trabalhar em sua worktree; outro agente só revisará em missão separadamente autorizada, preferencialmente com leitura do artefato imutável e sem acesso à worktree de escrita do primeiro.
4. O supervisor inspeciona arquivos rastreados, não rastreados, ignorados, symlinks, mudanças de escopo, segredos e saída do processo. Se houver desvio ou dúvida, bloqueia a publicação e registra incidente.
5. Produz dossiê RUC/1.0 e, se a publicação estiver autorizada e segura, Draft PR. **Nunca merge automático.**
6. A decisão do PO é registrada com escopo; aprovação parcial gera Fatia W residual e exige nova autorização para a parte não aceita.

Para um mesmo assunto, exemplos de branches curtas: `agy/wXX-visual`, `codex/wXX-testes`. O segundo executor não reescreve a branch do primeiro. Integração de propostas divergentes exige PR/revisão humana.

**Isolamento real:** as worktrees devem ser criadas sob diretório autorizado e distinto da instalação em produção; arquivos de mundos/saves/Docker não entram na árvore. A política deve verificar `realpath`, symlinks, hardlinks/mount points quando relevantes e todos os arquivos alterados, inclusive ignorados. Isolamento de processo (sandbox/contêiner sem acesso à produção), usuário com menores privilégios e rede restrita são obrigatórios para comandos não confiáveis.

## 5. Contratos e identidade

Reutilizar o contrato `w2a-mission/v0.1`, acrescentando apenas extensão **proposta** específica de painel, nunca substituindo a versão canônica sem nova ADR. Campos mínimos para uma execução: Issue, repositório e allowlist, branch/base SHA imutável, executor, prompt por referência versionada, autonomia CH, limites, modelo/modo de autenticação aprovado, digest da missão, aprovação autenticada e referência do evento.

**Hash não é consentimento.** A autorização corresponde ao SHA256 do payload canonizado + identidade GitHub verificada do PO + evento com ID/timestamp e janela de validade + separação entre credenciais do operador e credenciais de publicação. Mudança em prompt, escopo, executor, SHA ou custo invalida aprovação.

Chave de idempotência: `repo + issue + mission_digest + attempt`. Usar trava exclusiva atômica por host e reconciliar runs inconclusivos antes de reiniciar. Um comentário GitHub ou coluna Kanban não é mutex distribuído.

### Estados de negócio vs estados de execução

- **Negócio:** BACKLOG → PRONTA → EM_EXECUCAO → EM_REVISAO → AGUARDANDO_PO → APROVADA/PARCIAL/CORRECOES/REPROVADA → INTEGRADA → HOMOLOGADA, conforme RFC.
- **Execução:** UNAUTHORIZED → ELIGIBLE → PREFLIGHT_OK → CLAIMED → RUNNING → EVIDENCE_PENDING → DRAFT_PR_READY → AWAITING_PO, com BLOCKED/CANCELLED/TIMED_OUT/INDETERMINATE sem avanço automático.

## 6. Segurança e custo zero como gates externos aos agentes

- A interface só recebe comandos previamente cadastrados; jamais construir shell a partir de texto de Issue, PR, caminho ou modelo. `subprocess` usa lista de argumentos e `cwd` validado.
- Sem `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY` ou outras variáveis de cobrança no ambiente do worker. Autenticar-se por login de plano existente **não significa acesso ilimitado**; se não for possível comprovar o modo de uso incluído e sem gasto adicional, **bloquear**.
- Não ler, copiar, transmitir, registrar nem expor OAuth/tokens do Codex/AGY/`gh` no painel, logs, prompt, banco de dados, diff ou relatório. Credenciais devem permanecer no cofre/armazenamento do cliente oficial, sob controles do SO.
- Não fornecer ao processo do agente acesso irrestrito a `$HOME`, ao socket Docker, a chaves SSH, variáveis de ambiente sensíveis, volumes da produção ou GitHub com credencial capaz de integrar na `main`.
- Separar permissão de **ler**, **preparar**, **executar**, **publicar Draft PR**, **aprovar** e **integrar**. Cada escalonamento tem gate independente. No MVP inicial, apenas ler/preparar/simular.
- Logs sanitizados sem prompts secretos, caminhos pessoais desnecessários ou raciocínio privado. Salvar run_id, executor, versão de adaptador, SHA base, branch, duração, checks, diff seguro, incidentes e decisões.
- `Stop` deve sinalizar o grupo de processos, aguardar prazo de graça curto e forçar encerramento, sem matar outros programas do usuário; não excluir worktree automaticamente.
- A versão inicial fica local e com proteção contra CSRF no servidor; autenticação forte separada e controle de acesso são exigidos antes de acesso remoto ou de permitir decisões CH-2 pela UI.

## 7. Mínimo de telas

1. **Visão geral:** GitHub Project #2, Issue, executor e estado canônico, sem duplicar decisões.
2. **Missão:** objetivo, CHAVE, prompt versionado, files allowlist, baseline SHA, custo/status de autorização, prévia antes de qualquer ação.
3. **Operários:** status local dos CLIs (instalado, versão, login detectado sem revelar segredo, modos suportados, pendências).
4. **Execução:** na primeira fatia apenas mock/dry-run; posteriormente, progresso de eventos, elapsed, cancelar e erros de permissão.
5. **Auditoria/PO:** evidências RUC/1.0, diff, resultados e links da Issue/PR; botões de decisão só quando o controle de identidade estiver homologado.

## 8. Fases propostas (cada uma exige aprovação distinta)

| Fatia proposta | Entrega concreta | Permitido nesta proposta? |
|---|---|---|
| CC-00 / CH-1 | Esta especificação e decisão arquitetural | Sim, somente fora do repo |
| CC-01 / CH-1 ou implementação especificamente autorizada | Esqueleto FastAPI **somente leitura**, consultando Project #2, sem workers | Não autorizado a implementar por esta proposta |
| CC-02 / implementação autorizada | Validator + políticas + fake adapters + worktree manager em diretório sintético; testes offline T01–T28 | Não autorizado |
| CC-03 / implementação autorizada | Diagnóstico de compatibilidade sem consumo de modelo; adaptadores reais inicialmente read-only | Não autorizado |
| CC-04 / CH-2 por missão | Primeiro AGY em tarefa inofensiva do HallanCraft sob segurança e prova de custo zero | Não autorizado |
| CC-05 / decisão separada | Codex para implementação/revisão em worktree própria e eventual fluxo sequencial AGY→Codex | Não autorizado |
| CC-06 / decisão separada | Draft PR e governança de aprovações autenticadas integradas ao painel | Não autorizado |

W2-A (#8, Draft PR #9) continua em revisão; não ignorar sua homologação ou fazer mudanças concorrentes. Criar proposta de novo conjunto de Issues apenas após conciliação do PO com W2/W3 existentes.

## 9. Critérios de aceite para um MVP real

- **A1:** abrir interface manualmente em `127.0.0.1`, com leitura e sem qualquer escrita remota por padrão.
- **A2:** corresponder às Issues, decisões e Project reais; divergência implica BLOCKED, nunca aprovação inferida.
- **A3:** prévia determinística de missão com digest e baseline SHA fixos; aprovação inválida após edição.
- **A4:** testes negativos T01–T09, T12–T17, T20, T24–T26 da W2-A passam com **mocks offline** e evidência real, nunca simulada como homologação.
- **A5:** limite de uma execução, 900 segundos, cancelamento, idempotência e um retry após diagnóstico demonstrados nos testes de supervisão.
- **A6:** uso dos CLIs apenas após compatibilidade, permissão, login e **custo adicional zero comprovados**. Sem API de cobrança.
- **A7:** revisão e diff fora da produção; HallanCraft não é lido/modificado até autorização específica. Branches/worktrees descartáveis não conferem isolamento de segurança sozinhas.
- **A8:** nenhuma mutação de `main`, integração automática, deploy ou atualização do `STATUS.md` antes de aceite humano; PR sempre Draft.
- **A9:** RUC/1.0 reproduzível com run_id, executor, commits/artefatos, testes executados de verdade e riscos.
- **A10:** falhas ambíguas de autenticação/execução/rede/custo encerram em BLOCKED/INDETERMINATE e requerem diagnóstico humano.

## 10. Pendências antes da implementação

- Verificar **no host** `codex --version`, `codex login status` (sem exibir segredos), `agy --version`, `agy --help` e as versões de `gh`, Git, Python. Não instalar, atualizar nem executar modelos nesta etapa.
- Verificar método de **aprovação autenticada e vinculação criptográfica** do PO sem conceder ao worker poder de se autoaprovar.
- Decidir mecanismo específico de sandbox/processo para CachyOS, incluindo proteção de `/home/hallan/HallanCraft`, mundo familiar e Docker de produção.
- Confirmar custo/quotas e termos vigentes de *cada modo de login* oficial, inclusive limites de uso e eventuais créditos adicionais.
- Confirmar proteção real da `main` no GitHub e inexistência de bypass perigoso.
- Reconciliar o roadmap Control Center com a W2-A ainda pendente do aceite do PO e com a futura W3.

## 11. Encaminhamento recomendado ao PO

**Aprovar apenas a direção documental:** FastAPI leve + GitHub canônico + adaptadores independentes + worktrees por tarefa + supervisor manual + custo adicional zero. **Não** autorizar por esta aprovação a implementação, o login, o acionamento de agentes, o consumo de modelo, a instalação de dependências ou qualquer acesso ao HallanCraft. A primeira fatia futura recomendada é **CC-01 somente leitura**, numa branch curta do CHDevFlow e Draft PR, mediante autorização específica de arquivos e testes.

---

Documento independente preparado para revisão. Não constitui registro oficial até passar pelo gate do PO e ser integrado no repositório canônico.
