"""Testes unitários dos Contratos de Missão, Autorização e Resultado.

Verifica conformidade estrita com schemas, imutabilidade, cálculo de digest,
detecção de contratos adulterados e rejeição de divergências.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ch_sentinela.contracts import (
    ContratoAutorizacao,
    ContratoInvalidoErro,
    ContratoMissao,
    calcular_digest_sha256,
    serializar_json_canonico,
    validar_contrato_missao,
)
from ch_sentinela.security.policies import ViolacaoPoliticaSegurancaErro


class TestesContratos(unittest.TestCase):
    """Bateria de testes dos contratos canônicos da Sentinela."""

    def setUp(self) -> None:
        """Carrega a fixture de missão válida."""
        caminho_fixture = Path(__file__).resolve().parent / "fixtures" / "missao_valida.json"
        with open(caminho_fixture, "r", encoding="utf-8") as f:
            self.dados_missao_valida = json.load(f)

    def test_contrato_missao_valido(self) -> None:
        """Valida que uma missão em conformidade é aceita e tem seu digest calculado."""
        missao = validar_contrato_missao(self.dados_missao_valida)
        self.assertIsInstance(missao, ContratoMissao)
        self.assertEqual(missao.mission_id, "BOOT-01-LAB")
        self.assertEqual(len(missao.mission_digest), 64)
        self.assertEqual(missao.worker, "fake")
        self.assertEqual(missao.autonomy, "CH-0")

    def test_digest_canonico_determinismo(self) -> None:
        """Garante que a serialização canônica é determinística e a ordem das chaves não afeta o hash."""
        obj1 = {"b": 2, "a": 1, "c": [3, 2, 1]}
        obj2 = {"a": 1, "c": [3, 2, 1], "b": 2}
        self.assertEqual(serializar_json_canonico(obj1), serializar_json_canonico(obj2))
        self.assertEqual(calcular_digest_sha256(obj1), calcular_digest_sha256(obj2))

    def test_rejeicao_contrato_adulterado(self) -> None:
        """Rejeita missão cujo mission_digest não coincida com o cálculo real do payload."""
        caminho_adulterada = Path(__file__).resolve().parent / "fixtures" / "missao_adulterada.json"
        with open(caminho_adulterada, "r", encoding="utf-8") as f:
            dados_adulterados = json.load(f)

        with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
            validar_contrato_missao(dados_adulterados)
        self.assertIn("Digest da missão adulterado", str(ctx.exception))

    def test_rejeicao_repositorio_fora_da_allowlist(self) -> None:
        """Rejeita missão com repositório de destino não autorizado."""
        dados = dict(self.dados_missao_valida)
        dados["target"] = dict(dados["target"])
        dados["target"]["repository"] = "atacante/malicioso"

        with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
            validar_contrato_missao(dados)
        self.assertIn("não está na lista de permitidos", str(ctx.exception))

    def test_rejeicao_sha_baseline_invalido(self) -> None:
        """Rejeita missão com SHA de baseline curto, inexistente ou com caracteres inválidos."""
        dados = dict(self.dados_missao_valida)
        dados["target"] = dict(dados["target"])
        dados["target"]["base_sha"] = "sha_invalido_curto"

        with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
            validar_contrato_missao(dados)
        self.assertIn("SHA de baseline inválido", str(ctx.exception))

    def test_rejeicao_schema_incompativel(self) -> None:
        """Rejeita versão de schema desconhecida."""
        dados = dict(self.dados_missao_valida)
        dados["schema"] = "chdevflow.mission/999.0"

        with self.assertRaises(ContratoInvalidoErro) as ctx:
            validar_contrato_missao(dados)
        self.assertIn("Schema de missão incompatível", str(ctx.exception))

    def test_rejeicao_autonomia_invalida(self) -> None:
        """Rejeita nível de autonomia fora de CH-0, CH-1, CH-2."""
        dados = dict(self.dados_missao_valida)
        dados["autonomy"] = "CH-99"

        with self.assertRaises(ContratoInvalidoErro) as ctx:
            validar_contrato_missao(dados)
        self.assertIn("Nível de autonomia", str(ctx.exception))

    def test_validacao_autorizacao_sucesso(self) -> None:
        """Valida que uma autorização correspondente à missão passa no confronto."""
        missao = validar_contrato_missao(self.dados_missao_valida)
        autorizacao = ContratoAutorizacao(
            approval_type="CH2_RUN_APPROVAL",
            issue_ref="24",
            mission_digest=missao.mission_digest,
            baseline_sha=missao.target["base_sha"],
            authorized_executor=missao.worker,
            authorized_repo=missao.target["repository"],
            approved_by="hallanbrito",
            approved_at="2026-10-19T20:00:00Z",
            event_id="evt-12345",
            is_simulation=True,
        )
        # Não deve levantar exceção
        autorizacao.validar_contra_missao(missao)

    def test_rejeicao_autorizacao_sha_divergente(self) -> None:
        """Rejeita autorização se o SHA aprovado diferir do SHA da missão."""
        missao = validar_contrato_missao(self.dados_missao_valida)
        autorizacao = ContratoAutorizacao(
            approval_type="CH2_RUN_APPROVAL",
            issue_ref="24",
            mission_digest=missao.mission_digest,
            baseline_sha="0000000000000000000000000000000000000000",
            authorized_executor=missao.worker,
            authorized_repo=missao.target["repository"],
            approved_by="hallanbrito",
            approved_at="2026-10-19T20:00:00Z",
            event_id="evt-12345",
            is_simulation=True,
        )
        with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
            autorizacao.validar_contra_missao(missao)
        self.assertIn("Divergência de SHA de baseline", str(ctx.exception))

    def test_rejeicao_autoaprovacao_por_agente(self) -> None:
        """Garante que tentativa de aprovação assinada por agente ou bot seja vetada."""
        missao = validar_contrato_missao(self.dados_missao_valida)
        for agente_proibido in ("codex", "agy", "antigravity", "gemini-bot", "chatgpt"):
            autorizacao = ContratoAutorizacao(
                approval_type="CH2_RUN_APPROVAL",
                issue_ref="24",
                mission_digest=missao.mission_digest,
                baseline_sha=missao.target["base_sha"],
                authorized_executor=missao.worker,
                authorized_repo=missao.target["repository"],
                approved_by=agente_proibido,
                approved_at="2026-10-19T20:00:00Z",
                event_id="evt-fake",
                is_simulation=True,
            )
            with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
                autorizacao.validar_contra_missao(missao)
            self.assertIn("Tentativa de autoaprovação rejeitada", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
