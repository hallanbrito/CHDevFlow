"""E3-C2: provas negativas da autorização de missão V1 via GH LIVE."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import f7_v1_mission_gate as gate


class MissionGateTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "schema": gate.SCHEMA,
            "repository": gate.REPO,
            "mission_id": "F7-HELLO-001",
            "issue": 95,
            "producer_sha": "a" * 40,
            "baseline_sha": "b" * 40,
            "executor_tar_sha256": "c" * 64,
            "allowed_path": "src/frete.py",
            "prompt_path": "docs/mission.txt",
            "timeout_seconds": 480,
            "cost_brl": 0,
            "nonce": "d" * 32,
        }
        self.approval_id = 78655
        self.actor = {"login": gate.PO_LOGIN, "id": gate.PO_ID}
        self.repository = {"full_name": gate.REPO, "id": gate.REPO_ID}
        self.issue = {"number": self.data["issue"], "state": "open"}
        self.run_id = 43210
        self.run = {
            "id": self.run_id, "event": "workflow_dispatch",
            "head_branch": "main", "head_sha": self.data["producer_sha"],
            "path": ".github/workflows/f7-v1-producer.yml@refs/heads/main",
            "actor": copy.deepcopy(self.actor),
            "triggering_actor": copy.deepcopy(self.actor),
            "repository": {"id": gate.REPO_ID},
        }
        self.comments = [{
            "id": self.approval_id,
            "user": copy.deepcopy(self.actor),
            "body": gate.expected_approval(self.data),
            "created_at": "2026-11-16T18:30:00Z",
            "updated_at": "2026-11-16T18:30:00Z",
        }]

    def verify(self, **changes):
        args = {
            "manifest": self.data,
            "approval_id": self.approval_id,
            "actor": self.actor,
            "repository": self.repository,
            "issue": self.issue,
            "comments": self.comments,
            "workflow_sha": self.data["producer_sha"],
            "run": self.run,
            "run_id": self.run_id,
        }
        args.update(changes)
        return gate.validate_live(**args)

    def test_autorizacao_valida_somente_readiness(self):
        result = self.verify()
        self.assertEqual(result["state"], "PO_APPROVAL_VERIFIED_ONLY")
        self.assertFalse(result["agents_executed"])
        self.assertFalse(result["outbox_v1_created"])
        self.assertFalse(result["remote_publication_enabled"])
        self.assertEqual(result["mission_digest"], gate.validate_manifest(self.data))

    def test_contrato_nao_aceita_custo_falso_ou_schema_divergente(self):
        variants = [
            ("cost_brl", 2), ("cost_brl", False), ("cost_brl", "0"),
            ("repository", "outro/Repo"), ("timeout_seconds", 9999),
            ("timeout_seconds", True), ("nonce", "notnonce"),
            ("baseline_sha", "nope"), ("executor_tar_sha256", "z" * 64),
            ("producer_sha", "A" * 40), ("issue", True),
            ("allowed_path", "../main.py"), ("allowed_path", "tests/bypass.py"),
            ("allowed_path", ".github/evil.py"), ("allowed_path", "src/../../evil.py"),
            ("prompt_path", "../evil.md"), ("prompt_path", "docs/prompt.exe"),
            ("allowed_path", "docs/mission.txt"),
        ]
        for key, value in variants:
            with self.subTest(key=key, value=value):
                bad = {**self.data, key: value}
                with self.assertRaises(gate.MissionAuthorizationError):
                    gate.validate_manifest(bad)

    def test_aprovacao_tem_digest_exato(self):
        bad = copy.deepcopy(self.comments)
        bad[0]["body"] = bad[0]["body"].replace("COST_BRL=0", "COST_BRL=1")
        with self.assertRaisesRegex(gate.MissionAuthorizationError, "Aprovação"):
            self.verify(comments=bad)
        bad = copy.deepcopy(self.comments)
        bad[0]["body"] = bad[0]["body"].replace(self.data["baseline_sha"], "e" * 40)
        with self.assertRaises(gate.MissionAuthorizationError):
            self.verify(comments=bad)

    def test_po_id_login_e_identidade_live_obrigatorios(self):
        for actor in (
            {"login": gate.PO_LOGIN},
            {"login": gate.PO_LOGIN, "id": 999},
            {"login": gate.PO_LOGIN, "id": str(gate.PO_ID)},
            {"login": "outro", "id": gate.PO_ID},
        ):
            with self.subTest(actor=actor):
                with self.assertRaises(gate.MissionAuthorizationError):
                    self.verify(actor=actor)
                comments = copy.deepcopy(self.comments)
                comments[0]["user"] = actor
                with self.assertRaises(gate.MissionAuthorizationError):
                    self.verify(comments=comments)

    def test_run_de_branch_fork_workflow_ou_ator_diferente_bloqueia(self):
        variants = (
            ("head_branch", "feat/malicious"),
            ("head_sha", "f" * 40),
            ("event", "push"),
            ("path", ".github/workflows/f7-custody-producer.yml"),
            ("actor", {"login": gate.PO_LOGIN, "id": 999}),
            ("triggering_actor", {"login": gate.PO_LOGIN, "id": 999}),
            ("repository", {"id": 999}),
            ("id", True),
        )
        for name, value in variants:
            with self.subTest(name=name, value=value):
                with self.assertRaises(gate.MissionAuthorizationError):
                    self.verify(run={**self.run, name: value})

    def test_revoke_apos_aprovacao_bloqueia(self):
        revoke = {
            "id": self.approval_id + 1,
            "user": copy.deepcopy(self.actor),
            "body": "CH-F7-V1 REVOGAR ISSUE#95 MISSION#F7-HELLO-001",
        }
        with self.assertRaisesRegex(gate.MissionAuthorizationError, "revogada"):
            self.verify(comments=self.comments + [revoke])

    def test_aprovacao_editada_ou_duplicada_bloqueia(self):
        edited = copy.deepcopy(self.comments)
        edited[0]["updated_at"] = "2026-11-16T18:30:01Z"
        with self.assertRaisesRegex(gate.MissionAuthorizationError, "editada"):
            self.verify(comments=edited)
        with self.assertRaisesRegex(gate.MissionAuthorizationError, "univocamente"):
            self.verify(comments=self.comments + self.comments)

    def test_repo_issue_ou_pr_suspeitos_bloqueiam(self):
        with self.assertRaises(gate.MissionAuthorizationError):
            self.verify(repository={"full_name": gate.REPO, "id": 999})
        with self.assertRaises(gate.MissionAuthorizationError):
            self.verify(issue={"number": self.data["issue"], "state": "closed"})
        with self.assertRaises(gate.MissionAuthorizationError):
            self.verify(issue={**self.issue, "pull_request": {"url": "anything"}})

    def test_json_duplicado_ou_nao_seguro_bloqueia(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "mission.json"
            p.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaises(gate.MissionAuthorizationError):
                gate.read_manifest(p)
            p.write_text(json.dumps(self.data), encoding="utf-8")
            self.assertEqual(gate.read_manifest(p), self.data)
            link = Path(tmp) / "alias.json"
            try:
                link.symlink_to(p)
            except (NotImplementedError, OSError):
                return
            with self.assertRaises(gate.MissionAuthorizationError):
                gate.read_manifest(link)


if __name__ == "__main__":
    unittest.main()
