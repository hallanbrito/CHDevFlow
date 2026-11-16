"""E3-C4: contrato fail-closed do recibo de missao assinado externamente.

Os testes com mocks verificam o contrato; NAO representam atestacao real.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chdevflow.core import po_escalation_runtime_receipt as receipt


class ExternalRuntimeReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.outbox = {
            "schema": "CHDEVFLOW-F7-OUTBOX/1",
            "execution_id": "a" * 32,
            "mission_id": "F7-E3C4-TEST-001",
            "status": "AGUARDANDO_PO",
        }
        self.proof = {
            "mission_digest": "c" * 64,
            "files_sha256": {"attempt-01/testes.log": "d" * 64},
        }
        self.outbox_path = self.root / "escalonamento_po.json"
        self.outbox_path.write_text(json.dumps(self.outbox), encoding="utf-8")
        self.receipt_path = self.root / receipt.RECEIPT_FILE
        self.data = {
            "schema": receipt.SCHEMA, "repository": receipt.REPO,
            "repository_id": receipt.REPO_ID,
            "execution_id": self.outbox["execution_id"],
            "mission_id": self.outbox["mission_id"],
            "mission_digest": self.proof["mission_digest"],
            "producer_run_id": 987654,
            "producer_run_attempt": 1,
            "attestor_run_id": 888888,
            "attestor_run_attempt": 1,
            "outbox_sha256": hashlib.sha256(self.outbox_path.read_bytes()).hexdigest(),
            "files_sha256": self.proof["files_sha256"],
            "executor_tar_sha256": receipt.TAR_SHA256,
            "executor_image_id": receipt.IMAGE_ID,
            "executor_build_sha": receipt.EXECUTOR_SOURCE_SHA,
            "test_mode": "docker-attested-e3b-sigstore",
            "authorization": "V1_ATTESTOR_RUN_ONLY_NO_POST",
        }
        self._save()

    def _save(self):
        self.receipt_path.write_text(json.dumps(self.data), encoding="utf-8")

    def _live(self):
        return {
            "id": self.data["attestor_run_id"],
            "workflow_id": 7890,
            "path": receipt.WORKFLOW_PATH + "@refs/heads/main",
            "head_sha": "e" * 40,
            "head_branch": "main",
            "status": "completed",
            "conclusion": "success",
            "run_attempt": self.data["attestor_run_attempt"],
            "repository": {"id": receipt.REPO_ID},
        }

    def _verified(self, run=None):
        if run is None:
            run = self._live()
        with patch.object(receipt, "ATTESTOR_SHA_PIN", "e" * 40), \
             patch.object(receipt, "ATTESTOR_WORKFLOW_ID_PIN", 7890), \
             patch.object(receipt, "_live_attestor_run", return_value=run), \
             patch.object(receipt, "_verify_sigstore") as sigstore:
            outcome = receipt.verify_runtime_receipt(
                self.root, self.outbox, self.proof)
        return outcome, sigstore

    def test_default_sem_pin_rejeita_antes_de_gh(self):
        with patch.object(receipt, "_live_attestor_run") as live, \
             patch.object(receipt, "_verify_sigstore") as sigstore:
            with self.assertRaisesRegex(
                    receipt.ExternalRuntimeReceiptError, "nao esta pinado"):
                receipt.verify_runtime_receipt(self.root, self.outbox, self.proof)
            live.assert_not_called()
            sigstore.assert_not_called()

    def test_recibo_coerente_assinado_so_passa_em_ambiente_mockado(self):
        outcome, signature = self._verified()
        self.assertEqual(outcome["schema"], receipt.SCHEMA)
        self.assertEqual(outcome["executor_image_id"], receipt.IMAGE_ID)
        self.assertEqual(outcome["producer_run_id"], 987654)
        signature.assert_called_once()
        self.assertEqual(signature.call_args.kwargs["sha"], "e" * 40)

    def test_recibo_sem_assinatura_bloqueia(self):
        with patch.object(receipt, "ATTESTOR_SHA_PIN", "e" * 40), \
             patch.object(receipt, "ATTESTOR_WORKFLOW_ID_PIN", 7890), \
             patch.object(receipt, "_live_attestor_run", return_value=self._live()), \
             patch.object(receipt, "_verify_sigstore",
                          side_effect=receipt.ExternalRuntimeReceiptError("sem assinatura")):
            with self.assertRaisesRegex(
                    receipt.ExternalRuntimeReceiptError, "sem assinatura"):
                receipt.verify_runtime_receipt(self.root, self.outbox, self.proof)

    def test_alteracoes_no_recibo_nao_autorizam(self):
        variants = (
            ("repository_id", True),
            ("repository", "outro/CHDevFlow"),
            ("execution_id", "f" * 32),
            ("mission_digest", "f" * 64),
            ("outbox_sha256", "e" * 64),
            ("files_sha256", {}),
            ("executor_tar_sha256", "0" * 64),
            ("executor_image_id", "sha256:" + "0" * 64),
            ("executor_build_sha", "f" * 40),
            ("test_mode", "docker-readonly-no-network"),
            ("authorization", "V1_POST_AUTORIZADO"),
            ("producer_run_id", True),
            ("attestor_run_attempt", 0),
        )
        for key, invalid in variants:
            with self.subTest(field=key, value=invalid):
                original = self.data[key]
                self.data[key] = invalid
                self._save()
                with patch.object(receipt, "ATTESTOR_SHA_PIN", "e" * 40), \
                     patch.object(receipt, "ATTESTOR_WORKFLOW_ID_PIN", 7890), \
                     patch.object(receipt, "_live_attestor_run") as live:
                    with self.assertRaises(receipt.ExternalRuntimeReceiptError):
                        receipt.verify_runtime_receipt(
                            self.root, self.outbox, self.proof)
                    live.assert_not_called()
                self.data[key] = original
                self._save()

    def test_outbox_mudada_apos_recibo_bloqueia(self):
        forged = {**self.outbox, "status": "PUBLICADO"}
        self.outbox_path.write_text(json.dumps(forged), encoding="utf-8")
        with patch.object(receipt, "ATTESTOR_SHA_PIN", "e" * 40), \
             patch.object(receipt, "ATTESTOR_WORKFLOW_ID_PIN", 7890), \
             patch.object(receipt, "_live_attestor_run") as live:
            with self.assertRaises(receipt.ExternalRuntimeReceiptError):
                receipt.verify_runtime_receipt(self.root, self.outbox, self.proof)
            live.assert_not_called()

    def test_run_live_alterado_bloqueia(self):
        for changed in (
            {"head_sha": "f" * 40},
            {"workflow_id": 42},
            {"path": ".github/workflows/f7-custody-producer.yml"},
            {"head_branch": "feat/untrusted"},
            {"status": "in_progress"},
            {"conclusion": "failure"},
            {"run_attempt": 2},
            {"repository": {"id": 999}},
            {"id": True},
        ):
            with self.subTest(changed=changed):
                with patch.object(receipt, "ATTESTOR_SHA_PIN", "e" * 40), \
                     patch.object(receipt, "ATTESTOR_WORKFLOW_ID_PIN", 7890), \
                     patch.object(receipt, "_live_attestor_run",
                                  return_value={**self._live(), **changed}), \
                     patch.object(receipt, "_verify_sigstore") as sigstore:
                    with self.assertRaises(receipt.ExternalRuntimeReceiptError):
                        receipt.verify_runtime_receipt(
                            self.root, self.outbox, self.proof)
                    sigstore.assert_not_called()

    def test_recibo_simbolico_bloqueia(self):
        self.receipt_path.unlink()
        real = self.root / "real.json"
        real.write_text(json.dumps(self.data), encoding="utf-8")
        try:
            self.receipt_path.symlink_to(real)
        except (NotImplementedError, OSError):
            self.skipTest("Symlinks indisponiveis")
        with patch.object(receipt, "ATTESTOR_SHA_PIN", "e" * 40), \
             patch.object(receipt, "ATTESTOR_WORKFLOW_ID_PIN", 7890):
            with self.assertRaises(receipt.ExternalRuntimeReceiptError):
                receipt.verify_runtime_receipt(self.root, self.outbox, self.proof)

    def test_json_duplicado_bloqueia(self):
        raw = self.receipt_path.read_text(encoding="utf-8")
        self.receipt_path.write_text(
            raw.replace('"schema":', '"schema":"fake","schema":', 1),
            encoding="utf-8")
        with patch.object(receipt, "ATTESTOR_SHA_PIN", "e" * 40), \
             patch.object(receipt, "ATTESTOR_WORKFLOW_ID_PIN", 7890):
            with self.assertRaises(receipt.ExternalRuntimeReceiptError):
                receipt.verify_runtime_receipt(self.root, self.outbox, self.proof)


if __name__ == "__main__":
    unittest.main()
