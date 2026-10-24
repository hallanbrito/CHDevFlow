"""Diagnóstico de estado e governança local do projeto (`ch status`)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from chdevflow.core.config import load_manifest, ManifestError

ESSENTIAL_DOCS = [
    "AGENTS.md",
    "docs/PROJETO.md",
    "docs/STATUS.md",
    "docs/CH/DECISOES.md",
    "docs/CH/PROTOCOLO_AGENTES.md",
    "docs/CH/RELATORIO-UNIVERSAL-CH.md",
    "docs/ARVORE_PROJETO.md",
]


def check_git_status(path: Path) -> dict[str, Any]:
    """Obtém status do Git local sem realizar operações de rede."""
    is_git_cmd = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    if is_git_cmd.returncode != 0:
        return {
            "is_git": False,
            "branch": None,
            "commit_sha": None,
            "is_dirty": None,
            "message": "Diretório não é um repositório Git (pendente 'git init').",
        }

    branch_cmd = subprocess.run(
        ["git", "-C", str(path), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=False,
    )
    branch = branch_cmd.stdout.strip() or "HEAD (detached)"

    rev_cmd = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    sha = rev_cmd.stdout.strip() if rev_cmd.returncode == 0 else "sem commits"

    status_cmd = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    dirty = bool(status_cmd.stdout.strip())

    return {
        "is_git": True,
        "branch": branch,
        "commit_sha": sha,
        "is_dirty": dirty,
        "message": "Git ativo e monitorado.",
    }


def get_project_status(project_path: Path, strict: bool = False) -> dict[str, Any]:
    """Coleta o estado integral do projeto (Git, manifesto e governança C.H.)."""
    proj_resolved = project_path.resolve()
    if not proj_resolved.is_dir():
        raise FileNotFoundError(f"Diretório não existe: {proj_resolved}")

    # 1. Git
    git_info = check_git_status(proj_resolved)

    # 2. Manifesto chdevflow.yaml
    manifest_file = proj_resolved / "chdevflow.yaml"
    manifest_data: dict[str, Any] | None = None
    manifest_status = "PRESENTE"
    manifest_err = None

    if not manifest_file.exists():
        manifest_status = "AUSENTE"
        manifest_err = "Arquivo de manifesto chdevflow.yaml não encontrado."
    else:
        try:
            manifest_data = load_manifest(manifest_file)
        except ManifestError as exc:
            manifest_status = f"INVALIDO ({exc})"
            manifest_err = str(exc)
        except Exception as exc:
            manifest_status = f"INVALIDO ({exc})"
            manifest_err = str(exc)

    # 3. Documentos fundamentais
    docs_status: dict[str, str] = {}
    missing_docs: list[str] = []
    for doc in ESSENTIAL_DOCS:
        full_p = proj_resolved / doc
        if full_p.is_file():
            docs_status[doc] = "PRESENTE"
        elif full_p.is_dir():
            docs_status[doc] = "INVALIDO (diretório)"
            missing_docs.append(doc)
        elif full_p.is_symlink():
            docs_status[doc] = "INVALIDO (symlink quebrado)"
            missing_docs.append(doc)
        else:
            docs_status[doc] = "AUSENTE"
            missing_docs.append(doc)

    # 4. Pendências estruturais obrigatórias
    structural_pendencies: list[str] = []
    if manifest_status != "PRESENTE":
        structural_pendencies.append(f"Manifesto chdevflow.yaml pendente ou com erro: {manifest_status}")
    if missing_docs:
        structural_pendencies.append(f"Documentos fundamentais C.H. ausentes: {', '.join(missing_docs)}")

    structural_health = (len(structural_pendencies) == 0)

    # 5. Pendências gerais (Git + estrutural)
    pendencies: list[str] = []
    if not git_info["is_git"]:
        pendencies.append("Repositório Git não inicializado (executar 'git init').")
    elif git_info["is_dirty"]:
        pendencies.append("Alterações não commitadas na árvore de trabalho.")
    pendencies.extend(structural_pendencies)

    # 6. Códigos de saída esperados
    strict_exit_code = 0 if structural_health else 1
    expected_exit_code = strict_exit_code if strict else 0

    return {
        "path": str(proj_resolved),
        "name": manifest_data.get("project", {}).get("name") if manifest_data else proj_resolved.name,
        "git": git_info,
        "manifest": {
            "status": manifest_status,
            "path": str(manifest_file),
            "data": manifest_data,
            "error": manifest_err,
        },
        "docs": docs_status,
        "missing_docs": missing_docs,
        "pendencies": pendencies,
        "structural_pendencies": structural_pendencies,
        "structural_health": structural_health,
        "saude_estrutural": "CONFORME" if structural_health else "PENDENTE",
        "strict": strict,
        "expected_exit_code": expected_exit_code,
        "strict_exit_code": strict_exit_code,
        "authorization": {
            "status": "NÃO_INFERIDA",
            "message": "Autorizações CH-1/CH-2/CH-3 são concedidas exclusivamente pelo PO humano em Issue/documento formal.",
        },
    }


def render_status_human(status_data: dict[str, Any]) -> str:
    """Formata os dados de status para leitura humana no terminal."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"CHDevFlow — Estado do Projeto: {status_data['name']}")
    lines.append(f"Local: {status_data['path']}")
    lines.append("=" * 60)

    # Git
    git_info = status_data["git"]
    lines.append("\n[Repositório Git]")
    if git_info["is_git"]:
        lines.append(f"  • Branch atual : {git_info['branch']}")
        lines.append(f"  • Commit SHA   : {git_info['commit_sha']}")
        lines.append(f"  • Estado árvore: {'Modificada (dirty)' if git_info['is_dirty'] else 'Limpa'}")
    else:
        lines.append(f"  • Estado       : {git_info['message']}")

    # Manifesto
    m_info = status_data["manifest"]
    lines.append("\n[Manifesto chdevflow.yaml]")
    lines.append(f"  • Estado: {m_info['status']}")
    if m_info["data"]:
        data = m_info["data"]
        stack = data.get("stack", {})
        backend = stack.get("backend", {}).get("type", "nenhum")
        frontend = stack.get("frontend", {}).get("type", "nenhum")
        db = stack.get("database", {}).get("type", "nenhum")
        lines.append(f"  • Stack : backend={backend}, frontend={frontend}, database={db}")
        v_cmds = data.get("verification", {}).get("commands", [])
        lines.append(f"  • Checks de verificação: {', '.join(v_cmds) if v_cmds else 'nenhum'}")

    # Documentos
    lines.append("\n[Governança e Fundação C.H.]")
    for doc, st in status_data["docs"].items():
        symbol = "✓" if st == "PRESENTE" else "✗"
        lines.append(f"  {symbol} {doc:<35}: {st}")

    # Pendências
    lines.append("\n[Pendências Detectadas]")
    if status_data["pendencies"]:
        for p in status_data["pendencies"]:
            lines.append(f"  ! {p}")
    else:
        lines.append("  ✓ Nenhuma pendência estrutural identificada.")

    # Diagnóstico Estrutural
    lines.append("\n[Diagnóstico Estrutural]")
    health_label = (
        "CONFORME (100% da fundação presente)"
        if status_data.get("structural_health")
        else "PENDENTE (fundação obrigatória incompleta)"
    )
    lines.append(f"  • Saúde estrutural : {health_label}")
    if status_data.get("strict"):
        exit_code = status_data.get("expected_exit_code", 0)
        lines.append("  • Modo de avaliação: ESTRITO (--strict)")
        lines.append(f"  • Código de saída  : {exit_code}")
    else:
        lines.append("  • Modo de avaliação: INFORMATIVO (compatível, código 0)")

    # Autorização
    lines.append("\n[Governança de Autorização]")
    lines.append(f"  • Status : {status_data['authorization']['status']}")
    lines.append(f"  • Nota   : {status_data['authorization']['message']}")
    lines.append("=" * 60)

    return "\n".join(lines)
