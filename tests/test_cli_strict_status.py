"""Testes da fatia AUD-GERAL-P0-01 — ch status estrito e eliminação de falso PASS."""
from __future__ import annotations

import io
import json
import os
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

    # Regressões AUD-P0-01.1: ch verify com comandos customizados e gate obrigatório
    def test_verify_manifest_with_custom_true_fails_when_doc_missing(self) -> None:
        """Regressão AUD-P0-01.1 (1): Manifesto com commands: ['true'] e documento ausente retorna FAIL."""
        base = Path(self.test_dir)
        proj = create_project("CustomTrueApp", base_dir=base)
        manifest = load_manifest(proj / "chdevflow.yaml")
        manifest["verification"]["commands"] = ["true"]
        save_manifest(proj / "chdevflow.yaml", manifest)

        # Remove documento fundamental
        (proj / "docs" / "STATUS.md").unlink()

        ev = run_verification(proj, persist=False)
        self.assertEqual(ev.overall_state, "FAIL")
        self.assertGreaterEqual(len(ev.commands), 1)
        self.assertEqual(ev.commands[0].command, "ch status --strict")
        self.assertEqual(ev.commands[0].state, "FAIL")
        # Segundo comando ("true") deve ser SKIPPED devido ao fail-fast
        self.assertEqual(ev.commands[1].command, "true")
        self.assertEqual(ev.commands[1].state, "SKIPPED")

        # Via CLI verify
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cli_main(["verify", "--path", str(proj)])
        self.assertEqual(code, 1)

    def test_verify_manifest_with_simulated_real_command_fails_when_doc_missing(self) -> None:
        """Regressão AUD-P0-01.1 (2): Manifesto com comando real simulado retornando 0 e documento ausente falha."""
        base = Path(self.test_dir)
        proj = create_project("RealCmdApp", base_dir=base)
        manifest = load_manifest(proj / "chdevflow.yaml")
        manifest["verification"]["commands"] = ["python3 -c 'import sys; sys.exit(0)'"]
        save_manifest(proj / "chdevflow.yaml", manifest)

        # Remove AGENTS.md
        (proj / "AGENTS.md").unlink()

        ev = run_verification(proj, persist=False)
        self.assertEqual(ev.overall_state, "FAIL")
        self.assertEqual(ev.commands[0].command, "ch status --strict")
        self.assertEqual(ev.commands[0].state, "FAIL")
        self.assertEqual(ev.commands[1].state, "SKIPPED")

    def test_verify_manifest_structurally_sound_with_custom_commands_passes(self) -> None:
        """Regressão AUD-P0-01.1 (3): Projeto estruturalmente íntegro com comando próprio retorna PASS."""
        base = Path(self.test_dir)
        proj = create_project("SoundCustomApp", base_dir=base)
        manifest = load_manifest(proj / "chdevflow.yaml")
        manifest["verification"]["commands"] = ["echo 'custom build ok'", "echo 'custom test ok'"]
        save_manifest(proj / "chdevflow.yaml", manifest)

        ev = run_verification(proj, persist=False)
        self.assertEqual(ev.overall_state, "PASS")
        self.assertEqual(len(ev.commands), 3)
        self.assertEqual(ev.commands[0].command, "ch status --strict")
        self.assertEqual(ev.commands[0].state, "PASS")
        self.assertEqual(ev.commands[1].state, "PASS")
        self.assertEqual(ev.commands[2].state, "PASS")

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cli_main(["verify", "--path", str(proj)])
        self.assertEqual(code, 0)
        self.assertIn("PASS", buf.getvalue())

    def test_verify_gate_appears_only_once_when_already_in_manifest(self) -> None:
        """Regressão AUD-P0-01.1 (4): Gate 'ch status --strict' aparece uma única vez se já estiver no manifesto."""
        base = Path(self.test_dir)
        proj = create_project("DedupGateApp", base_dir=base)
        manifest = load_manifest(proj / "chdevflow.yaml")
        # Inclui ch status --strict explicitamente no manifesto
        manifest["verification"]["commands"] = ["ch status --strict", "echo 'teste ok'"]
        save_manifest(proj / "chdevflow.yaml", manifest)

        ev = run_verification(proj, persist=False)
        self.assertEqual(ev.overall_state, "PASS")
        # Não deve haver duplicata de ch status --strict
        strict_cmds = [c for c in ev.commands if c.command == "ch status --strict"]
        self.assertEqual(len(strict_cmds), 1)
        self.assertEqual(len(ev.commands), 2)
        self.assertEqual(ev.commands[0].command, "ch status --strict")
        self.assertEqual(ev.commands[1].command, "echo 'teste ok'")

    def test_verify_fail_fast_skips_subsequent_commands_on_structural_failure(self) -> None:
        """Regressão AUD-P0-01.1 (5): Comprova SKIPPED de comandos posteriores no modo fail-fast quando gate falha."""
        base = Path(self.test_dir)
        proj = create_project("SkipTestApp", base_dir=base)
        manifest = load_manifest(proj / "chdevflow.yaml")
        manifest["verification"]["commands"] = ["echo 'cmd1'", "echo 'cmd2'", "echo 'cmd3'"]
        save_manifest(proj / "chdevflow.yaml", manifest)

        (proj / "docs" / "PROJETO.md").unlink()

        ev = run_verification(proj, fail_fast=True, persist=False)
        self.assertEqual(ev.overall_state, "FAIL")
        self.assertEqual(len(ev.commands), 4)
        self.assertEqual(ev.commands[0].command, "ch status --strict")
        self.assertEqual(ev.commands[0].state, "FAIL")
        self.assertEqual(ev.commands[1].state, "SKIPPED")
        self.assertEqual(ev.commands[2].state, "SKIPPED")
        self.assertEqual(ev.commands[3].state, "SKIPPED")

    # Regressões AUD-P0-01.2: Diretório, symlink quebrado e validação de is_file em ESSENTIAL_DOCS
    def test_directory_in_place_of_document_fails_strict(self) -> None:
        """Regressão AUD-P0-01.2 (1): Diretório com nome de documento é classificado como inválido/ausente e falha no estrito."""
        base = Path(self.test_dir)
        proj = create_project("DirDocApp", base_dir=base)
        status_file = proj / "docs" / "STATUS.md"
        status_file.unlink()
        status_file.mkdir()  # Cria um diretório no lugar do arquivo

        # API Python
        st = get_project_status(proj, strict=True)
        self.assertFalse(st["structural_health"])
        self.assertIn("docs/STATUS.md", st["missing_docs"])
        self.assertEqual(st["docs"]["docs/STATUS.md"], "INVALIDO (diretório)")
        self.assertEqual(st["expected_exit_code"], 1)

        # CLI status informativa (código 0)
        buf_info = io.StringIO()
        with patch("sys.stdout", buf_info):
            code_info = cli_main(["status", "--path", str(proj)])
        self.assertEqual(code_info, 0)
        self.assertIn("INVALIDO (diretório)", buf_info.getvalue())

        # CLI status estrita (código 1)
        code_strict = cli_main(["status", "--path", str(proj), "--strict"])
        self.assertEqual(code_strict, 1)

        # ch verify falha
        ev = run_verification(proj, persist=False)
        self.assertEqual(ev.overall_state, "FAIL")

    def test_broken_symlink_in_place_of_document_fails_strict(self) -> None:
        """Regressão AUD-P0-01.2 (2): Symlink quebrado no lugar de documento fundamental falha no modo estrito."""
        base = Path(self.test_dir)
        proj = create_project("SymlinkDocApp", base_dir=base)
        doc_file = proj / "docs" / "CH" / "DECISOES.md"
        doc_file.unlink()
        try:
            doc_file.symlink_to(proj / "nonexistent_target.md")
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks não suportados no ambiente de teste.")

        st = get_project_status(proj, strict=True)
        self.assertFalse(st["structural_health"])
        self.assertIn("docs/CH/DECISOES.md", st["missing_docs"])
        self.assertEqual(st["docs"]["docs/CH/DECISOES.md"], "INVALIDO (symlink quebrado)")
        self.assertEqual(st["expected_exit_code"], 1)

        code_strict = cli_main(["status", "--path", str(proj), "--strict"])
        self.assertEqual(code_strict, 1)

        ev = run_verification(proj, persist=False)
        self.assertEqual(ev.overall_state, "FAIL")

    def test_valid_regular_file_and_nonexistent_document_classification(self) -> None:
        """Regressão AUD-P0-01.2 (3): Valida classificação correta de arquivo regular (PRESENTE) e inexistente (AUSENTE)."""
        base = Path(self.test_dir)
        proj = create_project("RegFileApp", base_dir=base)

        # Arquivo regular existente
        st = get_project_status(proj, strict=False)
        self.assertEqual(st["docs"]["AGENTS.md"], "PRESENTE")

        # Documento inexistente
        (proj / "AGENTS.md").unlink()
        st_missing = get_project_status(proj, strict=False)
        self.assertEqual(st_missing["docs"]["AGENTS.md"], "AUSENTE")
        self.assertIn("AGENTS.md", st_missing["missing_docs"])


if __name__ == "__main__":
    unittest.main()
