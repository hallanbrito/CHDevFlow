# CH-ACCESS-01 — Exportador Read-Only e Seguro do GitHub Project #2

**Missão:** [Issue #49](https://github.com/hallanbrito/CHDevFlow/issues/49)  
**Autorização:** CH-2 isolada em branch concedida pelo PO (Hallan de Sousa Brito) em 30/10/2026.  
**Estado:** `AGUARDANDO_REAUDITORIA_CHATGPT`.

---

## 1. Visão Geral e Arquitetura

O exportador de dados do GitHub Project #2 (`scripts/ch_project_export.py` e módulo `chdevflow.core.project_export`) implementa uma interface puramente somente-leitura (read-only) para extração estruturada de governança do GitHub Project #2 (esteiras C.H.).

### Princípios e Reutilização:
1. **Reutilização da Sentinela Python (`ch_sentinela`) sem Degradação (AUD-03)**:
   - Reutiliza `LeitorGitHub`, `executar_consulta_json` e `sanitizar_texto_segredos`.
   - Adicionada a função `validar_campos_projeto` e o método `listar_campos_projeto` em `LeitorGitHub`.
   - Proibição estrita de subcomandos mutáveis (`item-edit`, `item-create`, `field-create`, `field-delete`, `push`, `--apply`, etc.).
   - Eliminação de qualquer fallback enfraquecido: ausência de `ch_sentinela` aborta com `ImportError` explícito e seguro.
2. **Validação Dinâmica de Integridade a Cada Execução**:
   - Valida `totalCount == len(items)` para os cartões (26 cartões observados live).
   - Valida `totalCount == len(fields)` para os campos estruturados (19 campos observados live).
   - Valida unicidade estrita de `id` para todos os cartões. Qualquer ID duplicado interrompe a exportação.
3. **Higienização Integral e Proteção de Dados Privados (AUD-02)**:
   - Omissão categórica de `content.body` (corpo de issues), comentários, revisões e nomes de pessoas/assignees.
   - Mascaramento determinístico de segredos conhecidos (tokens `ghp_`, `gho_`, `github_pat_`, chaves `AIza...`) e e-mails pessoais (`[CREDENCIAL_OCULTADA]`, `[DADO_PESSOAL_OCULTADO]`).
   - Todos os valores extraídos de governança (`status`, `etapa_ch`, `esteira`, etc.) e registros em `integrity.anomalies` passam por sanitização completa antes da serialização.
   - Mensagens de erro e diagnóstico no `stderr` são sanitizadas para evitar vazamento em logs.
4. **Persistência Privada com Atomicidade Real e Preservação de Diretórios (AUD-01, AUD-05, AUD-06)**:
   - Gravação atômica via arquivo temporário exclusivo no mesmo diretório pai (`tempfile.mkstemp`).
   - Aplicação de `fchmod(0600)` e sincronização em disco (`os.fsync`) antes da substituição atômica (`os.replace`).
   - Garantia de que arquivos preexistentes com permissões permissivas (ex.: 0644) são rebaixados estritamente para `0o600` (`-rw-------`).
   - **Preservação de diretórios preexistentes (AUD-05)**: O exportador nunca altera o modo de diretórios preexistentes (ex.: `0755` ou diretório atual `.` permanecem idênticos). Apenas novos diretórios na cadeia são criados com modo restrito `0700`.
   - **Falha fechada para diretórios inseguros (AUD-05)**: Recusa imediata de operação caso o diretório pai seja gravável por outros sem sticky bit (`world-writable`) ou não possua permissão de escrita.
   - **Bloqueio de symlinks em toda a cadeia ancestral (AUD-06)**: Bloqueio incondicional de links simbólicos tanto no destino quanto em qualquer componente ancestral imediato ou intermediário, para caminhos absolutos ou relativos (fail-closed, sem seguir links).
   - Preservação do arquivo de destino original caso ocorra falha de escrita ou I/O.
   - Diretório padrão protegido com `0o700` em `.ch_sentinela/project_snapshot.json`.
   - Ignorado por padrão no `.gitignore` para impedir que snapshots reais sejam comitados no Git (AUD-04).
5. **Comportamento Fail-Closed (Falha Fechada)**:
   - Se o comando `gh`, rede, autenticação ou parsing falhar, o script encerra imediatamente com status `BLOQUEADO` e código de saída `1`.
   - Não há fallback automático para fixtures. Fixtures são aceitas única e exclusivamente com passagem explícita de argumentos `--fixture-items` e `--fixture-fields`.
6. **Preservação de Governança e Campos Estruturados**:
   - Preserva distinção entre `Status`, `Etapa CH`, `Esteira`, `Prioridade CH`, `Risco CH`, `Autonomia CH` e `Decisao PO`.
   - Campos vazios ou não definidos no cartão são registrados explicitamente como `"NÃO_OBSERVADO"`.
   - Opções não catalogadas geram registro em `integrity.anomalies` com código `OPCAO_DESCONHECIDA`, sem jamais deduzir aprovação humana ou avanço de etapa.

---

## 2. Uso do Script

### Validação de integridade ao vivo (sem gravação em disco):
```bash
python scripts/ch_project_export.py --validate-only
```

### Exportação ao vivo com gravação segura local (permissões 0600):
```bash
python scripts/ch_project_export.py --output .ch_sentinela/project_snapshot.json
```

### Simulação sem efeitos colaterais (dry-run):
```bash
python scripts/ch_project_export.py --dry-run
```

### Emissão compacta para stdout (para pipelines e ferramentas downstream):
```bash
python scripts/ch_project_export.py --stdout
```

### Testes e demonstração offline com fixtures:
```bash
python scripts/ch_project_export.py \
  --fixture-items tests/fixtures/items.json \
  --fixture-fields tests/fixtures/fields.json \
  --output .ch_sentinela/project_snapshot.json
```

---

## 3. Proposta Arquitetural: Canal de Leitura Automática para a Daily 07h

> **Nota de Governança:** Conforme restrições do escopo CH-ACCESS-01 e Decisão D05, **nenhum daemon 24/7, cron job ou upload remoto de snapshots reais foi ativado nesta fatia**. A proposta abaixo descreve a solução técnica recomendada para deliberação do PO e futura implementação em fatia específica.

### 3.1. Requisitos do Canal Automático
1. **Autenticação Mínima com Privilégio Estrito**:
   - Não utilizar tokens pessoais com privilégios de escrita em repositório ou organização.
   - Adotar um GitHub Fine-Grained Personal Access Token (PAT) ou GitHub App com permissão exclusiva:
     - `Projects (v2): Read-only`
     - `Metadata: Read-only`
   - O token não deve possuir permissões de `contents:write`, `pull_requests:write` ou `workflows`.
2. **Frescor Comprovado e TTL**:
   - O snapshot deve conter o carimbo `captured_at_utc`.
   - A ferramenta da Daily 07h deve validar que `now() - captured_at_utc <= 1800` (tolerância máxima de 30 minutos).
   - Se o snapshot tiver idade superior a 30 minutos ou o digest SHA-256 for inconsistente, a Daily deve recusar a leitura e acusar `DADOS_DESATUALIZADOS`, impedindo decisões baseadas em estado obsoleto.
3. **Disparo Pontual sob Demanda (Sem Daemon 24/7)**:
   - Em conformidade com a Decisão D05, a coleta deve ser executada como um comando pontual agendado (por exemplo, via systemd timer local na máquina do PO ou gatilho manual pré-daily), disparando `scripts/ch_project_export.py` às 06h55 UTC-3.
   - O script executa em ~2 segundos e encerra imediatamente.
4. **Isolamento de Dados e Privacidade**:
   - O snapshot deve permanecer em armazenamento local efêmero (`.ch_sentinela/project_snapshot.json`), protegido por `chmod 0600`.
   - O conector de consumo da Daily lê o JSON sanitizado localmente (já desprovido de bodies de issues, comentários e segredos).
   - Nunca realizar upload de snapshots brutos para serviços externos ou branches públicas.

---

## 4. Estrutura do Snapshot

O esquema oficial versionado é `chdevflow.project-snapshot/1.0`:

```json
{
  "schema_version": "chdevflow.project-snapshot/1.0",
  "source": "LIVE_GITHUB",
  "project_owner": "hallanbrito",
  "project_number": 2,
  "captured_at_utc": "2026-10-30T14:41:50Z",
  "integrity": {
    "total_items_reported": 26,
    "total_items_received": 26,
    "items_count_match": true,
    "total_fields_reported": 19,
    "total_fields_received": 19,
    "fields_count_match": true,
    "unique_card_ids": true,
    "anomalies": [],
    "snapshot_digest": "2fb55a62b2d4ad2676a182d46de33429ee2cf4724369e8b8c3d5b325b4cf3bad"
  },
  "fields": [ ... ],
  "items": [ ... ]
}
```

Um exemplo sintético completo encontra-se versionado em `docs/CH/exemplos/project_snapshot_sintetico.json`.
