"""CCC-01: testes offline. Nunca chamam CLIs AGY/Codex reais ou APIs pagas."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "src", ROOT / "apps/bootstrap/sentinela/src"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from chdevflow.cli import main as ch_main
from chdevflow.core.controlled_cycle import run_controlled_pilot
from chdevflow.core.experimental_pilot import (
    ACCEPTANCE_CCC, LabResult, MISSION, SOURCE,
)

VULNERABLE = '''def movimentar(saldo, tipo, quantidade):
    if type(saldo) is not int or type(quantidade) is not int or saldo < 0 or quantidade < 0:
        raise ValueError("invalid")
    if tipo == "entrada":
        return saldo + quantidade
    if tipo == "saida":
        if quantidade > saldo:
            raise ValueError("insufficient")
        return saldo - quantidade
    raise ValueError("invalid")

def pode_separar(saldo, quantidade):
    if type(saldo) is not int or type(quantidade) is not int or saldo < 0 or quantidade < 0:
        raise ValueError("invalid")
    return saldo >= quantidade
'''
SAFE = VULNERABLE.replace(
    '    if tipo == "entrada":',
    '    if type(tipo) is not str:\n        raise ValueError("invalid")\n    if tipo == "entrada":'
)


class CCC01Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.workspace = root / "workspace"
        self.evidence = root / "evidence"
        self.calls = []
        self.plan = ["PASS"]

    def fake_pilot(self, *, workspace, evidence, accepted, timeout,
                   feedback, previous_source, acceptance_source):
        idx = len(self.calls)
        self.assertTrue(accepted)
        self.assertGreaterEqual(timeout, 120)
        self.assertEqual(acceptance_source, ACCEPTANCE_CCC)
        self.assertFalse(workspace.exists())
        self.assertFalse(evidence.exists())
        self.calls.append({"feedback": feedback, "previous_source": previous_source,
                           "workspace": workspace, "evidence": evidence})
        state = self.plan[idx]
        evidence.mkdir()
        (workspace / "src").mkdir(parents=True)
        (workspace / "tests").mkdir()
        (workspace / "mission.txt").write_text(MISSION, encoding="utf-8")
        (workspace / "tests" / "test_acceptance.py").write_text(ACCEPTANCE_CCC, encoding="utf-8")
        source = SAFE if state == "PASS" else VULNERABLE
        with (workspace / SOURCE).open("w", encoding="utf-8", newline="\n") as out:
            out.write(source)
        import hashlib
        sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
        (evidence / "logs_testes.txt").write_text("Ran 10 tests\n\nOK", encoding="utf-8")
        result = LabResult(
            status="LAB_APROVADO_AGUARDANDO_CH1",
            stages={"TESTES": "PASS", "CODEX": "PASS"},
            agent_calls=["agy", "codex"],
            code_sha256=sha, codex_verdict="APROVAR_LAB",
            workspace=str(workspace), evidence_dir=str(evidence),
        )
        if state in ("VETO", "TAMPER_MISSION"):
            (evidence / "auditoria_codex.md").write_text(
                "VEREDITO: BLOQUEADO\nFalta type(tipo) is str.", encoding="utf-8")
            result.status = "LAB_BLOQUEADO"
            result.failure_kind = "CODEX_REPROVOU"
            result.codex_verdict = "BLOQUEADO"
            result.stages["CODEX"] = "BLOQUEADO"
            if state == "TAMPER_MISSION":
                (workspace / "mission.txt").write_text("missao adulterada", encoding="utf-8")
        elif state == "TEST_FAIL":
            (evidence / "logs_testes.txt").write_text(
                "FAILED (failures=1) test_tipo_nao_string_eq_enganoso", encoding="utf-8")
            result.status = "LAB_BLOQUEADO"
            result.failure_kind = "TESTES_REPROVADOS"
            result.codex_verdict = "NAO_EXECUTADO"
            result.agent_calls = ["agy"]
            result.stages["TESTES"] = "BLOQUEADO"
            result.stages["CODEX"] = "NAO_EXECUTADO"
        elif state == "INFRA":
            result.status = "LAB_BLOQUEADO"
            result.failure_kind = "BLOQUEADO_INFRA_OU_ESCOPO"
            result.codex_verdict = "INDETERMINADO"
            result.agent_calls = ["agy"]
            result.stages["TESTES"] = "NAO_EXECUTADO"
        elif state == "UNKNOWN_CODEX":
            result.status = "LAB_BLOQUEADO"
            result.failure_kind = "BLOQUEADO_INFRA_OU_ESCOPO"
            result.codex_verdict = "INDETERMINADO"
        return result

    def run_fake(self, plan):
        self.plan = plan
        with patch("chdevflow.core.controlled_cycle.run_local_pilot", side_effect=self.fake_pilot):
            return run_controlled_pilot(
                workspace=self.workspace, evidence=self.evidence,
                accepted=True, timeout=480,
            )

    def test_aprovou_primeira_e_parou_sem_devolucao(self):
        report = self.run_fake(["PASS"])
        self.assertEqual(report.status, "APROVADO_AGUARDANDO_CH1")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report.returns_used, 0)
        self.assertTrue((self.evidence / "execucao.json").is_file())
        self.assertTrue((self.evidence / "RELATORIO_COMPLETO_CH1.md").is_file())

    def test_duas_devolucoes_aprovou_na_terceira(self):
        report = self.run_fake(["VETO", "VETO", "PASS"])
        self.assertEqual(report.status, "APROVADO_AGUARDANDO_CH1")
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(report.returns_used, 2)
        self.assertIn("Falta type(tipo) is str", self.calls[1]["feedback"])
        self.assertEqual(self.calls[1]["previous_source"], VULNERABLE)
        self.assertTrue((self.evidence / "attempt-01" / "feedback_para_agy.md").is_file())
        self.assertTrue((self.evidence / "attempt-02" / "feedback_para_agy.md").is_file())
        self.assertEqual(self.calls[2]["previous_source"], VULNERABLE)

    def test_terceira_reprovacao_escalona_sem_quarta_chamada(self):
        report = self.run_fake(["VETO", "VETO", "VETO"])
        self.assertEqual(report.status, "AGUARDANDO_PO")
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(report.returns_used, 2)
        self.assertEqual(len(report.attempts), 3)
        self.assertFalse((self.evidence / "attempt-03" / "feedback_para_agy.md").exists())
        self.assertIn("AGUARDANDO_PO", (self.evidence / "RELATORIO_COMPLETO_CH1.md").read_text())

    def test_teste_python_falha_nao_chama_codex_nova_rodada(self):
        report = self.run_fake(["TEST_FAIL", "PASS"])
        self.assertEqual(report.status, "APROVADO_AGUARDANDO_CH1")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(report.returns_used, 1)
        self.assertEqual(report.attempts[0]["agent_calls"], ["agy"])
        self.assertIn("FAILED (failures=1)", self.calls[1]["feedback"])

    def test_infra_nunca_faz_retry(self):
        report = self.run_fake(["INFRA"])
        self.assertEqual(report.status, "BLOQUEADO_INFRA")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report.returns_used, 0)

    def test_missao_adulterada_interrompe_antes_da_devolucao(self):
        report = self.run_fake(["TAMPER_MISSION", "PASS"])
        self.assertEqual(report.status, "BLOQUEADO_INFRA")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(report.returns_used, 0)
        self.assertTrue(any("missao original alterada" in x for x in report.findings))

    def test_parecer_codex_indeterminado_nao_gera_retry(self):
        report = self.run_fake(["UNKNOWN_CODEX"])
        self.assertEqual(report.status, "BLOQUEADO_INFRA")
        self.assertEqual(len(self.calls), 1)

    def test_sem_aceite_nao_chama_nada_nem_cria_pasta(self):
        with patch("chdevflow.core.controlled_cycle.run_local_pilot",
                   side_effect=AssertionError("agentes proibidos")):
            with self.assertRaises(PermissionError):
                run_controlled_pilot(workspace=self.workspace,
                                     evidence=self.evidence, accepted=False)
        self.assertFalse(self.workspace.exists())
        self.assertFalse(self.evidence.exists())

    def test_replay_mesma_execucao_bloqueado_sem_chamadas(self):
        self.run_fake(["PASS"])
        with patch("chdevflow.core.controlled_cycle.run_local_pilot",
                   side_effect=AssertionError("replay proibido")):
            with self.assertRaises(ValueError):
                run_controlled_pilot(workspace=self.workspace, evidence=self.evidence,
                                     accepted=True, timeout=480)

    def test_timeout_invalido_nunca_cria_pastas(self):
        for timeout in (True, 0, 119, 901):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                run_controlled_pilot(workspace=self.workspace,
                                     evidence=self.evidence, accepted=True,
                                     timeout=timeout)
        self.assertFalse(self.workspace.exists())

    def test_cli_local_cycle_integra_e_repassa_optin(self):
        with patch("chdevflow.cli.local_executor_main", return_value=0) as mock_main:
            code = ch_main(["pipeline", "local-cycle", "--timeout", "300",
                            "--i-accept-local-risk"])
        self.assertEqual(code, 0)
        mock_main.assert_called_once_with(
            ["cycle", "--timeout", "300", "--i-accept-local-risk"])

    def test_aceite_adversarial_reprova_codigo_vulneravel_aprova_corrigido(self):
        """Teste Python REAL, sem agente: reproduz o veto do Codex do Windows."""
        root = self.workspace
        (root / "src").mkdir(parents=True)
        (root / "tests").mkdir()
        (root / "tests" / "test_acceptance.py").write_text(ACCEPTANCE_CCC, encoding="utf-8")
        target = root / SOURCE
        command = [sys.executable, "-I", "-B", "-m", "unittest",
                   "discover", "-s", "tests", "-p", "test_acceptance.py", "-v"]
        target.write_text(VULNERABLE, encoding="utf-8")
        vulnerable = subprocess.run(command, cwd=root, capture_output=True,
                                    text=True, timeout=30)
        self.assertNotEqual(vulnerable.returncode, 0)
        self.assertIn("test_tipo_nao_string_eq_enganoso", vulnerable.stderr)
        target.write_text(SAFE, encoding="utf-8")
        corrected = subprocess.run(command, cwd=root, capture_output=True,
                                   text=True, timeout=30)
        self.assertEqual(corrected.returncode, 0, corrected.stderr)
        self.assertIn("Ran 10 tests", corrected.stderr)


if __name__ == "__main__":
    unittest.main()
