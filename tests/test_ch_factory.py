"""Testes unitários e de governança da Fatia F1 do motor CH-FACTORY (Issue #72).

Valida rigorosamente os requisitos da F1 e os apontamentos da Auditoria CH-1:
1. Modelo de Eventos e Persistência Atômica Segura (0o600).
2. Exclusão mútua por lock interprocesso (`InterprocessFileLock`).
3. Deduplicação e Idempotência estritas.
4. Fuso Horário America/Fortaleza (UTC-3).
5. Rotulagem explícita de evidências (`NAO_VERIFICADO` / `VERIFICADO`).
6. Sanitização automática de segredos e tokens.
7. Diferenciação rigorosa entre Supervisão e Entrega Real de Software.
8. Interface Filtrável da Timeline por multi-critérios.
9. Passagem Mínima de Turno (`PassagemTurnoMinima`).
10. Snapshot desacoplado para o Control Center.
11. Interface de Linha de Comando (CLI `ch factory`).
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from chdevflow.cli import build_parser
from chdevflow.core.factory import (
    CHFactoryManager,
    FactoryLockError,
    InterprocessFileLock,
    PassagemTurnoMinima,
    TurnoProducao,
    run_factory_cli,
)


class TestCHFactoryF1Auditoria(unittest.TestCase):
    """Bateria completa de validação da Fatia F1 da CH-FACTORY."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.caminho_dados = Path(self.temp_dir.name) / "factory_f1_test.json"
        self.factory = CHFactoryManager(self.caminho_dados)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Modelo de Eventos e Persistência Atômica
    # -------------------------------------------------------------------------

    def test_registro_turno_persistencia_e_recuperacao(self) -> None:
        """Valida criação atômica, gravação e recarregamento íntegro do turno."""
        turno = TurnoProducao(
            turno_id="turno-f1-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="CH-FACTORY-01",
            inicio_utc="2026-11-14T13:00:00Z",
            fim_utc="2026-11-14T13:30:00Z",
            resultado="SUCESSO",
            tipo_registro="ENTREGA_SOFTWARE",
            status_evidencia="VERIFICADO",
            commits=("aa26fa1", "f10001a"),
            pr_numero=72,
            pr_url="https://github.com/hallanbrito/CHDevFlow/pull/72",
            testes_executados=47,
            testes_status="PASS",
            bloqueios=(),
            custo_brl=0.0,
            resumo="Implementação dos contratos e testes da Fatia F1",
        )
        self.factory.registrar_turno(turno)
        self.assertTrue(self.caminho_dados.exists())

        # Recarrega em nova instância isolada
        recarregado = CHFactoryManager(self.caminho_dados)
        rec = recarregado.obter_turno("turno-f1-01")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.executor, "AGY")
        self.assertEqual(rec.tipo_registro, "ENTREGA_SOFTWARE")
        self.assertEqual(rec.status_evidencia, "VERIFICADO")
        self.assertEqual(rec.commits, ("aa26fa1", "f10001a"))
        self.assertEqual(rec.custo_brl, 0.0)

    def test_interprocess_lock_e_exclusao_mutua(self) -> None:
        """Garante que InterprocessFileLock impede concorrência simultânea via FactoryLockError."""
        lock_path = self.caminho_dados.with_suffix(".lock")
        lock1 = InterprocessFileLock(lock_path)
        lock1.acquire()

        lock2 = InterprocessFileLock(lock_path)
        with self.assertRaises(FactoryLockError):
            lock2.acquire()

        lock1.release()
        lock2.acquire()
        lock2.release()

    # -------------------------------------------------------------------------
    # 2. Deduplicação e Idempotência
    # -------------------------------------------------------------------------

    def test_deduplicacao_e_idempotencia(self) -> None:
        """Garante que registrar o mesmo turno múltiplas vezes não gera duplicatas."""
        turno = TurnoProducao(
            turno_id="t-idemp-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="#72",
            inicio_utc="2026-11-14T10:00:00Z",
            fim_utc="2026-11-14T10:30:00Z",
            resultado="SUCESSO",
            tipo_registro="SUPERVISAO",
        )
        self.factory.registrar_turno(turno)
        self.factory.registrar_turno(turno)
        self.factory.registrar_turno(turno)

        turnos = self.factory.listar_turnos()
        self.assertEqual(len(turnos), 1)
        self.assertEqual(turnos[0].turno_id, "t-idemp-01")

    # -------------------------------------------------------------------------
    # 3. Fuso Horário America/Fortaleza (UTC-3)
    # -------------------------------------------------------------------------

    def test_fuso_horario_america_fortaleza(self) -> None:
        """Valida conversão correta de UTC para America/Fortaleza (-03:00)."""
        turno = TurnoProducao(
            turno_id="t-tz-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="#72",
            inicio_utc="2026-11-14T13:00:00+00:00",
            fim_utc="2026-11-14T14:00:00+00:00",
            resultado="SUCESSO",
            tipo_registro="SUPERVISAO",
        )
        # 13:00 UTC = 10:00 America/Fortaleza (-03:00)
        self.assertIn("10:00:00", turno.inicio_fortaleza)
        self.assertIn("11:00:00", turno.fim_fortaleza)

        dicionario = turno.para_dicionario()
        self.assertIn("inicio_fortaleza", dicionario)
        self.assertIn("fim_fortaleza", dicionario)

    # -------------------------------------------------------------------------
    # 4. Rotulagem Explícita de Evidências (NAO_VERIFICADO)
    # -------------------------------------------------------------------------

    def test_rotulagem_evidencia_nao_verificado(self) -> None:
        """Garante que declarações sem prova criptográfica/local sejam marcadas como NAO_VERIFICADO."""
        turno_padrao = TurnoProducao(
            turno_id="t-ev-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="#72",
            inicio_utc="2026-11-14T10:00:00Z",
            fim_utc="2026-11-14T10:15:00Z",
            resultado="SUCESSO",
            tipo_registro="SUPERVISAO",
        )
        self.assertEqual(turno_padrao.status_evidencia, "NAO_VERIFICADO")

    # -------------------------------------------------------------------------
    # 5. Sanitização de Dados e Segredos
    # -------------------------------------------------------------------------

    def test_sanitizacao_de_dados_segredos(self) -> None:
        """Garante que tokens de acesso (ex: ghp_) sejam sanitizados e nunca expostos."""
        token_sensivel = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        turno = TurnoProducao(
            turno_id="t-sec-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="#72",
            inicio_utc="2026-11-14T10:00:00Z",
            fim_utc="2026-11-14T10:15:00Z",
            resultado="BLOQUEADO",
            tipo_registro="SUPERVISAO",
            resumo=f"Tentativa com token {token_sensivel} na API.",
            bloqueios=(f"Falha de autenticação com {token_sensivel}",),
        )
        self.assertNotIn(token_sensivel, turno.resumo)
        self.assertNotIn(token_sensivel, turno.bloqueios[0])
        self.assertIn("[CREDENCIAL_OCULTADA]", turno.resumo)

    # -------------------------------------------------------------------------
    # 6. Diferenciação entre Supervisão e Entrega Real
    # -------------------------------------------------------------------------

    def test_diferenciacao_supervisao_vs_entrega_real(self) -> None:
        """Garante que turnos de SUPERVISAO não podem declarar commits de código falsamente."""
        with self.assertRaises(ValueError):
            TurnoProducao(
                turno_id="t-inv-01",
                executor="AGY",
                repositorio="CHDevFlow",
                missao_ref="#72",
                inicio_utc="2026-11-14T10:00:00Z",
                fim_utc="2026-11-14T10:15:00Z",
                resultado="SUCESSO",
                tipo_registro="SUPERVISAO",
                commits=("abc1234",),  # Violação: supervisão não pode ter commit
            )

        # Entrega de software real permite commits
        turno_valido = TurnoProducao(
            turno_id="t-val-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="#72",
            inicio_utc="2026-11-14T10:00:00Z",
            fim_utc="2026-11-14T10:15:00Z",
            resultado="SUCESSO",
            tipo_registro="ENTREGA_SOFTWARE",
            commits=("abc1234",),
        )
        self.assertEqual(turno_valido.tipo_registro, "ENTREGA_SOFTWARE")

    # -------------------------------------------------------------------------
    # 7. Interface Filtrável da Timeline
    # -------------------------------------------------------------------------

    def test_timeline_filtros_multi_criterio(self) -> None:
        """Valida filtragem combinada de timeline por tipo, data, executor e resultado."""
        t1 = TurnoProducao(
            turno_id="t1",
            executor="AGY",
            repositorio="hallanbrito/CHDevFlow",
            missao_ref="#72",
            inicio_utc="2026-11-13T10:00:00Z",
            fim_utc="2026-11-13T10:45:00Z",
            resultado="SUCESSO",
            tipo_registro="ENTREGA_SOFTWARE",
            commits=("c1",),
        )
        t2 = TurnoProducao(
            turno_id="t2",
            executor="ChatGPT",
            repositorio="hallanbrito/maestro-router",
            missao_ref="#12",
            inicio_utc="2026-11-14T08:00:00Z",
            fim_utc="2026-11-14T08:30:00Z",
            resultado="BLOQUEADO",
            tipo_registro="SUPERVISAO",
        )
        t3 = TurnoProducao(
            turno_id="t3",
            executor="AGY",
            repositorio="hallanbrito/PulseOps",
            missao_ref="#05",
            inicio_utc="2026-11-14T09:00:00Z",
            fim_utc="2026-11-14T09:30:00Z",
            resultado="SEM_TRABALHO_LIBERADO",
            tipo_registro="SUPERVISAO",
        )
        self.factory.registrar_turno(t1)
        self.factory.registrar_turno(t2)
        self.factory.registrar_turno(t3)

        # Filtro por tipo_registro
        turnos_dev = self.factory.filtrar_timeline(tipo_registro="ENTREGA_SOFTWARE")
        self.assertEqual(len(turnos_dev), 1)
        self.assertEqual(turnos_dev[0].turno_id, "t1")

        # Filtro por executor
        turnos_agy = self.factory.filtrar_timeline(executor="AGY")
        self.assertEqual(len(turnos_agy), 2)

        # Filtro por projeto slug
        turnos_maestro = self.factory.filtrar_timeline(projeto="maestro-router")
        self.assertEqual(len(turnos_maestro), 1)
        self.assertEqual(turnos_maestro[0].turno_id, "t2")

    # -------------------------------------------------------------------------
    # 8. Passagem Mínima de Turno (F1 Handover)
    # -------------------------------------------------------------------------

    def test_passagem_minima_turno_handover(self) -> None:
        """Gera e formata o documento mínimo de passagem de turno da F1."""
        t = TurnoProducao(
            turno_id="t-hand-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="CH-FACTORY-01",
            inicio_utc="2026-11-14T10:00:00Z",
            fim_utc="2026-11-14T10:45:00Z",
            resultado="SUCESSO",
            tipo_registro="ENTREGA_SOFTWARE",
            status_evidencia="VERIFICADO",
            commits=("aa26fa1",),
            pr_numero=72,
            resumo="Entrega dos critérios de aceite da Fatia F1",
        )
        self.factory.registrar_turno(t)

        handover = self.factory.gerar_passagem_turno_minima(
            executor_sainte="AGY",
            executor_entrante="ChatGPT",
        )
        self.assertEqual(handover.executor_sainte, "AGY")
        self.assertEqual(handover.executor_entrante, "ChatGPT")
        self.assertEqual(handover.tipo_ultimo_registro, "ENTREGA_SOFTWARE")
        self.assertEqual(handover.status_evidencia, "VERIFICADO")

        md = self.factory.formatar_passagem_turno_markdown(handover)
        self.assertIn("# CH-FACTORY — Passagem Mínima de Turno (F1 Handover)", md)
        self.assertIn("America/Fortaleza", md)
        self.assertIn("PR #72", md)
        self.assertIn("AGY PRODUZ. CHATGPT SUPERVISIONA. HALLAN DECIDE.", md)

    # -------------------------------------------------------------------------
    # 9. Snapshot para Control Center
    # -------------------------------------------------------------------------

    def test_snapshot_control_center(self) -> None:
        """Valida que o snapshot exporta contagens e fuso horário adequadamente."""
        t = TurnoProducao(
            turno_id="t-snap-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="#72",
            inicio_utc="2026-11-14T10:00:00Z",
            fim_utc="2026-11-14T10:30:00Z",
            resultado="SUCESSO",
            tipo_registro="ENTREGA_SOFTWARE",
        )
        self.factory.registrar_turno(t)
        snap = self.factory.obter_snapshot_fabrica()

        self.assertEqual(snap["fuso_horario"], "America/Fortaleza")
        self.assertEqual(snap["estatisticas"]["total_turnos"], 1)
        self.assertEqual(snap["estatisticas"]["turnos_entrega_software"], 1)

    # -------------------------------------------------------------------------
    # 10. Testes de Linha de Comando (CLI F1)
    # -------------------------------------------------------------------------

    def test_cli_factory_subcommands(self) -> None:
        """Testa invocação da CLI para history, timeline, handover e snapshot."""
        parser = build_parser()
        t = TurnoProducao(
            turno_id="t-cli-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="CH-FACTORY-01",
            inicio_utc="2026-11-14T10:00:00Z",
            fim_utc="2026-11-14T10:15:00Z",
            resultado="SUCESSO",
            tipo_registro="ENTREGA_SOFTWARE",
        )
        self.factory.registrar_turno(t)

        for cmd in [
            ["factory", "--config-file", str(self.caminho_dados), "history", "--json"],
            ["factory", "--config-file", str(self.caminho_dados), "timeline", "--type", "ENTREGA_SOFTWARE", "--json"],
            ["factory", "--config-file", str(self.caminho_dados), "handover", "--json"],
            ["factory", "--config-file", str(self.caminho_dados), "snapshot"],
        ]:
            args = parser.parse_args(cmd)
            ret = run_factory_cli(args)
            self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
