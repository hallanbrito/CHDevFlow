"""F5: teste offline do comando experimental; nunca inicia AGY/Codex reais."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT / "src", ROOT / "apps/bootstrap/sentinela/src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chdevflow.cli import main as cli_main
from chdevflow.core.experimental_pilot import (
    ProcessResult, _agent_environment, _files, run_local_pilot, diagnose_existing_lab,
)

SOURCE = '''def movimentar(saldo, tipo, quantidade):
    if type(saldo) is not int or type(quantidade) is not int or saldo < 0 or quantidade < 0:
        raise ValueError("inválido")
    if tipo == "entrada": return saldo + quantidade
    if tipo == "saida":
        if quantidade > saldo: raise ValueError("insuficiente")
        return saldo - quantidade
    raise ValueError("tipo inválido")

def pode_separar(saldo, quantidade):
    if type(saldo) is not int or type(quantidade) is not int or saldo < 0 or quantidade < 0:
        raise ValueError("inválido")
    return saldo >= quantidade
'''


class ExperimentalPilotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workspace = self.root / "pilot-workspace"
        self.evidence = self.root / "pilot-evidence"
        self.calls = []
        self.agy_behavior = "OK"
        self.test_behavior = "OK"
        self.codex_behavior = "PASS"

    def simulate(self, command, *, cwd, stdin, timeout):
        self.calls.append(command[0])
        self.assertTrue(cwd.is_dir())
        self.assertLessEqual(timeout, 900)
        if command[0] == "agy.exe":
            if self.agy_behavior == "TEXT":
                return ProcessResult(0, "```python\n" + SOURCE + "```\n", "")
            if self.agy_behavior == "TEXT_INVALID":
                return ProcessResult(0, "```python\nimport os\n" + SOURCE + "```\n", "")
            if self.agy_behavior == "TEXT_EXTRA":
                (cwd / "arquivo_extra.log").write_text("extra", encoding="utf-8")
                return ProcessResult(0, "```python\n" + SOURCE + "```\n", "")
            if self.agy_behavior == "NO_OUTPUT":
                return ProcessResult(0, "AGY respondeu sem gravar src/estoque.py", "")
            if self.agy_behavior == "TIMEOUT":
                return ProcessResult(-1, "", "timeout", True)
            if self.agy_behavior == "EXTRA":
                (cwd / "segredo.txt").write_text("fora do escopo")
            if self.agy_behavior == "TAMPER":
                (cwd / "tests" / "test_acceptance.py").write_text("alterado")
            if self.agy_behavior == "SYNTAX":
                (cwd / "src" / "estoque.py").write_text("def invalid(:")
            else:
                (cwd / "src" / "estoque.py").write_text(SOURCE, encoding="utf-8")
            return ProcessResult(0, "AGY gerou arquivo", "")
        if command[0] == sys.executable:
            self.assertIn("test_acceptance.py", command)
            if self.test_behavior == "FAIL":
                return ProcessResult(1, "", "FAILED (failures=1)")
            return ProcessResult(0, "", "Ran 9 tests in 0.1s\n\nOK")
        if command[0] == "codex.cmd":
            self.assertIsNotNone(stdin)
            self.assertIn("read-only", command)
            return ProcessResult(
                0, ("VEREDITO: APROVAR_LAB\n" if self.codex_behavior == "PASS"
                    else "VEREDITO: BLOQUEADO\n"), "")
        raise AssertionError("Processo inesperado: " + repr(command))

    def run_fake(self, **kwargs):
        with patch(
            "chdevflow.core.experimental_pilot._executables",
            return_value=(["agy.exe"], ["codex.cmd"]),
        ), patch(
            "chdevflow.core.experimental_pilot._run_command", side_effect=self.simulate,
        ), patch(
            "subprocess.Popen", side_effect=AssertionError("Agentes reais proibidos no CI"),
        ):
            return run_local_pilot(
                workspace=self.workspace, evidence=self.evidence,
                accepted=True, timeout=300, **kwargs,
            )

    def test_piloto_completo_com_fakes_e_dossie(self):
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_APROVADO_AGUARDANDO_CH1", report.findings)
        self.assertEqual(self.calls, ["agy.exe", sys.executable, "codex.cmd"])
        self.assertEqual(report.stages["TESTES"], "PASS")
        self.assertEqual(report.codex_verdict, "APROVAR_LAB")
        self.assertEqual(report.agent_calls, ["agy", "codex"])
        self.assertFalse(report.cost_verified)
        self.assertFalse(report.os_isolation_verified)
        for name in (
            "execucao.json", "resposta_agy.md", "logs_testes.txt",
            "alteracoes.patch", "auditoria_codex.md", "RELATORIO_COMPLETO_CH1.md",
        ):
            self.assertTrue((self.evidence / name).is_file(), name)
        self.assertEqual(
            json.loads((self.evidence / "execucao.json").read_text())["status"],
            "LAB_APROVADO_AGUARDANDO_CH1",
        )

    def test_aceite_ausente_impede_qualquer_execucao(self):
        with patch(
            "chdevflow.core.experimental_pilot._executables",
            side_effect=AssertionError("não consultar CLI"),
        ):
            with self.assertRaises(PermissionError):
                run_local_pilot(
                    workspace=self.workspace, evidence=self.evidence, accepted=False,
                )
        self.assertFalse(self.workspace.exists())

    def test_timeout_maximo_e_minimo(self):
        for timeout in (1, 119, 901, True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                run_local_pilot(
                    workspace=self.workspace, evidence=self.evidence,
                    accepted=True, timeout=timeout,
                )

    def test_diretorio_existente_nao_sobrescreve(self):
        self.workspace.mkdir()
        with self.assertRaises(ValueError):
            run_local_pilot(
                workspace=self.workspace, evidence=self.evidence, accepted=True,
            )

    def test_agy_timeout_bloqueia_codex(self):
        self.agy_behavior = "TIMEOUT"
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_BLOQUEADO")
        self.assertEqual(self.calls, ["agy.exe"])
        self.assertTrue((self.evidence / "execucao.json").is_file())

    def test_agy_responde_sucesso_sem_criar_codigo_diagnostico_preciso(self):
        self.agy_behavior = "NO_OUTPUT"
        result = self.run_fake()
        self.assertEqual(result.status, "LAB_BLOQUEADO")
        self.assertEqual(result.stages["AGY"], "BLOQUEADO")
        self.assertEqual(result.stages["ESCOPO"], "BLOQUEADO")
        self.assertIn("src/estoque.py", result.findings[0])
        self.assertEqual(self.calls, ["agy.exe"])
        self.assertIn("src/estoque.py", diagnose_existing_lab(
            workspace=self.workspace, evidence=self.evidence
        )["missing_files"])

    def test_lab_diagnose_ja_existente_nao_roda_agentes(self):
        self.agy_behavior = "NO_OUTPUT"
        self.run_fake()
        before_files = sorted(self.workspace.rglob("*"))
        with patch("subprocess.Popen", side_effect=AssertionError("Nenhuma CLI")), redirect_stdout(StringIO()) as out:
            status = cli_main([
                "pipeline", "lab-diagnose",
                "--workspace", str(self.workspace),
                "--evidence-dir", str(self.evidence),
                "--json",
            ])
        self.assertEqual(status, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "DIAGNOSTICO_SOMENTE_LEITURA")
        self.assertTrue(report["agy_log_exists"])
        self.assertIn("src/estoque.py", report["missing_files"])
        self.assertEqual(before_files, sorted(self.workspace.rglob("*")))

    def test_sem_log_agy_diagnostica_sem_falha(self):
        self.agy_behavior = "NO_OUTPUT"
        self.run_fake()
        (self.evidence / "resposta_agy.md").unlink()
        report = diagnose_existing_lab(
            workspace=self.workspace, evidence=self.evidence
        )
        self.assertFalse(report["agy_log_exists"])
        self.assertIsNone(report["agy_log_bytes"])

    def test_agy_headless_texto_aplicado_pelo_dispatcher_com_codex(self):
        self.agy_behavior = "TEXT"
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_APROVADO_AGUARDANDO_CH1", report.findings)
        self.assertEqual(self.calls, ["agy.exe", sys.executable, "codex.cmd"])
        self.assertEqual(report.stages["AGY_TEXT_ADAPTER"], "PASS")
        self.assertEqual((self.workspace / "src" / "estoque.py").read_text(), SOURCE)
        self.assertEqual(report.codex_verdict, "APROVAR_LAB")

    def test_agy_texto_com_import_nao_e_escrito_nem_executado(self):
        self.agy_behavior = "TEXT_INVALID"
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_BLOQUEADO")
        self.assertEqual(self.calls, ["agy.exe"])
        self.assertFalse((self.workspace / "src" / "estoque.py").exists())

    def test_agy_texto_com_extra_nao_faz_bypass_de_escopo(self):
        self.agy_behavior = "TEXT_EXTRA"
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_BLOQUEADO")
        self.assertEqual(self.calls, ["agy.exe"])
        self.assertFalse((self.workspace / "src" / "estoque.py").exists())

    def test_escopo_extra_bloqueia(self):
        self.agy_behavior = "EXTRA"
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_BLOQUEADO")
        self.assertEqual(self.calls, ["agy.exe"])

    def test_tentativa_alterar_aceite_bloqueia(self):
        self.agy_behavior = "TAMPER"
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_BLOQUEADO")
        self.assertEqual(self.calls, ["agy.exe"])

    def test_erro_de_sintaxe_bloqueia(self):
        self.agy_behavior = "SYNTAX"
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_BLOQUEADO")
        self.assertEqual(self.calls, ["agy.exe"])

    def test_teste_de_aceite_falha_sem_codex(self):
        self.test_behavior = "FAIL"
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_BLOQUEADO")
        self.assertEqual(self.calls, ["agy.exe", sys.executable])

    def test_codex_veta_sem_aprovacao_falsa(self):
        self.codex_behavior = "VETO"
        report = self.run_fake()
        self.assertEqual(report.status, "LAB_BLOQUEADO")
        self.assertEqual(report.codex_verdict, "BLOQUEADO")

    def test_env_elimina_chaves_de_api_sem_expor_valores(self):
        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "sk-SECRET",
            "GITHUB_TOKEN": "ghp-SECRET",
            "CODEX_API_KEY": "sk-OTHER",
            "AGY_NO_SECRET": "ok",
        }):
            env = _agent_environment()
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertEqual(env["AGY_NO_SECRET"], "ok")

    def test_comando_oficial_run_continua_bloqueado(self):
        with patch("subprocess.Popen", side_effect=AssertionError("Proibido")), redirect_stderr(StringIO()) as err:
            status = cli_main(["pipeline", "run", "--mission", "nao-existe.json"])
        self.assertEqual(status, 2)
        self.assertIn("BLOQUEADO_ATIVACAO", err.getvalue())

    def test_cli_lab_pilot_sem_flag_bloqueado(self):
        with patch("subprocess.Popen", side_effect=AssertionError("Proibido")), redirect_stderr(StringIO()) as err:
            status = cli_main([
                "pipeline", "lab-pilot",
                "--workspace", str(self.workspace),
                "--evidence-dir", str(self.evidence),
            ])
        self.assertEqual(status, 2)
        self.assertFalse(self.workspace.exists())

    def test_pastas_aninhadas_recusadas(self):
        with self.assertRaises(ValueError):
            run_local_pilot(
                workspace=self.workspace, evidence=self.workspace / "report",
                accepted=True,
            )


if __name__ == "__main__":
    unittest.main()
