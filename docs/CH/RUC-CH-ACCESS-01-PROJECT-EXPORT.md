# RUC/1.0 — CH-ACCESS-01 — Tentativa 2 (Correções da Auditoria Independente)

**Cabeçalho:** missão/Issue: [#49](https://github.com/hallanbrito/CHDevFlow/issues/49) | Draft PR: [#50](https://github.com/hallanbrito/CHDevFlow/pull/50) | parecer auditoria anterior: [CH-AUD-ACCESS-01](https://github.com/hallanbrito/CHDevFlow/pull/50#issuecomment-6525940749) | executor declarado: Google Antigravity (AGY) | coordenação: ChatGPT | PO: Hallan de Sousa Brito | autonomia e prova: CH-2 isolada autorizada pelo PO em 30/10/2026 na Issue #49 mantida para correções | ambiente: CachyOS Linux x86_64 / Python 3.13 / GitHub CLI (gh) 2.67.0 | fonte: LIVE_GITHUB / SNAPSHOT_OFFLINE | timestamp ISO 8601: 2026-10-30T15:17:00Z | run_id: [41079074136](https://github.com/hallanbrito/CHDevFlow/actions/runs/41079074136) (SUCCESS) | baseline SHA: `46fea0afd7d6c1a605fe49fb5f801ac125caa7a6` | HEAD SHA: `eb49286e572407c57064d407135045f3d8db79d8` | branch: `agy/ch-access-01-project-export` | resultado técnico: APROVADO_TECNICAMENTE.

---

## 1. Identificação

- **Missão:** CH-ACCESS-01 — Exportação segura e auditável do GitHub Project #2 (read-only)
- **Ciclo:** Tentativa 2 — Fechamento estrito dos apontamentos de auditoria AUD-01, AUD-02, AUD-03 e AUD-04
- **Issue Oficial:** https://github.com/hallanbrito/CHDevFlow/issues/49
- **Draft PR:** https://github.com/hallanbrito/CHDevFlow/pull/50
- **Repositório:** `hallanbrito/CHDevFlow`
- **Branch de Trabalho:** `agy/ch-access-01-project-export`
- **Worktree Isolada:** `/home/hallan/.gemini/antigravity/worktrees/CHDevFlow/github_project_exporter`
- **Baseline de Origem:** `46fea0afd7d6c1a605fe49fb5f801ac125caa7a6` (`origin/main`)
- **Autonomia Autorizada:** CH-2 restrita a branch, commits, testes locais e Draft PR.
- **Papel do Executor:** AGY em execução especializada CH-2.
- **Auditor Independente:** ChatGPT.
- **Product Owner (PO):** Hallan de Sousa Brito.
- **Custo Adicional:** R$ 0,00 (Nenhum consumo de API paga ou serviço externo faturável).
- **Estado Inicial da Tentativa:** CORREÇÕES NECESSÁRIAS / NÃO HOMOLOGADO (Parecer CH-AUD-ACCESS-01).
- **Estado Final Esperado:** `AGUARDANDO_REAUDITORIA_CHATGPT`.

---

## 2. Resumo Executivo

1. **AUD-01 (Persistência Atômica e Privada 0600):** Refatorada a função `save_snapshot_file` para gravação atômica via `tempfile.mkstemp` no mesmo diretório pai, com `fchmod(0600)` e `os.fsync` antes do `os.replace`. Rejeição fail-closed imediata de destinos ou diretórios que sejam links simbólicos (sem seguir links); rebaixamento forçado para 0600 de arquivos preexistentes permissivos (ex.: 0644); e preservação estrita do arquivo original diante de falha de escrita ou I/O.
2. **AUD-02 (Sanitização Integral de Valores de Governança e Anomalias):** Aplicada `sanitizar_texto_completo` a todos os valores extraídos de campos (`status`, `etapa_ch`, `esteira`, etc.) e na captura de anomalias (`anomalies[].value`), eliminando qualquer possibilidade de vazamento de tokens ou e-mails em snapshot, `--stdout` ou mensagens de erro no `stderr`.
3. **AUD-03 (Eliminação de Fallback Silencioso Degradado):** Removido o bloco `try/except ImportError` que substituía validadores centrais por implementações enfraquecidas. O módulo agora requer `ch_sentinela` estritamente, abortando com `ImportError` explícito e seguro caso inacessível.
4. **AUD-04 (Higiene de Governança no `.gitignore` e Redução de Duplicação):** Restaurado `.ch/evidence/` no `.gitignore` (em vez de ignorar `.ch/` por completo), mantendo o bloqueio de `*project_snapshot*.json` e exceção para `docs/CH/exemplos/*.json`. Eliminada a duplicata do RUC na raiz do repositório, consolidando `docs/CH/RUC-CH-ACCESS-01-PROJECT-EXPORT.md` como fonte única da verdade.
5. **Cobertura de Testes e CI:** Criados 8 novos testes negativos e de regressão em `tests/test_project_export.py` (total de 24 testes). Suíte integral local totaliza 315 testes aprovados (193 raiz + 69 Sentinela + 53 Control Center).

---

## 3. Consultas/atividades realizadas

1. **Análise Integral da Auditoria:** Leitura completa do parecer CH-AUD-ACCESS-01 no comentário 6525940749 do PR #50.
2. **Correção AUD-01 (Persistência Segura):**
   - Implementada verificação de links simbólicos via `is_symlink()` e `os.path.islink()` no destino e no diretório pai.
   - Implementada escrita em temporário exclusivo (`tempfile.mkstemp`) com `fchmod(0600)`, `flush()` e `os.fsync()`.
   - Adicionada substituição atômica via `os.replace` e `os.chmod(0600)` com verificação pós-escrita.
   - Implementado rollback com exclusão do temporário e preservação do arquivo original em caso de erro de I/O.
3. **Correção AUD-02 (Sanitização de Governança):**
   - Sanitização de retorno em `extrair_valor_campo` e `extrair_governanca`.
   - Sanitização de valores em `integrity.anomalies` e de mensagens de diagnóstico impressas em `stderr`.
   - Introduzido `REGEX_GITHUB_TOKEN` para contenção em profundidade de tokens concatenados.
4. **Correção AUD-03 (Dependência Estrita):**
   - Removido fallback permissivo em `src/chdevflow/core/project_export.py`; ausência de `ch_sentinela` gera `ImportError` formal.
5. **Correção AUD-04 (Governança e `.gitignore`):**
   - Atualizado `.gitignore` preservando `.ch/` e restringindo ignore a `.ch/evidence/` e `*project_snapshot*.json`.
   - Removido `RUC-CH-ACCESS-01-PROJECT-EXPORT.md` da raiz via `git rm`.
6. **Bateria de Testes Negativos e Regressivos:**
   - 8 novos testes adicionados em `tests/test_project_export.py` validando symlinks, substituição de arquivo 0644, falhas de I/O, sanitização de opções desconhecidas e ausência de degradação.
   - Execução das 3 suítes locais com 100% de aprovação.

---

## 4. Evidências verificáveis

| ID | Classe | Fonte/ref | Fato observado e limite |
|---|---|---|---|
| E01 | OBSERVADO | `python -m unittest tests/test_project_export.py` | 24 testes executados e aprovados em 0.439s (incluindo 8 testes para AUD-01 a AUD-04). |
| E02 | OBSERVADO | `python -m unittest discover -s apps/bootstrap/sentinela/tests` | 69 testes da Sentinela executados e aprovados em 0.063s. |
| E03 | OBSERVADO | `pytest apps/control-center/tests` | 53 testes do Control Center executados e aprovados em 0.46s. |
| E04 | OBSERVADO | `python -m unittest discover -s tests` | 193 testes da raiz executados e aprovados em 21.069s. |
| E05 | OBSERVADO | `python -m compileall -q src scripts apps` | Código 0 sem erros ou avisos sintáticos. |
| E06 | OBSERVADO | `test_save_snapshot_replaces_preexisting_0644_with_strict_0600` | Arquivo preexistente 0644 rebaixado com sucesso para 0600 após save. |
| E07 | OBSERVADO | `test_save_snapshot_destination_symlink_rejected_fail_closed` | Symlink rejeitado fail-closed; arquivo apontado permaneceu intacto. |
| E08 | OBSERVADO | `test_save_snapshot_preserves_original_file_on_write_failure` | Falha simulada no `fsync` preservou integralmente o conteúdo prévio do snapshot. |
| E09 | OBSERVADO | `test_governance_values_with_tokens_and_emails_are_sanitized` | Tokens e e-mails em campos de governança foram mascarados no snapshot e no JSON. |
| E10 | OBSERVADO | `test_missing_ch_sentinela_dependency_fails_explicitly_no_degradation` | Ausência simulada de `ch_sentinela` levantou `ImportError` explícito sem validadores fracos. |
| E11 | OBSERVADO | GitHub Actions runs 41074926726 e 41079074136 | CI remota no PR #50 concluída com SUCCESS (48s e 49s). |
| E12 | DECLARADO | Issue #49 | Autorização do PO Hallan de Sousa Brito mantida em CH-2 para correções da auditoria. |
| E13 | OBSERVADO | Ambiente local | R$ 0,00 de custo adicional; nenhuma chamada a serviços de IA pagos realizada. |

---

## 5. Verificações e resultados

| Teste | Critério | Resultado | Evidência |
|---|---|---|---|
| T01 | AUD-01: Persistência atômica, fchmod(0600), fsync, os.replace e bloqueio de symlinks | PASSOU | E01, E06, E07, E08 |
| T02 | AUD-02: Sanitização estrita de valores de governança, anomalias e mensagens de stderr | PASSOU | E01, E09 |
| T03 | AUD-03: Remoção de fallback de validação degradada com fail-closed explícito | PASSOU | E01, E10 |
| T04 | AUD-04: .gitignore refinado (restrito a .ch/evidence/) e eliminação de RUC duplicado | PASSOU | E04, git status |
| T05 | Consulta e validação dinâmica dos 26 cartões e 19 campos | PASSOU | Validado na Tentativa 1 |
| T06 | Operação 100% somente leitura sem modificar cartões, regras ou permissões | PASSOU | E01, E02, E03 |
| T07 | Execução integral da suíte de testes sem regressões (315 testes locais aprovados) | PASSOU | E01, E02, E03, E04 |
| T08 | Proposta arquitetural para Daily 07h mantida em documentação | PASSOU | `docs/CH/CH-ACCESS-01-EXPORTADOR.md` |

---

## 6. Riscos e bloqueios

- **Risco R1 (Concorrência Local de Escrita):** Mitigado pelo uso de arquivos temporários exclusivos (`tempfile.mkstemp`) e substituição atômica no mesmo diretório (`os.replace`).
- **Risco R2 (Symlink Hijacking):** Mitigado por checagem explícita com fail-closed tanto no destino quanto no diretório pai.
- **Risco R3 (Vazamento de Segredos em Valores Inválidos):** Mitigado pela sanitização antecipada de qualquer valor antes de sua inclusão em itens, anomalias ou logs.
- **Bloqueios Atuais:** Nenhum bloqueio técnico. Modificações prontas para reauditoria independente.

---

## 7. Alterações realizadas

- **Arquivos modificados:**
  - `src/chdevflow/core/project_export.py`:
    - Refatoração de `save_snapshot_file` com atomicidade, `fchmod(0600)`, `fsync`, `os.replace` e rejeição de links simbólicos (AUD-01).
    - Sanitização integral de valores de campos de governança, anomalias e erros (AUD-02).
    - Remoção do fallback enfraquecido de `ch_sentinela` (AUD-03).
  - `scripts/ch_project_export.py`:
    - Sanitização de mensagens de exceção e diagnósticos impressos no `stderr` (AUD-02).
  - `.gitignore`:
    - Restaurado `.ch/evidence/` em substituição ao ignore genérico de `.ch/` (AUD-04).
  - `tests/test_project_export.py`:
    - Adicionados 8 testes cobrindo permissões preexistentes, symlinks, falha de I/O, sanitização de governança/anomalias/stderr e dependência ausente.
  - `docs/CH/CH-ACCESS-01-EXPORTADOR.md`:
    - Atualizada a documentação técnica com os mecanismos de persistência atômica e sanitização integral.
  - `docs/CH/RUC-CH-ACCESS-01-PROJECT-EXPORT.md`:
    - Atualizado para Tentativa 2 com todas as evidências das correções.
- **Arquivos removidos:**
  - `RUC-CH-ACCESS-01-PROJECT-EXPORT.md` (removido da raiz para eliminar duplicação conforme AUD-04).

---

## 8. Recomendação técnica

**APROVADO_TECNICAMENTE** — Todas as pendências e vulnerabilidades apontadas no parecer CH-AUD-ACCESS-01 (AUD-01, AUD-02, AUD-03 e AUD-04) foram integralmente sanadas com testes negativos comprovando o comportamento seguro fail-closed. 

Encaminha-se para reauditoria técnica independente pelo ChatGPT no Draft PR #50.

---

## 9. Decisão necessária do PO

**PENDENTE** — Autorização do Product Owner (Hallan de Sousa Brito) para:
1. Recebimento e homologação da reauditoria técnica independente a ser conduzida pelo ChatGPT.
2. Deliberação sobre a proposta arquitetural para a Daily 07h descrita em `docs/CH/CH-ACCESS-01-EXPORTADOR.md`.
