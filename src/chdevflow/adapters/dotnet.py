"""Adapter para stack .NET."""
from __future__ import annotations

from pathlib import Path
import re
import shutil

from chdevflow.adapters.base import BaseAdapter, ToolDiagnostic, safe_run_command


class DotnetAdapter(BaseAdapter):
    name = "dotnet"
    display_name = ".NET SDK"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = False) -> list[ToolDiagnostic]:
        diagnostics: list[ToolDiagnostic] = []

        dotnet_path = shutil.which("dotnet")
        if not dotnet_path:
            diagnostics.append(ToolDiagnostic(
                tool="dotnet",
                required=is_required,
                installed=False,
                version=None,
                status="AUSENTE",
                details=".NET SDK não encontrado no PATH.",
                remediation="Instale o .NET SDK via https://dot.net ou pelo gerenciador de pacotes da sua distribuição (ex.: pacman -S dotnet-sdk, apt install dotnet-sdk-8.0).",
            ))
        else:
            code, out, err = safe_run_command(["dotnet", "--version"])
            if code == 0:
                v_match = re.search(r"([0-9\.]+)", out)
                v_str = v_match.group(1) if v_match else out
                diagnostics.append(ToolDiagnostic(
                    tool="dotnet",
                    required=is_required,
                    installed=True,
                    version=v_str,
                    status="OK",
                    details=f"SDK: {dotnet_path} (versão {v_str})",
                ))
            else:
                diagnostics.append(ToolDiagnostic(
                    tool="dotnet",
                    required=is_required,
                    installed=True,
                    version=None,
                    status="ERRO",
                    details=f"Falha ao consultar dotnet: {err or out}",
                ))

        return diagnostics

    def get_default_verification_commands(self) -> list[str]:
        return ["dotnet build", "dotnet test"]
