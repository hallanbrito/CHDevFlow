"""Testes da fatia CLI-05 — ch mission, ch ruc e ch submit."""
from __future__ import annotations

import io
import os
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
from chdevflow.core.config import create_manifest_data, save_manifest
from chdevflow.core.evidence import run_verification
from chdevflow.core.init import run_init
from chdevflow.core.tree import generate as generate_tree
from chdevflow.core.mission import create_mission, generate_mission_markdown, slugify
from chdevflow.core.ruc import generate_ruc, generate_ruc_text
from chdevflow.core.submit import SubmitError, SubmitSecurityError, validate_and_submit


class TestCli05MissionRucSubmit(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="ch_test_cli05_")
        self._orig_git_author_name = os.environ.get("GIT_AUTHOR_NAME")
        self._orig_git_author_email = os.environ.get("GIT_AUTHOR_EMAIL")
        self._orig_git_committer_name = os.environ.get("GIT_COMMITTER_NAME")
        self._orig_git_committer_email = os.environ.get("GIT_COMMITTER_EMAIL")
        os.environ["GIT_AUTHOR_NAME"] = "CHDevFlow Test"
        os.environ["GIT_AUTHOR_EMAIL"] = "test@chdevflow.local"
        os.environ["GIT_COMMITTER_NAME"] = "CHDevFlow Test"
        os.environ["GIT_COMMITTER_EMAIL"] = "test@chdevflow.local"

    def tearDown(self) -> None:
        if self._orig_git_author_name is not None:
            os.environ["GIT_AUTHOR_NAME"] = self._orig_git_author_name
        else:
            os.environ.pop("GIT_AUTHOR_NAME", None)
        if self._orig_git_author_email is not None:
            os.environ["GIT_AUTHOR_EMAIL"] = self._orig_git_author_email
        else:
            os.environ.pop("GIT_AUTHOR_EMAIL", None)
        if self._orig_git_committer_name is not None:
            os.environ["GIT_COMMITTER_NAME"] = self._orig_git_committer_name
        else:
            os.environ.pop("GIT_COMMITTER_NAME", None)
        if self._orig_git_committer_email is not None:
            os.environ["GIT_COMMITTER_EMAIL"] = self._orig_git_committer_email
        else:
            os.environ.pop("GIT_COMMITTER_EMAIL", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_slugify(self) -> None:
        self.assertEqual(slugify("Minha Primeira Fatia"), "minha-primeira-fatia")
        self.assertEqual(slugify("W-01: Setup & Config!"), "w-01-setup-config")

    def test_generate_mission_markdown_structure(self) -> None:
        md = generate_mission_markdown("Nova Feature", "MeuApp", executor="AGY", autonomy="CH-2")
        self.assertIn("# Fatia W — Nova Feature", md)
        self.assertIn("## C — Contextualizar", md)
        self.assertIn("## H — Harmonizar", md)
        self.assertIn("## A — Agir", md)
        self.assertIn("## V — Verificar", md)
        self.assertIn("## E — Evoluir", md)
        self.assertIn("AGUARDANDO_PO", md)
        self.assertIn("PENDENTE DE AUTORIZAÇÃO HUMANA FORMAL", md)

    def test_create_mission_local(self) -> None:
        target = Path(self.test_dir) / "LocalApp"
        target.mkdir()

        mission_file, msg = create_mission("Refatorar Banco", project_path=target)
        self.assertIsNotNone(mission_file)
        self.assertTrue(mission_file.exists())
        self.assertIn("MISSAO-REFATORAR-BANCO.md", mission_file.name)

    def test_generate_ruc_without_and_with_evidence(self) -> None:
        target = Path(self.test_dir) / "RucApp"
        target.mkdir()

        # 1. Sem evidência prévia
        dest1, content1 = generate_ruc(target)
        self.assertTrue(dest1.exists())
        self.assertIn("RUC/1.0", content1)
        self.assertIn("NÃO_VERIFICADO", content1)
        self.assertNotIn("AGUARDANDO_PO", content1)

        # 2. Com evidência de verify gerada
        run_init(target, apply=True)
        generate_tree(target)
        manifest = create_manifest_data("RucApp")
        manifest["verification"]["commands"] = ["echo 'teste aprovado'"]
        save_manifest(target / "chdevflow.yaml", manifest)
        run_verification(target, persist=True)

        dest2, content2 = generate_ruc(target)
        self.assertIn("APROVADO_TECNICAMENTE", content2)
        self.assertIn("echo 'teste aprovado'", content2)
        self.assertIn("PASS", content2)

    def test_submit_fails_on_branch_main(self) -> None:
        target = Path(self.test_dir) / "RepoMain"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "main"], check=True, capture_output=True)

        with self.assertRaises(SubmitSecurityError):
            validate_and_submit(target)

    def test_submit_fails_when_no_changes(self) -> None:
        target = Path(self.test_dir) / "RepoClean"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "feature/nova"], check=True, capture_output=True)

        with self.assertRaises(SubmitError) as cm:
            validate_and_submit(target)
        self.assertIn("Nenhuma alteração detectada", str(cm.exception))

    def test_submit_fails_when_verification_fails(self) -> None:
        target = Path(self.test_dir) / "RepoFailVerify"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "feature/err"], check=True, capture_output=True)
        manifest = create_manifest_data("RepoFailVerify")
        manifest["verification"]["commands"] = ["exit 1"]
        save_manifest(target / "chdevflow.yaml", manifest)

        with self.assertRaises(SubmitError) as cm:
            validate_and_submit(target)
        self.assertIn("Checks de verificação retornaram", str(cm.exception))

    def test_submit_success_local_mode(self) -> None:
        target = Path(self.test_dir) / "RepoGood"
        target.mkdir()
        run_init(target, apply=True)
        generate_tree(target)
        subprocess.run(["git", "-C", str(target), "init", "-b", "feature/sucesso"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.name", "Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.email", "tester@example.com"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "commit", "-m", "init"], check=True, capture_output=True)
        manifest = create_manifest_data("RepoGood")
        manifest["verification"]["commands"] = ["echo 'tudo ok'"]
        save_manifest(target / "chdevflow.yaml", manifest)

        # Modificação local para satisfazer dirty/changes
        (target / "README.md").write_text("# Repo Good", encoding="utf-8")

        res = validate_and_submit(target, remote=False)
        self.assertEqual(res["branch"], "feature/sucesso")
        self.assertEqual(res["verification"], "PASS")
        self.assertEqual(res["state"], "AGUARDANDO_PO")
        self.assertFalse(res["remote_executed"])
        self.assertTrue(Path(res["ruc_file"]).exists())

    def test_cli_mission_ruc_submit_commands(self) -> None:
        target = Path(self.test_dir) / "CliCycle"
        target.mkdir()
        run_init(target, apply=True)
        generate_tree(target)
        subprocess.run(["git", "-C", str(target), "init", "-b", "agy/teste-fatia"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.name", "Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.email", "tester@example.com"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "commit", "-m", "init"], check=True, capture_output=True)
        manifest = create_manifest_data("CliCycle")
        manifest["verification"]["commands"] = ["echo 'ok'"]
        save_manifest(target / "chdevflow.yaml", manifest)
        (target / "main.py").write_text("print(1)", encoding="utf-8")

        # ch mission new
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code_m = cli_main(["mission", "new", "Criar API", "--path", str(target)])
        self.assertEqual(code_m, 0)
        self.assertIn("Fatia W gerada localmente", buf.getvalue())

        # ch ruc
        buf_ruc = io.StringIO()
        with patch("sys.stdout", buf_ruc):
            code_r = cli_main(["ruc", "--path", str(target)])
        self.assertEqual(code_r, 0)
        self.assertIn("Relatório Universal C.H.", buf_ruc.getvalue())

        # ch submit
        buf_sub = io.StringIO()
        with patch("sys.stdout", buf_sub):
            code_s = cli_main(["submit", "--path", str(target)])
        self.assertEqual(code_s, 0)
        self.assertIn("AGUARDANDO_PO", buf_sub.getvalue())


if __name__ == "__main__":
    unittest.main()
