"""Testes da fatia AUD-GERAL-P0-01 — ch status estrito e eliminação de falso PASS."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from chdevflow.cli import main as cli_main
from chdevflow.core.config import create_manifest_data, load_manifest, save_manifest
from chdevflow.core.evidence import run_verification
from chdevflow.core.project import create_project
from chdevflow.core.status import ESSENTIAL_DOCS, get_project_status, render_status_human


class TestCliStrictStatus(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="ch_test_strict_")
        self._orig_git_author_name = os.environ.get("GIT_AUTHOR_NAME")
        self._orig_git_author_email = os.environ.get("GIT_AUTHOR_EMAIL")
        self._orig_git_committer_name = os.environ.get("GIT_COMMITTER_NAME")
        self._orig_git_committer_email = os.environ.get("GIT_COMMITTER_EMAIL")
        os.environ["GIT_AUTHOR_NAME"] = "CHDevFlow Strict Test"
        os.environ["GIT_AUTHOR_EMAIL"] = "test-strict@chdevflow.local"
        os.environ["GIT_COMMITTER_NAME"] = "CHDevFlow Strict Test"
        os.environ["GIT_COMMITTER_EMAIL"] = "test-strict@chdevflow.local"

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

    def test_complete_project_strict_returns_zero(self) -> None:
        """Comprova que projeto completo com manifesto e 100% dos documentos retorna 0 no modo estrito."""
        base = Path(self.test_dir)
        proj = create_project("CompleteApp", base_dir=base)

        # 1. API Python
        status_info = get_project_status(proj, strict=False)
        self.assertTrue(status_info["structural_health"])
        self.assertEqual(status_info["missing_docs"], [])
        self.assertEqual(status_info["structural_pendencies"], [])
        self.assertEqual(status_info["expected_exit_code"], 0)
        self.assertEqual(status_info["strict_exit_code"], 0)

        status_strict = get_project_status(proj, strict=True)
        self.assertTrue(status_strict["structural_health"])
        self.assertEqual(status_strict["expected_exit_code"], 0)
        self.assertEqual(status_strict["strict_exit_code"], 0)

        # 2. CLI informativa
        buf_info = io.StringIO()
        with patch("sys.stdout", buf_info):
            code_info = cli_main(["status", "--path", str(proj)])
        self.assertEqual(code_info, 0)
        self.assertIn("CONFORME (100% da fundação presente)", buf_info.getvalue())
        self.assertIn("INFORMATIVO", buf_info.getvalue())

        # 3. CLI estrita (--strict e -s)
        buf_strict = io.StringIO()
        with patch("sys.stdout", buf_strict):
            code_strict = cli_main(["status", "--path", str(proj), "--strict"])
        self.assertEqual(code_strict, 0)
        self.assertIn("ESTRITO", buf_strict.getvalue())
        self.assertIn("Código de saída  : 0", buf_strict.getvalue())

        code_s = cli_main(["status", "--path", str(proj), "-s"])
        self.assertEqual(code_s, 0)

        # 4. JSON estruturado
        buf_json = io.StringIO()
        with patch("sys.stdout", buf_json):
            code_json = cli_main(["status", "--path", str(proj), "--strict", "--json"])
        self.assertEqual(code_json, 0)
        parsed = json.loads(buf_json.getvalue())
        self.assertTrue(parsed["structural_health"])
        self.assertTrue(parsed["strict"])
        self.assertEqual(parsed["expected_exit_code"], 0)
        self.assertEqual(parsed["missing_docs"], [])
        self.assertEqual(parsed["structural_pendencies"], [])

        # 5. ch verify gera PASS real
        buf_ver = io.StringIO()
        with patch("sys.stdout", buf_ver):
            code_ver = cli_main(["verify", "--path", str(proj)])
        self.assertEqual(code_ver, 0)
        self.assertIn("PASS", buf_ver.getvalue())

    def test_individual_removal_of_each_essential_doc_fails_strict(self) -> None:
        """Remove individualmente cada documento obrigatório e comprova que modo estrito falha com código 1."""
        base = Path(self.test_dir)
        proj = create_project("FoundationApp", base_dir=base)

        for doc_rel in ESSENTIAL_DOCS:
            with self.subTest(removed_doc=doc_rel):
                doc_file = proj / doc_rel
                self.assertTrue(doc_file.is_file(), f"Documento base deveria existir: {doc_rel}")

                # Backup e remoção do documento
                content_backup = doc_file.read_bytes()
                doc_file.unlink()

                try:
                    # 1. API Python
                    st = get_project_status(proj, strict=True)
                    self.assertFalse(st["structural_health"])
                    self.assertIn(doc_rel, st["missing_docs"])
                    self.assertTrue(any(doc_rel in p for p in st["structural_pendencies"]))
                    self.assertEqual(st["expected_exit_code"], 1)
                    self.assertEqual(st["strict_exit_code"], 1)

                    # 2. Modo informativo preservado (código 0)
                    buf_info = io.StringIO()
                    with patch("sys.stdout", buf_info):
                        code_info = cli_main(["status", "--path", str(proj)])
                    self.assertEqual(code_info, 0)
                    self.assertIn("PENDENTE (fundação obrigatória incompleta)", buf_info.getvalue())
                    self.assertIn(f"✗ {doc_rel}", buf_info.getvalue())

                    # 3. Modo estrito retorna código 1
                    buf_strict = io.StringIO()
                    with patch("sys.stdout", buf_strict):
                        code_strict = cli_main(["status", "--path", str(proj), "--strict"])
                    self.assertEqual(code_strict, 1)
                    self.assertIn("Código de saída  : 1", buf_strict.getvalue())

                    # 4. JSON estrito indica saúde estrutural false e expected_exit_code 1
                    buf_json = io.StringIO()
                    with patch("sys.stdout", buf_json):
                        code_json = cli_main(["status", "--path", str(proj), "--strict", "--json"])
                    self.assertEqual(code_json, 1)
                    parsed = json.loads(buf_json.getvalue())
                    self.assertFalse(parsed["structural_health"])
                    self.assertEqual(parsed["expected_exit_code"], 1)
                    self.assertIn(doc_rel, parsed["missing_docs"])

                    # 5. ch verify NUNCA registra PASS quando fundação está incompleta
                    buf_ver = io.StringIO()
                    with patch("sys.stdout", buf_ver):
                        code_ver = cli_main(["verify", "--path", str(proj)])
                    self.assertEqual(code_ver, 1)
                    self.assertIn("FAIL", buf_ver.getvalue())
                    self.assertNotIn("overall_state: PASS", buf_ver.getvalue())

                    # Validação direta via run_verification
                    ev = run_verification(proj, persist=False)
                    self.assertEqual(ev.overall_state, "FAIL")

                finally:
                    # Restaura documento para a próxima iteração
                    doc_file.parent.mkdir(parents=True, exist_ok=True)
                    doc_file.write_bytes(content_backup)

    def test_missing_manifest_fails_strict(self) -> None:
        """Comprova que ausência do manifesto chdevflow.yaml causa falha estrita com código 1."""
        base = Path(self.test_dir)
        proj = create_project("NoManifestApp", base_dir=base)
        manifest_path = proj / "chdevflow.yaml"
        manifest_path.unlink()

        # 1. Modo informativo preservado (código 0)
        code_info = cli_main(["status", "--path", str(proj)])
        self.assertEqual(code_info, 0)

        # 2. Modo estrito retorna 1
        code_strict = cli_main(["status", "--path", str(proj), "--strict"])
        self.assertEqual(code_strict, 1)

        # 3. JSON estrito
        buf_json = io.StringIO()
        with patch("sys.stdout", buf_json):
            code_json = cli_main(["status", "--path", str(proj), "--strict", "--json"])
        self.assertEqual(code_json, 1)
        parsed = json.loads(buf_json.getvalue())
        self.assertFalse(parsed["structural_health"])
        self.assertEqual(parsed["manifest"]["status"], "AUSENTE")
        self.assertEqual(parsed["expected_exit_code"], 1)

    def test_invalid_manifest_fails_strict(self) -> None:
        """Comprova que manifesto chdevflow.yaml inválido/corrompido causa falha estrita com código 1."""
        base = Path(self.test_dir)
        proj = create_project("InvalidManifestApp", base_dir=base)
        manifest_path = proj / "chdevflow.yaml"
        # Escreve manifesto com erro de schema (sem governance)
        manifest_path.write_text("version: '1'\nproject:\n  name: Teste\n", encoding="utf-8")

        # 1. Modo informativo preservado (código 0)
        code_info = cli_main(["status", "--path", str(proj)])
        self.assertEqual(code_info, 0)

        # 2. Modo estrito retorna 1
        code_strict = cli_main(["status", "--path", str(proj), "--strict"])
        self.assertEqual(code_strict, 1)

        # 3. JSON estrito
        buf_json = io.StringIO()
        with patch("sys.stdout", buf_json):
            code_json = cli_main(["status", "--path", str(proj), "--strict", "--json"])
        self.assertEqual(code_json, 1)
        parsed = json.loads(buf_json.getvalue())
        self.assertFalse(parsed["structural_health"])
        self.assertTrue(parsed["manifest"]["status"].startswith("INVALIDO"))
        self.assertEqual(parsed["expected_exit_code"], 1)

    def test_new_project_without_real_build_configures_strict_status(self) -> None:
        """Comprova que projetos criados por ch new sem build real configuram 'ch status --strict'."""
        base = Path(self.test_dir)
        code_new = cli_main(["new", "CleanWeb", "--path", str(base), "--frontend", "react"])
        self.assertEqual(code_new, 0)

        proj_dir = base / "CleanWeb"
        manifest = load_manifest(proj_dir / "chdevflow.yaml")
        cmds = manifest["verification"]["commands"]
        self.assertIn("ch status --strict", cmds)
        self.assertNotIn("ch status", cmds)  # não deve ser o status frouxo antigo

        # Verificação do projeto recém-criado deve passar (100% dos docs presentes)
        ev = run_verification(proj_dir, persist=False)
        self.assertEqual(ev.overall_state, "PASS")

        # Ao deletar um documento, ch verify deve imediatamente falhar com FAIL
        (proj_dir / "docs" / "STATUS.md").unlink()
        ev_after = run_verification(proj_dir, persist=False)
        self.assertEqual(ev_after.overall_state, "FAIL")


if __name__ == "__main__":
    unittest.main()
