"""Testes unitários e de integração offline da Supervisão Horária da Esteira Peão (CH-AUTO-02)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
SENTINELA_PATH = REPO_ROOT / "apps" / "bootstrap" / "sentinela" / "src"
for p in (SRC_PATH, SENTINELA_PATH):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from ch_sentinela.contracts import ContratoAutorizacao
from chdevflow.cli import main as cli_main
from chdevflow.core.project_export import ProjectExportError
from chdevflow.core.supervisor_peao import (
    HourlySupervisor,
    HourlySupervisorLock,
    SupervisorConfig,
    SupervisorLockError,
    carregar_configuracao_supervisor,
)


def criar_cartao_base(
    numero: int = 42,
    esteira: str = "AGY",
    etapa: str = "PRONTA",
    status: str = "Todo",
    prioridade: str = "P1",
    risco: str = "BAIXO",
    autonomia: str = "CH-2",
    decisao_po: str = "APROVADO",
    labels: list[str] | None = None,
    repo: str = "hallanbrito/CHDevFlow",
) -> dict:
    """Cria um cartão de teste com todos os campos estruturados."""
    return {
        "card_id": f"PVTI_card_{numero:04d}",
        "number": numero,
        "title": f"Missão de teste #{numero}",
        "repository": repo,
        "esteira": esteira,
        "etapa_ch": etapa,
        "status": status,
        "prioridade_ch": prioridade,
        "risco_ch": risco,
        "autonomia_ch": autonomia,
        "decisao_po": decisao_po,
        "labels": labels or ["ch:workflow", "ch:agy"],
    }


def criar_autorizacao_valida(issue_number: int = 42) -> ContratoAutorizacao:
    return ContratoAutorizacao(
        approval_type="CH2_RUN_APPROVAL",
        issue_ref=str(issue_number),
        mission_digest="a" * 64,
        baseline_sha="aa26fa1c00000000000000000000000000000000",
        authorized_executor="agy_print",
        authorized_repo="hallanbrito/CHDevFlow",
        approved_by="hallanbrito",
        approved_at="2026-11-13T12:00:00Z",
        event_id=f"fixture:comment-{issue_number}",
        is_simulation=True,
    )


class TestSupervisorPeao(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_sup_peao_"))
        self.lock_file = self.temp_dir / "test.lock"
        self.checkpoint_file = self.temp_dir / "checkpoint.json"
        self.audit_file = self.temp_dir / "audit.jsonl"
        self.config = SupervisorConfig(
            enabled=False,
            dry_run=True,
            interval_minutes=60,
            data_dir=self.temp_dir,
            lock_file=self.lock_file,
            checkpoint_file=self.checkpoint_file,
            audit_file=self.audit_file,
        )
        self.supervisor = HourlySupervisor(config=self.config)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_architecture_inspection_and_disabled_by_default(self) -> None:
        """Critério 4 e 6: Configuração desativada por padrão e intervalo de 60 minutos."""
        cfg = SupervisorConfig()
        self.assertFalse(cfg.enabled, "A execução autônoma deve estar DESATIVADA por padrão")
        self.assertTrue(cfg.dry_run, "O modo dry-run deve estar ATIVO por padrão")
        self.assertEqual(cfg.interval_minutes, 60, "O intervalo horário deve ser de 60 minutos")
        self.assertEqual(cfg.max_parallel, 1, "Concorrência máxima deve ser estritamente 1")
        self.assertEqual(cfg.extra_cost_allowed_brl, 0.0, "Custo adicional permitido deve ser estritamente R$ 0")

    def test_02_project_inaccessible_fails_closed_bloqueado_dados(self) -> None:
        """Regra de Segurança: Falha no Project #2 resulta em BLOQUEADO_DADOS sem aproximações."""
        with patch.object(
            self.supervisor,
            "_obter_dados_projeto",
            side_effect=RuntimeError("BLOQUEADO_DADOS: Falha de autenticação gh"),
        ):
            report = self.supervisor.executar_ciclo()
            self.assertEqual(report.raw_status, "BLOQUEADO_DADOS")
            self.assertEqual(report.snapshot_id, "BLOQUEADO_DADOS")
            self.assertIn("BLOQUEADO_DADOS", report.risks_and_blockers[0])
            self.assertFalse(report.eligible_missions)
            self.assertIsNone(report.selected_mission)

    def test_03_lane_filtering_only_agy(self) -> None:
        """Regra: Selecionar somente itens comprovadamente pertencentes à Esteira AGY/Peão."""
        cards = [
            criar_cartao_base(numero=1, esteira="ChatGPT"),
            criar_cartao_base(numero=2, esteira="Codex"),
            criar_cartao_base(numero=3, esteira="Hallan"),
            criar_cartao_base(numero=4, esteira="AGY"),
        ]
        snapshot = {
            "snapshot_sha256": "sha_snap_01",
            "source": "FIXTURE_TEST",
            "items": cards,
        }
        approvals = {4: criar_autorizacao_valida(4)}
        report = self.supervisor.executar_ciclo(
            snapshot_override=snapshot,
            approval_fixtures=approvals,
        )
        self.assertEqual(report.total_cards_identified, 4)
        self.assertEqual(report.peao_cards_count, 1)
        self.assertEqual(report.selected_mission, 4)

    def test_04_no_inference_from_labels(self) -> None:
        """Regra de Segurança: Não inferir campos do Project a partir de labels ou Issues."""
        # Cartão com label ch:agy, mas Esteira = ChatGPT ou NÃO_OBSERVADO
        card1 = criar_cartao_base(numero=10, esteira="ChatGPT", labels=["ch:workflow", "ch:agy"])
        card2 = criar_cartao_base(numero=11, esteira="NÃO_OBSERVADO", labels=["ch:workflow", "ch:agy"])
        snapshot = {
            "snapshot_sha256": "sha_snap_02",
            "source": "FIXTURE_TEST",
            "items": [card1, card2],
        }
        report = self.supervisor.executar_ciclo(snapshot_override=snapshot)
        self.assertEqual(report.peao_cards_count, 0)
        self.assertEqual(len(report.eligible_missions), 0)
        self.assertIsNone(report.selected_mission)

    def test_05_missing_canonical_fields_blocked(self) -> None:
        """Política fail-closed: qualquer informação ausente ou inconsistente bloqueia a missão."""
        card_incompleto = criar_cartao_base(
            numero=20,
            esteira="AGY",
            prioridade="NÃO_OBSERVADO",  # Campo ausente
            autonomia="NÃO_OBSERVADO",
        )
        snapshot = {
            "snapshot_sha256": "sha_snap_03",
            "source": "FIXTURE_TEST",
            "items": [card_incompleto],
        }
        report = self.supervisor.executar_ciclo(snapshot_override=snapshot)
        self.assertEqual(report.peao_cards_count, 1)
        self.assertEqual(len(report.eligible_missions), 0)
        self.assertTrue(any("BLOQUEADO_DADOS" in b["reason"] for b in report.blocked_missions))

    def test_06_kanban_visual_stage_does_not_authorize(self) -> None:
        """Regra: Nenhum campo visual do Kanban, isoladamente, constitui autorização."""
        # Cartão marcado como PRONTA ou HOMOLOGADA, mas Decisao PO = PENDENTE
        card_pronta = criar_cartao_base(numero=30, etapa="PRONTA", decisao_po="PENDENTE")
        card_homologada = criar_cartao_base(numero=31, etapa="HOMOLOGADA", decisao_po="PENDENTE")
        snapshot = {
            "snapshot_sha256": "sha_snap_04",
            "source": "FIXTURE_TEST",
            "items": [card_pronta, card_homologada],
        }
        report = self.supervisor.executar_ciclo(snapshot_override=snapshot)
        self.assertEqual(len(report.eligible_missions), 0)
        self.assertIsNone(report.selected_mission)
        self.assertEqual(report.next_responsible, "PO")
        self.assertTrue(all("AGUARDANDO_PO" in b["reason"] or "ETAPA_INATIVA" in b["reason"] for b in report.blocked_missions))

    def test_07_cost_block_when_not_verified_or_exceeding_zero(self) -> None:
        """Regra de Segurança: Não usar APIs pagas nem gerar custo incremental sem autorização."""
        card = criar_cartao_base(numero=40)
        auth = criar_autorizacao_valida(40)
        # Injeta custo incremental não autorizado
        object.__setattr__(auth, "cost", {"currency": "BRL", "additional": 10.0, "verified": True})
        snapshot = {
            "snapshot_sha256": "sha_snap_05",
            "source": "FIXTURE_TEST",
            "items": [card],
        }
        report = self.supervisor.executar_ciclo(
            snapshot_override=snapshot,
            approval_fixtures={40: auth},
        )
        self.assertEqual(len(report.eligible_missions), 0)
        self.assertTrue(any("BLOQUEADO_CUSTO" in b["reason"] for b in report.blocked_missions))

    def test_08_scope_block_unauthorized_repository(self) -> None:
        """Regra de Segurança: Repositório fora da allowlist é bloqueado fail-closed."""
        card = criar_cartao_base(numero=50, repo="outro_usuario/outro_repo")
        snapshot = {
            "snapshot_sha256": "sha_snap_06",
            "source": "FIXTURE_TEST",
            "items": [card],
        }
        report = self.supervisor.executar_ciclo(
            snapshot_override=snapshot,
            approval_fixtures={50: criar_autorizacao_valida(50)},
        )
        self.assertEqual(len(report.eligible_missions), 0)
        self.assertTrue(any("REPOSITORIO_NAO_AUTORIZADO" in b["reason"] for b in report.blocked_missions))

    def test_09_sequential_queue_and_single_active_execution(self) -> None:
        """Regra: Fila sequencial, ordenada por prioridade (P0 > P1) e max 1 ativa."""
        card_p1 = criar_cartao_base(numero=61, prioridade="P1")
        card_p0 = criar_cartao_base(numero=62, prioridade="P0")
        card_p2 = criar_cartao_base(numero=63, prioridade="P2")
        snapshot = {
            "snapshot_sha256": "sha_snap_07",
            "source": "FIXTURE_TEST",
            "items": [card_p1, card_p2, card_p0],
        }
        approvals = {
            61: criar_autorizacao_valida(61),
            62: criar_autorizacao_valida(62),
            63: criar_autorizacao_valida(63),
        }
        report = self.supervisor.executar_ciclo(
            snapshot_override=snapshot,
            approval_fixtures=approvals,
        )
        self.assertEqual(report.eligible_missions, [62, 61, 63])
        self.assertEqual(report.selected_mission, 62, "A missão P0 deve ser a selecionada como prioridade mais alta")

    def test_10_lock_prevents_cycle_overlap(self) -> None:
        """Critério 4: Lock para evitar sobreposição de ciclos."""
        # Cria um lock manual ativo simulando um ciclo em andamento
        with HourlySupervisorLock(self.lock_file):
            # Outro ciclo tenta executar simultaneamente
            report = self.supervisor.executar_ciclo()
            self.assertEqual(report.raw_status, "CYCLE_OVERLAP_PREVENTED")
            self.assertTrue(any("sobreposição" in b["reason"].lower() or "bloqueio" in report.ci_status.lower() for b in report.blocked_missions))

    def test_11_idempotency_and_reprocessing_protection(self) -> None:
        """Critério 4: Persistência de checkpoint e proteção contra reprocessamento."""
        card = criar_cartao_base(numero=70)
        snapshot = {
            "snapshot_sha256": "sha_snap_08",
            "source": "FIXTURE_TEST",
            "items": [card],
        }
        approvals = {70: criar_autorizacao_valida(70)}

        # Simula uma execução já em andamento no checkpoint
        self.supervisor.checkpoint_mgr.reivindicar_execucao(
            run_id="run-70-active",
            mission_id="ISSUE-70",
            mission_digest="digest70",
            tentativa=1,
        )

        report = self.supervisor.executar_ciclo(
            snapshot_override=snapshot,
            approval_fixtures=approvals,
        )
        self.assertEqual(len(report.eligible_missions), 0)
        self.assertTrue(any("CONCORRENCIA" in b["reason"] for b in report.blocked_missions))

    def test_12_proves_zero_agent_subprocess_execution(self) -> None:
        """Critério 6: Testes comprovam ausência de execução real de agentes."""
        card = criar_cartao_base(numero=80)
        snapshot = {
            "snapshot_sha256": "sha_snap_09",
            "source": "FIXTURE_TEST",
            "items": [card],
        }
        approvals = {80: criar_autorizacao_valida(80)}

        with patch("subprocess.Popen") as mock_popen, patch("subprocess.run") as mock_run:
            report = self.supervisor.executar_ciclo(
                snapshot_override=snapshot,
                approval_fixtures=approvals,
            )
            # Garante que nenhum processo de agente foi disparado
            mock_popen.assert_not_called()
            for call in mock_run.call_args_list:
                args = call[0][0] if call[0] else []
                for proibido in ("agy", "codex", "claude"):
                    self.assertNotIn(proibido, args)
            self.assertEqual(report.selected_mission, 80)
            self.assertEqual(report.raw_status, "IMPLEMENTADO_NAO_ATIVADO")

    def test_13_standardized_report_format(self) -> None:
        """Critério 5 e 6: Relatório estruturado no formato padronizado estrito."""
        card = criar_cartao_base(numero=90)
        snapshot = {
            "snapshot_sha256": "abc123456789def0",
            "source": "FIXTURE_TEST",
            "items": [card],
        }
        approvals = {90: criar_autorizacao_valida(90)}
        report = self.supervisor.executar_ciclo(
            snapshot_override=snapshot,
            approval_fixtures=approvals,
        )
        texto = report.format_markdown()

        # Validação linha a linha dos campos obrigatórios da Seção 5
        self.assertTrue(texto.startswith("**CHDEVFLOW — RELATÓRIO AGY**"))
        self.assertIn("- Data e horário da verificação:", texto)
        self.assertIn("- Snapshot/identificador da leitura do Project: abc123456789def0", texto)
        self.assertIn("- Quantidade de cartões identificados: 1 (Esteira Peão: 1)", texto)
        self.assertIn("- Missões elegíveis e bloqueadas:", texto)
        self.assertIn("- Missão selecionada e evidência de autorização: #90 |", texto)
        self.assertIn("- Branch, commit e Draft PR:", texto)
        self.assertIn("- Testes executados e resultados reais:", texto)
        self.assertIn("- CI e pendências: CI_INTEGRAL_PASS", texto)
        self.assertIn("- Custos confirmados ou não verificados: R$ 0,00", texto)
        self.assertIn("- Riscos e bloqueios:", texto)
        self.assertIn("- Próximo responsável: ChatGPT", texto)

    def test_14_summary_mode_when_unchanged(self) -> None:
        """Seção 5: Registro resumido quando não há tarefas pendentes ou alterações."""
        snapshot = {
            "snapshot_sha256": "snap_vazio",
            "source": "FIXTURE_TEST",
            "items": [],
        }
        report = self.supervisor.executar_ciclo(snapshot_override=snapshot)
        self.assertTrue(report.is_summary_only)
        summary = report.format_summary()
        self.assertIn("[CHDEVFLOW-PEAO-SUPERVISOR]", summary)
        self.assertIn("snap_vazio", summary)

    def test_15_cli_supervise_dry_run_with_fixtures(self) -> None:
        """Valida execução do comando CLI 'ch supervise --once --dry-run'."""
        fixture_path = self.temp_dir / "fixture_snapshot.json"
        card = criar_cartao_base(numero=99, etapa="PRONTA", decisao_po="PENDENTE")
        fixture_path.write_text(
            json.dumps({
                "snapshot_sha256": "sha_cli_test_99",
                "source": "FIXTURE_CLI",
                "items": [card],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        out_report = self.temp_dir / "relatorio_cli.md"

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cli_main([
                "supervise",
                "--once",
                "--dry-run",
                "--fixture",
                str(fixture_path),
                "--output-report",
                str(out_report),
            ])

        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("**CHDEVFLOW — RELATÓRIO AGY**", output)
        self.assertTrue(out_report.exists())
        self.assertIn("**CHDEVFLOW — RELATÓRIO AGY**", out_report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
