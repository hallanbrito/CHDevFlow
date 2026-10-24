"""Adapter para stack Angular."""
from __future__ import annotations

from pathlib import Path
import re
import shutil

from chdevflow.adapters.base import BaseAdapter, ToolDiagnostic, safe_run_command
from chdevflow.adapters.node import NodeAdapter


class AngularAdapter(BaseAdapter):
    name = "angular"
    display_name = "Angular"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = False) -> list[ToolDiagnostic]:
        # Angular requer Node + npm como fundação
        node_adapter = NodeAdapter()
        diagnostics = node_adapter.check_prerequisites(project_path, is_required=is_required)

        # Diagnóstico opcional de Angular CLI global
        ng_path = shutil.which("ng")
        if ng_path:
            code, out, _ = safe_run_command(["ng", "version", "--help"])
            diagnostics.append(ToolDiagnostic(
                tool="ng",
                required=False,
                installed=True,
                version="detectado",
                status="OK",
                details=f"Angular CLI global: {ng_path}",
            ))
        else:
            diagnostics.append(ToolDiagnostic(
                tool="ng",
                required=False,
                installed=False,
                version=None,
                status="AVISO",
                details="Angular CLI (ng) global não detectado (projetos locais podem usar 'npx ng').",
                remediation="Instale globalmente via 'npm install -g @angular/cli' se desejar CLI global.",
            ))

        return diagnostics

    def get_default_verification_commands(self) -> list[str]:
        return ["npm test"]
