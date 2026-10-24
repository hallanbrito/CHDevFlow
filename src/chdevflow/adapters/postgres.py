"""Adapter para detecção de cliente PostgreSQL (detecção apenas)."""
from __future__ import annotations

from pathlib import Path
import re
import shutil

from chdevflow.adapters.base import BaseAdapter, ToolDiagnostic, safe_run_command


class PostgresAdapter(BaseAdapter):
    name = "postgres"
    display_name = "PostgreSQL (Detecção)"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = False) -> list[ToolDiagnostic]:
        diagnostics: list[ToolDiagnostic] = []

        # Detecção de ferramenta cliente (psql ou pg_isready) sem conexão de rede nem credenciais
        psql_path = shutil.which("psql")
        if psql_path:
            code, out, _ = safe_run_command(["psql", "--version"])
            v_match = re.search(r"psql\s+\(PostgreSQL\)\s+([0-9\.]+)", out)
            v_str = v_match.group(1) if v_match else "detectado"
            diagnostics.append(ToolDiagnostic(
                tool="psql",
                required=is_required,
                installed=True,
                version=v_str,
                status="OK",
                details=f"Cliente local: {psql_path}",
            ))
        else:
            diagnostics.append(ToolDiagnostic(
                tool="psql",
                required=is_required,
                installed=False,
                version=None,
                status="AUSENTE",
                details="Cliente psql não detectado localmente (apenas detecção estática).",
                remediation="Instale o cliente postgresql caso necessite de utilitários locais.",
            ))

        return diagnostics
