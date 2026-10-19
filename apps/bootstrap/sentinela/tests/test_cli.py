"""Testes unitários da Interface de Linha de Comando (CLI).

Cobre a execução dos comandos:
- ch-sentinela --help
- ch-sentinela watch --once --dry-run
- ch-sentinela demo --fake-worker
- ch-sentinela status
- ch-sentinela report
"""
from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from unittest.mock import patch

from ch_sentinela.audit import Auditoria
from ch_sentinela.cli import main
from ch_sentinela.github_reader import LeitorGitHubErro


class TestesCLI(unittest.TestCase):
    """Testes dos comandos da CLI da Sentinela."""

    def setUp(self) -> None:
        """Cria diretório temporário para isolar os dados durante a execução da CLI."""
        self.temp_dir = tempfile.mkdtemp(prefix="test_cli_")
        import os
        self.antigo_env = os.environ.get("CH_SENTINELA_DATA_DIR")
        os.environ["CH_SENTINELA_DATA_DIR"] = self.temp_dir

    def tearDown(self) -> None:
        """Restaura variáveis de ambiente e limpa arquivos temporários."""
        import os
        if self.antigo_env is not None:
            os.environ["CH_SENTINELA_DATA_DIR"] = self.antigo_env
        else:
            os.environ.pop("CH_SENTINELA_DATA_DIR", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_ajuda(self) -> None:
        """Valida que o comando com --help ou sem argumentos exibe a mensagem de ajuda."""
        # Teste 1: sem argumentos imprime ajuda e retorna 0
        f1 = io.StringIO()
        with redirect_stdout(f1):
            codigo = main([])
        self.assertEqual(codigo, 0)
        saida1 = f1.getvalue()
        self.assertIn("ch-sentinela", saida1)
        self.assertIn("watch", saida1)

        # Teste 2: --help sai com SystemExit código 0
        f2 = io.StringIO()
        with redirect_stdout(f2):
            with self.assertRaises(SystemExit) as cm:
                main(["--help"])
            self.assertEqual(cm.exception.code, 0)

    def test_cli_watch_once_dry_run_com_fixture(self) -> None:
        """Valida execução de 'watch --once --dry-run' utilizando fixture de teste."""
        caminho_fixture = str(Path(__file__).resolve().parent / "fixtures" / "projeto_snapshot_valido.json")
        f = io.StringIO()
        with redirect_stdout(f):
            codigo = main(["watch", "--once", "--dry-run", "--fixture", caminho_fixture])
        self.assertEqual(codigo, 0)
        saida = f.getvalue()
        self.assertIn("Sentinela Python", saida)
        self.assertIn("Tarefas observadas: 2", saida)
        self.assertIn("Issue #24", saida)

    def test_cli_demo_fake_worker(self) -> None:
        """Valida execução da demonstração completa via 'demo --fake-worker'."""
        f = io.StringIO()
        with redirect_stdout(f):
            codigo = main(["demo", "--fake-worker"])
        self.assertEqual(codigo, 0)
        saida = f.getvalue()
        self.assertIn("ETAPA 1: Execução sem autorização do PO", saida)
        self.assertIn("AWAITING_AUTH", saida)
        self.assertIn("ETAPA 2: Ciclo supervisionado com autorização simulada de teste", saida)
        self.assertIn("AWAITING_PO", saida)

    def test_cli_status_e_report(self) -> None:
        """Valida que 'status' e 'report' funcionam corretamente após a execução do demo."""
        # Executa o demo primeiro para popular dados
        main(["demo", "--fake-worker"])

        # Testa status
        f_status = io.StringIO()
        with redirect_stdout(f_status):
            codigo_status = main(["status"])
        self.assertEqual(codigo_status, 0)
        saida_status = f_status.getvalue()
        self.assertIn("Total de execuções registradas:", saida_status)
        self.assertIn("Total de eventos de auditoria no JSONL:", saida_status)

        # Testa report
        f_report = io.StringIO()
        with redirect_stdout(f_report):
            codigo_report = main(["report"])
        self.assertEqual(codigo_report, 0)
        saida_report = f_report.getvalue()
        self.assertIn("Relatório Universal C.H. (RUC/1.0)", saida_report)
        self.assertIn("APROVADO_TECNICAMENTE", saida_report)
        self.assertIn("AWAITING_PO", saida_report)

    def test_cli_watch_fixture_inexistente_falha_fechada(self) -> None:
        """AUD-01: Garante que passar --fixture com arquivo inexistente resulta em erro (código 1)."""
        f = io.StringIO()
        with redirect_stdout(f):
            codigo = main(["watch", "--once", "--dry-run", "--fixture", "arquivo_inexistente_9999.json"])
        self.assertEqual(codigo, 1)
        saida = f.getvalue()
        self.assertIn("[ERRO CRÍTICO]", saida)
        self.assertIn("não encontrado", saida)
        self.assertIn("fail-closed", saida)
        self.assertNotIn("Tarefas observadas", saida)
        self.assertNotIn("BOOT-00", saida)

    def test_cli_watch_fixture_malformada_falha_fechada(self) -> None:
        """AUD-01: Garante que fixture com JSON corrompido resulta em erro (código 1)."""
        caminho_ruim = Path(self.temp_dir) / "fixture_corrompida.json"
        caminho_ruim.write_text("{ json invalido...", encoding="utf-8")

        f = io.StringIO()
        with redirect_stdout(f):
            codigo = main(["watch", "--once", "--dry-run", "--fixture", str(caminho_ruim)])
        self.assertEqual(codigo, 1)
        saida = f.getvalue()
        self.assertIn("[ERRO CRÍTICO]", saida)
        self.assertIn("Falha ao ler ou decodificar fixture", saida)
        self.assertNotIn("Tarefas observadas", saida)

    def test_cli_watch_fixture_sem_items_falha_fechada(self) -> None:
        """AUD-01: Garante que fixture sem campo 'items' resulta em erro (código 1)."""
        caminho_sem_items = Path(self.temp_dir) / "fixture_sem_items.json"
        caminho_sem_items.write_text('{"chave": "sem_items"}', encoding="utf-8")

        f = io.StringIO()
        with redirect_stdout(f):
            codigo = main(["watch", "--once", "--dry-run", "--fixture", str(caminho_sem_items)])
        self.assertEqual(codigo, 1)
        saida = f.getvalue()
        self.assertIn("[ERRO CRÍTICO]", saida)
        self.assertIn("Estrutura da fixture", saida)
        self.assertNotIn("Tarefas observadas", saida)

    def test_cli_watch_ao_vivo_falha_gh_retorna_erro_sem_fallback_sintetico(self) -> None:
        """AUD-01: Garante que falha de leitura ao vivo falha fechada com LIVE_GITHUB FAILED e código 1."""
        with patch("ch_sentinela.cli.LeitorGitHub.listar_itens_projeto") as mock_list:
            mock_list.side_effect = LeitorGitHubErro("Erro simulado: rede indisponível ou gh não autenticado.")

            f = io.StringIO()
            with redirect_stdout(f):
                codigo = main(["watch", "--once", "--dry-run"])

            self.assertEqual(codigo, 1)
            saida = f.getvalue()
            self.assertIn("LIVE_GITHUB FAILED", saida)
            self.assertIn("fail-closed", saida)
            self.assertNotIn("Tarefas observadas", saida)
            self.assertNotIn("DISCOVERED", saida)
            self.assertNotIn("BOOT-00", saida)

    def test_cli_watch_ao_vivo_timeout_retorna_erro_sem_fallback(self) -> None:
        """AUD-01: Garante que timeout ao vivo resulta em código 1 e não carrega fixture sintética."""
        with patch("ch_sentinela.cli.LeitorGitHub.listar_itens_projeto") as mock_list:
            mock_list.side_effect = LeitorGitHubErro("Timeout de 30s excedido ao consultar o GitHub CLI.")

            f = io.StringIO()
            with redirect_stdout(f):
                codigo = main(["watch", "--once", "--dry-run"])

            self.assertEqual(codigo, 1)
            saida = f.getvalue()
            self.assertIn("LIVE_GITHUB FAILED", saida)
            self.assertNotIn("Tarefas observadas", saida)

    def test_cli_watch_ao_vivo_sucesso_com_mock_registra_origem_live(self) -> None:
        """AUD-01: Valida que sucesso de leitura ao vivo registra explicitamente LIVE_GITHUB."""
        snapshot_valido = {
            "totalCount": 1,
            "items": [
                {
                    "content": {
                        "type": "Issue",
                        "repository": "hallanbrito/CHDevFlow",
                        "number": 24,
                        "title": "Issue do Projeto Real",
                        "url": "https://github.com/hallanbrito/CHDevFlow/issues/24",
                    },
                    "labels": ["ch:workflow"],
                }
            ],
        }
        with patch("ch_sentinela.cli.LeitorGitHub.listar_itens_projeto", return_value=snapshot_valido):
            f = io.StringIO()
            with redirect_stdout(f):
                codigo = main(["watch", "--once", "--dry-run"])

            self.assertEqual(codigo, 0)
            saida = f.getvalue()
            self.assertIn("LIVE_GITHUB", saida)
            self.assertIn("Tarefas observadas: 1", saida)
            self.assertIn("Issue #24: Issue do Projeto Real", saida)

            # Verifica que a auditoria gravou a origem LIVE_GITHUB
            auditoria = Auditoria()
            eventos = auditoria.ler_eventos()
            self.assertGreater(len(eventos), 0)
            self.assertEqual(eventos[-1]["origem_dados"], "LIVE_GITHUB")


if __name__ == "__main__":
    unittest.main()
