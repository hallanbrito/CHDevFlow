"""Testes da fatia CLI-06 — ch watch, integração Sentinela e ensaio E2E completo."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_SENTINELA_SRC = Path(__file__).resolve().parent.parent / "apps" / "bootstrap" / "sentinela" / "src"
if _SENTINELA_SRC.is_dir() and str(_SENTINELA_SRC) not in sys.path:
    sys.path.insert(0, str(_SENTINELA_SRC))

from chdevflow.cli import main as cli_main
from chdevflow.core.config import load_manifest
from chdevflow.core.watch import WatchSecurityError, run_watch


class TestCli06WatchAndE2E(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="ch_test_cli06_")
        # Garante autossuficiência do executável 'ch' no ambiente de testes E2E mesmo sem instalação prévia
        import chdevflow
        src_path = Path(chdevflow.__file__).resolve().parent.parent
        bin_dir = Path(self.test_dir) / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        ch_shim = bin_dir / "ch"
        ch_shim.write_text(
            f'#!/bin/sh\nexport PYTHONPATH="{src_path}:${{PYTHONPATH}}"\nexec "{sys.executable}" -m chdevflow.cli "$@"\n',
            encoding="utf-8",
        )
        ch_shim.chmod(0o755)
        self._orig_path = os.environ.get("PATH", "")
        self._orig_pypath = os.environ.get("PYTHONPATH", "")
        os.environ["PATH"] = f"{bin_dir}:{self._orig_path}"
        os.environ["PYTHONPATH"] = f"{src_path}:{self._orig_pypath}" if self._orig_pypath else str(src_path)

    def tearDown(self) -> None:
        if hasattr(self, "_orig_path"):
            os.environ["PATH"] = self._orig_path
        if hasattr(self, "_orig_pypath"):
            if self._orig_pypath:
                os.environ["PYTHONPATH"] = self._orig_pypath
            else:
                os.environ.pop("PYTHONPATH", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_watch_without_once_raises_security_error(self) -> None:
        with self.assertRaises(WatchSecurityError):
            run_watch(once=False)

    def test_watch_delegates_to_sentinela(self) -> None:
        # Mock do comando_watch da Sentinela
        with patch("ch_sentinela.cli.comando_watch", return_value=0) as mock_cw:
            code = run_watch(once=True, dry_run=True)
            self.assertEqual(code, 0)
            mock_cw.assert_called_once()
            args_passed = mock_cw.call_args[0][0]
            self.assertTrue(args_passed.once)
            self.assertTrue(args_passed.dry_run)

    def test_e2e_full_cycle(self) -> None:
        """
        Ensaio E2E temporário definido no épico CLI-06 e auditoria AUD-CLI:
        1. ch new exemplo --frontend react (sem package.json -> check local executável ch status)
        2. ch doctor
        3. ch status
        4. ch verify com check local inofensivo -> exigência code_ver == 0 e PASS real
        5. ch ruc -> reflete PASS real e APROVADO_TECNICAMENTE
        6. ch watch --once --dry-run
        """
        base = Path(self.test_dir)

        # 1. ch new exemplo --frontend react
        code_new = cli_main(["new", "exemplo", "--path", str(base), "--frontend", "react"])
        self.assertEqual(code_new, 0)
        exemplo_dir = base / "exemplo"
        self.assertTrue((exemplo_dir / "chdevflow.yaml").exists())
        self.assertTrue((exemplo_dir / "AGENTS.md").exists())
        self.assertTrue((exemplo_dir / ".gitignore").exists())

        # Garante que npm test NÃO foi configurado sem package.json e usa status estrito
        manifest = load_manifest(exemplo_dir / "chdevflow.yaml")
        commands = manifest["verification"]["commands"]
        self.assertNotIn("npm test", commands)
        self.assertIn("ch status --strict", commands)

        # 2. ch doctor
        buf_doc = io.StringIO()
        with patch("sys.stdout", buf_doc):
            code_doc = cli_main(["doctor", "--path", str(exemplo_dir)])
        self.assertEqual(code_doc, 0)
        self.assertIn("CHDevFlow Doctor", buf_doc.getvalue())

        # 3. ch status
        buf_st = io.StringIO()
        with patch("sys.stdout", buf_st):
            code_st = cli_main(["status", "--path", str(exemplo_dir)])
        self.assertEqual(code_st, 0)
        self.assertIn("CHDevFlow — Estado do Projeto: exemplo", buf_st.getvalue())

        # 4. ch verify com check local inofensivo (ch status)
        buf_ver = io.StringIO()
        with patch("sys.stdout", buf_ver):
            code_ver = cli_main(["verify", "--path", str(exemplo_dir)])
        self.assertEqual(code_ver, 0)
        self.assertIn("PASS", buf_ver.getvalue())

        # 5. ch ruc
        buf_ruc = io.StringIO()
        with patch("sys.stdout", buf_ruc):
            code_ruc = cli_main(["ruc", "--path", str(exemplo_dir)])
        self.assertEqual(code_ruc, 0)
        ruc_file = exemplo_dir / "docs" / "CH" / "RELATORIO-UNIVERSAL-CH-ULTIMO.md"
        self.assertTrue(ruc_file.exists())
        ruc_text = ruc_file.read_text(encoding="utf-8")
        self.assertIn("RUC/1.0", ruc_text)
        self.assertIn("APROVADO_TECNICAMENTE", ruc_text)
        self.assertIn("PASS", ruc_text)

        # 6. ch watch --once --dry-run
        with patch("ch_sentinela.cli.comando_watch", return_value=0):
            buf_watch = io.StringIO()
            with patch("sys.stdout", buf_watch):
                code_watch = cli_main(["watch", "--once", "--dry-run"])
            self.assertEqual(code_watch, 0)


if __name__ == "__main__":
    unittest.main()
