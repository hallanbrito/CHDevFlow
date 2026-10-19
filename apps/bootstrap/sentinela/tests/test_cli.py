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

from ch_sentinela.cli import main


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


if __name__ == "__main__":
    unittest.main()
