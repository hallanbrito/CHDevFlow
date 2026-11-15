# Auditoria independente da F7 pelo Codex CLI (somente leitura).
# Nao modifica repo, GitHub Project, issues ou agentes.
param([string]$RepoRoot = (Split-Path -Parent $PSScriptRoot))

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path $RepoRoot).Path
$sha = (git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') {
    throw "Git SHA invalido; auditoria nao iniciada."
}
Get-Command codex -ErrorAction Stop | Out-Null
$items = @(
    "src/chdevflow/core/po_escalation_publication.py",
    "src/chdevflow/core/po_escalation.py",
    "src/chdevflow/core/intake.py",
    "src/chdevflow/core/generic_cycle.py",
    "scripts/ch_project_sync.py",
    "tests/test_ch_pipe_01_f7_publication.py",
    "tests/test_ch_pipe_01_f7_po_escalation.py"
)
$segments = [System.Collections.Generic.List[string]]::new()
$segments.Add(@"
MISSAO: AUDITORIA INDEPENDENTE DE SEGURANCA F7/CHDevFlow.
SHA Git sob revisao: $sha.
Voce e um auditor externo (Codex). NAO altere arquivos, NAO use ferramentas,
NAO simule evidencias nem afirme testes que nao estejam documentados.
A publicacao GitHub real esta DESAUTORIZADA; o escopo permite somente
comentario na Issue com outbox V1 e autorizacao individual do PO.
Verifique criticamente:
1. Autorizacao PO por acao, identidade GitHub/ACL, ligacao a issue e SHA.
2. Integridade e proveniencia da outbox, paths relativos, symlinks e junctions.
3. Snapshot pinado, revisao/retirada da aprovacao e TOCTOU.
4. Corridas e duplicidade: host unico vs varios hosts, lock e readback.
5. Falha/timeout APOS POST, recibo PENDENTE_PUBLICACAO e idempotencia.
6. Entrada nao confiavel: JSON, GitHub CLI, comentarios, Unicode, segredos.
7. Acoplamento com Intake F1, Project #2 e KSYNC-03; default sem escrita.
8. Testes ausentes e falsos positivos, compatibilidade Windows e Linux.

Obrigatorio responder primeiro:
VEREDITO: APROVAR_LAB
ou
VEREDITO: BLOQUEADO

Depois liste achados com severidade CRITICO/ALTO/MEDIO/BAIXO,
arquivo, funcao, trecho/padrao, explorabilidade, risco e correcao objetiva.
Conclua com GATES FALTANTES para homologar com uma outbox V1 elegivel.
Um teste offline com mock GH nao equivale a publicacao real.
"@)

foreach ($relative in $items) {
    $file = Join-Path $RepoRoot ($relative -replace '/', [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Arquivo de auditoria ausente: $relative"
    }
    $content = Get-Content -LiteralPath $file -Raw -Encoding utf8
    $segments.Add("### ARQUIVO: $relative" + [Environment]::NewLine + $content)
}
$prompt = $segments -join ([Environment]::NewLine + [Environment]::NewLine)
$labRoot = Join-Path $HOME "CHDevFlow-Labs"
if (-not (Test-Path -LiteralPath $labRoot -PathType Container)) {
    throw "CHDevFlow-Labs nao existe; nao criar diretorios automaticamente."
}
$dest = Join-Path $labRoot ("CH-F7-Codex-Auditoria-" + $sha.Substring(0, 8) + ".jsonl")
if (Test-Path -LiteralPath $dest) {
    throw "Dossie da auditoria ja existe: $dest (nao sobrescrever)."
}
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$prompt | codex -a never exec --sandbox read-only --ephemeral --skip-git-repo-check --json - |
    Tee-Object -FilePath $dest
if ($LASTEXITCODE -ne 0) {
    throw "Codex falhou. Evidencia preservada em: $dest"
}
$eventos = Get-Content -LiteralPath $dest -Encoding utf8 |
    ForEach-Object { try { $_ | ConvertFrom-Json } catch { $null } }
$parecer = $eventos |
    Where-Object { $_.type -eq "item.completed" -and $_.item.type -eq "agent_message" } |
    Select-Object -Last 1
if ($null -eq $parecer) {
    throw "Codex sem parecer final. Examine o JSONL: $dest"
}
Write-Host ""
Write-Host "=== VEREDITO CODEX F7 ==="
Write-Host $parecer.item.text
Write-Host "Evidencia salva em: $dest"
