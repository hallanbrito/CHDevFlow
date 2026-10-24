"""Testes da fatia CLI-03 — ch doctor e adapters de stack."""
from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from chdevflow.adapters import ADAPTERS_REGISTRY, get_adapter
from chdevflow.adapters.base import safe_run_command, sanitize_output
from chdevflow.adapters.generic import GenericAdapter
from chdevflow.adapters.dotnet import DotnetAdapter
from chdevflow.adapters.python import PythonAdapter
from chdevflow.adapters.node import NodeAdapter
from chdevflow.adapters.angular import AngularAdapter
from chdevflow.adapters.react import ReactAdapter
from chdevflow.adapters.java import JavaAdapter
from chdevflow.adapters.postgres import PostgresAdapter
from chdevflow.cli import main as cli_main
from chdevflow.core.config import create_manifest_data, save_manifest
from chdevflow.core.doctor import render_doctor_human, run_doctor


class TestCli03DoctorAndAdapters(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="ch_test_cli03_")

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_registry_contains_all_required_adapters(self) -> None:
        required = ["generic", "python", "dotnet", "node", "angular", "react", "java", "postgres"]
        for name in required:
            adapter = get_adapter(name)
            self.assertIsNotNone(adapter, f"Adapter '{name}' não registrado")

    def test_sanitize_output_strips_github_tokens(self) -> None:
        raw = "Logged in to github.com account hallanbrito (token: gho_secrettoken123456789)"
        cleaned = sanitize_output(raw)
        self.assertNotIn("gho_secrettoken123456789", cleaned)
        self.assertIn("[REDACTED_TOKEN]", cleaned)

        bearer_raw = "Authorization: Bearer my-super-secret-token"
        bearer_clean = sanitize_output(bearer_raw)
        self.assertNotIn("my-super-secret-token", bearer_clean)
        self.assertIn("[REDACTED_BEARER]", bearer_clean)

    def test_safe_run_command_handles_not_found_and_timeout(self) -> None:
        # Comando inexistente
        code, out, err = safe_run_command(["nonexistent_command_xyz_123"])
        self.assertEqual(code, -2)
        self.assertIn("não encontrado", err)

        # Timeout simulado
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["sleep"], timeout=0.1)):
            code_t, _, err_t = safe_run_command(["sleep", "1"], timeout=0.1)
            self.assertEqual(code_t, -1)
            self.assertIn("Timeout", err_t)

    def test_generic_adapter_diagnostics(self) -> None:
        adapter = GenericAdapter()
        diag = adapter.check_prerequisites(is_required=True)
        tools = [d.tool for d in diag]
        self.assertIn("git", tools)
        self.assertIn("gh", tools)
        self.assertIn("docker", tools)

        git_diag = next(d for d in diag if d.tool == "git")
        self.assertTrue(git_diag.required)
        self.assertTrue(git_diag.installed)
        self.assertEqual(git_diag.status, "OK")

    def test_dotnet_adapter_mock_present_and_absent(self) -> None:
        adapter = DotnetAdapter()

        # Presente
        with patch("shutil.which", return_value="/usr/bin/dotnet"), \
             patch("chdevflow.adapters.dotnet.safe_run_command", return_value=(0, "8.0.100", "")):
            diag = adapter.check_prerequisites(is_required=True)
            self.assertEqual(len(diag), 1)
            self.assertTrue(diag[0].installed)
            self.assertEqual(diag[0].version, "8.0.100")
            self.assertEqual(diag[0].status, "OK")

        # Ausente
        with patch("shutil.which", return_value=None):
            diag_absent = adapter.check_prerequisites(is_required=True)
            self.assertEqual(len(diag_absent), 1)
            self.assertFalse(diag_absent[0].installed)
            self.assertEqual(diag_absent[0].status, "AUSENTE")
            self.assertIsNotNone(diag_absent[0].remediation)

    def test_postgres_adapter_detection_only(self) -> None:
        adapter = PostgresAdapter()
        diag = adapter.check_prerequisites(is_required=False)
        self.assertEqual(len(diag), 1)
        self.assertEqual(diag[0].tool, "psql")
        # Deve ser puramente consultivo/detecção
        self.assertFalse(diag[0].required)

    def test_run_doctor_with_manifest_requirements(self) -> None:
        target = Path(self.test_dir) / "DotnetProject"
        target.mkdir()
        manifest = create_manifest_data("DotnetProject", backend="dotnet", frontend="angular")
        save_manifest(target / "chdevflow.yaml", manifest)

        # Simula dotnet instalado com versão requerida 10 e ng ausente
        with patch("shutil.which") as mock_which, \
             patch("chdevflow.adapters.generic.safe_run_command", return_value=(0, "git version 2.44.0", "")), \
             patch("chdevflow.adapters.dotnet.safe_run_command", return_value=(0, "10.0.100", "")), \
             patch("chdevflow.adapters.node.safe_run_command", return_value=(0, "v20.0.0", "")):
            def custom_which(name: str):
                if name in ("git", "dotnet", "node", "npm"):
                    return f"/usr/bin/{name}"
                return None
            mock_which.side_effect = custom_which

            report = run_doctor(target)
            self.assertTrue(report["manifest_found"])
            self.assertIn("dotnet", report["required_stacks"])
            self.assertIn("angular", report["required_stacks"])
            self.assertTrue(report["healthy"])

    def test_cli_doctor_output_human_and_json(self) -> None:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cli_main(["doctor", "--path", str(self.test_dir)])
        # No diretório de teste vazio, git é requerido e está instalado, logo healthy == 0
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("CHDevFlow Doctor", output)
        self.assertIn("Obrigatórias:", output)

        buf_json = io.StringIO()
        with patch("sys.stdout", buf_json):
            code_json = cli_main(["doctor", "--path", str(self.test_dir), "--json"])
        self.assertEqual(code_json, 0)
        parsed = json.loads(buf_json.getvalue())
        self.assertIn("healthy", parsed)
        self.assertIn("summary", parsed)


if __name__ == "__main__":
    unittest.main()
