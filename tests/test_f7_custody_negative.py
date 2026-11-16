"""F7 Gate 1: negativas fail-closed para custodia Solo, sem credenciais reais.

Os testes desta suite nao acessam secrets de GitHub, nao usam rede e nao
constituem prova de permissoes administrativas do Environment f7-attestor.
"""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import f7_custody_live as custody


class Gate1FailClosedTest(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 40
        self.run = {
            "id": 21,
            "workflow_id": 31,
            "run_attempt": 2,
            "path": custody.PRODUCER,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": self.sha,
            "conclusion": "success",
            "status": "completed",
            "repository": {"id": custody.REPOSITORY_ID},
            "head_repository": {"id": custody.REPOSITORY_ID},
        }

    def test_run_negado_quando_identidade_estado_ou_tentativa_diferem(self):
        self.assertEqual(custody.validate_run(self.run, 21, 31, self.sha), 2)
        mutations = [
            {"path": "other.yml"},
            {"event": "pull_request"},
            {"head_branch": "not-main"},
            {"head_sha": "b" * 40},
            {"id": 22},
            {"workflow_id": 32},
            {"run_attempt": 0},
            {"run_attempt": True},
            {"status": "in_progress"},
            {"conclusion": "failure"},
            {"repository": {"id": 1}},
            {"head_repository": {"id": 1}},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "Origem"):
                custody.validate_run({**self.run, **mutation}, 21, 31, self.sha)

    def test_produtor_sem_id_pinado_bloqueia(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "CH_F7_PRODUCER_WORKFLOW_ID"):
                custody.configured("CH_F7_PRODUCER_WORKFLOW_ID", r"[1-9][0-9]*")
        with patch.dict(os.environ, {"CH_F7_PRODUCER_WORKFLOW_ID": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "CH_F7_PRODUCER_WORKFLOW_ID"):
                custody.configured("CH_F7_PRODUCER_WORKFLOW_ID", r"[1-9][0-9]*")

    def test_sign_sem_secret_nao_cria_recibo(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "public"
            fake_evidence = (Path(root) / "outbox.json", self.sha, "probe:1")
            with (
                patch.dict(os.environ, {"GITHUB_SHA": self.sha, "CH_F7_ATTESTOR_SHA": self.sha}, clear=True),
                patch.object(custody, "trusted_key", return_value="public-test-key"),
                patch.object(custody, "get_evidence", return_value=fake_evidence),
                patch.object(sys, "argv", ["f7_custody_live.py", "sign", "21", str(output)]),
            ):
                with self.assertRaisesRegex(ValueError, "Credencial protegida"):
                    custody.main()
            self.assertFalse(output.exists(), "Nao gerar recibo quando falta chave privada")

    def test_sign_com_sha_nao_pinado_nao_cria_recibo(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "public"
            fake_evidence = (Path(root) / "outbox.json", self.sha, "probe:1")
            with (
                patch.dict(os.environ, {
                    "GITHUB_SHA": "b" * 40,
                    "CH_F7_ATTESTOR_SHA": self.sha,
                    # Credencial deliberadamente falsa: a verificacao SHA ocorre antes de tocar no arquivo.
                    "CH_F7_SIGNING_KEY": "-----BEGIN OPENSSH PRIVATE KEY-----FAKE",
                }, clear=True),
                patch.object(custody, "trusted_key", return_value="public-test-key"),
                patch.object(custody, "get_evidence", return_value=fake_evidence),
                patch.object(sys, "argv", ["f7_custody_live.py", "sign", "21", str(output)]),
            ):
                with self.assertRaisesRegex(ValueError, "Commit do atestador"):
                    custody.main()
            self.assertFalse(output.exists(), "SHA divergente nao deve gerar artefato")

    def test_artefato_negado_com_origem_digest_ou_sha_incorretos(self):
        artifact = {
            "id": 41,
            "name": "f7-custody-evidence-21-2",
            "expired": False,
            "size_in_bytes": 300,
            "digest": "sha256:" + "a" * 64,
            "workflow_run": {
                "id": 21, "head_branch": "main", "head_sha": self.sha,
                "repository_id": custody.REPOSITORY_ID,
                "head_repository_id": custody.REPOSITORY_ID,
            },
        }
        custody.validate_artifact(artifact, artifact["name"], 21, self.sha)
        changes = [
            {"expired": True},
            {"digest": "not-sha256"},
            {"size_in_bytes": 0},
            {"id": 0},
            {"name": "f7-custody-evidence-21-1"},
            {"workflow_run": {**artifact["workflow_run"], "head_sha": "b" * 40}},
            {"workflow_run": {**artifact["workflow_run"], "repository_id": 1}},
            {"workflow_run": {**artifact["workflow_run"], "id": 22}},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "Artefato"):
                custody.validate_artifact({**artifact, **change}, artifact["name"], 21, self.sha)

    @staticmethod
    def _zip(entries):
        buf = io.BytesIO()
        with ZipFile(buf, "w") as archive:
            for item, value in entries:
                archive.writestr(item, value)
        data = buf.getvalue()
        return data, "sha256:" + hashlib.sha256(data).hexdigest()

    def test_zip_nega_duplicacao_entrada_ilegal_e_bytes_alterados(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                duplicated, digest = self._zip([
                    ("attempt-01/testes.log", "primeiro"),
                    ("attempt-01/testes.log", "segundo"),
                ])
            with self.assertRaisesRegex(ValueError, "duplicado"):
                custody.unpack(duplicated, digest, root)
            illegal, digest = self._zip([("../evil.py", "nao executar")])
            with self.assertRaisesRegex(ValueError, "Entrada"):
                custody.unpack(illegal, digest, root)
            valid, digest = self._zip([("attempt-01/testes.log", "ok")])
            with self.assertRaisesRegex(ValueError, "Digest"):
                custody.unpack(valid + b"adulterado", digest, root)

    def test_zip_nega_symlink_e_arquivo_desproporcional(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            symlink = ZipInfo("attempt-01/testes.log")
            symlink.create_system = 3
            symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
            data, digest = self._zip([(symlink, "target")])
            with self.assertRaisesRegex(ValueError, "Entrada"):
                custody.unpack(data, digest, root)
            big, digest = self._zip([("attempt-01/testes.log", "x" * 100001)])
            with self.assertRaisesRegex(ValueError, "Entrada"):
                custody.unpack(big, digest, root)

    def test_politica_estatica_separa_secret_de_produtor_e_ci_pr(self):
        workflows = ROOT / ".github" / "workflows"
        attestor = (workflows / "f7-custody-attestor.yml").read_text(encoding="utf-8")
        producer = (workflows / "f7-custody-producer.yml").read_text(encoding="utf-8")
        secret_ref = "secrets." + "CH_F7_SIGNING_KEY"
        self.assertIn("environment: f7-attestor", attestor)
        self.assertIn("workflow_dispatch:", attestor)
        self.assertNotIn("pull_request:", attestor)
        self.assertEqual(attestor.count(secret_ref), 1)
        self.assertIn("verify:\n    needs: sign", attestor)
        self.assertNotIn(secret_ref, producer)
        self.assertIn("github.ref == 'refs/heads/main'", producer)
        for path in workflows.glob("*.yml"):
            if path.name != "f7-custody-attestor.yml":
                with self.subTest(workflow=path.name):
                    self.assertNotIn(secret_ref, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
