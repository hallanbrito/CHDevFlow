"""Adapter para runtime Node.js e gerenciador npm."""
from __future__ import annotations

from pathlib import Path
import re
import shutil

from chdevflow.adapters.base import BaseAdapter, ToolDiagnostic, safe_run_command


class NodeAdapter(BaseAdapter):
    name = "node"
    display_name = "Node.js / npm"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = False) -> list[ToolDiagnostic]:
        diagnostics: list[ToolDiagnostic] = []

        # 1. Node.js
        node_path = shutil.which("node")
        if not node_path:
            diagnostics.append(ToolDiagnostic(
                tool="node",
                required=is_required,
                installed=False,
                version=None,
                status="AUSENTE",
                details="Node.js não encontrado no PATH.",
                remediation="Instale o Node.js via nvm, fnm ou pelo gerenciador de pacotes do sistema.",
            ))
        else:
            code, out, err = safe_run_command(["node", "-v"])
            if code == 0:
                v_match = re.search(r"v?([0-9\.]+)", out)
                v_str = v_match.group(1) if v_match else out
                diagnostics.append(ToolDiagnostic(
                    tool="node",
                    required=is_required,
                    installed=True,
                    version=v_str,
                    status="OK",
                    details=f"Binário: {node_path}",
                ))
            else:
                diagnostics.append(ToolDiagnostic(
                    tool="node",
                    required=is_required,
                    installed=True,
                    version=None,
                    status="ERRO",
                    details=f"Falha ao executar node: {err or out}",
                ))

        # 2. npm
        npm_path = shutil.which("npm")
        if not npm_path:
            diagnostics.append(ToolDiagnostic(
                tool="npm",
                required=is_required,
                installed=False,
                version=None,
                status="AUSENTE",
                details="npm não encontrado no PATH.",
                remediation="Instale o npm junto com o Node.js.",
            ))
        else:
            code, out, _ = safe_run_command(["npm", "-v"])
            v_match = re.search(r"([0-9\.]+)", out)
            v_str = v_match.group(1) if v_match else out
            diagnostics.append(ToolDiagnostic(
                tool="npm",
                required=is_required,
                installed=True,
                version=v_str,
                status="OK",
                details=f"Binário: {npm_path}",
            ))

        return diagnostics

    def get_default_verification_commands(self) -> list[str]:
        return ["npm test"]
