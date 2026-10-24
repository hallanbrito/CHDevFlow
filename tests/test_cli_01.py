"""Testes da fatia CLI-01 — empacotamento e núcleo inicial do comando ch."""
from __future__ import annotations

import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

# Garante acesso a src mesmo sem instalação global
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from chdevflow import __version__
from chdevflow.cli import main as cli_main
from chdevflow.core.init import run_init
from chdevflow.core.tree import safe, generate as generate_tree


class TestCli01Core(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="ch_test_cli01_")

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_version_constant(self) -> None:
        self.assertEqual(__version__, "0.1.0.dev0")

    def test_cli_version_flag(self) -> None:
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm, patch("sys.stdout", buf):
            cli_main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("chdevflow 0.1.0.dev0", buf.getvalue())

    def test_cli_help_flag(self) -> None:
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm, patch("sys.stdout", buf):
            cli_main(["--help"])
        self.assertEqual(cm.exception.code, 0)
        output = buf.getvalue()
        self.assertIn("init", output)
        self.assertIn("tree", output)

    def test_init_dry_run_does_not_create_files(self) -> None:
        target = Path(self.test_dir) / "project_dry"
        target.mkdir()
        buf = io.StringIO()

        created, skipped = run_init(destination=target, apply=False, out=buf)
        self.assertGreater(created, 0)
        self.assertEqual(skipped, 0)
        self.assertIn("CRIARIA", buf.getvalue())
        self.assertFalse((target / "AGENTS.md").exists())
        self.assertFalse((target / "docs").exists())

    def test_init_apply_and_non_overwrite(self) -> None:
        target = Path(self.test_dir) / "project_apply"
        target.mkdir()

        # 1. Aplicação inicial
        created1, skipped1 = run_init(destination=target, apply=True)
        self.assertGreater(created1, 0)
        self.assertEqual(skipped1, 0)
        self.assertTrue((target / "AGENTS.md").exists())
        self.assertTrue((target / "docs" / "PROJETO.md").exists())

        # Modifica um arquivo existente para atestar preservação
        agents_file = target / "AGENTS.md"
        custom_content = "CONTEUDO CUSTOMIZADO PO"
        agents_file.write_text(custom_content, encoding="utf-8")

        # 2. Segunda execução com --apply
        buf = io.StringIO()
        created2, skipped2 = run_init(destination=target, apply=True, out=buf)
        self.assertEqual(created2, 0)
        self.assertGreater(skipped2, 0)
        self.assertIn("PRESERVAR AGENTS.md", buf.getvalue())
        self.assertEqual(agents_file.read_text(encoding="utf-8"), custom_content)

    def test_tree_excludes_sensitive_names_and_suffixes(self) -> None:
        self.assertTrue(safe(Path("src/main.py")))
        self.assertTrue(safe(Path("README.md")))

        # Nomes proibidos
        self.assertFalse(safe(Path(".env")))
        self.assertFalse(safe(Path(".env.local")))
        self.assertFalse(safe(Path("config/.env.prod")))
        self.assertFalse(safe(Path("secrets.json")))
        self.assertFalse(safe(Path("token")))
        self.assertFalse(safe(Path("credentials.json")))
        self.assertFalse(safe(Path("my_key.secret")))

        # Extensões proibidas
        self.assertFalse(safe(Path("server.pem")))
        self.assertFalse(safe(Path("cert.pfx")))
        self.assertFalse(safe(Path("private.key")))

        # Diretórios proibidos
        self.assertFalse(safe(Path(".git/config")))
        self.assertFalse(safe(Path("node_modules/package.json")))
        self.assertFalse(safe(Path(".venv/bin/python")))

    def test_tree_generation_in_directory(self) -> None:
        target = Path(self.test_dir) / "project_tree"
        target.mkdir()
        (target / "src").mkdir()
        (target / "src" / "app.py").write_text("print('hello')", encoding="utf-8")
        (target / ".env").write_text("SECRET=12345", encoding="utf-8")
        (target / "token").write_text("mytoken", encoding="utf-8")

        tree_path, changed = generate_tree(target)
        self.assertTrue(changed)
        self.assertTrue(tree_path.exists())

        content = tree_path.read_text(encoding="utf-8")
        self.assertIn("app.py", content)
        self.assertNotIn(".env", content)
        self.assertNotIn("mytoken", content)
        self.assertNotIn("SECRET", content)

    def test_cli_subcommands_dispatch(self) -> None:
        target = Path(self.test_dir) / "project_cli"
        target.mkdir()

        code_init = cli_main(["init", "--path", str(target), "--apply"])
        self.assertEqual(code_init, 0)
        self.assertTrue((target / "AGENTS.md").exists())

        code_tree = cli_main(["tree", "--path", str(target)])
        self.assertEqual(code_tree, 0)
        self.assertTrue((target / "docs" / "ARVORE_PROJETO.md").exists())


if __name__ == "__main__":
    unittest.main()
