"""Preparação segura e submissão da entrega da fatia (`ch submit`)."""
from __future__ import annotations

from pathlib import Path
import subprocess

from chdevflow.core.evidence import run_verification
from chdevflow.core.ruc import generate_ruc
from chdevflow.core.status import check_git_status


class SubmitError(RuntimeError):
    """Erro em caso de pré-requisitos não satisfeitos para submissão."""
    pass


class SubmitSecurityError(PermissionError):
    """Erro de segurança ao tentar submeter em branches proibidas (ex.: main)."""
    pass


def validate_and_submit(
    project_path: Path | None = None,
    remote: bool = False,
    title: str | None = None,
    body: str | None = None,
    skip_verify: bool = False,
) -> dict:
    """
    Valida a entrega da fatia e prepara o ciclo para revisão humana (AGUARDANDO_PO).
    Nunca realiza merge. Bloqueia submissão na branch main e em casos de verify falho.
    """
    target = (project_path or Path.cwd()).resolve()
    git_info = check_git_status(target)

    # 1. Validação de Git
    if not git_info["is_git"]:
        raise SubmitError("Operação bloqueada: O diretório não é um repositório Git.")

    current_branch = git_info["branch"]
    if current_branch in ("main", "master"):
        raise SubmitSecurityError(
            f"Operação bloqueada: 'ch submit' não pode ser executado diretamente na branch '{current_branch}'. "
            "Trabalhe sempre em uma branch de fatia dedicada (ex.: agy/..., ch/...)."
        )

    # 2. Validação de alterações (diffs ou commits à frente)
    is_dirty = git_info["is_dirty"]

    # Verifica commits à frente da branch base (main)
    rev_cmd = subprocess.run(
        ["git", "-C", str(target), "rev-list", "--count", f"HEAD", "^origin/main"],
        capture_output=True,
        text=True,
        check=False,
    )
    if rev_cmd.returncode != 0:
        # Fallback para main local
        rev_cmd = subprocess.run(
            ["git", "-C", str(target), "rev-list", "--count", f"HEAD", "^main"],
            capture_output=True,
            text=True,
            check=False,
        )

    commits_ahead = 0
    if rev_cmd.returncode == 0 and rev_cmd.stdout.strip().isdigit():
        commits_ahead = int(rev_cmd.stdout.strip())

    if not is_dirty and commits_ahead == 0:
        raise SubmitError(
            "Operação bloqueada: Nenhuma alteração detectada para submeter "
            "(árvore de trabalho limpa e zero commits à frente da branch base)."
        )

    # 3. Execução dos checks de verificação
    verify_state = "IGNORADO"
    if not skip_verify:
        ev = run_verification(target, fail_fast=True)
        verify_state = ev.overall_state
        if ev.overall_state != "PASS":
            raise SubmitError(
                f"Operação bloqueada: Checks de verificação retornaram '{ev.overall_state}'. "
                "Corrija as falhas antes de prosseguir com a submissão."
            )

    # 4. Geração do RUC
    ruc_path, _ = generate_ruc(
        target,
        mission_title=title or f"Fatia em {current_branch}",
    )

    result = {
        "branch": current_branch,
        "is_dirty": is_dirty,
        "commits_ahead": commits_ahead,
        "verification": verify_state,
        "ruc_file": str(ruc_path),
        "state": "AGUARDANDO_PO",
        "remote_executed": False,
        "remote_details": None,
    }

    # 5. Operação remota opcional (somente com confirmação explícita --remote)
    if remote:
        gh_check = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, check=False)
        if gh_check.returncode != 0:
            raise SubmitError("GitHub CLI (gh) não autenticado. Operação remota cancelada.")

        # Push seguro da branch de trabalho
        push_cmd = subprocess.run(
            ["git", "-C", str(target), "push", "-u", "origin", current_branch],
            capture_output=True,
            text=True,
            check=False,
        )
        if push_cmd.returncode != 0:
            raise SubmitError(f"Falha ao realizar git push na branch '{current_branch}': {push_cmd.stderr.strip()}")

        # Verifica se já existe um PR aberto para a branch
        view_pr = subprocess.run(
            ["gh", "pr", "view", current_branch, "--json", "url,isDraft"],
            cwd=str(target),
            capture_output=True,
            text=True,
            check=False,
        )

        pr_title = title or f"Fatia: {current_branch}"
        pr_body = body or f"Submissão da fatia sob governança C.H.\n\nEstado: AGUARDANDO_PO.\nRUC gerado em `{ruc_path.name}`."

        if view_pr.returncode == 0:
            result["remote_details"] = "Draft PR existente identificado e sincronizado."
        else:
            # Cria Draft PR (nunca cria PR direto para merge)
            create_pr = subprocess.run(
                ["gh", "pr", "create", "--draft", "--title", pr_title, "--body", pr_body],
                cwd=str(target),
                capture_output=True,
                text=True,
                check=False,
            )
            if create_pr.returncode == 0:
                result["remote_details"] = f"Draft PR criado com sucesso: {create_pr.stdout.strip()}"
            else:
                result["remote_details"] = f"Aviso ao registrar PR: {create_pr.stderr.strip()}"

        result["remote_executed"] = True

    return result
