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
from chdevflow.core.mission import MissionError, create_mission, generate_mission_markdown, slugify
from chdevflow.core.intake import validate_issue
from chdevflow.core.ruc import generate_ruc, generate_ruc_text
from chdevflow.core.submit import SubmitError, SubmitSecurityError, validate_and_submit


_ORIG_SUBPROCESS_RUN = subprocess.run


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
        self.assertIn("**Verificações e evidências exigidas**", md)
        self.assertIn("## E — Evoluir", md)
        self.assertIn("AGUARDANDO_PO", md)
        self.assertIn("PENDENTE DE AUTORIZAÇÃO HUMANA FORMAL", md)

    def _init_git_repo(self, path: Path) -> None:
        subprocess.run(["git", "-C", str(path), "init", "-b", "main"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(path), "config", "user.name", "Tester"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(path), "config", "user.email", "tester@example.com"], check=True, capture_output=True)
        # F1 exige baseline SHA real para a criacao remota.
        subprocess.run(["git", "-C", str(path), "commit", "--allow-empty", "-m", "initial"], check=True, capture_output=True)

    def test_create_mission_local(self) -> None:
        target = Path(self.test_dir) / "LocalApp"
        target.mkdir()

        mission_file, msg = create_mission("Refatorar Banco", project_path=target)
        self.assertIsNotNone(mission_file)
        self.assertTrue(mission_file.exists())
        self.assertIn("MISSAO-REFATORAR-BANCO.md", mission_file.name)
        self.assertIn("Fatia W gerada localmente em:", msg)
        self.assertNotIn("Issue remota criada", msg)

    def test_create_mission_local_cli(self) -> None:
        target = Path(self.test_dir) / "LocalAppCli"
        target.mkdir()

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cli_main(["mission", "new", "Nova Tarefa Local", "--path", str(target)])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("Fatia W gerada localmente em:", out)
        self.assertNotIn("Issue remota criada", out)
        expected_file = target / "prompts" / "MISSAO-NOVA-TAREFA-LOCAL.md"
        self.assertTrue(expected_file.exists())

    def test_create_mission_remote_success_mocked(self) -> None:
        target = Path(self.test_dir) / "RemoteAppSuccess"
        target.mkdir()
        self._init_git_repo(target)

        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == "gh":
                if cmd[1:3] == ["auth", "status"]:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Logged in to github.com\n", stderr="")
                if cmd[1:3] == ["issue", "create"]:
                    return subprocess.CompletedProcess(
                        args=cmd,
                        returncode=0,
                        stdout="https://github.com/hallanbrito/CHDevFlow/issues/99\n",
                        stderr="",
                    )
            return _ORIG_SUBPROCESS_RUN(cmd, *args, **kwargs)

        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run):
            mission_file, msg = create_mission("Tarefa Remota OK", project_path=target, remote=True)
            self.assertIsNotNone(mission_file)
            self.assertTrue(mission_file.exists())
            self.assertIn("MISSAO-TAREFA-REMOTA-OK.md", mission_file.name)
            self.assertIn("Issue remota criada: https://github.com/hallanbrito/CHDevFlow/issues/99", msg)

        # Também testa execução via CLI com retorno 0
        buf_out = io.StringIO()
        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run), patch("sys.stdout", buf_out):
            code = cli_main(["mission", "new", "Tarefa Remota OK CLI", "--path", str(target), "--remote"])
        self.assertEqual(code, 0)
        self.assertIn("Issue remota criada: https://github.com/hallanbrito/CHDevFlow/issues/99", buf_out.getvalue())

    def test_remote_emits_intake_compliant_labels_and_metadata(self) -> None:
        target = Path(self.test_dir) / "RemoteIntake"
        target.mkdir()
        self._init_git_repo(target)
        issued = []

        def fake_gh(cmd, *args, **kwargs):
            if cmd[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[:3] == ["gh", "issue", "create"]:
                issued.append(cmd)
                return subprocess.CompletedProcess(cmd, 0, "https://github.com/hallanbrito/CHDevFlow/issues/98\n", "")
            return _ORIG_SUBPROCESS_RUN(cmd, *args, **kwargs)

        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_gh):
            _, output = create_mission("Revisar teste", project_path=target,
                                       executor="Codex", autonomy="CH-1", remote=True)
        self.assertIn("issues/98", output)
        self.assertEqual(len(issued), 1)
        cmd = issued[0]
        labels = [cmd[i + 1] for i, v in enumerate(cmd[:-1]) if v == "--label"]
        self.assertEqual(labels, ["ch:workflow", "ch:codex"])
        content = cmd[cmd.index("--body") + 1]
        result = validate_issue({"number": 98, "title": "W: Revisar teste",
                                 "body": content, "labels": labels})
        self.assertEqual(result["content_status"], "CONTENT_VALID", result)
        self.assertFalse(result["project_fields_verified"])
        self.assertFalse(result["po_authorized"])
        self.assertFalse(result["execution_allowed"])

    def test_remote_rejects_invalid_executor_without_gh(self) -> None:
        target = Path(self.test_dir) / "RemoteInvalid"
        target.mkdir()
        self._init_git_repo(target)
        with patch("chdevflow.core.mission.check_git_status", return_value={
            "is_git": True, "branch": "main", "commit_sha": "a" * 40
        }), patch("chdevflow.core.mission.subprocess.run") as mocked:
            with self.assertRaisesRegex(MissionError, "Executor remoto invalido"):
                create_mission("Nao criar", project_path=target, executor="Outro",
                               autonomy="CH-1", remote=True)
            mocked.assert_not_called()

    def test_remote_requires_committed_baseline(self) -> None:
        target = Path(self.test_dir) / "RemoteUnborn"
        target.mkdir()
        subprocess.run(["git", "-C", str(target), "init", "-b", "main"],
                       check=True, capture_output=True)
        with self.assertRaisesRegex(MissionError, "BASELINE_SHA_MISSING"):
            create_mission("Sem baseline", project_path=target, executor="AGY",
                           autonomy="CH-1", remote=True)

    def test_issue_form_is_triage_only(self) -> None:
        template = (Path(__file__).resolve().parents[1] /
                    ".github" / "ISSUE_TEMPLATE" / "fatia-w.yml").read_text(encoding="utf-8")
        self.assertIn('labels: ["ch:workflow"]', template)
        self.assertNotIn("\nprojects:", template)

    def test_create_mission_remote_auth_failure(self) -> None:
        target = Path(self.test_dir) / "RemoteAppAuthFail"
        target.mkdir()
        self._init_git_repo(target)

        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == "gh":
                if cmd[1:3] == ["auth", "status"]:
                    return subprocess.CompletedProcess(
                        args=cmd,
                        returncode=1,
                        stdout="",
                        stderr="You are not logged into any GitHub hosts. Run gh auth login to authenticate.",
                    )
            return _ORIG_SUBPROCESS_RUN(cmd, *args, **kwargs)

        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run):
            with self.assertRaises(MissionError) as cm:
                create_mission("Tarefa Auth Fail", project_path=target, remote=True)
            err_msg = str(cm.exception)
            self.assertIn("GitHub CLI (gh) não está autenticado", err_msg)
            self.assertIn("Execute 'gh auth login' primeiro", err_msg)
            self.assertIn("O artefato local foi criado em:", err_msg)

        # O artefato local DEVE ter sido preservado
        local_file = target / "prompts" / "MISSAO-TAREFA-AUTH-FAIL.md"
        self.assertTrue(local_file.exists(), "Artefato local deve existir mesmo após falha de autenticação")

        # Via CLI: deve retornar exit code 1 e mensagem de erro em stderr (nunca falso PASS)
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run), \
             patch("sys.stdout", buf_out), \
             patch("sys.stderr", buf_err):
            code = cli_main(["mission", "new", "Tarefa Auth Fail CLI", "--path", str(target), "--remote"])
        self.assertEqual(code, 1)
        self.assertIn("Erro em 'ch mission': GitHub CLI (gh) não está autenticado", buf_err.getvalue())
        self.assertNotIn("Issue remota criada", buf_out.getvalue())

    def test_create_mission_remote_issue_create_failure(self) -> None:
        target = Path(self.test_dir) / "RemoteAppCreateFail"
        target.mkdir()
        self._init_git_repo(target)

        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == "gh":
                if cmd[1:3] == ["auth", "status"]:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                if cmd[1:3] == ["issue", "create"]:
                    return subprocess.CompletedProcess(
                        args=cmd,
                        returncode=1,
                        stdout="",
                        stderr="GraphQL: Resource not accessible by integration (HTTP 403)",
                    )
            return _ORIG_SUBPROCESS_RUN(cmd, *args, **kwargs)

        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run):
            with self.assertRaises(MissionError) as cm:
                create_mission("Tarefa Create Fail", project_path=target, remote=True)
            err_msg = str(cm.exception)
            self.assertIn("Falha ao criar Issue remota no GitHub", err_msg)
            self.assertIn("GraphQL: Resource not accessible by integration (HTTP 403)", err_msg)
            self.assertIn("O artefato local foi criado em:", err_msg)

        # O artefato local DEVE ter sido preservado
        local_file = target / "prompts" / "MISSAO-TAREFA-CREATE-FAIL.md"
        self.assertTrue(local_file.exists(), "Artefato local deve existir mesmo após falha na criação remota")

        # Via CLI: deve retornar exit code 1 e mensagem em stderr (elimina falso PASS)
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run), \
             patch("sys.stdout", buf_out), \
             patch("sys.stderr", buf_err):
            code = cli_main(["mission", "new", "Tarefa Create Fail CLI", "--path", str(target), "--remote"])
        self.assertEqual(code, 1, "CLI deve falhar com exit code 1 quando gh issue create falhar")
        self.assertIn("Erro em 'ch mission': Falha ao criar Issue remota no GitHub", buf_err.getvalue())
        self.assertNotIn("Issue remota criada", buf_out.getvalue())

    def test_create_mission_remote_issue_create_sanitizes_secret(self) -> None:
        target = Path(self.test_dir) / "RemoteAppSanitize"
        target.mkdir()
        self._init_git_repo(target)

        leaked_token = "ghp_supersecretleak123456789012345678901234567"
        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == "gh":
                if cmd[1:3] == ["auth", "status"]:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                if cmd[1:3] == ["issue", "create"]:
                    return subprocess.CompletedProcess(
                        args=cmd,
                        returncode=1,
                        stdout="",
                        stderr=f"HTTP 401: Bad credentials (token: {leaked_token})",
                    )
            return _ORIG_SUBPROCESS_RUN(cmd, *args, **kwargs)

        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run):
            with self.assertRaises(MissionError) as cm:
                create_mission("Tarefa Leak", project_path=target, remote=True)
            err_msg = str(cm.exception)
            self.assertNotIn(leaked_token, err_msg)
            self.assertIn("[REDACTED_TOKEN]", err_msg)

        # Via CLI: valida que stderr nunca exibe o token vazado
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run), \
             patch("sys.stdout", buf_out), \
             patch("sys.stderr", buf_err):
            code = cli_main(["mission", "new", "Tarefa Leak CLI", "--path", str(target), "--remote"])
        self.assertEqual(code, 1)
        self.assertNotIn(leaked_token, buf_err.getvalue())
        self.assertIn("[REDACTED_TOKEN]", buf_err.getvalue())

    def test_create_mission_remote_not_git_repository(self) -> None:
        target = Path(self.test_dir) / "RemoteAppNoGit"
        target.mkdir()

        with self.assertRaises(MissionError) as cm:
            create_mission("Tarefa Sem Git", project_path=target, remote=True)
        err_msg = str(cm.exception)
        self.assertIn("Não é possível criar Issue remota fora de um repositório Git", err_msg)
        self.assertIn("O artefato local foi criado em:", err_msg)

        local_file = target / "prompts" / "MISSAO-TAREFA-SEM-GIT.md"
        self.assertTrue(local_file.exists())

        # Via CLI
        buf_err = io.StringIO()
        with patch("sys.stderr", buf_err):
            code = cli_main(["mission", "new", "Tarefa Sem Git CLI", "--path", str(target), "--remote"])
        self.assertEqual(code, 1)
        self.assertIn("Não é possível criar Issue remota fora de um repositório Git", buf_err.getvalue())

    def test_create_mission_remote_gh_not_found(self) -> None:
        target = Path(self.test_dir) / "RemoteAppGhNotFound"
        target.mkdir()
        self._init_git_repo(target)

        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == "gh":
                raise FileNotFoundError("gh not found")
            return _ORIG_SUBPROCESS_RUN(cmd, *args, **kwargs)

        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run):
            with self.assertRaises(MissionError) as cm:
                create_mission("Tarefa Gh Not Found", project_path=target, remote=True)
            err_msg = str(cm.exception)
            self.assertIn("GitHub CLI (gh) não foi encontrado no PATH", err_msg)
            self.assertIn("O artefato local foi criado em:", err_msg)

        buf_err = io.StringIO()
        with patch("chdevflow.core.mission.subprocess.run", side_effect=fake_subprocess_run), \
             patch("sys.stderr", buf_err):
            code = cli_main(["mission", "new", "Tarefa Gh Not Found CLI", "--path", str(target), "--remote"])
        self.assertEqual(code, 1)
        self.assertIn("GitHub CLI (gh) não foi encontrado no PATH", buf_err.getvalue())

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
        run_verification(target, persist=True, trust=True)

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
        run_verification(target, trust=True)

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
        run_verification(target, trust=True)

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
