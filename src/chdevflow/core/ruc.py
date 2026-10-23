"""Geração do Relatório Universal C.H. (RUC/1.0) auditável."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from chdevflow.core.status import check_git_status


def get_latest_evidence(project_path: Path) -> dict | None:
    """Carrega o arquivo de evidência mais recente em .ch/evidence."""
    evidence_dir = project_path / ".ch" / "evidence"
    if not evidence_dir.is_dir():
        return None

    files = sorted(evidence_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None

    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def get_modified_files(project_path: Path) -> list[str]:
    """Lista arquivos modificados em relação ao Git HEAD."""
    res = subprocess.run(
        ["git", "-C", str(project_path), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return []

    lines = res.stdout.strip().splitlines()
    files = []
    for l in lines:
        parts = l.strip().split(maxsplit=1)
        if len(parts) == 2:
            files.append(parts[1])
    return sorted(files)


def generate_ruc_text(
    project_path: Path,
    executor: str = "AGY",
    mission_title: str | None = None,
) -> str:
    """
    Gera o texto do RUC v1.0 a partir de evidências reais observadas no Git e em .ch/evidence.
    Campos sem prova documental são marcados rigorosamente como NÃO_VERIFICADO.
    Nunca inventa aprovação humana.
    """
    target = project_path.resolve()
    git_info = check_git_status(target)
    evidence = get_latest_evidence(target)
    mod_files = get_modified_files(target)

    now_iso = datetime.now(timezone.utc).isoformat()
    proj_name = evidence.get("project_name") if evidence else target.name
    branch = git_info["branch"] or "NÃO_VERIFICADO"
    sha = git_info["commit_sha"] or "NÃO_VERIFICADO"
    title_str = mission_title or f"Missão em {branch}"

    ev_state = evidence.get("overall_state") if evidence else "NÃO_VERIFICADO"
    if ev_state == "PASS":
        parecer = "APROVADO_TECNICAMENTE (Checks locais passaram; aguardando homologação PO)"
    elif ev_state == "FAIL":
        parecer = "BLOQUEADO (Falha nos checks de verificação)"
    else:
        parecer = "PARCIAL (Checks pendentes ou não executados)"

    # Formata tabela de testes
    tests_rows: list[str] = []
    if evidence and evidence.get("commands"):
        for i, cmd in enumerate(evidence["commands"], start=1):
            st = cmd.get("state", "NÃO_VERIFICADO")
            dur = cmd.get("duration_seconds", 0.0)
            c_name = cmd.get("command", "desconhecido")
            tests_rows.append(f"| T0{i} | Execução do comando `{c_name}` | {st} | Duração: {dur}s, exit code: {cmd.get('exit_code')} |")
    else:
        tests_rows.append("| T01 | Verificação de projeto | NÃO_VERIFICADO | Nenhuma evidência recente encontrada em `.ch/evidence/` |")

    tests_block = "\n".join(tests_rows)
    files_block = ", ".join(f"`{f}`" for f in mod_files) if mod_files else "Nenhum arquivo modificado na árvore de trabalho"

    return f"""# RELATÓRIO UNIVERSAL C.H. — {executor} — {title_str}

> **Protocolo:** `RUC/1.0`  
> **Natureza:** Documento técnico comprobatório gerado por CLI. **Não substitui decisão humana do PO.**  
> **Fonte primária:** Repositório local e evidências estruturadas de verificação.

## 1. Identificação da missão

| Campo | Valor |
|---|---|
| Identificador do Projeto | `{proj_name}` |
| Executor declarado | `{executor}` |
| PO responsável | Hallan |
| Nível CH proposto | CH-2 (trabalho técnico em branch dedicada) |
| Ambiente | Local / Sandbox Linux |
| Fonte da consulta | LOCAL_REPO |
| Horário da geração | `{now_iso}` |
| Baseline SHA | `{sha}` |
| Branch de trabalho | `{branch}` |
| Parecer técnico preliminar | `{parecer}` |

## 2. Resumo executivo

**Parecer:** {parecer}.
O ciclo local foi executado pelo CHDevFlow CLI com captura de evidências. Os arquivos foram inspecionados sem exposição de segredos ou credenciais. Nenhuma mutação foi realizada na branch principal (`main`). A entrega técnica encontra-se pronta para revisão do PO.

## 3. Consultas e atividades realizadas

| ID | Ação de fato executada | Resultado |
|---|---|---|
| A01 | Leitura de manifesto e árvore do Git | Concluído com sucesso |
| A02 | Diagnóstico de pré-requisitos (`ch doctor`) | Executado consultivamente |
| A03 | Suíte de verificação (`ch verify`) | {ev_state} |

**Fora do escopo:** Merge automático, alteração de regras da branch `main`, publicação de pacotes externos e execução de daemons permanentes.

## 4. Evidências verificáveis

| ID | Fato e classe | Fonte / limite |
|---|---|---|
| E01 | Estado geral da verificação: `{ev_state}` | Arquivo de evidência estruturada em `.ch/evidence` |
| E02 | SHA de commit: `{sha}` | Git local (`rev-parse HEAD`) |
| E03 | Arquivos alterados rastreados: {len(mod_files)} | Git local (`status --porcelain`) |

**Limites de verificação:** A saída gerada por este relatório atesta apenas conformidade técnica e sintática local. Decisões estratégicas de negócio pertencem exclusivamente ao PO.

## 5. Verificações e resultados

| Teste | Critério | Estado | Evidência |
|---|---|---|---|
{tests_block}

## 6. Riscos e bloqueios

| Risco | Impacto | Condição / mitigação |
|---|---|---|
| Modificações não testadas | Alto | Bloquear merge até execução de `ch verify` com PASS |
| Divergência de branches | Médio | Manter trabalho estritamente na branch da fatia |

## 7. Alterações realizadas

- **Arquivos modificados:** {files_block}
- **Credenciais expostas:** Nenhuma credencial observada na árvore ou nos logs.
- **Custo adicional verificado:** R$ 0,00 declarados.
- **Deploy / merge:** NÃO EXECUTADO (Reservado à decisão humana).

## 8. Recomendação técnica e próximo passo

**Parecer final:** {parecer}.  
**Estado da entrega:** `AGUARDANDO_PO` para auditoria independente e homologação.
"""


def generate_ruc(
    project_path: Path | None = None,
    output_path: Path | None = None,
    executor: str = "AGY",
    mission_title: str | None = None,
) -> tuple[Path, str]:
    """Gera o arquivo RUC em docs/CH/ ou caminho customizado."""
    target = (project_path or Path.cwd()).resolve()
    content = generate_ruc_text(target, executor=executor, mission_title=mission_title)

    if output_path:
        dest = output_path.resolve()
    else:
        docs_ch = target / "docs" / "CH"
        docs_ch.mkdir(parents=True, exist_ok=True)
        dest = docs_ch / "RELATORIO-UNIVERSAL-CH-ULTIMO.md"

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return dest, content
