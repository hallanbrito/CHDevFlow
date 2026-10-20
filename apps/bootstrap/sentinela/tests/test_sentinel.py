"""Testes unitários da Sentinela de Observação (Sentinela).

Verifica a observação de execução única, detecção de tarefas novas,
identificação de duplicatas, tratamento de entradas inválidas e ausência de loops.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ch_sentinela.audit import Auditoria
from ch_sentinela.github_reader import LeitorGitHub, LeitorGitHubErro
from ch_sentinela.sentinel import Sentinela


class TestesSentinela(unittest.TestCase):
    """Bateria de testes para a Sentinela."""

    def setUp(self) -> None:
        """Carrega fixtures do Project."""
        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        with open(fixtures_dir / "projeto_snapshot_valido.json", "r", encoding="utf-8") as f:
            self.snapshot_valido = json.load(f)
        with open(fixtures_dir / "projeto_snapshot_duplicado.json", "r", encoding="utf-8") as f:
            self.snapshot_duplicado = json.load(f)
        with open(fixtures_dir / "projeto_snapshot_incompleto.json", "r", encoding="utf-8") as f:
            self.snapshot_incompleto = json.load(f)

    def test_observacao_unica_sucesso(self) -> None:
        """Garante que a Sentinela reconhece tarefas elegíveis e encerra a consulta."""
        sentinela = Sentinela(leitor=LeitorGitHub(executor_customizado=lambda args: json.dumps(self.snapshot_valido)))
        eventos = sentinela.observar_uma_vez()

        self.assertEqual(len(eventos), 2)
        tipos = [e.tipo_evento for e in eventos]
        self.assertEqual(tipos, ["DISCOVERED", "DISCOVERED"])
        self.assertEqual(eventos[0].numero_issue, 24)
        self.assertEqual(eventos[1].numero_issue, 26)

    def test_deteccao_issue_duplicada(self) -> None:
        """Valida que entradas duplicadas na mesma fotografia são sinalizadas como DUPLICATE_IGNORED."""
        sentinela = Sentinela()
        eventos = sentinela.observar_uma_vez(snapshot_projeto=self.snapshot_duplicado)

        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos[0].tipo_evento, "DISCOVERED")
        self.assertEqual(eventos[1].tipo_evento, "DUPLICATE_IGNORED")
        self.assertEqual(eventos[1].numero_issue, 24)

    def test_ignorada_sem_workflow_label(self) -> None:
        """Valida que tarefas sem a etiqueta 'ch:workflow' são classificadas como NO_WORKFLOW_IGNORED."""
        snapshot = {
            "totalCount": 1,
            "items": [
                {
                    "content": {
                        "type": "Issue",
                        "repository": "hallanbrito/CHDevFlow",
                        "number": 99,
                        "title": "Issue comum sem workflow",
                        "url": "https://github.com/hallanbrito/CHDevFlow/issues/99",
                    },
                    "labels": ["bug", "documentacao"],
                }
            ],
        }
        sentinela = Sentinela()
        eventos = sentinela.observar_uma_vez(snapshot_projeto=snapshot)

        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0].tipo_evento, "NO_WORKFLOW_IGNORED")

    def test_tratamento_entradas_invalidas(self) -> None:
        """Valida tratamento seguro de itens corrompidos ou com URLs divergentes."""
        snapshot = {
            "totalCount": 2,
            "items": [
                "item_invalido_que_nao_e_dicionario",
                {
                    "content": {
                        "type": "Issue",
                        "repository": "hallanbrito/CHDevFlow",
                        "number": 10,
                        "title": "URL maliciosa",
                        "url": "https://github.com/outro/malicioso/issues/10",
                    },
                    "labels": ["ch:workflow"],
                },
            ],
        }
        sentinela = Sentinela()
        eventos = sentinela.observar_uma_vez(snapshot_projeto=snapshot)

        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos[0].tipo_evento, "INVALID_IGNORED")
        self.assertEqual(eventos[1].tipo_evento, "INVALID_IGNORED")
        self.assertIn("URL", eventos[1].detalhes)

    def test_rejeicao_snapshot_incompleto_falha_fechada(self) -> None:
        """AUD-02: Snapshot incompleto (fixture com contagem divergente) levanta LeitorGitHubErro e gera 0 eventos."""
        sentinela = Sentinela()
        with self.assertRaises(LeitorGitHubErro) as ctx:
            sentinela.observar_uma_vez(snapshot_projeto=self.snapshot_incompleto)
        self.assertIn("Project incompleto", str(ctx.exception))

    def test_rejeicao_snapshot_sem_totalcount(self) -> None:
        """AUD-02: Snapshot sem 'totalCount' levanta LeitorGitHubErro sem emitir eventos."""
        sentinela = Sentinela()
        with self.assertRaises(LeitorGitHubErro) as ctx:
            sentinela.observar_uma_vez(snapshot_projeto={"items": []})
        self.assertIn("campo 'totalCount' ausente", str(ctx.exception))

    def test_rejeicao_snapshot_items_tipo_invalido(self) -> None:
        """AUD-02: Snapshot com 'items' não-lista levanta LeitorGitHubErro sem emitir eventos."""
        sentinela = Sentinela()
        with self.assertRaises(LeitorGitHubErro) as ctx:
            sentinela.observar_uma_vez(snapshot_projeto={"totalCount": 0, "items": "invalido"})
        self.assertIn("campo 'items' deve ser uma lista", str(ctx.exception))

    def test_rejeicao_snapshot_totalcount_invalido(self) -> None:
        """AUD-02: Snapshot com 'totalCount' booleano ou negativo levanta LeitorGitHubErro."""
        sentinela = Sentinela()
        with self.assertRaises(LeitorGitHubErro) as ctx:
            sentinela.observar_uma_vez(snapshot_projeto={"totalCount": True, "items": [{}]})
        self.assertIn("campo 'totalCount' deve ser um inteiro", str(ctx.exception))

        with self.assertRaises(LeitorGitHubErro) as ctx_neg:
            sentinela.observar_uma_vez(snapshot_projeto={"totalCount": -1, "items": []})
        self.assertIn("não pode ser negativo", str(ctx_neg.exception))

    def test_rejeicao_snapshot_contagem_divergente_sem_auditoria(self) -> None:
        """AUD-02: Snapshot com divergência não gera nenhum evento na auditoria."""
        from unittest.mock import MagicMock
        auditoria_mock = MagicMock()
        sentinela = Sentinela(auditoria=auditoria_mock)

        snapshot_ruim = {
            "totalCount": 2,
            "items": [
                {
                    "content": {
                        "type": "Issue",
                        "repository": "hallanbrito/CHDevFlow",
                        "number": 24,
                        "title": "Apenas um item",
                        "url": "https://github.com/hallanbrito/CHDevFlow/issues/24",
                    },
                    "labels": ["ch:workflow"],
                }
            ],
        }
        with self.assertRaises(LeitorGitHubErro):
            sentinela.observar_uma_vez(snapshot_projeto=snapshot_ruim)

        # Garante que nenhum evento de auditoria foi registrado
        auditoria_mock.registrar_evento.assert_not_called()


if __name__ == "__main__":
    unittest.main()
