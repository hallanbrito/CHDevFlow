"""Regressoes na fronteira de confianca do atestador F7."""
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from f7_custody_live import PRODUCER, REPOSITORY_ID, unpack, validate_artifact, validate_run
from chdevflow.core.po_escalation_attestation import validate_trusted_key


class CustodyAdmissionTest(unittest.TestCase):
    def test_run_exige_origem_sha_e_tentativa(self):
        sha = "a" * 40
        run = {
            "id": 21, "workflow_id": 31, "run_attempt": 2, "path": PRODUCER,
            "event": "workflow_dispatch", "head_branch": "main", "head_sha": sha,
            "conclusion": "success", "status": "completed",
            "repository": {"id": REPOSITORY_ID}, "head_repository": {"id": REPOSITORY_ID},
        }
        self.assertEqual(validate_run(run, 21, 31, sha), 2)
        for change in ({"event": "pull_request"}, {"head_sha": "b" * 40},
                       {"workflow_id": 32}, {"id": 22}, {"head_branch": "other"},
                       {"head_repository": {"id": 1}}, {"status": "in_progress"}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "Origem"):
                validate_run({**run, **change}, 21, 31, sha)

    def test_metadados_e_digest_do_zip(self):
        sha = "a" * 40
        name = "f7-custody-evidence-21-2"
        stream = io.BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("attempt-01/testes.log", "exemplo")
        data = stream.getvalue()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        artifact = {
            "id": 41, "name": name, "digest": digest, "expired": False,
            "size_in_bytes": len(data), "workflow_run": {
                "id": 21, "head_branch": "main", "head_sha": sha,
                "repository_id": REPOSITORY_ID, "head_repository_id": REPOSITORY_ID,
            },
        }
        validate_artifact(artifact, name, 21, sha)
        for changed in ({"name": "f7-custody-evidence-21-1"}, {"expired": True},
                        {"digest": None}, {"workflow_run": {"id": 22}}):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "vinculo"):
                validate_artifact({**artifact, **changed}, name, 21, sha)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ValueError, "Digest"):
                unpack(data + b"alterado", digest, root)
            unpack(data, digest, root)
            self.assertEqual((root / "attempt-01/testes.log").read_text(), "exemplo")
            outside = io.BytesIO()
            with ZipFile(outside, "w") as archive:
                archive.writestr("../script.py", "ignorar")
            invalid = outside.getvalue()
            with self.assertRaisesRegex(ValueError, "Entrada"):
                unpack(invalid, "sha256:" + hashlib.sha256(invalid).hexdigest(), root)

    def test_revogacao_nega_chave_mesmo_quando_politica_a_referencia(self):
        key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI" + "A" * 43
        fingerprint = validate_trusted_key(key, "NONE")
        with self.assertRaisesRegex(ValueError, "revogada"):
            validate_trusted_key(key, fingerprint)
        with self.assertRaisesRegex(ValueError, "ausente ou invalida"):
            validate_trusted_key("ssh-ed25519 invalida", "NONE")


if __name__ == "__main__":
    unittest.main()
