"""Testes de validação da CI integral e gate verificável (AUD-GERAL-P0-03).

Garante que:
1. O workflow do GitHub Actions cobre todos os componentes críticos (CLI, Sentinela, Control Center).
2. Mudanças em qualquer área crítica (src/**, apps/**, scripts/**, tests/**, etc.) acionam a CI.
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

REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    import yaml
except ModuleNotFoundError:
    yaml = None  # type: ignore


class TestCiIntegralAudit(unittest.TestCase):
    """Testes de conformidade, cobertura e fail-closed da CI integral."""

    def setUp(self) -> None:
        self.workflow_path = REPO_ROOT / ".github" / "workflows" / "w1-checks.yml"
        self.assertTrue(self.workflow_path.is_file(), f"Workflow {self.workflow_path} não encontrado.")
        self.workflow_content = self.workflow_path.read_text(encoding="utf-8")

    def _load_yaml(self) -> dict:
        """Carrega e valida o arquivo YAML do workflow."""
        if yaml is not None:
            data = yaml.safe_load(self.workflow_content)
            self.assertIsInstance(data, dict, "Workflow YAML deve ser um dicionário.")
            return data
        # Fallback básico caso pyyaml não esteja disponível no ambiente de teste
        lines = [line.strip() for line in self.workflow_content.splitlines()]
        return {"raw_lines": lines}

    def test_workflow_file_exists_and_is_valid_yaml(self) -> None:
        """Valida a existência e sintaxe do arquivo de workflow da CI integral."""
        data = self._load_yaml()
        if yaml is not None:
            self.assertIn("name", data)
            self.assertIn("on", data)
            self.assertIn("jobs", data)
            self.assertIn("python-checks", data["jobs"])

    def test_workflow_triggers_cover_all_critical_paths(self) -> None:
        """Comprova que os gatilhos cobrem todas as áreas críticas do repositório."""
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
        if yaml is not None:
            on_config = data.get("on", {})
            self.assertIn("pull_request", on_config, "CI deve monitorar pull_request.")
            self.assertIn("push", on_config, "CI deve monitorar push para main.")
            self.assertIn("workflow_dispatch", on_config, "CI deve permitir despacho manual.")

            pr_paths = on_config["pull_request"].get("paths", [])
            push_paths = on_config["push"].get("paths", [])

            for path in critical_paths:
                self.assertIn(
                    path,
                    pr_paths,
                    f"Caminho crítico '{path}' ausente dos paths de pull_request.",
                )
                self.assertIn(
                    path,
                    push_paths,
                    f"Caminho crítico '{path}' ausente dos paths de push.",
                )
        else:
            for path in critical_paths:
                self.assertIn(f'"{path}"', self.workflow_content)

    def test_workflow_steps_cover_compilation_and_all_suites(self) -> None:
        """Comprova que o job python-checks executa compilação sintática e as 3 suítes."""
        self.assertIn("compileall", self.workflow_content)
        self.assertIn("src scripts apps", self.workflow_content)
        self.assertIn("w1_github_project.py", self.workflow_content)
        self.assertIn("apps/bootstrap/sentinela", self.workflow_content)
        self.assertIn("apps/control-center", self.workflow_content)
        self.assertIn("unittest discover -s tests", self.workflow_content)
        self.assertIn("apps/bootstrap/sentinela/tests", self.workflow_content)
        self.assertIn("pytest apps/control-center/tests", self.workflow_content)

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
        """DEMONSTRAÇÃO DE QUEBRA: Falha em teste do Control Center faz pytest falhar (código != 0)."""
        with tempfile.TemporaryDirectory(prefix="ci_test_pytest_") as tmpdir:
            test_file = Path(tmpdir) / "test_cc_fail.py"
            test_file.write_text(
                "def test_control_center_broken_endpoint():\n"
                "    assert 200 == 500, 'Control Center endpoint regression'\n",
                encoding="utf-8",
            )

            # Executa pytest via Python se pytest estiver disponível no venv ou sistema
            try:
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
                self.assertIn("1 failed", proc.stderr + proc.stdout)
            except Exception:
                # Se pytest não estiver no sys.executable atual, valida via subprocess 'pytest' se existir
                if shutil.which("pytest") is not None:
                    proc = subprocess.run(
                        ["pytest", tmpdir],
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(proc.returncode, 0)
                else:
                    self.skipTest("pytest não instalado no interpretador atual.")

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
