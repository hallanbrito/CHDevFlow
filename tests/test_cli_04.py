"""Testes da fatia CLI-04 — ch verify e evidências estruturadas."""
from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from chdevflow.cli import main as cli_main
from chdevflow.core.config import create_manifest_data, save_manifest
from chdevflow.core.evidence import (
    VerificationEvidence,
    VerificationSecurityError,
    execute_single_command,
    render_evidence_human,
    run_verification,
    validate_command_safety,
)


class TestCli04VerifyAndEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="ch_test_cli04_")

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_forbidden_mutable_commands_blocked(self) -> None:
        forbidden = [
            "git push origin main",
            "git push --force",
            "git merge origin/main",
            "npm publish --access public",
            "mvn deploy",
            "docker push myrepo/myimage:v1",
        ]
        for cmd in forbidden:
            with self.assertRaises(VerificationSecurityError):
                validate_command_safety(cmd)

    def test_manifest_without_checks_returns_not_run(self) -> None:
        target = Path(self.test_dir) / "EmptyApp"
        target.mkdir()
        manifest = create_manifest_data("EmptyApp")
        manifest["verification"]["commands"] = []
        save_manifest(target / "chdevflow.yaml", manifest)

        ev = run_verification(target, persist=False)
        self.assertEqual(ev.overall_state, "NOT_RUN")
        self.assertEqual(len(ev.commands), 0)

    def test_successful_verification_and_evidence_file(self) -> None:
        target = Path(self.test_dir) / "PassingApp"
        target.mkdir()
        manifest = create_manifest_data("PassingApp")
        manifest["verification"]["commands"] = ["echo 'check one'", "echo 'check two'"]
        save_manifest(target / "chdevflow.yaml", manifest)

        ev = run_verification(target, persist=True)
        self.assertEqual(ev.overall_state, "PASS")
        self.assertEqual(len(ev.commands), 2)
        self.assertEqual(ev.commands[0].state, "PASS")
        self.assertEqual(ev.commands[1].state, "PASS")

        # Verifica arquivo de evidência persistido
        self.assertIsNotNone(ev.evidence_file)
        ev_path = Path(ev.evidence_file)
        self.assertTrue(ev_path.is_file())
        saved_json = json.loads(ev_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_json["overall_state"], "PASS")
        self.assertEqual(saved_json["project_name"], "PassingApp")

    def test_fail_fast_skips_subsequent_commands(self) -> None:
        target = Path(self.test_dir) / "FailingApp"
        target.mkdir()
        manifest = create_manifest_data("FailingApp")
        manifest["verification"]["commands"] = [
            "echo 'primeiro ok'",
            "exit 1",
            "echo 'nao deve rodar'",
        ]
        save_manifest(target / "chdevflow.yaml", manifest)

        # 1. Com fail-fast ativo (padrão)
        ev_ff = run_verification(target, fail_fast=True, persist=False)
        self.assertEqual(ev_ff.overall_state, "FAIL")
        self.assertEqual(len(ev_ff.commands), 3)
        self.assertEqual(ev_ff.commands[0].state, "PASS")
        self.assertEqual(ev_ff.commands[1].state, "FAIL")
        self.assertEqual(ev_ff.commands[2].state, "SKIPPED")

        # 2. Sem fail-fast
        ev_no_ff = run_verification(target, fail_fast=False, persist=False)
        self.assertEqual(ev_no_ff.overall_state, "FAIL")
        self.assertEqual(ev_no_ff.commands[0].state, "PASS")
        self.assertEqual(ev_no_ff.commands[1].state, "FAIL")
        self.assertEqual(ev_no_ff.commands[2].state, "PASS")

    def test_sanitization_of_secrets_in_command_output(self) -> None:
        target = Path(self.test_dir)
        res = execute_single_command("echo 'Token simulado: gho_secrettoken999999'", cwd=target)
        self.assertEqual(res.state, "PASS")
        self.assertNotIn("gho_secrettoken999999", res.stdout)
        self.assertIn("[REDACTED_TOKEN]", res.stdout)

    def test_cli_verify_output_and_exit_code(self) -> None:
        target = Path(self.test_dir) / "CliApp"
        target.mkdir()
        manifest = create_manifest_data("CliApp")
        manifest["verification"]["commands"] = ["echo 'teste unitario'"]
        save_manifest(target / "chdevflow.yaml", manifest)

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code_pass = cli_main(["verify", "--path", str(target)])
        self.assertEqual(code_pass, 0)
        self.assertIn("CHDevFlow Verify", buf.getvalue())
        self.assertIn("PASS", buf.getvalue())

        # Teste com --json
        buf_json = io.StringIO()
        with patch("sys.stdout", buf_json):
            code_json = cli_main(["verify", "--path", str(target), "--json"])
        self.assertEqual(code_json, 0)
        parsed = json.loads(buf_json.getvalue())
        self.assertEqual(parsed["overall_state"], "PASS")


if __name__ == "__main__":
    unittest.main()
