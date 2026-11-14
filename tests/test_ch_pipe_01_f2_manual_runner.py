"""F2 — testes de contrato, bloqueios e zero execução real de agentes."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chdevflow.cli import main as cli_main
from chdevflow.core.manual_pipeline_runner import (
    Mission, ProcessAdapter, SCHEMA, SimulatedPipeline, load_manifest,
    plan_manual_mission,
)

SHA = "a" * 40


class ManualF2Tests(TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "missions").mkdir()
        (self.root / "missions" / "mission.md").write_text(
            "Escrever somente em src/demo.py", encoding="utf-8"
        )
        self.data = {
            "schema": SCHEMA, "mission_id": "LAB-F2-001",
            "repository": "hallanbrito/CHDevFlow", "issue": 78,
            "base_sha": SHA, "worktree": str(self.root),
            "allowed_paths": ["src/demo.py", "tests/test_demo.py"],
            "prompt_ref": "missions/mission.md", "timeout_seconds": 900,
        }

    def mission(self):
        return Mission.from_dict(self.data)

    def plan(self, *, sha=SHA, branch="feature/f2", clean=True):
        return plan_manual_mission(self.mission(), observed_sha=sha,
                                   observed_branch=branch, worktree_clean=clean)

    def test_plano_real_e_bloqueio_de_execucao(self):
        plan = self.plan()
        self.assertEqual(plan.state, "PLANEJADO_AGUARDANDO_GATE")
        self.assertFalse(plan.may_execute_agents)
        self.assertEqual(len(plan.mission_digest), 64)
        self.assertIn("Codex".upper(), plan.stages)

    def test_diferenca_de_baseline_bloqueia(self):
        self.assertEqual(self.plan(sha="b"*40).state, "BLOQUEADO")
        self.assertEqual(self.plan(sha=None).state, "BLOQUEADO")

    def test_branch_main_ou_dirty_bloqueados(self):
        self.assertEqual(self.plan(branch="main").state, "BLOQUEADO")
        self.assertEqual(self.plan(branch="master").state, "BLOQUEADO")
        self.assertEqual(self.plan(branch=None).state, "BLOQUEADO")
        self.assertEqual(self.plan(clean=False).state, "BLOQUEADO")

    def test_timeout_custo_e_esquema_fechados(self):
        self.data["timeout_seconds"] = 901
        self.assertEqual(plan_manual_mission(self.mission(), observed_sha=SHA).state, "BLOQUEADO")
        self.data["timeout_seconds"] = 900
        self.data["schema"] = "outro/v9"
        self.assertEqual(plan_manual_mission(self.mission(), observed_sha=SHA).state, "BLOQUEADO")

    def test_escopo_traversal_e_symlink(self):
        self.data["allowed_paths"] = ["../segredo.txt"]
        self.assertEqual(plan_manual_mission(self.mission(), observed_sha=SHA).state, "BLOQUEADO")
        self.data["allowed_paths"] = ["src/demo.py"]
        p = self.root / "src" / "demo.py"
        try:
            p.symlink_to(self.root / "missions" / "mission.md")
        except (OSError, NotImplementedError):
            self.skipTest("Symlink não permitido neste host")
        self.assertEqual(plan_manual_mission(self.mission(), observed_sha=SHA).state, "BLOQUEADO")

    def test_manifesto_campos_extra_falham(self):
        self.data["extra"] = "run"
        with self.assertRaises(ValueError):
            self.mission()

    def test_prompt_ausente_bloqueia(self):
        (self.root / "missions" / "mission.md").unlink()
        self.assertEqual(plan_manual_mission(self.mission(), observed_sha=SHA).state, "BLOQUEADO")

    def test_adapters_somente_catalogo(self):
        self.assertEqual(ProcessAdapter.command("agy")[0], "agy")
        self.assertEqual(ProcessAdapter.command("codex")[0], "codex")
        self.assertIn("read-only", ProcessAdapter.command("codex"))
        with self.assertRaises(ValueError):
            ProcessAdapter.command("bash")
        self.assertNotIn("ghp_EXAMPLEtoken123456789012345", ProcessAdapter.sanitize("ghp_EXAMPLEtoken123456789012345"))

    def test_simulacao_duas_etapas_em_ordem(self):
        engine = SimulatedPipeline()
        with patch("subprocess.run", side_effect=AssertionError("EXECUÇÃO REAL PROIBIDA")):
            report = engine.run_fixture(
                self.mission(), {"agy": "código criado", "codex": "APROVAR_LAB"}, tests_ok=True
            )
            same = engine.run_fixture(
                self.mission(), {"agy": "outro código", "codex": "BLOQUEADO"}, tests_ok=False
            )
        self.assertEqual(report["status"], "FIXTURE_CONCLUIDA_SEM_EXECUCAO")
        self.assertEqual(report["agent_processes"], 0)
        self.assertEqual(report, same)

    def test_codex_bloqueio_e_testes_falharam(self):
        engine = SimulatedPipeline()
        report = engine.run_fixture(
            self.mission(), {"agy": "código", "codex": "BLOQUEADO"}, tests_ok=True
        )
        self.assertEqual(report["status"], "FIXTURE_BLOQUEADA")
        engine2 = SimulatedPipeline()
        fail = engine2.run_fixture(
            self.mission(), {"agy": "código", "codex": "APROVAR_LAB"}, tests_ok=False
        )
        self.assertEqual(fail["status"], "FIXTURE_BLOQUEADA")
        self.assertNotIn("codex", fail["stages"])

    def test_adapter_real_falha_sem_gate_antes_do_subprocesso(self):
        with patch("subprocess.run", side_effect=AssertionError("NUNCA")):
            with self.assertRaises(PermissionError):
                ProcessAdapter()._invoke_inactive("agy", "teste", self.root, 5)

    def test_cli_run_bloqueado_sem_subprocessos(self):
        manifest = self.root / "mission.json"
        manifest.write_text(json.dumps(self.data), encoding="utf-8")
        with patch("subprocess.run", side_effect=AssertionError("EXECUÇÃO REAL PROIBIDA")):
            code = cli_main(["pipeline", "run", "--mission", str(manifest)])
        self.assertEqual(code, 2)

    def test_cli_plan_consulta_somente_git(self):
        manifest = self.root / "mission.json"
        manifest.write_text(json.dumps(self.data), encoding="utf-8")
        with patch("subprocess.run") as mock:
            def git_result(command, **kwargs):
                from subprocess import CompletedProcess
                outputs = {
                    "rev-parse": SHA,
                    "branch": "feature/f2",
                    "status": "",
                }
                return CompletedProcess(command, 0, stdout=outputs[command[1]], stderr="")
            mock.side_effect = git_result
            code = cli_main(["pipeline", "plan", "--mission", str(manifest), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(mock.call_count, 3)
            self.assertEqual(mock.call_args_list[0].args[0][:2], ["git", "rev-parse"])

    def test_dados_fixture_nao_podem_ser_callable(self):
        engine = SimulatedPipeline()
        called = []
        def unsafe():
            called.append(True)
            return "APROVAR_LAB"
        # Python pode receber dados não tipados, mas não invoca callables.
        report = engine.run_fixture(self.mission(),
                                    {"agy": unsafe, "codex": unsafe}, tests_ok=True)
        self.assertEqual(called, [])
        self.assertEqual(report["status"], "FIXTURE_BLOQUEADA")


if __name__ == "__main__":
    main()
