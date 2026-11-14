"""Testes offline CH-PIPE-01: nenhum processo de agente é acionado."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from chdevflow.core.manual_lab_pipeline import (
    INTERFACES, inspect_lab_dossier, render_inspection,
)


def digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class ManualLabPipelineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "ORIGINAL"
        self.root.mkdir()
        self.recheck = self.root / "RECHECK-01"
        self.recheck.mkdir()
        self.original = {
            "run_id": "ORIG-01", "simulate": False,
            "etapas": {
                "agy": {"status": "SUCESSO", "exit_code": 0},
                "github": {"status": "SUCESSO"},
            },
        }
        self.recheck_data = {
            "schema": "chdevflow-poc03/v1",
            "run_id": "RECHECK-01",
            "recheck_source_run": "ORIG-01",
            "simulate": False, "erros": [], "escopo_extra": [],
            "etapas": {
                "github": {"status": "REUTILIZADO_DA_RODADA_ORIGINAL"},
                "agy": {"status": "REUTILIZADO_DA_RODADA_ORIGINAL"},
                "escopo": {"status": "PASS"}, "ast": {"status": "PASS"},
                "testes_agy": {"status": "PASS", "ok": True, "exit_code": 0},
                "aceite_independente": {"status": "PASS", "ok": True, "exit_code": 0},
                "codex": {"status": "SUCESSO", "ok": True, "exit_code": 0},
            },
            "veredito_codex": "APROVAR_LAB",
        }
        self.artifacts = {
            "resposta_agy.md": "AGY implementou uma função testável.\n",
            "alteracoes.patch": "--- /dev/null\n+++ b/src/estoque.py\n+def exemplo(): pass\n",
            "auditoria_codex.md": "**VEREDITO: APROVAR_LAB.**\n",
            "logs_testes.txt": (
                "=== testes_agy ===\nRan 13 tests in 0.001s\n\nOK\n"
                "=== aceite_independente ===\nRan 9 tests in 0.001s\n\nOK\n"
            ),
        }
        self.write_fixture()

    def write_fixture(self):
        (self.root / "execucao.json").write_text(
            json.dumps(self.original), encoding="utf-8"
        )
        (self.recheck / "execucao.json").write_text(
            json.dumps(self.recheck_data), encoding="utf-8"
        )
        for name, content in self.artifacts.items():
            (self.recheck / name).write_text(content, encoding="utf-8")
        lines = ["# Dossiê", ""]
        for name, label in (
            ("alteracoes.patch", "diff"),
            ("resposta_agy.md", "AGY"),
            ("auditoria_codex.md", "Codex"),
        ):
            lines.append(
                f"- SHA256 {label}: `{digest(self.artifacts[name].removesuffix(chr(10)))}`"
            )
        (self.recheck / "RELATORIO_COMPLETO_CH1.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def test_cadeia_recheck_consistente_aguarda_ch1(self):
        result = inspect_lab_dossier(self.recheck)
        self.assertEqual(result.state, "LAB_CONSISTENTE_AGUARDANDO_CH1", result.findings)
        self.assertEqual(result.checks["origem_agy"], "PASS")
        self.assertIn("nenhuma autorização", render_inspection(result).lower())

    def test_sem_chamada_subprocessos(self):
        with patch("subprocess.run", side_effect=AssertionError("NUNCA")):
            self.assertEqual(inspect_lab_dossier(self.recheck).state,
                             "LAB_CONSISTENTE_AGUARDANDO_CH1")

    def test_codex_negou(self):
        self.recheck_data["veredito_codex"] = "BLOQUEADO"
        self.write_fixture()
        self.assertEqual(inspect_lab_dossier(self.recheck).state, "BLOQUEADO")

    def test_codex_texto_nao_confere(self):
        self.artifacts["auditoria_codex.md"] = "VEREDITO: BLOQUEADO\n"
        self.write_fixture()
        self.assertEqual(inspect_lab_dossier(self.recheck).checks["codex"], "BLOQUEADO")

    def test_testes_falharam(self):
        self.artifacts["logs_testes.txt"] = (
            "=== testes_agy ===\nRan 13 tests in 0.001s\nFAILED (failures=1)\n"
        )
        self.write_fixture()
        self.assertEqual(inspect_lab_dossier(self.recheck).state, "BLOQUEADO")

    def test_erros_ou_escopo_extra(self):
        self.recheck_data["escopo_extra"] = ["segredo.txt"]
        self.write_fixture()
        self.assertEqual(inspect_lab_dossier(self.recheck).state, "BLOQUEADO")

    def test_recheck_sem_agy_original(self):
        self.original["etapas"]["agy"]["status"] = "FALHOU"
        self.write_fixture()
        self.assertEqual(inspect_lab_dossier(self.recheck).checks["origem_agy"], "BLOQUEADO")

    def test_hash_de_artefato_adulterado(self):
        self.write_fixture()
        with (self.recheck / "alteracoes.patch").open("a", encoding="utf-8") as f:
            f.write("+pass\n")
        self.assertEqual(inspect_lab_dossier(self.recheck).checks["hash_diff"], "BLOQUEADO")

    def test_arquivo_ausente(self):
        (self.recheck / "auditoria_codex.md").unlink()
        self.assertEqual(inspect_lab_dossier(self.recheck).state, "BLOQUEADO")

    def test_windows_crlf_consistente(self):
        # Path.write_text no Windows pode converter LF -> CRLF.
        for name in (
            "resposta_agy.md", "auditoria_codex.md", "alteracoes.patch",
            "logs_testes.txt", "RELATORIO_COMPLETO_CH1.md",
        ):
            p = self.recheck / name
            p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        result = inspect_lab_dossier(self.recheck)
        self.assertEqual(result.state, "LAB_CONSISTENTE_AGUARDANDO_CH1", result.findings)

    def test_metadados_malformados_bloqueados_sem_traceback(self):
        self.recheck_data["etapas"]["codex"] = None
        self.write_fixture()
        self.assertEqual(inspect_lab_dossier(self.recheck).state, "BLOQUEADO")

    def test_simulacao_nao_passa(self):
        self.recheck_data["simulate"] = True
        self.write_fixture()
        self.assertEqual(inspect_lab_dossier(self.recheck).state, "BLOQUEADO")

    def test_symlink_de_artefato_bloqueado(self):
        p = self.recheck / "auditoria_codex.md"
        p.unlink()
        try:
            p.symlink_to(self.root / "execucao.json")
        except (NotImplementedError, OSError):
            self.skipTest("Symlink indisponível neste host")
        self.assertEqual(inspect_lab_dossier(self.recheck).state, "BLOQUEADO")

    def test_interface_declarativa_sem_execucao(self):
        self.assertEqual([i.agent for i in INTERFACES], ["agy", "codex"])
        self.assertTrue(INTERFACES[1].read_only)
        self.assertFalse(hasattr(INTERFACES[0], "execute"))


if __name__ == "__main__":
    unittest.main()
