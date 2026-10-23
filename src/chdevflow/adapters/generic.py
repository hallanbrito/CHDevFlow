"""Adapter genérico de governança universal (Git, GitHub CLI, Docker)."""
from __future__ import annotations

from pathlib import Path
import re
import shutil

from chdevflow.adapters.base import BaseAdapter, ToolDiagnostic, safe_run_command, sanitize_output


class GenericAdapter(BaseAdapter):
    name = "generic"
    display_name = "Governança Universal"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = True) -> list[ToolDiagnostic]:
        diagnostics: list[ToolDiagnostic] = []

        # 1. Git (Sempre obrigatório)
        git_path = shutil.which("git")
        if not git_path:
            diagnostics.append(ToolDiagnostic(
                tool="git",
                required=True,
                installed=False,
                version=None,
                status="AUSENTE",
                details="Git não encontrado no PATH.",
                remediation="Instale o Git via gerenciador de pacotes do sistema (ex.: pacman -S git, apt install git).",
            ))
        else:
            code, out, err = safe_run_command(["git", "--version"])
            if code == 0:
                v_match = re.search(r"git version\s+([0-9\.]+)", out)
                v_str = v_match.group(1) if v_match else out
                diagnostics.append(ToolDiagnostic(
                    tool="git",
                    required=True,
                    installed=True,
                    version=v_str,
                    status="OK",
                    details=f"Binário: {git_path}",
                ))
            else:
                diagnostics.append(ToolDiagnostic(
                    tool="git",
                    required=True,
                    installed=True,
                    version=None,
                    status="ERRO",
                    details=f"Falha ao executar git: {err or out}",
                ))

        # 2. GitHub CLI (gh) - Opcional para diagnósticos locais, obrigatório se operações remotas forem usadas
        gh_path = shutil.which("gh")
        if not gh_path:
            diagnostics.append(ToolDiagnostic(
                tool="gh",
                required=False,
                installed=False,
                version=None,
                status="AUSENTE",
                details="GitHub CLI (gh) não encontrado no PATH.",
                remediation="Instale o gh para operações integradas com GitHub (ex.: pacman -S github-cli).",
            ))
        else:
            # gh version
            code_v, out_v, _ = safe_run_command(["gh", "--version"])
            v_match = re.search(r"gh version\s+([0-9\.]+)", out_v)
            v_str = v_match.group(1) if v_match else "detectado"

            # gh auth status (sem exibir tokens!)
            code_auth, out_auth, err_auth = safe_run_command(["gh", "auth", "status"])
            auth_raw = f"{out_auth} {err_auth}"
            auth_clean = sanitize_output(auth_raw)

            is_authed = (code_auth == 0) or ("Logged in to" in auth_clean)
            auth_msg = "Autenticado no GitHub" if is_authed else "Não autenticado (execute 'gh auth login')"

            diagnostics.append(ToolDiagnostic(
                tool="gh",
                required=False,
                installed=True,
                version=v_str,
                status="OK" if is_authed else "AVISO",
                details=f"{auth_msg}. Binário: {gh_path}",
                remediation=None if is_authed else "Execute 'gh auth login' para conectar sua conta GitHub.",
            ))

        # 3. Docker (Opcional)
        docker_path = shutil.which("docker")
        if docker_path:
            code_d, out_d, _ = safe_run_command(["docker", "--version"])
            v_match = re.search(r"Docker version\s+([0-9\.]+)", out_d)
            v_str = v_match.group(1) if v_match else "detectado"
            diagnostics.append(ToolDiagnostic(
                tool="docker",
                required=False,
                installed=True,
                version=v_str,
                status="OK",
                details=f"Binário: {docker_path}",
            ))
        else:
            diagnostics.append(ToolDiagnostic(
                tool="docker",
                required=False,
                installed=False,
                version=None,
                status="AUSENTE",
                details="Docker não detectado (opcional para containers).",
            ))

        return diagnostics
