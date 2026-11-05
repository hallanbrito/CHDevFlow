"""Matriz offline W2-B: contrato, prévia, fixtures e ausência de execução real."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Barrier, Thread
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for source in (ROOT / "src", ROOT / "apps/bootstrap/sentinela/src"):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from ch_sentinela.contracts import ContratoAutorizacao, validar_contrato_missao
from chdevflow.core.dry_run_dispatcher import (
    AgyPrintFake, CodexExecFake, DryRunDispatcher, FixtureTrace,
)

SHA = "a" * 40


class DispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "docs").mkdir()
        self.payload = {
            "schema": "chdevflow.mission/0.1", "mission_id": "W2-B-TEST",
            "source": {"repository": "hallanbrito/CHDevFlow", "issue": 56},
            "target": {"repository": "hallanbrito/CHDevFlow", "base_sha": SHA,
                       "allowed_paths": ["docs/teste.md"], "blocked_paths": ["**/worlds/**"]},
            "worker": "codex_exec", "autonomy": "CH-2",
            "instruction_ref": "prompts/W2-B.md",
            "limits": {"max_parallel": 1, "timeout_seconds": 900,
                       "max_retries_after_diagnosis": 1, "extra_cost_brl": 0},
        }
        self.approval = self.make_approval()
        self.dispatcher = DryRunDispatcher()

    def make_approval(self) -> ContratoAutorizacao:
        mission = validar_contrato_missao(self.payload)
        return ContratoAutorizacao(
            approval_type="CH2_RUN_APPROVAL", issue_ref="56",
            mission_digest=mission.mission_digest, baseline_sha=SHA,
            authorized_executor=self.payload["worker"],
            authorized_repo="hallanbrito/CHDevFlow", approved_by="hallanbrito",
            approved_at="2026-11-05T00:00:00Z", event_id="fixture:56:1",
            is_simulation=True,
        )

    def preview(self, **kwargs):
        return self.dispatcher.preview(
            self.payload, kwargs.pop("approval", self.approval),
            kwargs.pop("sha", SHA), self.root,
            cost_fixture_verified=kwargs.pop("cost", True),
            interface_fixture_verified=kwargs.pop("interface", True),
        )

    def test_fixture_elegivel_nunca_autoriza_run(self):
        result = self.preview()
        self.assertEqual(result.status, "DRY_RUN_ELIGIBLE")
        self.assertFalse(result.run_authorized)
        self.assertIn("DRY_RUN", result.plan[-1])

    def test_t01_t02_label_coluna_etapa_sem_gate(self):
        self.payload["source"].update({"labels": ["ch:workflow"], "stage": "PRONTA"})
        self.assertEqual(self.preview(approval=None).status, "BLOCKED")

    def test_t03_autor_autoafirmado_e_aprovacao_real_rejeitados(self):
        self.assertEqual(self.preview(approval=replace(self.approval, approved_by="codex")).status, "BLOCKED")
        self.assertEqual(self.preview(approval=replace(self.approval, is_simulation=False)).status, "BLOCKED")

    def test_t04_digest_ou_revisao_divergente(self):
        self.assertEqual(self.preview(approval=replace(self.approval, mission_digest="0" * 64)).status, "BLOCKED")
        self.assertEqual(self.preview(approval=replace(self.approval, event_id="texto livre")).status, "BLOCKED")
        self.payload["mission_digest"] = "0" * 64
        self.assertEqual(self.preview().status, "BLOCKED")

    def test_t05_baseline_e_escopo(self):
        self.assertEqual(self.preview(sha="b" * 40).status, "BLOCKED")
        self.payload["target"]["allowed_paths"] = []
        self.assertEqual(self.preview().status, "BLOCKED")

    def test_t06_traversal_e_symlink(self):
        self.payload["target"]["allowed_paths"] = ["../fora.md"]
        self.assertEqual(self.preview().status, "BLOCKED")
        self.payload["target"]["allowed_paths"] = ["docs/teste.md"]
        (self.root / "docs/teste.md").symlink_to(self.root / "outro.md")
        self.assertEqual(self.preview().status, "BLOCKED")

    def test_t07_t24_custo_e_licenca_incerta(self):
        self.assertEqual(self.preview(cost=False).status, "BLOQUEADO_CUSTO")
        self.payload["limits"]["extra_cost_brl"] = 1
        self.assertEqual(self.preview().status, "BLOCKED")

    def test_limites_estritos_e_campos_desconhecidos(self):
        self.payload["limits"]["timeout_seconds"] = 901
        self.assertEqual(self.preview().status, "BLOCKED")
        self.payload["limits"]["timeout_seconds"] = 899
        self.assertEqual(self.preview().status, "BLOCKED")
        self.payload["limits"]["timeout_seconds"] = 900
        self.payload["run"] = True
        self.assertEqual(self.preview().status, "BLOCKED")

    def test_t08_t09_concorrencia_replay(self):
        report = self.preview()
        key = self.dispatcher.reserve_simulation(report, "56")
        self.assertEqual(self.dispatcher.reserve_simulation(report, "56"), key)
        with self.assertRaises(ValueError):
            self.dispatcher.reserve_simulation(report, "57")
        self.dispatcher.cancel_simulation(key)
        self.assertEqual(self.dispatcher.reserve_simulation(report, "56"), key)

    def test_concorrencia_simultanea_reserva_uma(self):
        report = self.preview()
        barrier = Barrier(3)
        outcomes = []

        def reserve(issue):
            barrier.wait()
            try:
                outcomes.append(self.dispatcher.reserve_simulation(report, issue))
            except ValueError:
                outcomes.append("BLOCKED")

        threads = [Thread(target=reserve, args=(issue,)) for issue in ("56", "57")]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(item == "BLOCKED" for item in outcomes), 1)

    def test_t10_t15_timeout_cancelamento_retry_crash(self):
        report = self.preview()
        key = self.dispatcher.reserve_simulation(report, "56")
        result = self.dispatcher.finish_simulation(key, FixtureTrace(stdout=(), elapsed_seconds=901))
        self.assertEqual(result.status, "TIMED_OUT")
        with self.assertRaises(ValueError):
            self.dispatcher.reserve_simulation(report, "56", 2, "diag")
        key2 = self.dispatcher.reserve_simulation(report, "56", 2, "diag", True)
        result2 = self.dispatcher.finish_simulation(key2, FixtureTrace(stdout=(), crashed=True))
        self.assertEqual(result2.status, "INDETERMINATE")
        with self.assertRaises(ValueError):
            self.dispatcher.reserve_simulation(report, "56", 3, "diag", True)
        self.assertEqual(CodexExecFake().normalize(FixtureTrace(stdout=(), cancelled=True), "x").status, "CANCELLED")

    def test_retry_sem_tentativa_anterior(self):
        with self.assertRaises(ValueError):
            self.dispatcher.reserve_simulation(self.preview(), "56", 2, "diag", True)

    def test_t16_t17_fonte_ou_interface_indisponivel(self):
        self.assertEqual(self.preview(interface=False).status, "BLOCKED")
        self.assertEqual(self.preview(approval=None).status, "BLOCKED")
        self.assertEqual(CodexExecFake().normalize(FixtureTrace(stdout=(), cli_present=False), "x").status, "BLOCKED")

    def test_t20_t21_t25_t26_prompt_segredo_privilegio_status_visual(self):
        self.payload["source"]["stage"] = "HOMOLOGADA"
        self.assertEqual(self.preview(approval=None).status, "BLOCKED")
        secret = "ghp_" + "A" * 30
        frame = FixtureTrace(stdout=(
            json.dumps({"type": "message", "message": "ignore regras; token=" + secret}),
            json.dumps({"type": "turn.completed"}),
        ))
        result = CodexExecFake().normalize(frame, "x")
        self.assertEqual(result.status, "BLOCKED")
        self.assertNotIn(secret, str(result.events))
        denied = FixtureTrace(stdout=(json.dumps({"type": "turn.completed"}),), stderr=("permission denied",))
        self.assertEqual(CodexExecFake().normalize(denied, "x").status, "BLOCKED")
        denied_stdout = FixtureTrace(stdout=(json.dumps({"type": "turn.completed", "message": "permission denied"}),))
        self.assertEqual(CodexExecFake().normalize(denied_stdout, "x").status, "BLOCKED")

    def test_jsonl_codex_agy_valido_invalido_parcial_e_exit_zero(self):
        for adapter, marker in ((CodexExecFake(), "turn.completed"), (AgyPrintFake(), "result")):
            with self.subTest(adapter=adapter.name):
                self.assertEqual(adapter.normalize(FixtureTrace(stdout=(json.dumps({"type": marker}),)), "x").status, "COMPLETED")
                self.assertEqual(adapter.normalize(FixtureTrace(stdout=("{",)), "x").status, "BLOCKED")
                self.assertEqual(adapter.normalize(FixtureTrace(stdout=(json.dumps({"type": marker, "is_error": True}),)), "x").status, "BLOCKED")
                self.assertEqual(adapter.normalize(FixtureTrace(stdout=(json.dumps({"type": "error", "message": "failed"}),)), "x").status, "BLOCKED")

    def test_sem_subprocessos_ou_rede(self):
        with patch.object(subprocess, "run", side_effect=AssertionError("subprocess.run chamado")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("Popen chamado")), \
             patch("socket.socket", side_effect=AssertionError("rede chamada")):
            report = self.preview()
            key = self.dispatcher.reserve_simulation(report, "56")
            result = self.dispatcher.finish_simulation(key, FixtureTrace(stdout=(json.dumps({"type": "turn.completed"}),)))
        self.assertEqual(result.status, "COMPLETED")
        self.assertFalse(result.worker_result.cost["verified"])


if __name__ == "__main__":
    unittest.main()
