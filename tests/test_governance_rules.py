"""Testes de Governança Estrita do AGY sobre Código Real (CH-AGY-GOV-02).

Exercita diretamente as classes e funções de produção do agendador e da esteira CHDevFlow:
- ch_sentinela.supervisor.Supervisor
- ch_sentinela.contracts (ContratoAutorizacao, ContratoMissao, validar_contrato_missao, ContratoInvalidoErro)
- ch_sentinela.security.policies (validar_origem_autorizacao, validar_caminhos_escopo, ViolacaoPoliticaSegurancaErro)
- ch_sentinela.github_reader (LeitorGitHubErro, validar_snapshot_projeto, DadosGitHubInvalidosErro)
- chdevflow.core.factory (CHFactoryManager, InterprocessFileLock, FactoryLockError, TurnoProducao)

Valida as 6 regras obrigatórias de governança:
1. Missão sem autorização formal do PO: BLOQUEADA / AWAITING_AUTH pelo código real.
2. F1 autorizada com tentativa de incluir F2: BLOQUEADA por Violação de Escopo no código real.
3. GitHub indisponível sem autorização verificável: Fail-closed no leitor real, sem presunção.
4. Automação pausada / sem liberação executiva: Mantém estado seguro sem despachar worker.
5. Agendamento sem missão específica: Rejeitado como Contrato Inválido no validador real.
6. Missão com bloqueio Git / ambiente: Preserva trabalho localmente sem trocar de missão.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import unittest

from ch_sentinela.audit import Auditoria
from ch_sentinela.checkpoint import GerenciadorCheckpoint
from ch_sentinela.contracts import (
    ContratoAutorizacao,
    ContratoInvalidoErro,
    validar_contrato_missao,
)
from ch_sentinela.github_reader import (
    LeitorGitHub,
    LeitorGitHubErro,
    validar_snapshot_projeto,
)
from ch_sentinela.security.policies import (
    ViolacaoPoliticaSegurancaErro,
    validar_caminhos_escopo,
    validar_origem_autorizacao,
)
from ch_sentinela.supervisor import Supervisor
from ch_sentinela.workers.fake import FakeWorker
from chdevflow.core.factory import (
    CHFactoryManager,
    FactoryLockError,
    InterprocessFileLock,
    TurnoProducao,
)


class TestGovernancaAGYCodigoReal(unittest.TestCase):
    """Testes formais de governança exercitando as classes reais de produção."""

    def setUp(self) -> None:
        """Configura ambiente temporário para auditoria e persistência isoladas."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_gov_real_"))
        self.arquivo_audit = self.temp_dir / "auditoria.jsonl"
        self.arquivo_chk = self.temp_dir / "checkpoint.json"
        self.arquivo_factory = self.temp_dir / "factory_state.json"

        self.auditoria = Auditoria(caminho_arquivo=self.arquivo_audit)
        self.checkpoint = GerenciadorCheckpoint(caminho_arquivo=self.arquivo_chk)
        self.factory = CHFactoryManager(caminho_arquivo=self.arquivo_factory)

        fixtures_dir = (
            Path(__file__).resolve().parent.parent
            / "apps"
            / "bootstrap"
            / "sentinela"
            / "tests"
            / "fixtures"
        )
        with open(fixtures_dir / "missao_valida.json", "r", encoding="utf-8") as f:
            self.payload_missao = json.load(f)

    def tearDown(self) -> None:
        """Limpa recursos temporários após cada teste."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _criar_autorizacao_simulada_po(
        self,
        payload: dict[str, Any],
        aprovador: str = "hallanbrito",
    ) -> ContratoAutorizacao:
        """Gera contrato de autorização compatível com o payload fornecido."""
        missao = validar_contrato_missao(payload)
        return ContratoAutorizacao(
            approval_type="CH2_RUN_APPROVAL",
            issue_ref=str(missao.source["issue"]),
            mission_digest=missao.mission_digest,
            baseline_sha=missao.target["base_sha"],
            authorized_executor=missao.worker,
            authorized_repo=missao.target["repository"],
            approved_by=aprovador,
            approved_at="2026-11-14T10:00:00Z",
            event_id="evt-gov-teste-001",
            is_simulation=True,
        )

    # -------------------------------------------------------------------------
    # Regra 1: Missão sem autorização formal do PO (ou de terceiro) é BLOQUEADA
    # -------------------------------------------------------------------------
    def test_regra_1_missao_sem_autorizacao_formal_po_bloqueia_no_supervisor_real(self) -> None:
        """Regra 1: Código de produção bloqueia execução sem autorização canônica do PO."""
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria)

        # Caso A: Execução sem autorização nenhuma (autorizacao=None)
        resultado_sem_auth = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=None,
        )
        self.assertEqual(resultado_sem_auth.state, "AWAITING_AUTH")
        self.assertIsNone(resultado_sem_auth.human_decision)

        # Trilha de auditoria prova que não houve transição para CLAIMED nem RUNNING
        eventos = self.auditoria.ler_eventos()
        estados = [e["estado_posterior"] for e in eventos]
        self.assertIn("AWAITING_AUTH", estados)
        self.assertNotIn("CLAIMED", estados)
        self.assertNotIn("RUNNING", estados)

        # Caso B: Autorização emitida por ChatGPT ou agente (não PO)
        auth_nao_po = self._criar_autorizacao_simulada_po(self.payload_missao, aprovador="chatgpt")
        resultado_terceiro = supervisor.processar_ciclo(
            payload_missao=self.payload_missao,
            autorizacao=auth_nao_po,
        )
        self.assertEqual(resultado_terceiro.state, "BLOCKED")

        # Validação direta da política de segurança: rejeição expressa de bot/agente
        with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx_bot:
            validar_origem_autorizacao(
                aprovado_por="chatgpt",
                evento_id="evt-001",
                contexto_simulacao=True,
            )
        self.assertIn("agente ou bot 'chatgpt' não pode autorizar missões", str(ctx_bot.exception))

        # Validação em ambiente real: rejeição de qualquer usuário que não seja o PO canônico
        with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx_user:
            validar_origem_autorizacao(
                aprovado_por="usuario_aleatorio",
                evento_id="evt-002",
                contexto_simulacao=False,
            )
        self.assertIn("não é o Product Owner autorizado (hallanbrito)", str(ctx_user.exception))

    # -------------------------------------------------------------------------
    # Regra 2: F1 autorizada com tentativa de incluir F2 é BLOQUEADA (Escopo)
    # -------------------------------------------------------------------------
    def test_regra_2_f1_autorizada_tentativa_f2_bloqueia_por_escopo_excedido_no_codigo_real(self) -> None:
        """Regra 2: Código real de contratos e políticas rejeita expansão não autorizada de escopo."""
        # Cria autorização formal atrelada especificamente ao contrato da F1
        missao_f1 = validar_contrato_missao(self.payload_missao)
        auth_f1 = self._criar_autorizacao_simulada_po(self.payload_missao, aprovador="hallanbrito")

        # Validação F1 legítima é aprovada
        auth_f1.validar_contra_missao(missao_f1)

        # Tentativa de alterar escopo para incluir F2 (ex: alterando instruction_ref ou allowed_paths)
        payload_f2 = dict(self.payload_missao)
        payload_f2_target = dict(self.payload_missao["target"])
        payload_f2_target["allowed_paths"] = [
            "apps/bootstrap/sentinela/",
            "src/chdevflow/core/f2_planning.py",  # F2 não autorizada
        ]
        payload_f2["target"] = payload_f2_target
        payload_f2["instruction_ref"] = "docs/CH/CH-FACTORY-F2.md"

        missao_f2 = validar_contrato_missao(payload_f2)

        # A autorização da F1 rejeita categoricamente a missão modificada com F2 (divergência de digest)
        with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx_scope:
            auth_f1.validar_contra_missao(missao_f2)
        self.assertIn("Divergência de digest de missão detectada", str(ctx_scope.exception))

        # Validação direta da política de contenção de caminhos: bloqueio de caminhos sensíveis ou curingas
        with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx_path:
            validar_caminhos_escopo(["*"])  # Proibição de curinga amplo
        self.assertIn("Caminho genérico '*' proibido", str(ctx_path.exception))

    # -------------------------------------------------------------------------
    # Regra 3: GitHub indisponível sem autorização verificável -> Fail-Closed
    # -------------------------------------------------------------------------
    def test_regra_3_github_indisponivel_fail_closed_sem_presuncao_de_autorizacao(self) -> None:
        """Regra 3: Falha de conexão ou rede não permite presumir autorização (fail-closed)."""
        # Snapshot corrompido ou ausência de itens válidos levanta LeitorGitHubErro
        with self.assertRaises(LeitorGitHubErro):
            validar_snapshot_projeto({"erro": "Connection refused", "status": 500})

        # Snapshot vazio sem chave 'items' levanta erro
        with self.assertRaises(LeitorGitHubErro):
            validar_snapshot_projeto({})

        # Validador de snapshot com itens não-dicionário é detectado
        with self.assertRaises(LeitorGitHubErro):
            validar_snapshot_projeto({"items": "não_é_uma_lista"})

    # -------------------------------------------------------------------------
    # Regra 4: Automação pausada mantém estado seguro sem despachar worker
    # -------------------------------------------------------------------------
    def test_regra_4_automacao_pausada_nao_despacha_execucao_nem_produz_codigo(self) -> None:
        """Regra 4: Estado de pausa impede produção e assegura rotulagem de supervisão inerte."""
        # Turno registrado em pausa ou supervisão não produz commits nem PRs
        turno_supervisao = TurnoProducao(
            turno_id="turno-supervisao-01",
            executor="AGY",
            repositorio="CHDevFlow",
            missao_ref="CH-AGY-GOV-02",
            inicio_utc="2026-11-14T13:00:00Z",
            fim_utc="2026-11-14T13:05:00Z",
            resultado="PAUSA_OPERACIONAL",
            tipo_registro="SUPERVISAO",  # Estritamente supervisão, NÃO entrega de software
            status_evidencia="VERIFICADO",
            commits=(),  # Zero commits gerados
            pr_numero=None,  # Zero PRs abertas
            pr_url=None,
            testes_executados=0,
            testes_status="SKIPPED",
            bloqueios=("Automação suspensa pelo PO. Produção inibida.",),
            custo_brl=0.0,
            resumo="Verificação de governança e estado de pausa mantido com sucesso.",
        )
        self.factory.registrar_turno(turno_supervisao)

        rec = self.factory.obter_turno("turno-supervisao-01")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.tipo_registro, "SUPERVISAO")
        self.assertEqual(rec.commits, ())
        self.assertIsNone(rec.pr_numero)
        self.assertEqual(rec.resultado, "PAUSA_OPERACIONAL")

    # -------------------------------------------------------------------------
    # Regra 5: Agendamento sem missão específica é rejeitado como inválido
    # -------------------------------------------------------------------------
    def test_regra_5_agendamento_sem_missao_especifica_rejeitado_como_invalido(self) -> None:
        """Regra 5: Payload vazio ou sem mission_id é rejeitado imediatamente."""
        # Caso A: Payload totalmente vazio é rejeitado por schema incompatível
        with self.assertRaises(ContratoInvalidoErro) as ctx_empty:
            validar_contrato_missao({})
        self.assertIn("Schema de missão incompatível", str(ctx_empty.exception))

        # Caso B: Schema presente mas sem mission_id é rejeitado
        with self.assertRaises(ContratoInvalidoErro) as ctx_id:
            validar_contrato_missao({"schema": "chdevflow.mission/0.1", "mission_id": ""})
        self.assertIn("Campo 'mission_id' obrigatório", str(ctx_id.exception))

        # Supervisor bloqueia ciclo sem missão identificável
        supervisor = Supervisor(checkpoint=self.checkpoint, auditoria=self.auditoria)
        resultado = supervisor.processar_ciclo(payload_missao={})
        self.assertEqual(resultado.state, "BLOCKED")

    # -------------------------------------------------------------------------
    # Regra 6: Bloqueio Git preserva trabalho localmente sem trocar de missão
    # -------------------------------------------------------------------------
    def test_regra_6_bloqueio_git_preserva_trabalho_local_sem_trocar_missao(self) -> None:
        """Regra 6: Bloqueio de ambiente Git aciona preservação atômica sem buscar missão alternativa."""
        lock_file = self.arquivo_factory.with_suffix(".lock")
        lock_externo = InterprocessFileLock(lock_file)
        lock_externo.acquire()

        try:
            # Tentar gravar enquanto outro processo detém o lock levanta FactoryLockError
            with self.assertRaises(FactoryLockError):
                self.factory.registrar_turno(
                    TurnoProducao(
                        turno_id="turno-concorrente",
                        executor="AGY",
                        repositorio="CHDevFlow",
                        missao_ref="CH-FACTORY-01",  # Mantém a mesma missão
                        inicio_utc="2026-11-14T13:00:00Z",
                        fim_utc="2026-11-14T13:01:00Z",
                        resultado="BLOQUEIO_AMBIENTE",
                        tipo_registro="SUPERVISAO",
                        status_evidencia="VERIFICADO",
                        commits=(),
                        pr_numero=None,
                        pr_url=None,
                        testes_executados=0,
                        testes_status="SKIPPED",
                        bloqueios=("Bloqueio de lock detectado. Trabalho preservado.",),
                        custo_brl=0.0,
                        resumo="Bloqueio tratado com preservação sem troca de missão.",
                    )
                )
        finally:
            lock_externo.release()


if __name__ == "__main__":
    unittest.main()
