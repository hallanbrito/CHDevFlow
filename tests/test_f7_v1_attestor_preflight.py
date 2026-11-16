"""E3-C5: guard do atestador V1 independente. Sem assinar nada."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import f7_v1_attestor_preflight as guard


class AttestorOriginTests(unittest.TestCase):
    def setUp(self):
        self.pin_sha = "e" * 40
        self.pin_id = 54321
        self.repo = {"full_name": guard.REPO, "id": guard.REPO_ID}
        self.actor = {"login": "hallanbrito", "id": guard.PO_ID}
        self.run = {
            "id": 4567123, "workflow_id": self.pin_id,
            "head_sha": self.pin_sha, "head_branch": "main",
            "event": "workflow_dispatch", "run_attempt": 1,
            "status": "completed", "conclusion": "success",
            "path": guard.PRODUCER_WORKFLOW_PATH + "@refs/heads/main",
            "actor": copy.deepcopy(self.actor),
            "triggering_actor": copy.deepcopy(self.actor),
            "repository": copy.deepcopy(self.repo),
            "head_repository": copy.deepcopy(self.repo),
        }
        self.event = {
            "workflow_run": copy.deepcopy(self.run),
            "repository": copy.deepcopy(self.repo),
        }

    def check(self, event=None, live=None, **kwargs):
        return guard.check_origin(
            self.event if event is None else event,
            self.run if live is None else live,
            pinned_sha=kwargs.get("pinned_sha", self.pin_sha),
            pinned_workflow_id=kwargs.get("pinned_workflow_id", self.pin_id),
        )

    def test_producer_evento_e_live_coerentes_nao_autorizam_assinatura(self):
        d = self.check()
        self.assertEqual(d["state"], "ORIGIN_ONLY_NOT_MISSION_ATTESTED")
        self.assertFalse(d["agents_verified"])
        self.assertFalse(d["outbox_verified"])
        self.assertFalse(d["signature_emitted"])

    def test_pin_default_sem_producao_bloqueia(self):
        with self.assertRaisesRegex(guard.AttestorAdmissionError, "nao provisionado"):
            guard.check_origin(self.event, self.run)
        self.assertFalse(guard.ATTESTOR_SIGNING_ENABLED)

    def test_run_live_divergente_bloqueia(self):
        variants = (
            ("id", True), ("id", 99), ("workflow_id", 99),
            ("head_sha", "f" * 40), ("head_branch", "feat/x"),
            ("event", "push"), ("run_attempt", 2),
            ("status", "in_progress"), ("conclusion", "failure"),
            ("path", ".github/workflows/f7-custody-producer.yml"),
            ("actor", {"login": "outro", "id": guard.PO_ID}),
            ("triggering_actor", {"login": "hallanbrito", "id": 999}),
            ("repository", {"id": guard.REPO_ID + 1, "full_name": guard.REPO}),
            ("head_repository", {"id": guard.REPO_ID + 1, "full_name": guard.REPO}),
        )
        for field, value in variants:
            with self.subTest(field=field, value=value):
                with self.assertRaises(guard.AttestorAdmissionError):
                    self.check(live={**self.run, field: value})

    def test_ator_sem_id_numerico_bloqueia(self):
        for actor in (
            {"login": "hallanbrito"},
            {"login": "hallanbrito", "id": str(guard.PO_ID)},
            {"login": "hallanbrito", "id": True},
        ):
            with self.subTest(actor=actor):
                with self.assertRaises(guard.AttestorAdmissionError):
                    record = copy.deepcopy(self.run)
                    record["actor"] = actor
                    event = copy.deepcopy(self.event)
                    event["workflow_run"]["actor"] = actor
                    self.check(event=event, live=record)

    def test_fork_ou_evento_de_outro_repo_bloqueado(self):
        event = copy.deepcopy(self.event)
        event["repository"]["id"] = guard.REPO_ID + 1
        with self.assertRaisesRegex(guard.AttestorAdmissionError, "Evento nao"):
            self.check(event=event)

    def test_evento_e_api_nao_podem_divergir(self):
        event = copy.deepcopy(self.event)
        event["workflow_run"]["run_attempt"] = 3
        with self.assertRaisesRegex(guard.AttestorAdmissionError, "divergentes"):
            self.check(event=event)

    def test_pins_com_tipo_invalido_bloqueados(self):
        for sha, ident in ((self.pin_sha, True), ("f", self.pin_id),
                           (True, self.pin_id), (self.pin_sha, 0)):
            with self.subTest(sha=sha, ident=ident):
                with self.assertRaises(guard.AttestorAdmissionError):
                    self.check(pinned_sha=sha, pinned_workflow_id=ident)

    def test_nao_existe_modo_para_emitir_assinatura(self):
        with patch.object(guard, "_gh_run") as gh:
            with patch.dict(guard.os.environ, {}, clear=True):
                with self.assertRaises(guard.AttestorAdmissionError):
                    guard.main()
                gh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
