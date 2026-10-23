"""Testes da fatia CLI-02 — manifesto chdevflow.yaml, ch new e ch status."""
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

from chdevflow.cli import main as cli_main
from chdevflow.core.config import (
    ManifestError,
    ManifestSecurityError,
    create_manifest_data,
    dump_yaml_text,
    load_manifest,
    parse_yaml_text,
    save_manifest,
    validate_manifest,
)
from chdevflow.core.project import create_project
from chdevflow.core.status import get_project_status, render_status_human


class TestCli02ManifestAndCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="ch_test_cli02_")

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_valid_manifest_schema(self) -> None:
        data = create_manifest_data("PulseOps", backend="dotnet", frontend="angular", database="postgres")
        errors = validate_manifest(data)
        self.assertEqual(errors, [])
        self.assertEqual(data["version"], "1")
        self.assertEqual(data["project"]["name"], "PulseOps")
        self.assertEqual(data["governance"]["method"], "CH")
        self.assertTrue(data["governance"]["require_po_approval"])

    def test_invalid_manifest_missing_or_bad_fields(self) -> None:
        bad_manifest = {
            "version": "2",
            "project": {},
            "governance": {"method": "AGILE"},
        }
        errors = validate_manifest(bad_manifest)
        self.assertTrue(any("version" in e for e in errors))
        self.assertTrue(any("name" in e for e in errors))
        self.assertTrue(any("method" in e for e in errors))

    def test_manifest_disallows_secrets_in_keys_and_values(self) -> None:
        with self.assertRaises(ManifestSecurityError):
            create_manifest_data("LeakyApp", backend="python")
            # Injeta campo com chave proibida
            data = {"version": "1", "project": {"name": "Test"}, "api_key": "12345"}
            validate_manifest(data)

        with self.assertRaises(ManifestSecurityError):
            data = {"version": "1", "project": {"name": "Test"}, "db_password": "supersecret"}
            validate_manifest(data)

        with self.assertRaises(ManifestSecurityError):
            data = {"version": "1", "project": {"name": "Test"}, "auth_header": "Bearer secret-token-xyz"}
            validate_manifest(data)

    def test_dump_and_load_yaml_manifest(self) -> None:
        data = create_manifest_data("MiniApp", backend="python", frontend="react")
        m_file = Path(self.test_dir) / "chdevflow.yaml"
        save_manifest(m_file, data)
        self.assertTrue(m_file.exists())

        loaded = load_manifest(m_file)
        self.assertEqual(loaded["project"]["name"], "MiniApp")
        self.assertEqual(loaded["stack"]["backend"]["type"], "python")
        self.assertEqual(loaded["stack"]["frontend"]["type"], "react")

    def test_create_project_new_success_and_conflict(self) -> None:
        base = Path(self.test_dir)
        proj_dir = create_project(
            name="AlphaOne",
            base_dir=base,
            backend="dotnet",
            frontend="angular",
            database="postgres",
        )
        self.assertTrue(proj_dir.is_dir())
        self.assertTrue((proj_dir / "chdevflow.yaml").exists())
        self.assertTrue((proj_dir / "AGENTS.md").exists())
        self.assertTrue((proj_dir / "docs" / "ARVORE_PROJETO.md").exists())

        # Tentativa de criar novamente sobre diretório ocupado deve falhar fechado
        with self.assertRaises(FileExistsError):
            create_project(name="AlphaOne", base_dir=base)

    def test_create_project_preset(self) -> None:
        base = Path(self.test_dir)
        proj_dir = create_project(
            name="PresetApp",
            base_dir=base,
            preset="dotnet-angular",
        )
        loaded = load_manifest(proj_dir / "chdevflow.yaml")
        self.assertEqual(loaded["stack"]["backend"]["type"], "dotnet")
        self.assertEqual(loaded["stack"]["frontend"]["type"], "angular")

    def test_status_outside_and_inside_git(self) -> None:
        base = Path(self.test_dir)
        proj_dir = create_project(name="GitStatusTest", base_dir=base)

        # 1. Fora do Git
        st1 = get_project_status(proj_dir)
        self.assertFalse(st1["git"]["is_git"])
        self.assertEqual(st1["authorization"]["status"], "NÃO_INFERIDA")
        self.assertTrue(any("git init" in p for p in st1["pendencies"]))

        # 2. Inicializa Git localmente
        subprocess.run(["git", "-C", str(proj_dir), "init", "-b", "main"], check=True, capture_output=True)
        st2 = get_project_status(proj_dir)
        self.assertTrue(st2["git"]["is_git"])
        self.assertEqual(st2["git"]["branch"], "main")
        self.assertTrue(st2["git"]["is_dirty"])

    def test_cli_new_and_status_commands(self) -> None:
        base = Path(self.test_dir)
        buf = io.StringIO()

        # Executa ch new via CLI
        code_new = cli_main([
            "new", "WebShop",
            "--path", str(base),
            "--backend", "python",
            "--frontend", "react",
        ])
        self.assertEqual(code_new, 0)
        webshop_dir = base / "WebShop"
        self.assertTrue((webshop_dir / "chdevflow.yaml").exists())

        # Executa ch status normal
        with patch("sys.stdout", buf):
            code_status = cli_main(["status", "--path", str(webshop_dir)])
        self.assertEqual(code_status, 0)
        output = buf.getvalue()
        self.assertIn("CHDevFlow — Estado do Projeto: WebShop", output)
        self.assertIn("NÃO_INFERIDA", output)

        # Executa ch status --json
        buf_json = io.StringIO()
        with patch("sys.stdout", buf_json):
            code_json = cli_main(["status", "--path", str(webshop_dir), "--json"])
        self.assertEqual(code_json, 0)
        parsed = json.loads(buf_json.getvalue())
        self.assertEqual(parsed["name"], "WebShop")
        self.assertEqual(parsed["manifest"]["status"], "PRESENTE")


if __name__ == "__main__":
    unittest.main()
