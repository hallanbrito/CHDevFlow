"""F4 — testes offline de custo, sandbox sem rede e CLI fail-closed."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for source in (ROOT / "src", ROOT / "apps/bootstrap/sentinela/src"):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from chdevflow.cli import main as ch_main
from chdevflow.core.manual_pipeline_runner import Mission, PipelinePlan, SCHEMA
from chdevflow.core.pilot_readiness import (
    assess_cost, inspect_readiness, plan_fake_sandbox,
)

SHA = "a" * 40
IMAGE = "docker.io/library/python@sha256:" + "b" * 64


class F4ReadinessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "missions").mkdir()
        (self.root / "missions" / "pilot.md").write_text(
            "Uma missão somente documental", encoding="utf-8"
        )
        self.manifest = {
            "schema": SCHEMA,
            "mission_id": "LAB-F4-001",
            "repository": "hallanbrito/CHDevFlow",
            "issue": 78,
            "base_sha": SHA,
            "worktree": str(self.root),
            "allowed_paths": ["src/lab.py", "tests/test_lab.py"],
            "prompt_ref": "missions/pilot.md",
            "timeout_seconds": 900,
        }
        self.mission = Mission.from_dict(self.manifest)
        self.plan = PipelinePlan(
            "PLANEJADO_AGUARDANDO_GATE", "Plano documental",
            self.mission.mission_id, self.mission.digest,
            ("PREFLIGHT", "AGY", "TESTES", "CODEX", "DOSSIER", "CH1"),
        )
        self.lab = self.root / "sandbox"
        (self.lab / "tests").mkdir(parents=True)
        (self.lab / ".chdevflow-fake-lab.json").write_text(
            json.dumps({"schema": "chdevflow.fake-lab/v1", "kind": "fake-only"}),
            encoding="utf-8",
        )
        (self.lab / "tests" / "test_fake_agent.py").write_text(
            "import unittest\nclass Fake(unittest.TestCase):\n"
            "    def test_fake(self): self.assertTrue(True)\n",
            encoding="utf-8",
        )

    def fake_which(self, runtime):
        return "/usr/bin/" + runtime if runtime in ("docker", "podman") else None

    def sandbox(self, **kwargs):
        return plan_fake_sandbox(
            kwargs.pop("lab_dir", self.lab),
            runtime=kwargs.pop("runtime", "docker"),
            image=kwargs.pop("image", IMAGE),
            which=kwargs.pop("which", self.fake_which),
        )

    def test_custo_desconhecido_bloqueia(self):
        cost = assess_cost(env={})
        self.assertEqual(cost.status, "BLOQUEADO_CUSTO")
        self.assertFalse(cost.independently_verified)
        self.assertEqual(cost.can_spend_brl, 0)
        self.assertEqual(cost.codex, "NAO_VERIFICADO")
        self.assertEqual(cost.agy, "NAO_VERIFICADO")

    def test_api_key_exposta_apenas_como_risco_sem_exibir_secret(self):
        secret = "sk-ULTRASECRETOVALOR123456789"
        cost = assess_cost(env={"OPENAI_API_KEY": secret})
        self.assertEqual(cost.status, "BLOQUEADO_CUSTO")
        self.assertNotIn(secret, json.dumps(cost.to_dict()))
        self.assertTrue(any("Variáveis" in x for x in cost.reasons))

    def test_comprovante_autodeclarado_nao_autoriza(self):
        cost = assess_cost(
            env={},
            claimed_evidence={"provider": "codex", "free": True, "verified": True},
        )
        self.assertEqual(cost.status, "BLOQUEADO_CUSTO")
        self.assertFalse(cost.independently_verified)

    def test_readiness_com_plano_valido_ainda_bloqueia_custo(self):
        report = inspect_readiness(
            self.mission, self.plan, env={},
            which=self.fake_which, os_name="Windows",
        )
        self.assertEqual(report.status, "BLOQUEADO_CUSTO")
        self.assertFalse(report.can_execute_agents)
        self.assertEqual(report.host_os, "Windows")
        self.assertEqual(report.runtime_detected, ("docker", "podman"))
        self.assertGreaterEqual(len(report.required_next), 4)

    def test_readiness_plano_invalido_bloqueia(self):
        bad = PipelinePlan("BLOQUEADO", "SHA divergente", "X", "0"*64, ())
        report = inspect_readiness(
            self.mission, bad, env={}, which=lambda x: None
        )
        self.assertEqual(report.status, "BLOQUEADO")
        self.assertFalse(report.can_execute_agents)

    def test_sandbox_gera_argv_fake_com_restricoes(self):
        plan = self.sandbox()
        self.assertEqual(plan.status, "PLANO_FAKE_APENAS")
        self.assertFalse(plan.real_agents_allowed)
        self.assertFalse(plan.isolation_verified)
        self.assertEqual(plan.network, "none")
        command = list(plan.command)
        self.assertEqual(command[:2], ["docker", "run"])
        for item in (
            "--pull=never", "--network=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            "--pids-limit=32", "--memory=256m", "--cpus=1",
            "--user=65534:65534", "--entrypoint=python",
        ):
            self.assertIn(item, command)
        self.assertIn("readonly", command[command.index("--mount")+1])
        self.assertIn(IMAGE, command)
        self.assertNotIn("agy", command)
        self.assertNotIn("codex", command)
        self.assertNotIn("--privileged", command)
        self.assertNotIn("--network=host", command)

    def test_podman_tambem_gera_plano_sem_execucao(self):
        plan = self.sandbox(runtime="podman")
        self.assertEqual(plan.status, "PLANO_FAKE_APENAS")
        self.assertEqual(plan.command[0], "podman")

    def test_imagem_nao_pinada_bloqueia(self):
        for image in ("python:latest", "python@sha256:xyz", IMAGE + ";evil", ""):
            with self.subTest(image=image):
                self.assertEqual(
                    self.sandbox(image=image).status, "BLOQUEADO_ISOLAMENTO"
                )

    def test_runtime_desconhecido_bloqueia(self):
        self.assertEqual(
            self.sandbox(runtime="powershell").status, "BLOQUEADO_ISOLAMENTO"
        )

    def test_runtime_nao_encontrado_bloqueia(self):
        self.assertEqual(
            self.sandbox(which=lambda runtime: None).status,
            "BLOQUEADO_ISOLAMENTO",
        )

    def test_lab_com_segredos_bloqueia(self):
        (self.lab / ".env").write_text("OPENAI_API_KEY=secret", encoding="utf-8")
        self.assertEqual(self.sandbox().status, "BLOQUEADO_ISOLAMENTO")

    def test_lab_com_git_bloqueia(self):
        (self.lab / ".git").mkdir()
        (self.lab / ".git" / "config").write_text("token", encoding="utf-8")
        self.assertEqual(self.sandbox().status, "BLOQUEADO_ISOLAMENTO")

    def test_lab_com_arquivo_inesperado_bloqueia(self):
        (self.lab / "tests" / "test_real_agent.py").write_text("pass", encoding="utf-8")
        self.assertEqual(self.sandbox().status, "BLOQUEADO_ISOLAMENTO")

    def test_lab_com_arquivo_grande_bloqueia(self):
        (self.lab / "tests" / "test_fake_agent.py").write_text("a" * 20000)
        self.assertEqual(self.sandbox().status, "BLOQUEADO_ISOLAMENTO")

    def test_lab_sem_marcador_bloqueia(self):
        (self.lab / ".chdevflow-fake-lab.json").unlink()
        self.assertEqual(self.sandbox().status, "BLOQUEADO_ISOLAMENTO")

    def test_lab_marcador_alterado_bloqueia(self):
        (self.lab / ".chdevflow-fake-lab.json").write_text(
            json.dumps({"schema": "wrong", "kind": "fake-only"}),
            encoding="utf-8",
        )
        self.assertEqual(self.sandbox().status, "BLOQUEADO_ISOLAMENTO")

    def test_symlink_em_lab_bloqueia(self):
        target = self.lab / "README.md"
        try:
            target.symlink_to(self.root / "missions" / "pilot.md")
        except (OSError, NotImplementedError):
            self.skipTest("Symlink indisponível no host")
        self.assertEqual(self.sandbox().status, "BLOQUEADO_ISOLAMENTO")

    def test_comando_sandbox_nao_dispara_runtime(self):
        with patch("subprocess.run", side_effect=AssertionError("NUNCA")):
            self.assertEqual(self.sandbox().status, "PLANO_FAKE_APENAS")

    def test_cli_readiness_nao_inicia_agentes(self):
        manifest = self.root / "mission.json"
        manifest.write_text(json.dumps(self.manifest), encoding="utf-8")
        def git_only(argv, **kwargs):
            if argv[0] != "git":
                raise AssertionError("Comando externo não permitido")
            outputs = {"rev-parse": SHA, "branch": "feat/teste", "status": ""}
            return subprocess.CompletedProcess(argv, 0, outputs[argv[1]], "")
        with patch("subprocess.run", side_effect=git_only) as mock, \
                redirect_stdout(StringIO()) as out:
            status = ch_main(
                ["pipeline", "readiness", "--mission", str(manifest), "--json"]
            )
        self.assertEqual(status, 2)
        self.assertEqual(mock.call_count, 3)
        response = json.loads(out.getvalue())
        self.assertEqual(response["status"], "BLOQUEADO_CUSTO")
        self.assertFalse(response["can_execute_agents"])

    def test_cli_sandbox_plan_nao_inicia_containers_ou_agentes(self):
        with patch("subprocess.run", side_effect=AssertionError("NUNCA")), \
                patch("shutil.which", side_effect=self.fake_which), \
                redirect_stdout(StringIO()) as out:
            status = ch_main([
                "pipeline", "sandbox-plan", "--lab-dir", str(self.lab),
                "--runtime", "docker", "--image", IMAGE, "--json",
            ])
        self.assertEqual(status, 2)
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "PLANO_FAKE_APENAS")
        self.assertFalse(report["real_agents_allowed"])

    def test_cli_run_permanece_bloqueado(self):
        with patch("subprocess.run", side_effect=AssertionError("NUNCA")), \
                redirect_stderr(StringIO()) as err:
            status = ch_main(["pipeline", "run", "--mission", "fake.json"])
        self.assertEqual(status, 2)
        self.assertIn("BLOQUEADO_ATIVACAO", err.getvalue())


if __name__ == "__main__":
    unittest.main()
