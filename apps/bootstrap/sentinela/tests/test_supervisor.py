"""Testes unitários do Supervisor e da Máquina de Estados.

Cobre todo o ciclo supervisionado:
DISCOVERED -> PROPOSED -> AWAITING_AUTH -> PREFLIGHT_OK -> CLAIMED -> RUNNING -> EVIDENCE_PENDING -> AWAITING_PO
além de cenários com FakeWorker (sucesso, falha, timeout, cancelamento, estado indeterminado),
bloqueio de concorrência, idempotência e geração de auditoria sem sobrescrita.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ch_sentinela.audit import Auditoria
from ch_sentinela.checkpoint import (
    ConcorrenciaBloqueadaErro,
    GerenciadorCheckpoint,
    IdempotenciaVioladaErro,
)
from ch_sentinela.contracts import (
    ContratoAutorizacao,
    ContratoMissao,
    validar_contrato_missao,
)
from ch_sentinela.supervisor import Supervisor
from ch_sentinela.workers.fake import FakeWorker


class TestesSupervisor(unittest.TestCase):
    """Testes da máquina de estados do Supervisor."""

    def setUp(self) -> None:
        """Configura ambiente temporário para auditoria e checkpoints isolados."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_sup_"))
        self.arquivo_audit = self.temp_dir / "auditoria.jsonl"
        self.arquivo_chk = self.temp_dir / "checkpoint.json"

        self.auditoria = Auditoria(caminho_arquivo=self.arquivo_audit)
        self.checkpoint = GerenciadorCheckpoint(caminho_arquivo=self.arquivo_chk)

        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        with open(fixtures_dir / "missao_valida.json", "r", encoding="utf-8") as f:
            self.payload_missao = json.load(f)

    def tearDown(self) -> None:
        """Limpa diretório temporário após os testes."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _criar_autorizacao_simulada(self, payload: dict) -> ContratoAutorizacao:
        """Gera autorização simulada válida correspondente ao payload."""
        missao = validar_contrato_missao(payload)
        return ContratoAutorizacao(
            approval_type="CH2_RUN_APPROVAL",
            issue_ref=str(missao.source["issue"]),
            mission_digest=missao.mission_digest,
            baseline_sha=missao.target["base_sha"],
            authorized_executor=missao.worker,
            authorized_repo=missao.target["repository"],
            approved_by="hallanbrito",
            approved_at="2026-10-19T20:00:00Z",
            event_id="evt-teste-supervisionado-001",
            is_simulation=True,
        )

    def test_parada_em_awaiting_auth_sem_autorizacao(self) -> None:
        """Garante que execução sem autorização do PO pára estritamente em AWAITING_AUTH."""
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria)
        resultado = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=None,
        )
        self.assertEqual(resultado.state, "AWAITING_AUTH")
        self.assertIsNone(resultado.human_decision)

        # Verifica eventos na auditoria
        eventos = self.auditoria.ler_eventos()
        estados = [e["estado_posterior"] for e in eventos]
        self.assertIn("DISCOVERED", estados)
        self.assertIn("PROPOSED", estados)
        self.assertIn("AWAITING_AUTH", estados)
        self.assertNotIn("CLAIMED", estados)
        self.assertNotIn("RUNNING", estados)

    def test_ciclo_completo_com_autorizacao_simulada_termina_em_awaiting_po(self) -> None:
        """Valida avanço por todos os estados até AWAITING_PO com fixture de simulação."""
        auth = self._criar_autorizacao_simulada(self.payload_missao)
        worker = FakeWorker(modo_simulacao="SUCESSO")
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria, worker=worker)

        resultado = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=auth,
            run_id_fornecido="run-teste-sucesso-1",
        )

        self.assertEqual(resultado.state, "AWAITING_PO")
        self.assertEqual(resultado.validations["scope"], "PASS")
        self.assertEqual(resultado.validations["time"], "PASS")
        self.assertEqual(resultado.validations["cost"], "PASS")
        self.assertEqual(resultado.validations["audit"], "PASS")
        self.assertIsNone(resultado.human_decision)
        self.assertIsNotNone(resultado.ruc_ref)

        # Verifica arquivo de auditoria append-only
        eventos = self.auditoria.ler_eventos("run-teste-sucesso-1")
        estados = [e["estado_posterior"] for e in eventos]
        esperados = ["DISCOVERED", "PROPOSED", "AWAITING_AUTH", "PREFLIGHT_OK", "CLAIMED", "RUNNING", "EVIDENCE_PENDING", "AWAITING_PO"]
        self.assertEqual(estados, esperados)

    def test_bloqueio_por_contrato_invalido(self) -> None:
        """Garante que contrato inválido resulte em transição para BLOCKED."""
        payload_ruim = dict(self.payload_missao)
        payload_ruim["schema"] = "invalido"

        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria)
        resultado = supervisor.processar_ciclo(payload_missao=payload_ruim)

        self.assertEqual(resultado.state, "BLOCKED")

    def test_bloqueio_por_autorizacao_invalida(self) -> None:
        """Garante que autorização com SHA divergente resulte em BLOCKED."""
        auth_falsa = ContratoAutorizacao(
            approval_type="CH2_RUN_APPROVAL",
            issue_ref="24",
            mission_digest="digest_incompativel",
            baseline_sha="0000000000000000000000000000000000000000",
            authorized_executor="fake",
            authorized_repo="hallanbrito/CHDevFlow",
            approved_by="hallanbrito",
            approved_at="2026-10-19T20:00:00Z",
            event_id="evt-falso",
            is_simulation=True,
        )
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria)
        resultado = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=auth_falsa,
        )
        self.assertEqual(resultado.state, "BLOCKED")

    def test_simulacao_timeout_do_worker(self) -> None:
        """Valida que status TIMED_OUT do worker resulte no estado seguro TIMED_OUT."""
        auth = self._criar_autorizacao_simulada(self.payload_missao)
        worker = FakeWorker(modo_simulacao="TIMEOUT")
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria, worker=worker)

        resultado = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=auth,
            run_id_fornecido="run-timeout-1",
        )
        self.assertEqual(resultado.state, "TIMED_OUT")
        self.assertEqual(resultado.validations["time"], "FALHOU")

    def test_simulacao_cancelamento_manual(self) -> None:
        """Valida que parada manual solicitada pelo operador resulte em CANCELLED."""
        auth = self._criar_autorizacao_simulada(self.payload_missao)
        worker = FakeWorker(modo_simulacao="CANCELADO")
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria, worker=worker)

        resultado = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=auth,
            run_id_fornecido="run-cancel-1",
        )
        self.assertEqual(resultado.state, "CANCELLED")

    def test_simulacao_falha_do_worker(self) -> None:
        """Valida que falha reportada pelo worker resulte em BLOCKED."""
        auth = self._criar_autorizacao_simulada(self.payload_missao)
        worker = FakeWorker(modo_simulacao="FALHA")
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria, worker=worker)

        resultado = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=auth,
            run_id_fornecido="run-falha-1",
        )
        self.assertEqual(resultado.state, "BLOCKED")

    def test_idempotencia_na_repeticao_da_mesma_missao(self) -> None:
        """Garante que a repetição imediata da mesma missão e tentativa seja impedida por violação de idempotência."""
        auth = self._criar_autorizacao_simulada(self.payload_missao)
        worker = FakeWorker(modo_simulacao="SUCESSO")
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria, worker=worker)

        # Primeira execução conclui com sucesso
        res1 = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=auth,
            run_id_fornecido="run-idemp-1",
        )
        self.assertEqual(res1.state, "AWAITING_PO")

        # Segunda tentativa com o mesmo payload e tentativa deve ser bloqueada no checkpoint
        res2 = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=auth,
            run_id_fornecido="run-idemp-2",
        )
        self.assertEqual(res2.state, "BLOCKED")

    def test_auditoria_incremental_sem_sobrescrita(self) -> None:
        """Valida que múltiplos eventos acumulam no JSONL sem sobrescrever o conteúdo anterior."""
        auth = self._criar_autorizacao_simulada(self.payload_missao)
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria)

        # Execução 1
        supervisor.processar_ciclo(self.payload_missao, autorizacao=None, run_id_fornecido="run-audit-1")
        total_eventos_1 = len(self.auditoria.ler_eventos())

        # Execução 2
        supervisor.processar_ciclo(self.payload_missao, autorizacao=None, run_id_fornecido="run-audit-2")
        total_eventos_2 = len(self.auditoria.ler_eventos())

        self.assertGreater(total_eventos_2, total_eventos_1)


if __name__ == "__main__":
    unittest.main()
