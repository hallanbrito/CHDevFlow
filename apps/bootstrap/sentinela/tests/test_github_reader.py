"""Testes unitários do leitor GitHub (LeitorGitHub).

Cobre consultas somente leitura, validação de repositório, detecção de JSON malformado,
bloqueio de subcomandos mutáveis e simulação de falhas de rede.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ch_sentinela.github_reader import (
    LeitorGitHub,
    LeitorGitHubErro,
    executar_comando_gh,
    validar_snapshot_projeto,
)
from ch_sentinela.security.policies import ViolacaoPoliticaSegurancaErro


class TestesLeitorGitHub(unittest.TestCase):
    """Testes de conformidade e segurança do leitor GitHub."""

    def setUp(self) -> None:
        """Carrega fixtures para testes offline."""
        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        with open(fixtures_dir / "issue_valida.json", "r", encoding="utf-8") as f:
            self.fixture_issue = json.load(f)
        with open(fixtures_dir / "projeto_snapshot_valido.json", "r", encoding="utf-8") as f:
            self.fixture_projeto = json.load(f)
        with open(fixtures_dir / "projeto_snapshot_incompleto.json", "r", encoding="utf-8") as f:
            self.fixture_incompleto = json.load(f)

    def test_leitura_issue_sucesso_com_mock(self) -> None:
        """Valida leitura estruturada de Issue usando provedor mock."""
        def mock_executor(args: list[str]) -> str:
            self.assertIn("view", args)
            self.assertIn("24", args)
            return json.dumps(self.fixture_issue)

        leitor = LeitorGitHub(executor_customizado=mock_executor)
        dados = leitor.obter_issue(24)
        self.assertEqual(dados["number"], 24)
        self.assertEqual(dados["state"], "OPEN")
        self.assertIn("ch:workflow", dados["labels"])

    def test_bloqueio_operacao_mutavel(self) -> None:
        """Garante que subcomandos de escrita/mutação levantem violação de segurança imediata."""
        subcomandos_proibidos = ["item-edit", "create", "close", "merge", "push", "--apply", "--apply-plan"]
        for subcmd in subcomandos_proibidos:
            with self.assertRaises(ViolacaoPoliticaSegurancaErro) as ctx:
                executar_comando_gh(["issue", subcmd, "24"])
            self.assertIn("Tentativa de operação mutável bloqueada", str(ctx.exception))

    def test_rejeicao_repositorio_nao_autorizado(self) -> None:
        """Rejeita consultas a repositórios externos à allowlist."""
        with self.assertRaises(ViolacaoPoliticaSegurancaErro):
            LeitorGitHub(repositorio_padrao="outro_usuario/outro_repo")

    def test_rejeicao_numero_issue_invalido(self) -> None:
        """Rejeita números de Issue não inteiros ou não positivos."""
        leitor = LeitorGitHub(executor_customizado=lambda args: "{}")
        with self.assertRaises(ViolacaoPoliticaSegurancaErro):
            leitor.obter_issue(-1)
        with self.assertRaises(ViolacaoPoliticaSegurancaErro):
            leitor.obter_issue(0)

    def test_rejeicao_json_malformado(self) -> None:
        """Detecta e reporta adequadamente quando o retorno não é JSON válido."""
        leitor = LeitorGitHub(executor_customizado=lambda args: "Texto corrompido, não é JSON {")
        with self.assertRaises(LeitorGitHubErro) as ctx:
            leitor.obter_issue(24)
        self.assertIn("não é um JSON válido", str(ctx.exception))

    def test_rejeicao_project_incompleto(self) -> None:
        """Rejeita snapshot do Project onde totalCount difere da quantidade de items."""
        leitor = LeitorGitHub(executor_customizado=lambda args: json.dumps(self.fixture_incompleto))
        with self.assertRaises(LeitorGitHubErro) as ctx:
            leitor.listar_itens_projeto()
        self.assertIn("Project incompleto", str(ctx.exception))

    def test_simulacao_falha_de_rede(self) -> None:
        """Simula exceção de rede/comunicação e valida tratamento gracioso."""
        def mock_falha(args: list[str]) -> str:
            raise LeitorGitHubErro("error connecting to api.github.com: rede indisponível")

        leitor = LeitorGitHub(executor_customizado=mock_falha)
        with self.assertRaises(LeitorGitHubErro) as ctx:
            leitor.obter_issue(24)
        self.assertIn("rede indisponível", str(ctx.exception))

    def test_sanitizacao_de_credenciais_em_erro(self) -> None:
        """Garante que tokens do GitHub presentes em mensagens de erro sejam mascarados."""
        def mock_com_token(args: list[str]) -> str:
            raise LeitorGitHubErro("Erro com token ghp_1234567890abcdefghijklmnopqrstuvwxyz no log.")

        leitor = LeitorGitHub(executor_customizado=mock_com_token)
        with self.assertRaises(LeitorGitHubErro) as ctx:
            leitor.obter_issue(24)
        self.assertNotIn("ghp_1234567890", str(ctx.exception))

    def test_validar_snapshot_projeto_sucesso(self) -> None:
        """AUD-02: Snapshot estruturalmente íntegro e consistente passa sem exceções."""
        # Não deve levantar exceção
        validar_snapshot_projeto(self.fixture_projeto)

    def test_validar_snapshot_projeto_nao_dicionario(self) -> None:
        """AUD-02: Snapshot que não seja dicionário levanta LeitorGitHubErro."""
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto(["item_na_lista"])
        self.assertIn("esperado objeto JSON (dict)", str(ctx.exception))

    def test_validar_snapshot_projeto_sem_items(self) -> None:
        """AUD-02: Snapshot sem chave 'items' levanta LeitorGitHubErro."""
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto({"totalCount": 0})
        self.assertIn("campo 'items' ausente", str(ctx.exception))

    def test_validar_snapshot_projeto_items_nao_lista(self) -> None:
        """AUD-02: Snapshot onde 'items' não é lista levanta LeitorGitHubErro."""
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto({"items": "não_é_lista", "totalCount": 1})
        self.assertIn("campo 'items' deve ser uma lista", str(ctx.exception))

    def test_validar_snapshot_projeto_sem_totalcount(self) -> None:
        """AUD-02: Snapshot sem chave 'totalCount' levanta LeitorGitHubErro."""
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto({"items": []})
        self.assertIn("campo 'totalCount' ausente", str(ctx.exception))

    def test_validar_snapshot_projeto_totalcount_invalido(self) -> None:
        """AUD-02: Snapshot com totalCount não-inteiro, booleano ou negativo levanta LeitorGitHubErro."""
        # Booleano (em Python, isinstance(True, int) é True, mas deve ser rejeitado)
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto({"items": [{}], "totalCount": True})
        self.assertIn("campo 'totalCount' deve ser um inteiro", str(ctx.exception))

        # Float
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto({"items": [], "totalCount": 0.0})
        self.assertIn("campo 'totalCount' deve ser um inteiro", str(ctx.exception))

        # String
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto({"items": [], "totalCount": "0"})
        self.assertIn("campo 'totalCount' deve ser um inteiro", str(ctx.exception))

        # Negativo
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto({"items": [], "totalCount": -1})
        self.assertIn("não pode ser negativo", str(ctx.exception))

    def test_validar_snapshot_projeto_contagem_divergente(self) -> None:
        """AUD-02: Snapshot onde totalCount difere de len(items) levanta LeitorGitHubErro."""
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto(self.fixture_incompleto)
        self.assertIn("Project incompleto", str(ctx.exception))

    def test_validar_snapshot_projeto_excede_limite_maximo(self) -> None:
        """AUD-02: Snapshot com totalCount superior ao limite MAXIMO_ITEMS_PROJECT levanta LeitorGitHubErro."""
        snapshot_gigante = {"totalCount": 501, "items": [{}] * 501}
        with self.assertRaises(LeitorGitHubErro) as ctx:
            validar_snapshot_projeto(snapshot_gigante)
        self.assertIn("excede limite seguro de leitura", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
