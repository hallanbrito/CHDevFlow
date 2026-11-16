"""Negativas do preflight E3-C1; nenhuma chamada a agentes/POST."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import f7_v1_preflight as gate


def lab_manifest() -> dict:
    return {
        "schema": gate.LAB_SCHEMA,
        "source_run": 43887485901,
        "source_artifact_id": 14235142079,
        "source_commit": gate.SOURCE_SHA,
        "consumer_commit": gate.E3C0_SHA,
        "consumer_run": 43888441966,
        "tar_sha256": gate.TAR_SHA,
        "image_id": gate.IMAGE_ID,
        "authorization": gate.LAB_AUTH,
        "reports": {
            "self": {"status": "SELF_CHECK_OK", "sha256": "a" * 64},
            "pass": {"status": "TESTS_PASS", "sha256": "b" * 64},
            "fail": {"status": "TESTS_FAILED", "sha256": "c" * 64},
        },
    }


class PreflightV1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "manifest.json"
        self.manifest = lab_manifest()
        self._save()

    def _save(self):
        self.path.write_text(json.dumps(self.manifest), encoding="ascii")

    def test_e3c0_prova_lab_nao_libera_agentes_ou_outbox(self):
        data = gate.classify_lab_chain(self.manifest)
        self.assertEqual(data["classification"], "LAB_ONLY_NOT_V1")
        self.assertEqual(data["state"], "BLOCKED_V1_NOT_AUTHORIZED")
        self.assertFalse(data["v1_run_created"])
        self.assertFalse(data["remote_publication_enabled"])
        self.assertIn("REAL_AGY_EXECUTION_AND_CODEX_AUDIT", data["missing_gates"])

    def test_rejeita_promocao_lab_v1_e_doc_desconhecido(self):
        for version in (gate.LAB_SCHEMA, gate.V1_SCHEMA, "random"):
            with self.subTest(version=version):
                with self.assertRaises(PermissionError):
                    gate.reject_v1_elevation({"schema": version})

    def test_negativas_de_identidade_e_autorizacao(self):
        variants = (
            ("schema", "CHDEVFLOW-F7-OUTBOX/1"),
            ("authorization", "V1_APPROVED"),
            ("source_commit", "e" * 40),
            ("consumer_commit", "f" * 40),
            ("tar_sha256", "0" * 64),
            ("image_id", "sha256:" + "e" * 64),
            ("consumer_run", 1),
            ("consumer_run", True),
            ("reports", {}),
        )
        for field, invalid in variants:
            with self.subTest(field=field, invalid=invalid):
                changed = {**self.manifest, field: invalid}
                with self.assertRaises(ValueError):
                    gate.classify_lab_chain(changed)

    def test_negativas_digest_ou_status_dos_testes(self):
        changed = json.loads(json.dumps(self.manifest))
        changed["reports"]["fail"]["status"] = "TESTS_PASS"
        with self.assertRaisesRegex(ValueError, "Prova LAB"):
            gate.classify_lab_chain(changed)
        changed = json.loads(json.dumps(self.manifest))
        changed["reports"]["pass"]["sha256"] = "curto"
        with self.assertRaisesRegex(ValueError, "Prova LAB"):
            gate.classify_lab_chain(changed)

    def test_json_duplicado_nega(self):
        self.path.write_text('{"schema":"a","schema":"b"}', encoding="ascii")
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            gate.read_json_safely(self.path)

    def test_symlink_rejeitado_quando_suportado(self):
        original = self.path
        linked = original.parent / "symlink.json"
        try:
            linked.symlink_to(original)
        except (OSError, NotImplementedError):
            self.skipTest("Link simbolico nao permitido neste SO")
        with self.assertRaisesRegex(ValueError, "simbolico"):
            gate.read_json_safely(linked)

    def test_cli_produz_relatorio_bloqueado_sem_alterar_entrada(self):
        original = self.path.read_bytes()
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = gate.main(["--manifest", str(self.path)])
        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["state"], "BLOCKED_V1_NOT_AUTHORIZED")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.path.parent / "escalonamento_po.json").exists())


if __name__ == "__main__":
    unittest.main()
