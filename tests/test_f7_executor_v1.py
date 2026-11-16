"""E3-B: contrato offline do executor (sem docker/credenciais)."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import f7_executor_v1 as exe


class ExecutorV1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_contract.py").write_text(
            "import unittest\n"
            "class Contract(unittest.TestCase):\n"
            "  def test_ok(self): self.assertEqual(2 + 2, 4)\n", encoding="utf-8")

    def test_arvore_permitida(self):
        exe.validate_test_tree(self.root)

    def test_nao_aceita_link(self):
        (self.root / "tests" / "test_contract.py").unlink()
        target = self.root / "original.py"
        target.write_text("pass\n", encoding="utf-8")
        try:
            (self.root / "tests" / "test_contract.py").symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Sem permissao symlink")
        with self.assertRaisesRegex(ValueError, "Link"):
            exe.validate_test_tree(self.root)

    def test_nao_aceita_arquivo_estranho(self):
        (self.root / "tests" / "payload.bin").write_bytes(b"\x00")
        with self.assertRaisesRegex(ValueError, "fora do contrato"):
            exe.validate_test_tree(self.root)

    def test_testes_reais_passam_e_geram_digest(self):
        out = io.StringIO()
        with patch.object(exe, "TEST_ROOT", self.root), redirect_stdout(out):
            result = exe.run_tests()
        record = json.loads(out.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(record["status"], "TESTS_PASS")
        self.assertRegex(record["log_sha256"], r"^[0-9a-f]{64}$")

    def test_testes_reais_falham_sem_falso_sucesso(self):
        (self.root / "tests" / "test_contract.py").write_text(
            "import unittest\n"
            "class Contract(unittest.TestCase):\n"
            "  def test_fail(self): self.assertEqual(1, 2)\n", encoding="utf-8")
        out = io.StringIO()
        with patch.object(exe, "TEST_ROOT", self.root), redirect_stdout(out):
            result = exe.run_tests()
        self.assertEqual(result, 12)
        self.assertEqual(json.loads(out.getvalue())["status"], "TESTS_FAILED")

    def test_sem_credencial_github(self):
        with patch.object(exe.os, "geteuid", return_value=65534), \
             patch.object(exe.os, "getegid", return_value=65534), \
             patch.dict(exe.os.environ, {"GH_TOKEN": "nao_permitido"}):
            with self.assertRaisesRegex(ValueError, "credencial"):
                exe.safety_preflight()


if __name__ == "__main__":
    unittest.main()
