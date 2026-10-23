"""Adapter para stack Java."""
from __future__ import annotations

from pathlib import Path
import re
import shutil

from chdevflow.adapters.base import BaseAdapter, ToolDiagnostic, safe_run_command


class JavaAdapter(BaseAdapter):
    name = "java"
    display_name = "Java JDK / Maven"

    def check_prerequisites(self, project_path: Path | None = None, is_required: bool = False) -> list[ToolDiagnostic]:
        diagnostics: list[ToolDiagnostic] = []

        # 1. Java runtime / JDK
        java_path = shutil.which("java")
        if not java_path:
            diagnostics.append(ToolDiagnostic(
                tool="java",
                required=is_required,
                installed=False,
                version=None,
                status="AUSENTE",
                details="Java runtime / JDK não encontrado no PATH.",
                remediation="Instale o JDK (ex.: OpenJDK 21) via gerenciador de pacotes do sistema.",
            ))
        else:
            code, out, err = safe_run_command(["java", "-version"])
            raw = f"{out} {err}"
            v_match = re.search(r"version\s+\"([0-9\._]+)\"", raw)
            v_str = v_match.group(1) if v_match else "detectado"
            diagnostics.append(ToolDiagnostic(
                tool="java",
                required=is_required,
                installed=True,
                version=v_str,
                status="OK",
                details=f"Binário: {java_path}",
            ))

        # 2. Maven (opcional/recomendado para builds Java)
        mvn_path = shutil.which("mvn")
        if mvn_path:
            code_m, out_m, _ = safe_run_command(["mvn", "-v"])
            v_match = re.search(r"Apache Maven\s+([0-9\.]+)", out_m)
            v_str = v_match.group(1) if v_match else "detectado"
            diagnostics.append(ToolDiagnostic(
                tool="mvn",
                required=False,
                installed=True,
                version=v_str,
                status="OK",
                details=f"Binário: {mvn_path}",
            ))
        else:
            diagnostics.append(ToolDiagnostic(
                tool="mvn",
                required=False,
                installed=False,
                version=None,
                status="AUSENTE",
                details="Maven (mvn) não detectado.",
                remediation="Instale o Maven se o projeto utilizar build baseado em pom.xml.",
            ))

        return diagnostics

    def get_default_verification_commands(self) -> list[str]:
        return ["mvn test"]
