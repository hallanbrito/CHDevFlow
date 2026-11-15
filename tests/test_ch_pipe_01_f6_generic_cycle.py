"""F6: testes offline do ciclo generico, sem CLIs reais, rede ou API paga."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "apps/bootstrap/sentinela/src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chdevflow.core import generic_cycle as f6
from chdevflow.core.experimental_pilot import ProcessResult
from chdevflow.core.manual_pipeline_runner import SCHEMA


BASE = "a" * 40
INITIAL = "def resposta():\n    return 0\n"
GOOD = "def resposta():\n    return 42\n"
BAD = "def resposta():\n    return 13\n"


def events(verdict):
    return "\n".join(json.dumps(x) for x in [
        {"type": "item.completed",
         "item": {"type": "agent_message", "text": "VEREDITO: " + verdict +
                  "\nValidacao estaticamente finalizada."}},
        {"type": "turn.completed"},
    ])


class GenericCycleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.worktree = root / "CH-Lab-F6-test"
        self.worktree.mkdir()
        (self.worktree / "src").mkdir()
        (self.worktree / "tests").mkdir()
        self.target = self.worktree / "src" / "resposta.py"
        self.target.write_text(INITIAL, encoding="utf-8")
        (self.worktree / "prompt.txt").write_text(
            "Implemente resposta() -> 42.", encoding="utf-8")
        (self.worktree / "tests" / "test_resposta.py").write_text(
            "# Teste independente para resposta", encoding="utf-8")
        self.manifest = root / "mission.json"
        self.data = {
            "schema": SCHEMA, "mission_id": "F6-TEST-001",
            "repository": "hallanbrito/CHDevFlow", "issue": 85,
            "base_sha": BASE, "worktree": str(self.worktree),
            "allowed_paths": ["src/resposta.py"], "prompt_ref": "prompt.txt",
            "timeout_seconds": 480,
        }
        self._write_manifest()
        self.evidence = root / "CH-Dossie-F6-test"
        self.commands = []
        self.verdicts = ["APROVAR_LAB"]
        self.fail_tests = set()
        self.calls_agy = 0
        self.calls_codex = 0
        self.codex_prompts = []
        self.agy_infra_error = False
        self.agy_changes_test = False
        self.tests_infra_error = False

    def _write_manifest(self):
        self.manifest.write_text(
            json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def fake_git(self, root, *args):
        self.assertEqual(root, self.worktree)
        if args[0] == "rev-parse":
            return BASE
        if args[0] == "remote":
            return "https://github.com/hallanbrito/CHDevFlow.git"
        if args[0] == "branch":
            return "feat/f6-test"
        if args[0] == "status":
            if self.target.read_text(encoding="utf-8") == INITIAL:
                return ""
            return " M src/resposta.py"
        raise AssertionError("Git comando inesperado " + repr(args))

    def fake_command(self, command, *, cwd, stdin, timeout):
        self.assertEqual(cwd, self.worktree)
        self.assertGreater(timeout, 0)
        self.commands.append(command[0])
        if command[0] == "agy.exe":
            self.calls_agy += 1
            self.assertIn("F6-TEST-001", command[-1])
            if self.agy_infra_error:
                return ProcessResult(1, "", "quota/credentials invalid")
            if self.agy_changes_test:
                (cwd / "tests" / "test_resposta.py").write_text(
                    "adulterado", encoding="utf-8")
            if self.calls_agy > 1:
                self.assertIn("Correcao obrigatoria:", command[-1])
            code = GOOD if self.calls_agy == 3 or self.verdicts == ["APROVAR_LAB"] else BAD
            response = chr(96) * 3 + "python\n" + code.rstrip() + "\n" + chr(96) * 3
            return ProcessResult(
                0, json.dumps({"status": "SUCCESS", "response": response}), "")
        if command[0] in (sys.executable, "docker"):
            if self.tests_infra_error:
                return ProcessResult(
                    1, "", "Ran 2 tests\nFAILED (errors=1)\nModuleNotFoundError")
            if self.calls_agy in self.fail_tests:
                return ProcessResult(1, "", "Ran 2 tests\nFAILED (failures=1)")
            return ProcessResult(0, "", "Ran 2 tests\nOK")
        if command[0] == "codex.exe":
            self.calls_codex += 1
            self.codex_prompts.append(stdin)
            return ProcessResult(0, events(self.verdicts[self.calls_codex - 1]), "")
        raise AssertionError("Comando nao permitido: " + repr(command))

    def run_fake(self):
        with patch.object(f6, "_git", side_effect=self.fake_git), \
             patch.object(f6, "_executables", return_value=(
                 ["agy.exe"], ["codex.exe"])), \
             patch.object(f6, "_run_command", side_effect=self.fake_command):
            return f6.run_generic_cycle(
                manifest_path=self.manifest,
                evidence=self.evidence,
                accepted=True, timeout=480)

    def test_isolamento_docker_bloqueia_antes_do_agy_se_indisponivel(self):
        with patch.object(f6, "_git", side_effect=self.fake_git), \
             patch.object(f6.docker_acceptance, "preflight",
                          side_effect=ValueError("Docker nao disponivel")), \
             patch.object(f6, "_executables",
                          side_effect=AssertionError("Nunca chamar agentes")):
            with self.assertRaisesRegex(ValueError, "Docker"):
                f6.run_generic_cycle(
                    manifest_path=self.manifest, evidence=self.evidence,
                    accepted=True, isolated_tests=True)
        self.assertFalse(self.evidence.exists())

    def test_isolamento_docker_invoca_runner_antes_do_codex(self):
        with patch.object(f6, "_git", side_effect=self.fake_git), \
             patch.object(f6, "_executables",
                          return_value=(["agy.exe"], ["codex.exe"])), \
             patch.object(f6, "_run_command", side_effect=self.fake_command), \
             patch.object(f6.docker_acceptance, "preflight",
                          return_value="sha256:" + "d"*64), \
             patch.object(f6.docker_acceptance, "build_command",
                          return_value=["docker", "run", "--network=none"]):
            result = f6.run_generic_cycle(
                manifest_path=self.manifest, evidence=self.evidence,
                accepted=True, isolated_tests=True)
        self.assertEqual(result.status, "APROVADO_AGUARDANDO_CH1")
        self.assertEqual(result.test_execution,
                         "docker-readonly-no-network:sha256:" + "d"*64)
        self.assertEqual(self.commands, ["agy.exe", "docker", "codex.exe"])

    def test_git_porcelain_preserva_espaco_xy_e_autoriza_alvo(self):
        # Regressao real do incidente Windows F6-FRETE: strip() quebrava XY.
        payload = subprocess.CompletedProcess(
            ["git", "status", "--porcelain"], 0,
            " M src/resposta.py\r\n", "")
        with patch.object(f6.subprocess, "run", return_value=payload):
            dirty = f6._git(
                self.worktree, "status", "--porcelain", "--untracked-files=all")
        self.assertEqual(dirty, " M src/resposta.py")
        snapshot = {
            "prompt.txt": (self.worktree / "prompt.txt").read_bytes(),
            "tests/test_resposta.py": (
                self.worktree / "tests" / "test_resposta.py").read_bytes(),
        }
        with patch.object(f6, "_git", return_value=dirty):
            f6._guard(self.worktree, "src/resposta.py", snapshot,
                      allow_target=True)
        # Arquivos NAO autorizados continuam bloqueados.
        with patch.object(
                f6, "_git", return_value=" M src/extra.py"):
            with self.assertRaisesRegex(ValueError, "fora do escopo"):
                f6._guard(self.worktree, "src/resposta.py", snapshot,
                          allow_target=True)

    def test_patch_sem_lf_final_mantem_docstring_em_linha_propria(self):
        # Causa raiz F6-FRETE: difflib colava linha sem LF com adicao.
        old = "def resposta():\r\n    raise NotImplementedError('stub')"
        new = 'def resposta():\n    """Calcula frete.\n    Args: numero inteiro.\n    """\n    return 42\n'
        evidence = f6._audit_patch(old, new, "src/resposta.py")
        self.assertIn("\n-    raise NotImplementedError('stub')\n", evidence)
        self.assertIn('\n+    """Calcula frete.\n', evidence)
        self.assertIn('\n+    Args: numero inteiro.\n', evidence)
        self.assertTrue(evidence.endswith("\n"))
        self.assertNotIn("NotImplementedError('stub')+    ", evidence)

    def test_codex_ve_codigo_completo_e_diff_baseline_em_retentativa(self):
        # AGY devolve mesmo SHA na rodada 2: prompt Codex ainda tem patch.
        self.verdicts = ["BLOQUEADO", "APROVAR_LAB"]
        result = self.run_fake()
        self.assertEqual(result.status, "APROVADO_AGUARDANDO_CH1")
        self.assertEqual(self.calls_agy, 2)
        self.assertEqual(self.calls_codex, 2)
        self.assertEqual(len(self.codex_prompts), 2)
        for request in self.codex_prompts:
            self.assertIn("Codigo completo gerado, SHA256=", request)
            self.assertIn(BAD, request)
            self.assertIn(" M src/resposta.py", request)
            self.assertIn("Patch textual (baseline original", request)
            self.assertIn("\n-    return 0\n", request)
            self.assertIn("\n+    return 13\n", request)
            self.assertIn("Ran 2 tests", request)
        self.assertEqual(
            hashlib.sha256(BAD.encode("utf-8")).hexdigest(),
            result.attempts[1]["sha256"])

    def test_aprova_primeira_e_nao_repete_modelos(self):
        report = self.run_fake()
        self.assertEqual(report.status, "APROVADO_AGUARDANDO_CH1")
        self.assertEqual(self.calls_agy, 1)
        self.assertEqual(self.calls_codex, 1)
        self.assertEqual(report.returns_used, 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), GOOD)
        self.assertTrue((self.evidence / "execucao.json").exists())

    def test_aprova_terceira_com_duas_devolucoes(self):
        self.verdicts = ["BLOQUEADO", "BLOQUEADO", "APROVAR_LAB"]
        report = self.run_fake()
        self.assertEqual(report.status, "APROVADO_AGUARDANDO_CH1")
        self.assertEqual(self.calls_agy, 3)
        self.assertEqual(self.calls_codex, 3)
        self.assertEqual(report.returns_used, 2)
        self.assertTrue((self.evidence / "attempt-02" /
                         "feedback_para_agy.md").exists())

    def test_terceira_reprovacao_escalona_sem_quarta(self):
        self.verdicts = ["BLOQUEADO"] * 3
        report = self.run_fake()
        self.assertEqual(report.status, "AGUARDANDO_PO")
        self.assertEqual(self.calls_agy, 3)
        self.assertEqual(report.returns_used, 2)
        payload = json.loads(
            (self.evidence / "escalonamento_po.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "AGUARDANDO_PO")
        self.assertEqual(payload["issue"], 85)
        self.assertEqual(payload["publication_status"], "PENDENTE_DE_AUTORIZACAO")

    def test_falha_de_teste_nao_gasta_codex_na_primeira(self):
        self.fail_tests = {1}
        report = self.run_fake()
        self.assertEqual(report.status, "APROVADO_AGUARDANDO_CH1")
        self.assertEqual(self.calls_agy, 2)
        self.assertEqual(self.calls_codex, 1)
        self.assertEqual(report.returns_used, 1)

    def test_falha_de_autenticacao_nao_repete(self):
        self.agy_infra_error = True
        report = self.run_fake()
        self.assertEqual(report.status, "BLOQUEADO_INFRA_OU_ESCOPO")
        self.assertEqual(self.calls_agy, 1)
        self.assertEqual(self.calls_codex, 0)
        self.assertEqual(report.returns_used, 0)

    def test_erro_importacao_de_testes_nao_gasta_segunda_rodada(self):
        self.tests_infra_error = True
        report = self.run_fake()
        self.assertEqual(report.status, "BLOQUEADO_INFRA_OU_ESCOPO")
        self.assertEqual(self.calls_agy, 1)
        self.assertEqual(self.calls_codex, 0)
        self.assertEqual(report.returns_used, 0)

    def test_agy_altera_teste_independente_bloqueia(self):
        self.agy_changes_test = True
        report = self.run_fake()
        self.assertEqual(report.status, "BLOQUEADO_INFRA_OU_ESCOPO")
        self.assertEqual(self.calls_agy, 1)
        self.assertEqual(self.calls_codex, 0)
        self.assertEqual(report.returns_used, 0)

    def test_sem_optin_sem_executar(self):
        with patch.object(f6, "_executables", side_effect=AssertionError("Nao iniciar")):
            with self.assertRaises(PermissionError):
                f6.run_generic_cycle(
                    manifest_path=self.manifest, evidence=self.evidence,
                    accepted=False)
        self.assertFalse(self.evidence.exists())

    def test_impede_replay_sem_mais_chamadas(self):
        self.run_fake()
        with patch.object(f6, "_executables",
                          side_effect=AssertionError("Nao iniciar")):
            with self.assertRaises(ValueError):
                f6.run_generic_cycle(
                    manifest_path=self.manifest, evidence=self.evidence,
                    accepted=True)

    def test_bloqueia_baseline_incorreta(self):
        self.data["base_sha"] = "b" * 40
        self._write_manifest()
        with patch.object(f6, "_git", side_effect=self.fake_git), \
             patch.object(f6, "_executables", side_effect=AssertionError("Sem CLI")):
            with self.assertRaises(ValueError):
                f6.run_generic_cycle(
                    manifest_path=self.manifest, evidence=self.evidence,
                    accepted=True)
        self.assertFalse(self.evidence.exists())

    def test_bloqueia_escopo_do_teste(self):
        self.data["allowed_paths"] = ["tests/test_resposta.py"]
        self._write_manifest()
        with self.assertRaises(ValueError):
            f6._preflight(self.manifest)

    def test_extrator_recusa_prosa_ou_codigo_invalido(self):
        for value in ("arquivo pronto", "def exemplo():\n pass",
                      chr(96)*3 + "python\nimport (\n" + chr(96)*3):
            with self.subTest(value=value), self.assertRaises(ValueError):
                f6._extract(value)

    def test_estado_de_escalonamento_nao_publica_project(self):
        self.verdicts = ["BLOQUEADO"] * 3
        self.run_fake()
        self.assertEqual(self.commands.count("agy.exe"), 3)
        self.assertFalse((self.evidence / "github_project_write.json").exists())


if __name__ == "__main__":
    unittest.main()
