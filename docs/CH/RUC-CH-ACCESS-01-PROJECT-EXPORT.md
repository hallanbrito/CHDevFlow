# RUC/1.0 — CH-ACCESS-01 — Tentativa 3 (Correções da Reauditoria Independente)

**Cabeçalho:** missão/Issue: [#49](https://github.com/hallanbrito/CHDevFlow/issues/49) | Draft PR: [#50](https://github.com/hallanbrito/CHDevFlow/pull/50) | pareceres auditoria anteriores: [CH-AUD-ACCESS-01 (Tentativa 1)](https://github.com/hallanbrito/CHDevFlow/pull/50#issuecomment-6525940749) e [CH-AUD-ACCESS-01 (Tentativa 2)](https://github.com/hallanbrito/CHDevFlow/pull/50#issuecomment-6528283173) | executor declarado: Google Antigravity (AGY) | auditoria independente: ChatGPT | PO: Hallan de Sousa Brito | autonomia e prova: CH-2 isolada autorizada pelo PO em 30/10/2026 na Issue #49 mantida exclusivamente para correções AUD-05, AUD-06 e AUD-07 | ambiente: CachyOS Linux x86_64 / Python 3.13 / GitHub CLI (gh) 2.67.0 | fonte: LIVE_GITHUB / SNAPSHOT_OFFLINE | timestamp ISO 8601: 2026-10-30T17:15:00Z | runs anteriores: [41074926726](https://github.com/hallanbrito/CHDevFlow/actions/runs/41074926726) (SUCCESS) e [41084068176](https://github.com/hallanbrito/CHDevFlow/actions/runs/41084068176) (SUCCESS) | baseline SHA: `46fea0afd7d6c1a605fe49fb5f801ac125caa7a6` | branch: `agy/ch-access-01-project-export` | resultado técnico: APROVADO_TECNICAMENTE.

---

## 1. Identificação

- **Missão:** CH-ACCESS-01 — Exportação segura e auditável do GitHub Project #2 (read-only)
- **Ciclo:** Tentativa 3 — Fechamento estrito dos apontamentos de auditoria AUD-05, AUD-06 e AUD-07
- **Issue Oficial:** https://github.com/hallanbrito/CHDevFlow/issues/49
- **Draft PR:** https://github.com/hallanbrito/CHDevFlow/pull/50
- **Repositório:** `hallanbrito/CHDevFlow`
- **Branch de Trabalho:** `agy/ch-access-01-project-export`
- **Worktree Isolada:** `/home/hallan/.gemini/antigravity/worktrees/CHDevFlow/github_project_exporter`
- **Baseline de Origem:** `46fea0afd7d6c1a605fe49fb5f801ac125caa7a6` (`origin/main`)
- **Autonomia Autorizada:** CH-2 restrita a branch, commits, testes locais e Draft PR.
- **Papel do Executor:** AGY em execução especializada CH-2.
- **Auditor Independente:** ChatGPT (via pareceres formais em comentários do PR #50).
- **Product Owner (PO):** Hallan de Sousa Brito.
- **Custo Adicional:** R$ 0,00 (Nenhum consumo de API paga ou serviço externo faturável).
- **Estado Inicial da Tentativa:** CORREÇÕES PONTUAIS OBRIGATÓRIAS / NÃO HOMOLOGADO (Parecer 6528283173).
- **Estado Final Esperado:** `AGUARDANDO_REAUDITORIA_CHATGPT`.

---

## 2. Resumo Executivo

1. **AUD-05 (Eliminação de chmod Indiscriminado em Diretórios Preexistentes):**
   - Refatorada a função `save_snapshot_file` em `src/chdevflow/core/project_export.py` para nunca alterar permissões de diretórios preexistentes.
   - Pastas preexistentes (como `0755` ou o diretório de trabalho atual `.`) mantêm seus modos inalterados sem qualquer chamada invasiva de `os.chmod`.
   - Apenas componentes da cadeia de diretórios que não existiam previamente são criados com modo restrito `0700`.
   - Adicionada validação de segurança fail-closed: se o diretório pai for inseguro (ex.: permissão *world-writable* sem sticky bit `01777`) ou não possuir permissão de escrita, a gravação é abortada com recusa explícita.
2. **AUD-06 (Validação de Links Simbólicos em Toda a Cadeia Ancestral):**
   - A validação contra links simbólicos foi expandida para cobrir não apenas o destino final e o pai direto, mas todos os ancestrais da cadeia (tanto na representação relativa fornecida quanto na representação absoluta normalizada).
   - Bloqueio incondicional fail-closed de symlinks intermediários (ex.: `pasta_link/subpasta/snapshot.json` com `pasta_link` simbólico e `subpasta` real).
3. **AUD-07 (Rastreabilidade e Rigor Metodológico):**
   - Atualizados os cabeçalhos, SHAs e referências de CI para refletir com fidelidade o histórico e a entrega atual.
   - Formalizada a distinção metodológica: os 26 cartões e 19 campos observados ao vivo constituem evidência técnica coletada e relatada pelo AGY em ambiente CH-2, submetida para avaliação da auditoria independente do ChatGPT.
4. **Cobertura de Testes e CI:**
   - Adicionados 6 novos testes negativos e regressivos em `tests/test_project_export.py` (total de 30 testes no arquivo).
   - Suíte integral do repositório totaliza **321 testes locais aprovados** (199 testes raiz + 69 Sentinela + 53 Control Center), com 100% de sucesso e zero regressões.

---

## 3. Consultas/atividades realizadas

1. **Análise Integral da Reauditoria:** Leitura do parecer CH-AUD-ACCESS-01 no comentário [6528283173](https://github.com/hallanbrito/CHDevFlow/pull/50#issuecomment-6528283173) do PR #50.
2. **Correção AUD-05 (Preservação de Diretórios e Escopo Mínimo):**
   - Verificação dinâmica de quais pastas no caminho já existem.
   - Exclusão de qualquer comando `chmod` sobre diretórios preexistentes.
   - Aplicação de `0700` estritamente aos novos diretórios criados.
   - Validação de segurança fail-closed para diretórios inseguros (bloqueio de world-writable sem sticky bit).
3. **Correção AUD-06 (Hardening de Symlinks em Ancestrais):**
   - Coleta de componentes do caminho relativo e de `os.path.abspath(caminho)` (preservando symlinks sem resolução via `realpath`).
   - Verificação exaustiva de `is_symlink()` e `os.path.islink()` em todos os ancestrais.
   - Rejeição fail-closed antes de qualquer operação de temporário ou substituição.
   - Verificação final concorrente repetida sobre todos os ancestrais antes de `os.replace`.
4. **Correção AUD-07 (Rastreabilidade e Atualização Metodológica):**
   - Atualização documental em `docs/CH/CH-ACCESS-01-EXPORTADOR.md` e `docs/CH/RUC-CH-ACCESS-01-PROJECT-EXPORT.md`.
   - Registro exato da titularidade de relatos live (AGY) versus pareceres de homologação (ChatGPT / PO).
5. **Bateria de Testes Abrangente:**
   - Teste de preservação de diretório preexistente `0755` (modo inalterado).
   - Teste de caminho relativo na raiz (`.`) e sem prefixo (CWD inalterado com `0755`).
   - Teste de criação de hierarquia nova com `0700` preservando o pai existente com `0755`.
   - Teste de recusa fail-closed para diretório pai `0777` sem sticky bit.
   - Teste de rejeição fail-closed para ancestral intermediário simbólico absoluto.
   - Teste de rejeição fail-closed para ancestral intermediário simbólico relativo.

---

## 4. Evidências verificáveis

| ID | Classe | Fonte/ref | Fato observado e limite |
|---|---|---|---|
| E01 | OBSERVADO | `python -m unittest tests/test_project_export.py` | 30 testes executados e aprovados em 0.699s (incluindo 6 testes específicos para AUD-05 e AUD-06). |
| E02 | OBSERVADO | `python -m unittest discover -s apps/bootstrap/sentinela/tests` | 69 testes da Sentinela executados e aprovados em 0.080s. |
| E03 | OBSERVADO | `pytest apps/control-center/tests` | 53 testes do Control Center executados e aprovados em 0.41s. |
| E04 | OBSERVADO | `python -m unittest discover -s tests` | 199 testes da raiz executados e aprovados em 36.600s. |
| E05 | OBSERVADO | `python -m compileall -q src scripts apps tests` | Código 0 sem erros ou avisos sintáticos. |
| E06 | OBSERVADO | `test_save_snapshot_preserves_preexisting_directory_0755_permissions` | Diretório pai preexistente `0755` preservou modo idêntico após gravação do arquivo `0600`. |
| E07 | OBSERVADO | `test_save_snapshot_relative_path_in_current_directory_preserves_cwd_mode` | Gravação relativa via `./` ou nome direto preservou o modo `0755` do CWD (`.`). |
| E08 | OBSERVADO | `test_save_snapshot_creates_new_hierarchy_with_0700_without_touching_existing_parent` | Apenas subpastas novas foram criadas com `0700`; diretório pai existente manteve `0755`. |
| E09 | OBSERVADO | `test_save_snapshot_insecure_world_writable_parent_fails_closed` | Tentativa de salvar em pasta `0777` sem sticky bit falhou fechado e preservou a pasta intacta. |
| E10 | OBSERVADO | `test_save_snapshot_intermediate_ancestor_symlink_rejected_fail_closed` | Symlink em ancestral intermediário rejeitado fail-closed sem criar arquivos no destino real. |
| E11 | OBSERVADO | `test_save_snapshot_relative_intermediate_ancestor_symlink_rejected` | Symlink intermediário em caminho relativo rejeitado fail-closed. |
| E12 | OBSERVADO | GitHub Actions run 41084068176 | CI remota na HEAD `5d2bd2bd...` concluída com SUCCESS (50s, 315 testes). |
| E13 | DECLARADO | Relato de execução AGY | 26 cartões e 19 campos observados dinamicamente via `gh` CLI pelo executor AGY (CH-2). |
| E14 | DECLARADO | Issue #49 | Autorização do PO Hallan de Sousa Brito mantida em CH-2 para fechamento de AUD-05, AUD-06 e AUD-07. |
| E15 | OBSERVADO | Ambiente local | R$ 0,00 de custo adicional; nenhuma chamada a serviços de IA pagos realizada. |

---

## 5. Verificações e resultados

| Teste | Critério | Resultado | Evidência |
|---|---|---|---|
| T01 | AUD-05: Preservação estrita de permissões de diretórios preexistentes (0755 / CWD '.') | PASSOU | E01, E06, E07 |
| T02 | AUD-05: Criação restrita (0700) exclusiva para subpastas novas na cadeia | PASSOU | E01, E08 |
| T03 | AUD-05: Falha fechada para diretórios preexistentes inseguros (world-writable sem sticky bit) | PASSOU | E01, E09 |
| T04 | AUD-06: Bloqueio estrito de links simbólicos intermediários e ancestrais (absolutos e relativos) | PASSOU | E01, E10, E11 |
| T05 | AUD-07: Rastreabilidade, atualização fidedigna de SHAs/CI e distinção metodológica AGY/auditor | PASSOU | RUC/1.0, git log |
| T06 | AUD-01 a AUD-04: Persistência atômica, sanitização de governança/erros, Sentinela estrita e .gitignore | PASSOU | Validado na Tentativa 2 |
| T07 | Consulta e validação dinâmica dos 26 cartões e 19 campos (relato AGY submetido à auditoria) | PASSOU | E13, scripts/ch_project_export.py |
| T08 | Execução integral das 3 suítes sem regressões (321 testes locais aprovados) | PASSOU | E01, E02, E03, E04, E05 |
| T09 | Operação puramente somente-leitura sem modificar cartões, regras ou branches protegidas | PASSOU | E01, E02, E03, git status |

---

## 6. Riscos e bloqueios

- **Risco R1 (Alteração Indesejada de Permissões no Host):** Mitigado pelo isolamento rigoroso: o exportador inspeciona a existência antes de criar e jamais executa `chmod` em diretórios preexistentes.
- **Risco R2 (Symlink Traversal em Ancestrais Intermediários):** Mitigado pela validação exaustiva de todos os componentes da cadeia (tanto no caminho original quanto no caminho absoluto).
- **Risco R3 (Gravação em Diretórios Compartilhados Inseguros):** Mitigado pela checagem fail-closed de bits *world-writable* sem sticky bit.
- **Bloqueios Atuais:** Nenhum bloqueio técnico. Modificações prontas para reauditoria independente.

---

## 7. Alterações realizadas

- **Arquivos modificados:**
  - `src/chdevflow/core/project_export.py`:
    - Refatoração de `save_snapshot_file` com preservação incondicional de permissões de pastas existentes (AUD-05).
    - Aplicação de `0700` restrita aos novos diretórios criados (AUD-05).
    - Verificação fail-closed contra diretórios pai inseguros (world-writable sem sticky bit) (AUD-05).
    - Verificação expandida contra links simbólicos em todos os componentes ancestrais imediatos e intermediários (AUD-06).
  - `tests/test_project_export.py`:
    - Adicionados 6 novos testes cobrindo preservação de diretório 0755, CWD `.`, criação de hierarquia 0700, recusa de pasta insegura 0777 e symlinks intermediários absolutos e relativos (AUD-05 e AUD-06).
  - `docs/CH/CH-ACCESS-01-EXPORTADOR.md`:
    - Documentação técnica atualizada com as garantias de preservação de diretórios existentes e hardening de symlinks ancestrais.
  - `docs/CH/RUC-CH-ACCESS-01-PROJECT-EXPORT.md`:
    - Atualização completa para Tentativa 3 (AUD-05, AUD-06 e AUD-07).

---

## 8. Recomendação técnica

**APROVADO_TECNICAMENTE** — As três exigências da reauditoria independente (AUD-05, AUD-06 e AUD-07) foram integralmente sanadas com testes negativos específicos e execução com 100% de sucesso nas três suítes de testes (321 testes aprovados).

Encaminha-se para reauditoria técnica independente pelo ChatGPT no Draft PR #50.

---

## 9. Decisão necessária do PO

**PENDENTE** — Autorização do Product Owner (Hallan de Sousa Brito) para:
1. Recebimento e homologação da reauditoria técnica independente conduzida pelo ChatGPT no Draft PR #50.
2. Deliberação sobre a proposta arquitetural para a Daily 07h descrita em `docs/CH/CH-ACCESS-01-EXPORTADOR.md`.
