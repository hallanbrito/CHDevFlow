"""CH-WIN-01: testes deterministas Windows/Linux, sem shell nem rede."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from chdevflow.core.evidence import (
    VerificationSecurityError, execute_single_command,
    parse_and_validate_command, sanitize_subprocess_env,
)


class CrossPlatformVerifyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.safe_path = sanitize_subprocess_env(None, self.root).get("PATH", "")

    def test_python_e_python3_usam_interprete_da_sessao(self):
        for bin_name in ("python", "python3"):
            with self.subTest(bin_name=bin_name):
                args = parse_and_validate_command(
                    bin_name + " -m unittest", self.root, self.safe_path)
                self.assertEqual(Path(args[0]).resolve(), Path(sys.executable).resolve())
                self.assertEqual(args[1:3], ["-m", "unittest"])

    def test_echo_sem_shell_com_interprete_seguro(self):
        command = parse_and_validate_command(
            "echo validacao ok", self.root, "")
        self.assertEqual(Path(command[0]).resolve(), Path(sys.executable).resolve())
        self.assertIn("-I", command)
        self.assertIn("-c", command)
        self.assertEqual(command[-2:], ["validacao", "ok"])

    def test_echo_executa_sem_cmd_ou_bash(self):
        outcome = execute_single_command("echo 'validacao ok'", cwd=self.root)
        self.assertEqual(outcome.state, "PASS", outcome.stderr)
        self.assertIn("validacao ok", outcome.stdout)

    def test_shell_metacharacter_e_python_c_permanecem_bloqueados(self):
        for command in ("echo ok && echo perigo", "python3 -c print(1)",
                        "echo x; echo y"):
            with self.subTest(command=command), self.assertRaises(
                    VerificationSecurityError):
                parse_and_validate_command(command, self.root, self.safe_path)


if __name__ == "__main__":
    unittest.main()
