"""Adapter para stack Python."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys

from chdevflow.adapters.base import BaseAdapter, ToolDiagnostic, safe_run_command


class PythonAdapter(BaseAdapter):
    name = "python"
    display_name = "Python"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = False) -> list[ToolDiagnostic]:
        diagnostics: list[ToolDiagnostic] = []

        # 1. Interpretador Python
        py_path = shutil.which("python3") or shutil.which("python") or sys.executable
        code, out, _ = safe_run_command([py_path, "--version"])
        v_match = re.search(r"Python\s+([0-9\.]+)", out)
        v_str = v_match.group(1) if v_match else "3.x"

        diagnostics.append(ToolDiagnostic(
            tool="python",
            required=is_required,
            installed=True,
            version=v_str,
            status="OK",
            details=f"Interpretador: {py_path}",
        ))

        # 2. uv (gerenciador moderno recomendado)
        uv_path = shutil.which("uv")
        if uv_path:
            code_uv, out_uv, _ = safe_run_command(["uv", "--version"])
            v_match = re.search(r"uv\s+([0-9\.]+)", out_uv)
            v_str = v_match.group(1) if v_match else "detectado"
            diagnostics.append(ToolDiagnostic(
                tool="uv",
                required=False,
                installed=True,
                version=v_str,
                status="OK",
                details=f"Binário: {uv_path}",
            ))
        else:
            diagnostics.append(ToolDiagnostic(
                tool="uv",
                required=False,
                installed=False,
                version=None,
                status="AUSENTE",
                details="uv não detectado (recomendado para empacotamento rápido).",
                remediation="Instale uv via: curl -LsSf https://astral.sh/uv/install.sh | sh",
            ))

        return diagnostics

    def get_default_verification_commands(self) -> list[str]:
        return ["python -m unittest"]
