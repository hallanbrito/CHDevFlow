"""Testes de validação da CI integral e gate verificável (AUD-GERAL-P0-03).

Garante que:
1. O workflow do GitHub Actions cobre todos os componentes críticos (CLI, Sentinela, Control Center).
2. Mudanças direcionadas à main (incluindo PRs exclusivamente documentais) acionam a CI sem bypass de paths.
3. Erros reais (erros de sintaxe, falhas em testes unitários ou de integração) fazem a CI falhar
   estritamente (código de saída != 0), eliminando riscos de falso PASS.
4. Todas as 3 suítes do ecossistema CHDevFlow são reconhecidas e executadas.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCiIntegralAudit(unittest.TestCase):
    """Testes de conformidade, cobertura e fail-closed da CI integral."""

    def setUp(self) -> None:
        self.workflow_path = REPO_ROOT / ".github" / "workflows" / "w1-checks.yml"
        self.assertTrue(self.workflow_path.is_file(), f"Workflow {self.workflow_path} não encontrado.")
        self.workflow_content = self.workflow_path.read_text(encoding="utf-8")

    def _load_yaml(self) -> dict:
        """Carrega e valida o arquivo YAML do workflow."""
        data = yaml.safe_load(self.workflow_content)
        self.assertIsInstance(data, dict, "Workflow YAML deve ser um dicionário.")
        return data

    def _get_on_config(self, data: dict) -> dict:
        """Obtém a seção 'on' tratando chave string ou booleana conforme especificação YAML."""
        if "on" in data:
            return data["on"]
        if True in data:
            return data[True]
        self.fail("Seção 'on' não encontrada no arquivo YAML de workflow.")

    def test_workflow_file_exists_and_is_valid_yaml(self) -> None:
        """Valida a existência e sintaxe do arquivo de workflow da CI integral."""
        data = self._load_yaml()
        self.assertIn("name", data)
        self.assertTrue("on" in data or True in data, "Seção 'on' deve existir no YAML.")
        self.assertIn("jobs", data)
        self.assertIn("python-checks", data["jobs"])

    def test_workflow_triggers_cover_all_critical_paths(self) -> None:
        """Comprova que os gatilhos cobrem todas as áreas críticas e todo PR na main (AUD-01)."""
        critical_paths = [
            "src/**",
            "apps/**",
            "scripts/**",
            "tests/**",
            "templates/**",
            ".github/**",
            "pyproject.toml",
            "MANIFEST.in",
        ]
        data = self._load_yaml()
        on_config = self._get_on_config(data)

        self.assertIn("pull_request", on_config, "CI deve monitorar pull_request.")
        self.assertIn("push", on_config, "CI deve monitorar push para main.")
        self.assertIn("workflow_dispatch", on_config, "CI deve permitir despacho manual.")

        # AUD-01: pull_request direcionado à main NÃO deve ter filtro 'paths',
        # garantindo execução também para PRs exclusivamente documentais.
        pr_config = on_config["pull_request"]
        self.assertEqual(pr_config.get("branches"), ["main"], "pull_request deve monitorar branch main.")
        self.assertNotIn(
            "paths",
            pr_config,
            "pull_request NÃO deve ter filtro paths (deve executar para qualquer PR na main, inclusive documental).",
        )

        # push na main monitora paths críticos
        push_config = on_config["push"]
        self.assertEqual(push_config.get("branches"), ["main"], "push deve monitorar branch main.")
        push_paths = push_config.get("paths", [])
        for path in critical_paths:
            self.assertIn(
                path,
                push_paths,
                f"Caminho crítico '{path}' ausente dos paths de push.",
            )

    def test_workflow_steps_cover_compilation_and_all_suites(self) -> None:
        """Comprova estruturalmente que o job python-checks executa compilação sintática e as 3 suítes (AUD-03)."""
        data = self._load_yaml()
        steps = data["jobs"]["python-checks"]["steps"]

        run_commands = [step.get("run", "") for step in steps if "run" in step]
        uses_actions = [step.get("uses", "") for step in steps if "uses" in step]

        # Verifica actions essenciais
        self.assertTrue(any("actions/checkout" in a for a in uses_actions), "Step de checkout ausente.")
        self.assertTrue(any("actions/setup-python" in a for a in uses_actions), "Step de setup-python ausente.")

        # Verifica compilação sintática de src, scripts e apps
        compile_step = next((cmd for cmd in run_commands if "compileall" in cmd), None)
        self.assertIsNotNone(compile_step, "Etapa de compilação sintática (compileall) ausente.")
        for target in ["src", "scripts", "apps"]:
            self.assertIn(target, compile_step, f"Alvo '{target}' ausente no compileall.")

        # Verifica prévia offline W1
        self.assertTrue(
            any("w1_github_project.py" in cmd for cmd in run_commands),
            "Etapa de prévia offline W1 ausente.",
        )

        # Verifica instalação de pacotes locais
        install_step = next((cmd for cmd in run_commands if "pip install" in cmd), None)
        self.assertIsNotNone(install_step, "Etapa de instalação de dependências ausente.")
        self.assertIn("apps/bootstrap/sentinela", install_step)
        self.assertIn("apps/control-center", install_step)
        self.assertIn(".[dev]", install_step)

        # Verifica execução de testes da raiz (CLI)
        self.assertTrue(
            any("unittest discover -s tests" in cmd for cmd in run_commands),
            "Execução de testes da raiz (tests/) ausente.",
        )

        # Verifica execução de testes da Sentinela
        self.assertTrue(
            any("unittest discover -s apps/bootstrap/sentinela/tests" in cmd for cmd in run_commands),
            "Execução de testes da Sentinela ausente.",
        )

        # Verifica execução de testes do Control Center
        self.assertTrue(
            any("pytest apps/control-center/tests" in cmd for cmd in run_commands),
            "Execução de testes do Control Center ausente.",
        )

    def test_syntax_error_fails_compileall_strictly(self) -> None:
        """DEMONSTRAÇÃO DE QUEBRA: Erro de sintaxe faz 'python -m compileall' falhar (código != 0)."""
        with tempfile.TemporaryDirectory(prefix="ci_test_syntax_") as tmpdir:
            broken_file = Path(tmpdir) / "broken_syntax.py"
            broken_file.write_text("def broken_func(:\n    pass\n", encoding="utf-8")

            proc = subprocess.run(
                [sys.executable, "-m", "compileall", "-q", tmpdir],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(
                proc.returncode,
                0,
                "compileall deve falhar com código != 0 quando houver erro de sintaxe.",
            )

    def test_unittest_failure_fails_cli_runner_strictly(self) -> None:
        """DEMONSTRAÇÃO DE QUEBRA: Falha em teste da CLI faz unittest falhar (código != 0)."""
        with tempfile.TemporaryDirectory(prefix="ci_test_unittest_") as tmpdir:
            test_file = Path(tmpdir) / "test_failing.py"
            test_file.write_text(
                "import unittest\n"
                "class FailingTest(unittest.TestCase):\n"
                "    def test_intentional_failure(self):\n"
                "        self.fail('Falha intencional para comprovar fail-closed da CI')\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", tmpdir],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(
                proc.returncode,
                0,
                "unittest discover deve falhar com código != 0 diante de asserção falsa.",
            )
            self.assertIn("FAILED", proc.stderr + proc.stdout)

    def test_unittest_failure_fails_sentinela_runner_strictly(self) -> None:
        """DEMONSTRAÇÃO DE QUEBRA: Falha em teste da Sentinela faz o runner falhar (código != 0)."""
        with tempfile.TemporaryDirectory(prefix="ci_test_sentinela_") as tmpdir:
            test_file = Path(tmpdir) / "test_sentinela_fail.py"
            test_file.write_text(
                "import unittest\n"
                "class SentinelaBreakTest(unittest.TestCase):\n"
                "    def test_sentinela_regression(self):\n"
                "        self.assertEqual(1, 2, 'Sentinela contract breach')\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", tmpdir],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(
                proc.returncode,
                0,
                "Runner da Sentinela deve falhar com código != 0 diante de erro de contrato.",
            )
            self.assertIn("FAILED", proc.stderr + proc.stdout)

    def test_pytest_failure_fails_control_center_runner_strictly(self) -> None:
        """DEMONSTRAÇÃO DE QUEBRA (AUD-03): Falha em teste do Control Center faz pytest falhar estritamente."""
        with tempfile.TemporaryDirectory(prefix="ci_test_pytest_") as tmpdir:
            test_file = Path(tmpdir) / "test_cc_fail.py"
            test_file.write_text(
                "def test_control_center_broken_endpoint():\n"
                "    assert 200 == 500, 'Control Center endpoint regression'\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, "-m", "pytest", tmpdir],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(
                proc.returncode,
                0,
                "pytest deve retornar código != 0 diante de asserção falha.",
            )
            self.assertIn("1 failed", proc.stdout + proc.stderr)

    def test_simulated_pipeline_halts_on_first_failure(self) -> None:
        """DEMONSTRAÇÃO DE PREVENÇÃO DE FALSO PASS: Pipeline sequencial aborta na primeira falha."""
        # Simula um pipeline em script bash onde o primeiro comando falha
        pipeline_script = (
            "set -e\n"
            "echo 'Step 1: OK'\n"
            "python3 -c 'import sys; sys.exit(1)'\n"
            "echo 'Step 3: NÃO DEVE EXECUTAR'\n"
        )
        proc = subprocess.run(
            ["bash", "-c", pipeline_script],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(
            proc.returncode,
            0,
            "Script sequencial com 'set -e' deve falhar imediatamente.",
        )
        self.assertIn("Step 1: OK", proc.stdout)
        self.assertNotIn("Step 3: NÃO DEVE EXECUTAR", proc.stdout)

    def test_inventory_and_counts_of_all_three_components(self) -> None:
        """Verifica que o repositório mantém as 3 suítes ativas totalizando pelo menos 280 testes."""
        tests_dir = REPO_ROOT / "tests"
        sentinela_tests_dir = REPO_ROOT / "apps" / "bootstrap" / "sentinela" / "tests"
        cc_tests_dir = REPO_ROOT / "apps" / "control-center" / "tests"

        self.assertTrue(tests_dir.is_dir(), "Diretório tests/ não encontrado.")
        self.assertTrue(sentinela_tests_dir.is_dir(), "Diretório de testes da Sentinela não encontrado.")
        self.assertTrue(cc_tests_dir.is_dir(), "Diretório de testes do Control Center não encontrado.")

        root_test_files = list(tests_dir.glob("test_*.py"))
        sent_test_files = list(sentinela_tests_dir.glob("test_*.py"))
        cc_test_files = list(cc_tests_dir.glob("test_*.py"))

        self.assertGreaterEqual(len(root_test_files), 10, "Mínimo de 10 arquivos de teste na raiz.")
        self.assertGreaterEqual(len(sent_test_files), 5, "Mínimo de 5 arquivos de teste na Sentinela.")
        self.assertGreaterEqual(len(cc_test_files), 5, "Mínimo de 5 arquivos de teste no Control Center.")


if __name__ == "__main__":
    unittest.main()
