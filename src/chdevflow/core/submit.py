"""Preparação segura e submissão da entrega da fatia (`ch submit`)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from chdevflow.core.evidence import run_verification
from chdevflow.core.ruc import generate_ruc
from chdevflow.core.status import check_git_status


class SubmitError(RuntimeError):
    """Erro em caso de pré-requisitos não satisfeitos para submissão."""
    pass


class SubmitSecurityError(PermissionError):
    """Erro de segurança ao tentar submeter em branches proibidas (ex.: main) ou sem Draft."""
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
    Nunca realiza merge. Bloqueia submissão na branch main e em casos de verify falho/ignorado.
    Exige que alterações e RUC estejam commitados para submissão remota com push.
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

    # 2. Validação de alterações e commits à frente
    is_dirty = git_info["is_dirty"]

    rev_cmd = subprocess.run(
        ["git", "-C", str(target), "rev-list", "--count", "HEAD", "^origin/main"],
        capture_output=True,
        text=True,
        check=False,
    )
    if rev_cmd.returncode != 0:
        rev_cmd = subprocess.run(
            ["git", "-C", str(target), "rev-list", "--count", "HEAD", "^main"],
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

    # 3. Verificação prévia
    if skip_verify:
        verify_state = "NÃO_VERIFICADO"
        delivery_state = "BLOQUEADO"
        if remote:
            raise SubmitError(
                "Operação remota proibida: submissão remota exige obrigatoriamente verificação com estado PASS. "
                "O modo --no-verify permanece BLOQUEADO."
            )
    else:
        ev = run_verification(target, fail_fast=True)
        verify_state = ev.overall_state
        if ev.overall_state != "PASS":
            raise SubmitError(
                f"Operação bloqueada: Checks de verificação retornaram '{ev.overall_state}'. "
                "Submissão permanece em estado BLOQUEADO até que todos os checks passem."
            )
        delivery_state = "AGUARDANDO_PO"

    # 4. Geração do RUC
    ruc_path, _ = generate_ruc(
        target,
        mission_title=title or f"Fatia em {current_branch}",
    )

    # Re-checa is_dirty após gerar o RUC
    git_info_after = check_git_status(target)
    is_dirty = git_info_after["is_dirty"]

    # 5. Operação remota: exige árvore limpa de alterações não commitadas
    if remote:
        if is_dirty:
            raise SubmitError(
                "Operação remota bloqueada: Existem alterações não commitadas na árvore de trabalho (árvore dirty). "
                "Commite todas as alterações e o RUC gerado antes de submeter com '--remote'."
            )
        if commits_ahead == 0:
            raise SubmitError(
                "Operação remota bloqueada: Nenhum commit à frente da branch base para enviar ao repositório remoto."
            )

        gh_check = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, check=False)
        if gh_check.returncode != 0:
            raise SubmitError("GitHub CLI (gh) não autenticado. Operação remota cancelada.")

        # Push da branch atual
        push_cmd = subprocess.run(
            ["git", "-C", str(target), "push", "-u", "origin", current_branch],
            capture_output=True,
            text=True,
            check=False,
        )
        if push_cmd.returncode != 0:
            raise SubmitError(f"Falha ao realizar git push na branch '{current_branch}': {push_cmd.stderr.strip()}")

        # Consulta PR existente
        view_pr = subprocess.run(
            ["gh", "pr", "view", current_branch, "--json", "number,url,isDraft,state"],
            cwd=str(target),
            capture_output=True,
            text=True,
            check=False,
        )

        pr_title = title or f"Fatia: {current_branch}"
        pr_body = body or f"Submissão da fatia sob governança C.H.\n\nEstado: AGUARDANDO_PO.\nRUC gerado em `{ruc_path.name}`."
        remote_details = ""

        if view_pr.returncode == 0:
            try:
                pr_data = json.loads(view_pr.stdout)
            except Exception as exc:
                raise SubmitError(f"Falha ao processar resposta do GitHub para o PR: {exc}")

            if not pr_data.get("isDraft"):
                raise SubmitSecurityError(
                    f"Operação remota bloqueada: O PR existente ({pr_data.get('url')}) NÃO é um Draft PR. "
                    "O CHDevFlow proíbe PRs regulares para merge sem autorização humana formal do PO."
                )
            if pr_data.get("state") in ("MERGED", "CLOSED"):
                raise SubmitError(f"Operação remota bloqueada: O PR existente está {pr_data.get('state')}.")

            remote_details = f"Draft PR existente identificado e validado: {pr_data.get('url')}"
        else:
            # Cria novo Draft PR
            create_pr = subprocess.run(
                ["gh", "pr", "create", "--draft", "--title", pr_title, "--body", pr_body],
                cwd=str(target),
                capture_output=True,
                text=True,
                check=False,
            )
            if create_pr.returncode != 0:
                raise SubmitError(f"Falha ao criar Draft PR no GitHub: {create_pr.stderr.strip()}")

            # Confirmação pós-criação do Draft PR
            confirm_cmd = ["gh", "pr", "view", current_branch, "--json", "number,url,isDraft"]
            confirm_res = subprocess.run(confirm_cmd, cwd=str(target), capture_output=True, text=True, check=False)
            if confirm_res.returncode != 0:
                raise SubmitError("Falha na confirmação do Draft PR: o PR criado não pôde ser verificado no GitHub.")

            try:
                confirm_data = json.loads(confirm_res.stdout)
            except Exception as exc:
                raise SubmitError(f"Resposta inválida na confirmação do PR: {exc}")

            if not confirm_data.get("isDraft"):
                raise SubmitSecurityError("Falha de segurança: o PR confirmado no GitHub não está marcado como Draft!")

            remote_details = f"Draft PR criado e confirmado com sucesso: {confirm_data.get('url')}"

        return {
            "branch": current_branch,
            "is_dirty": is_dirty,
            "commits_ahead": commits_ahead,
            "verification": verify_state,
            "ruc_file": str(ruc_path),
            "state": delivery_state,
            "remote_executed": True,
            "remote_details": remote_details,
        }

    return {
        "branch": current_branch,
        "is_dirty": is_dirty,
        "commits_ahead": commits_ahead,
        "verification": verify_state,
        "ruc_file": str(ruc_path),
        "state": delivery_state,
        "remote_executed": False,
        "remote_details": None,
    }
