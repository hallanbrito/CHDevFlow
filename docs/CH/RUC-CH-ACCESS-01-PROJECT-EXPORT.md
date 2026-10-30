# RUC/1.0 — CH-ACCESS-01 — Tentativa 1

**Cabeçalho:** missão/Issue: [#49](https://github.com/hallanbrito/CHDevFlow/issues/49) | executor declarado: Google Antigravity (AGY) | coordenação: ChatGPT | PO: Hallan de Sousa Brito | autonomia e prova: CH-2 isolada autorizada pelo PO em 30/10/2026 na Issue #49 | ambiente: CachyOS Linux x86_64 / Python 3.13 / GitHub CLI (gh) 2.67.0 | fonte: LIVE_GITHUB / SNAPSHOT_OFFLINE | timestamp ISO 8601: 2026-10-30T14:46:00Z | run_id: NÃO_APLICÁVEL | baseline SHA: `46fea0afd7d6c1a605fe49fb5f801ac125caa7a6` | branch: `agy/ch-access-01-project-export` | resultado técnico: APROVADO_TECNICAMENTE.

---

## 1. Identificação

- **Missão:** CH-ACCESS-01 — Exportação segura e auditável do GitHub Project #2 (read-only)
- **Issue Oficial:** https://github.com/hallanbrito/CHDevFlow/issues/49
- **Repositório:** `hallanbrito/CHDevFlow`
- **Branch de Trabalho:** `agy/ch-access-01-project-export`
- **Worktree Isolada:** `/home/hallan/.gemini/antigravity/worktrees/CHDevFlow/github_project_exporter`
- **Baseline de Origem:** `46fea0afd7d6c1a605fe49fb5f801ac125caa7a6` (`origin/main`)
- **Autonomia Autorizada:** CH-2 restrita a branch, commits, testes locais e Draft PR.
- **Papel do Executor:** AGY em execução especializada CH-2.
- **Auditor Independente:** ChatGPT.
- **Product Owner (PO):** Hallan de Sousa Brito.
- **Custo Adicional:** R$ 0,00 (Nenhum consumo de API paga ou serviço externo faturável).
- **Estado Inicial:** PRONTA PARA EXECUÇÃO ISOLADA PELO AGY.
- **Estado Final Esperado:** `AGUARDANDO_AUDITORIA_CHATGPT`.

---

## 2. Resumo Executivo

1. Implementado exportador somente-leitura do GitHub Project #2 (`scripts/ch_project_export.py` e `src/chdevflow/core/project_export.py`), reutilizando componentes centrais de `ch_sentinela`.
2. A validação dinâmica conferiu com exatidão os 26 cartões reais e os 19 campos observados do Project #2, com 26 IDs únicos e sem anomalias.
3. Produz snapshot JSON compacto sob esquema `chdevflow.project-snapshot/1.0`, com permissões privadas UNIX 0600 (`-rw-------`), digest SHA-256 canônico e sanitização de segredos e e-mails.
4. Omissão rigorosa de `content.body`, comentários e nomes de pessoas/assignees; snapshots reais protegidos no `.gitignore`.
5. Bateria integral de 307 testes locais executada e aprovada com 100% de sucesso (185 raiz + 69 Sentinela + 53 Control Center), sem regressões.

---

## 3. Consultas/atividades realizadas

1. **Inspeção de Baseline e Permissões:**
   - Conferido `origin/main` no commit `46fea0a`.
   - Criada branch isolada `agy/ch-access-01-project-export`.
   - Conferido `gh auth status` confirmando escopos `'gist', 'project', 'read:org', 'repo', 'workflow'`, sem exposição de tokens.
2. **Reutilização e Extensão da Sentinela:**
   - Estendido `LeitorGitHub` em `apps/bootstrap/sentinela/src/ch_sentinela/github_reader.py` com o método `listar_campos_projeto` e função de validação estrutural `validar_campos_projeto`.
   - Adicionada salvaguarda `field-delete` a `SUBCOMANDOS_MUTAVEIS_PROIBIDOS`.
   - Atualizado adaptador `SentinelFacade` em `apps/control-center/src/ch_control_center/adapters/sentinela_adapter.py` para expor `validar_campos` e `obter_campos_ao_vivo`.
3. **Construção do Núcleo do Exportador:**
   - Desenvolvido `src/chdevflow/core/project_export.py` contendo a lógica central de extração, sumarização sanitizada, checagem de unicidade por Card ID, integridade estrutural, digest canônico e gravação atômica com `0600`.
   - Criado script executável `scripts/ch_project_export.py` com suporte às flags `--validate-only`, `--dry-run`, `--stdout`, `--output`, `--fixture-items` e `--fixture-fields`.
4. **Proteção de Segredos e Exemplo Sintético:**
   - Atualizado `.gitignore` para bloquear `.ch/`, `.ch_sentinela/` e `*project_snapshot*.json`, excetuando exemplos sintéticos.
   - Criado exemplo sintético versionado em `docs/CH/exemplos/project_snapshot_sintetico.json`.
5. **Proposta Arquitetural para Futura Daily 07h:**
   - Elaborada proposta detalhada em `docs/CH/CH-ACCESS-01-EXPORTADOR.md` contemplando autenticação mínima (Read-only em Projects), validação de frescor (TTL <= 30 min) e ausência de daemons 24/7 (Decisão D05).
6. **Suíte de Testes:**
   - Criado `tests/test_project_export.py` com 16 testes offline cobrindo todos os requisitos e cenários de quebra.
   - Adicionados 2 testes unitários em `apps/bootstrap/sentinela/tests/test_github_reader.py`.

---

## 4. Evidências verificáveis

| ID | Classe | Fonte/ref | Fato observado e limite |
|---|---|---|---|
| E01 | OBSERVADO | `gh project item-list 2 --owner hallanbrito --limit 500 --format json` | Retornou `totalCount=26` e 26 itens recebidos; 26 IDs de cartões únicos. |
| E02 | OBSERVADO | `gh project field-list 2 --owner hallanbrito --format json` | Retornou `totalCount=19` e 19 campos estruturados recebidos. |
| E03 | OBSERVADO | `python scripts/ch_project_export.py --validate-only` | Validou com sucesso os 26 cartões e 19 campos ao vivo (`LIVE_GITHUB`), 0 anomalias, digest gerado. |
| E04 | OBSERVADO | `python scripts/ch_project_export.py` | Gravou `.ch_sentinela/project_snapshot.json` com permissão estrita `0600` (`-rw-------`). |
| E05 | OBSERVADO | `python -m unittest tests/test_project_export.py` | 16 testes executados e aprovados em 0.315s. |
| E06 | OBSERVADO | `python -m unittest discover -s apps/bootstrap/sentinela/tests` | 69 testes executados e aprovados em 0.100s. |
| E07 | OBSERVADO | `pytest apps/control-center/tests` | 53 testes executados e aprovados em 0.44s. |
| E08 | OBSERVADO | `python -m unittest discover -s tests` | 185 testes da raiz executados e aprovados em 29.962s. |
| E09 | OBSERVADO | `python -m compileall -q src scripts apps` | Compilação sintática de todos os arquivos concluída com código 0. |
| E10 | OBSERVADO | `git status` | Snapshot real local não é rastreado pelo Git devido à regra em `.gitignore`. |
| E11 | DECLARADO | Issue #49 | Autorização do PO Hallan de Sousa Brito para missão CH-2 isolada sem merge/deploy. |
| E12 | OBSERVADO | Ambiente local | R$ 0,00 de custo adicional; nenhuma chamada a serviços de IA pagos realizada. |

---

## 5. Verificações e resultados

| Teste | Critério | Resultado | Evidência |
|---|---|---|---|
| T01 | Consulta e validação dinâmica dos 26 cartões e 19 campos | PASSOU | E01, E02, E03, E04 |
| T02 | Produção de snapshot compacto, auditável, com UTC e governança | PASSOU | E03, E04, E05 |
| T03 | Proteção e não publicação de snapshots reais e mascaramento de credenciais | PASSOU | E04, E05, E10 |
| T04 | Operação 100% somente leitura sem modificar cartões, regras ou permissões | PASSOU | E01, E03, E04 |
| T05 | Testes offline de fail-closed (falha gh, timeout, json inválido, contagens divergentes) | PASSOU | E05, E06 |
| T06 | Trabalho restrito à branch isolada `agy/ch-access-01-project-export` | PASSOU | E10 |
| T07 | Execução integral da suíte de testes sem regressões (307 testes locais aprovados) | PASSOU | E05, E06, E07, E08 |
| T08 | Proposta arquitetural para Daily 07h com autenticação mínima e frescor comprovado | PASSOU | Documentado em `docs/CH/CH-ACCESS-01-EXPORTADOR.md` |

---

## 6. Riscos e bloqueios

- **Risco R1 (Vazamento Acidental de Snapshot Real):** Mitigado com inclusão explícita de `.ch_sentinela/`, `.ch/` e `*project_snapshot*.json` no `.gitignore` e permissão `0600` no sistema de arquivos. Exemplo fornecido é 100% sintético.
- **Risco R2 (Falha ou Indisponibilidade de Rede do GitHub CLI):** Mitigado com comportamento fail-closed rigoroso; o script encerra com código 1 e erro seguro sanitizado, sem gerar falsos sucessos.
- **Risco R3 (Incompatibilidade com Daily 07h):** A proposta arquitetural foi isolada e não ativa daemons nem cron jobs automáticos nesta fatia, respeitando rigorosamente a Decisão D05.
- **Bloqueios Atuais:** Nenhum bloqueio técnico. Missão concluída e apta para auditoria independente.

---

## 7. Alterações realizadas

- **Arquivos modificados:**
  - `.gitignore`: Adicionada proteção para `.ch/` e `*project_snapshot*.json`, mantendo exceção para `docs/CH/exemplos/*.json`.
  - `apps/bootstrap/sentinela/src/ch_sentinela/github_reader.py`: Adicionados `listar_campos_projeto`, `validar_campos_projeto` e salvaguarda `field-delete`.
  - `apps/bootstrap/sentinela/tests/test_github_reader.py`: Adicionados testes unitários para campos de projeto.
  - `apps/control-center/src/ch_control_center/adapters/sentinela_adapter.py`: Adicionados `validar_campos` e `obter_campos_ao_vivo`.
- **Arquivos criados:**
  - `src/chdevflow/core/project_export.py`: Módulo central de exportação segura, validação e persistência restrita (0600).
  - `scripts/ch_project_export.py`: Script CLI executável com flags `--validate-only`, `--dry-run`, `--stdout`, `--fixture-items`, etc.
  - `tests/test_project_export.py`: Bateria com 16 testes offline de conformidade e fail-closed.
  - `docs/CH/CH-ACCESS-01-EXPORTADOR.md`: Documentação técnica completa e proposta arquitetural para a Daily 07h.
  - `docs/CH/exemplos/project_snapshot_sintetico.json`: Snapshot sintético de exemplo para fins documentais.
  - `docs/CH/RUC-CH-ACCESS-01-PROJECT-EXPORT.md`: Este relatório RUC/1.0.
  - `RUC-CH-ACCESS-01-PROJECT-EXPORT.md`: Cópia espelhada na raiz do repositório.

---

## 8. Recomendação técnica

**APROVADO_TECNICAMENTE** — A missão CH-ACCESS-01 atendeu integralmente a todos os critérios de aceite estipulados na Issue #49:
- Consulta segura e validada dos 26 cartões e 19 campos.
- Snapshot compacto, higienizado e protegido com permissão 0600.
- Falha fechada absoluta comprovada por testes offline.
- Total de 307 testes locais aprovados sem regressões.
- Nenhuma alteração remota, mutação de cartões, merge ou custo financeiro.

Encaminha-se o Draft PR para auditoria técnica independente do revisor declarado (ChatGPT).

---

## 9. Decisão necessária do PO

**PENDENTE** — Autorização do Product Owner (Hallan de Sousa Brito) para:
1. Recebimento e homologação da auditoria técnica independente a ser conduzida pelo ChatGPT.
2. Deliberação sobre a proposta arquitetural para a Daily 07h descrita em `docs/CH/CH-ACCESS-01-EXPORTADOR.md`.
3. Eventual abertura de fatia W subsequente para integração ou implementação do canal automático da Daily.
