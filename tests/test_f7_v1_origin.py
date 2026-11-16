"""Negativas offline do vinculo entre recibo V1 e metadados GitHub LIVE."""
from __future__ import annotations

from pathlib import Path
import copy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chdevflow.core import po_escalation_origin as origin


class V1OriginTests(unittest.TestCase):
    def setUp(self):
        self.run_id = 12345
        self.attempt = 2
        self.artifact_id = 777
        self.producer_sha = "a" * 40
        self.workflow_id = 98765
        self.digest = "sha256:" + "c" * 64
        self.receipt_origin = (
            f"github-actions:v1:{self.run_id}:{self.attempt}:"
            f"{self.artifact_id}:{self.digest}"
        )
        self.run = {
            "id": self.run_id, "workflow_id": self.workflow_id,
            "path": origin.V1_PRODUCER_PATH + "@refs/heads/main",
            "event": "workflow_dispatch", "head_branch": "main",
            "head_sha": self.producer_sha, "status": "completed",
            "conclusion": "success", "run_attempt": self.attempt,
            "repository": {"id": origin.REPOSITORY_ID},
            "head_repository": {"id": origin.REPOSITORY_ID},
        }
        self.artifact = {
            "id": self.artifact_id,
            "name": f"f7-v1-evidence-{self.run_id}-{self.attempt}",
            "digest": self.digest, "expired": False,
            "workflow_run": {
                "id": self.run_id, "head_branch": "main",
                "head_sha": self.producer_sha,
                "repository_id": origin.REPOSITORY_ID,
                "head_repository_id": origin.REPOSITORY_ID,
            },
        }

    def check(self, *, receipt=None, run=None, artifact=None):
        observed = []
        run_record = self.run if run is None else run
        artifact_record = self.artifact if artifact is None else artifact
        def api(endpoint):
            observed.append(endpoint)
            if endpoint.endswith(f"/actions/runs/{self.run_id}"):
                return copy.deepcopy(run_record)
            if endpoint.endswith(f"/actions/artifacts/{self.artifact_id}"):
                return copy.deepcopy(artifact_record)
            raise AssertionError("Consulta inesperada ao GitHub: " + endpoint)
        result = origin.verify_v1_producer_origin(
            self.receipt_origin if receipt is None else receipt,
            producer_sha=self.producer_sha, workflow_id=self.workflow_id,
            api=api)
        return result, observed

    def test_v1_admite_apenas_run_e_artifact_identicos(self):
        result, calls = self.check()
        self.assertEqual(result["run_id"], self.run_id)
        self.assertEqual(result["artifact_digest"], self.digest)
        self.assertEqual(len(calls), 3)

    def test_recibo_de_sonda_ou_local_bloqueado_sem_consulta(self):
        for untrusted in (
            "github-actions:custody:12345:2:777:" + self.digest,
            "github-actions:probe:12345:2",
            "ci-f7:issuer-receipt-1", "github-actions:v1:0:2:777:" + self.digest,
            "github-actions:v1:12345:2:777:sha256:curto",
        ):
            with self.subTest(receipt=untrusted):
                with self.assertRaisesRegex(origin.ProducerOriginError, "Origem"):
                    self.check(receipt=untrusted)

    def test_run_de_outro_repo_branch_workflow_ou_tentativa_bloqueado(self):
        cases = (
            {"head_branch": "feat/f7"},
            {"head_sha": "f" * 40},
            {"workflow_id": 999},
            {"path": ".github/workflows/f7-custody-producer.yml"},
            {"run_attempt": 3},
            {"conclusion": "failure"},
            {"repository": {"id": 999}},
            {"head_repository": {"id": 999}},
        )
        for update in cases:
            with self.subTest(update=update):
                with self.assertRaisesRegex(origin.ProducerOriginError, "Run"):
                    self.check(run={**self.run, **update})

    def test_artifact_de_outro_run_ou_digest_bloqueado(self):
        cases = (
            {"name": "f7-v1-evidence-forjado"},
            {"digest": "sha256:" + "d" * 64},
            {"expired": True},
            {"workflow_run": {**self.artifact["workflow_run"], "id": 999}},
            {"workflow_run": {**self.artifact["workflow_run"], "head_sha": "f" * 40}},
            {"workflow_run": {**self.artifact["workflow_run"], "repository_id": 999}},
        )
        for update in cases:
            with self.subTest(update=update):
                with self.assertRaisesRegex(origin.ProducerOriginError, "Artefato"):
                    self.check(artifact={**self.artifact, **update})


if __name__ == "__main__":
    unittest.main()
