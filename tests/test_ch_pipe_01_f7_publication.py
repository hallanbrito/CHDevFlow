"""F7 publication: testes offline sem qualquer gh real nem comentario remoto."""
from __future__ import annotations

import contextlib
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from chdevflow.core import po_escalation_publication as pub
from chdevflow.core.po_escalation_attestation import SSH_NAMESPACE, execution_statement, statement_bytes
from chdevflow.core.manual_pipeline_runner import Mission, SCHEMA as MISSION_SCHEMA
from chdevflow.core.po_escalation_provenance import create_provenance, verify_provenance
from chdevflow.core.attested_executor import IMAGE_ID as ATTESTED_IMAGE_ID
from chdevflow.core.po_escalation_runtime_receipt import ExternalRuntimeReceiptError
from chdevflow.core.po_escalation_reservation import (
    GitReservationStore, NAMESPACE, ReservationError,
)


def issue_body():
    return (
        "### Esteira\nAGY\n"
        "### Nível de autonomia\nCH-0\n"
        "### Objetivo e valor\nEntregar uma missao Python auditavel\n"
        "### Escopo, exclusões e critérios de aceite\n"
        "Codigo Python com testes independentes e gate humano\n"
        "### Baseline Git (branch e SHA)\nfeat/f6 " + ("a" * 40) + "\n"
        "### Verificações e evidências exigidas\n"
        "Docker e Codex devem registrar resultados verificaveis\n"
    )


class PublicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.outbox = self.root / "escalonamento_po.json"
        self.code = "def cotar_frete():\n    return 500\n"
        self.data = {
            "schema": pub.SCHEMA, "execution_id": "a" * 32,
            "mission_id": "F6-FRETE-TEST-001", "issue": 85,
            "status": "AGUARDANDO_PO",
            "publication_status": "PENDENTE_DE_AUTORIZACAO",
            "attempts": 3, "returns": 2,
            "code_sha256": hashlib.sha256(self.code.encode()).hexdigest(),
            "third_attempt_status": "CODEX_REPROVOU",
            "evidence_files": list(pub.EVIDENCE_FILES),
        }
        self.outbox.write_text(
            json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        for index in range(1, 4):
            folder = self.root / f"attempt-{index:02d}"
            folder.mkdir(parents=True, exist_ok=True)
            for rel in ("agy.log", "codigo.py", "alteracoes.patch",
                        "testes.log", "codex.log", "auditoria_codex.md"):
                (folder / rel).write_text(
                    self.code if rel == "codigo.py" else
                    "Evidencia de laboratorio sem rede",
                    encoding="utf-8")
        (self.root / "RELATORIO_COMPLETO_CH1.md").write_text(
            "Tres vetos em laboratorio\n", encoding="utf-8")
        manifest = Mission.from_dict({
            "schema": MISSION_SCHEMA,
            "mission_id": self.data["mission_id"],
            "repository": pub.REPO, "issue": 85,
            "base_sha": "a" * 40,
            "worktree": str(self.root / "CH-Lab-F6-lab"),
            "allowed_paths": ["src/frete.py"],
            "prompt_ref": "prompt.txt", "timeout_seconds": 480,
        })
        (self.root / "manifesto_missao.json").write_bytes(manifest.canonical())
        record = {
            "status": "AGUARDANDO_PO", "execution_id": self.data["execution_id"],
            "mission_id": self.data["mission_id"], "issue": 85,
            "mission_digest": manifest.digest, "returns_used": 2,
            "os_isolation_verified": True,
            "test_execution": "docker-attested-e3b-sigstore:" + ATTESTED_IMAGE_ID,
            "attempts": [{
                "number": num, "status": "CODEX_REPROVOU",
                "sha256": self.data["code_sha256"],
                "codex_verdict": "BLOQUEADO",
            } for num in (1, 2, 3)],
        }
        (self.root / "execucao.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8")
        self.data["provenance"] = create_provenance(self.root)
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        # Mock explicito em testes de governanca anteriores: nao afirma
        # que exista uma assinatura REAL de missao. As negativas E3-C5
        # deixam claro que a publicacao REAL exige o verificador externo.
        receipt_patch = patch(
            "chdevflow.core.po_escalation_provenance.verify_runtime_receipt",
            return_value={"schema": "CHDEVFLOW-F7-E3C4-RUNTIME-RECEIPT/1"})
        self.addCleanup(receipt_patch.stop)
        self.mock_runtime_receipt = receipt_patch.start()
        self.approval_id = 448200
        self.f7_sha = "b" * 40
        statement = (
            "CH-GOV-01 F7 PUBLICAR PROJECT#2 ISSUE#85 "
            "EXECUTION#" + self.data["execution_id"] + " "
            "CODE_SHA256=" + self.data["code_sha256"] + " " +
            "BASE_SHA=" + self.data["provenance"]["base_sha"] + " " +
            "MISSION_DIGEST=" + self.data["provenance"]["mission_digest"] +
            " F7_AUDITED_SHA=" + self.f7_sha +
            " ACTION=COMMENT_ONLY"
        )
        self.context = {
            "who": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
            "repository": {"permissions": {"push": True}},
            "base_commit": {"sha": "a" * 40, "tree": {"sha": "d" * 40}},
            "f7_commit": {
                "policy_sha": self.f7_sha, "local_sha": self.f7_sha,
                "git_commit": {"sha": self.f7_sha, "tree": {"sha": "c" * 40}},
                "runtime_digest": "e" * 64,
            },
            "issue": {
                "id": "I_id_mock", "number": 85, "state": "OPEN",
                "url": "https://github.com/hallanbrito/CHDevFlow/issues/85",
                "title": "Missao F6", "body": issue_body(),
                "labels": [{"name": "ch:workflow"}, {"name": "ch:agy"}],
            },
            "project": {"items": [], "totalCount": 0},
            "approval": {
                "id": self.approval_id, "issue_url":
                    "https://api.github.com/repos/hallanbrito/CHDevFlow/issues/63",
                "body": statement, "updated_at": "2026-11-15T12:00:00Z",
                "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
            },
            "comments": [],
        }
        self.context["approval_history"] = [self.context["approval"]]
        self.audit = []
        reservation_patch = patch.object(pub, "_reservation_store")
        self.addCleanup(reservation_patch.stop)
        self.reservations = reservation_patch.start()
        self.reservations.return_value.claim.return_value = "e" * 40
        self.guard_reservation = pub._verify_reservation_protection
        protection_patch = patch.object(pub, "_verify_reservation_protection")
        self.addCleanup(protection_patch.stop)
        self.gate = protection_patch.start()
        self.verify_attestation = pub._verify_attestation
        attestation_patch = patch.object(pub, "_verify_attestation")
        self.addCleanup(attestation_patch.stop)
        self.attestation = attestation_patch.start()
        self.attestation.return_value = {"producer_run": "isolated-test", "producer_sha": "e" * 40}

    def _outbox(self):
        return pub._eligible_outbox(self.outbox)

    def _plan(self):
        return pub.build_publication_plan(self._outbox(), self.context)

    def _legacy_plan(self):
        plan = self._plan()
        plan.pop("reservation_protocol")
        plan.pop("digest")
        return {**plan, "digest": pub._digest(plan)}

    def _apply(self, plan=None, reader=None, poster=None, answer=None):
        """Somente simulacao offline; habilitacao temporaria no escopo do teste."""
        plan = plan or self._plan()
        with patch.object(pub, "REMOTE_PUBLICATION_ENABLED", True):
            return pub.apply_publication_plan(
                self.outbox, plan, plan["digest"],
                reader=reader or (lambda *_: self.context),
                poster=poster or (lambda *_: self.fail("POST proibido")),
                human_prompt=answer or (
                    lambda _: "APROVO F7 PUBLICAR " + plan["digest"][:12]),
                audit=self.audit.append)

    def test_plano_seguro_sem_segredos_e_sem_project_write(self):
        plan = self._plan()
        self.assertEqual(plan["action"], "POST_COMMENT")
        self.assertEqual(plan["project_state"], "EXIGE_ADMISSAO_PO")
        self.assertEqual(plan["remote_project_writes"], 0)
        self.assertNotIn(str(self.root), json.dumps(plan))
        self.assertEqual(plan["approval_comment"], self.approval_id)
        self.assertIn("CHDEVFLOW-F7-EXECUTION", plan["body"])
        self.assertEqual(plan["digest"], pub._digest({
            k: v for k, v in plan.items() if k != "digest"}))

    def test_sem_aprovacao_default_nao_consulta_gh(self):
        with patch.object(pub.subprocess, "run",
                          side_effect=AssertionError("gh foi acionado")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = pub.main(["--outbox", str(self.outbox)])
        self.assertEqual(result, 0)
        self.assertIn("AGUARDANDO_AUTORIZACAO_PO", output.getvalue())

    def test_approval_nao_pode_vir_de_outro_usuario_ou_issue(self):
        for altered in (
            {"user": {"login": "outro"}},
            {"issue_url": "https://api.github.com/repos/hallanbrito/CHDevFlow/issues/1"},
            {"body": "aprovo tudo"},
        ):
            self.context["approval"].update(altered)
            with self.subTest(altered=altered), self.assertRaises(pub.PublicationError):
                self._plan()
            self.context["approval"].update({
                "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
                "issue_url": "https://api.github.com/repos/hallanbrito/CHDevFlow/issues/63",
                "body": ("CH-GOV-01 F7 PUBLICAR PROJECT#2 ISSUE#85 "
                         "EXECUTION#" + self.data["execution_id"] + " "
                         "CODE_SHA256=" + self.data["code_sha256"] + " " +
            "BASE_SHA=" + self.data["provenance"]["base_sha"] + " " +
            "MISSION_DIGEST=" + self.data["provenance"]["mission_digest"] +
            " F7_AUDITED_SHA=" + self.f7_sha +
            " ACTION=COMMENT_ONLY"),
            })

    def test_gate3_po_id_numerico_no_aprovador_bloqueia_sem_id_ou_trocado(self):
        original = copy.deepcopy(self.context["approval"]["user"])
        for invalid in ({"login": pub.OWNER},
                        {"login": pub.OWNER, "id": 999},
                        {"login": pub.OWNER, "id": str(pub.PO_GITHUB_ID)}):
            with self.subTest(invalid=invalid):
                self.context["approval"]["user"] = invalid
                with self.assertRaisesRegex(pub.PublicationError, "Autor"):
                    self._plan()
        self.context["approval"]["user"] = original

    def test_gate3_po_id_numerico_no_historico_aprovacao_bloqueia(self):
        original = self.context["approval_history"][0]
        try:
            for invalid in ({"login": pub.OWNER},
                            {"login": pub.OWNER, "id": 999},
                            {"login": pub.OWNER, "id": str(pub.PO_GITHUB_ID)}):
                with self.subTest(invalid=invalid):
                    fake = copy.deepcopy(self.context["approval"])
                    fake["user"] = invalid
                    self.context["approval_history"][0] = fake
                    with self.assertRaisesRegex(pub.PublicationError, "historico LIVE"):
                        self._plan()
        finally:
            self.context["approval_history"][0] = original

    def test_gate3_po_id_numerico_na_sessao_bloqueia(self):
        original = copy.deepcopy(self.context["who"])
        for invalid in ({"login": pub.OWNER},
                        {"login": pub.OWNER, "id": 999},
                        {"login": pub.OWNER, "id": str(pub.PO_GITHUB_ID)}):
            with self.subTest(invalid=invalid):
                self.context["who"] = invalid
                with self.assertRaisesRegex(pub.PublicationError, "Identidade/ACL"):
                    self._plan()
        self.context["who"] = original

    def test_gate3_po_id_numerico_em_revogacao_suspeita_bloqueia(self):
        self.context["approval_history"].append({
            "id": self.approval_id + 1001,
            "body": "CH-GOV-01 F7 REVOGAR PROJECT#2 ISSUE#85 EXECUTION#"
                    + self.data["execution_id"],
            "user": {"login": pub.OWNER, "id": 999},
            "updated_at": "2026-11-16T15:00:00Z",
        })
        with self.assertRaisesRegex(pub.PublicationError, "Identidade numerica"):
            self._plan()

    def test_revogacao_no_ultimo_snapshot_live_bloqueia_post(self):
        plan = self._plan()
        calls = []
        def reader(*_):
            calls.append("GET")
            if len(calls) == 3:
                self.context["approval_history"].append({
                    "id": self.approval_id + 99,
                    "body": ("CH-GOV-01 F7 REVOGAR PROJECT#2 ISSUE#85 EXECUTION#"
                             + self.data["execution_id"]),
                    "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
                })
            return self.context
        with self.assertRaises(pub.PublicationPending):
            self._apply(
                plan, reader=reader,
                poster=lambda *_: self.fail("POST apos revogacao"))
        self.assertEqual(len(calls), 3)
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        self.assertEqual(json.loads(lock.read_text())["publication_status"],
                         "PENDENTE_PUBLICACAO")

    def test_revogacao_posterior_do_po_bloqueia_antes_do_post(self):
        self.context["approval_history"].append({
            "id": self.approval_id + 1,
            "body": ("CH-GOV-01 F7 REVOGAR PROJECT#2 ISSUE#85 EXECUTION#"
                     + self.data["execution_id"] + " ACTION=COMMENT_ONLY"),
            "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
            "updated_at": "2026-11-15T13:00:00Z",
        })
        with self.assertRaisesRegex(pub.PublicationError, "revogada"):
            self._plan()

    def test_autorizacao_com_linha_contraditoria_bloqueia(self):
        self.context["approval"]["body"] += "\\nREVOGADO PELO PO"
        with self.assertRaisesRegex(pub.PublicationError, "alterada"):
            self._plan()

    def test_historico_aprovacao_indisponivel_bloqueia(self):
        self.context.pop("approval_history")
        with self.assertRaisesRegex(pub.PublicationError, "Historico"):
            self._plan()

    def test_retirada_apos_plano_invalida_digest_antes_post(self):
        plan = self._plan()
        self.context["approval_history"].append({
            "id": self.approval_id + 3,
            "body": ("CH-GOV-01 F7 REVOGAR PROJECT#2 ISSUE#85 EXECUTION#"
                     + self.data["execution_id"]),
            "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
        })
        with self.assertRaisesRegex(pub.PublicationError, "revogada"):
            self._apply(plan, poster=lambda *_: self.fail("POST desautorizado"))
        self.assertFalse(self.audit)

    def test_revogacao_editada_em_comentario_antigo_bloqueia(self):
        self.context["approval_history"].insert(0, {
            "id": self.approval_id - 1,
            "body": ("CH-GOV-01 F7 REVOGAR PROJECT#2 ISSUE#85 EXECUTION#"
                     + self.data["execution_id"]),
            "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
            "updated_at": "2026-11-15T14:00:00Z",
        })
        with self.assertRaisesRegex(pub.PublicationError, "revogada"):
            self._plan()

    def test_baseline_issue_divergente_bloqueia(self):
        self.context["issue"]["body"] = issue_body().replace("a" * 40, "b" * 40)
        with self.assertRaisesRegex(pub.PublicationError, "Baseline Git"):
            self._plan()

    def test_baseline_truncado_nao_e_aprovacao_suficiente(self):
        self.context["issue"]["body"] = issue_body().replace("a" * 40, "a" * 12)
        with self.assertRaisesRegex(pub.PublicationError, "Baseline Git"):
            self._plan()

    def test_baseline_exige_objeto_git_correspondente(self):
        self.assertEqual(self._plan()["base_tree"], "d" * 40)
        for commit in (None, {"sha": "b" * 40}, {"sha": "a" * 40, "tree": {"sha": "d"}}):
            with self.subTest(commit=commit):
                self.context["base_commit"] = commit
                with self.assertRaisesRegex(pub.PublicationError, "Objeto .* base Git"):
                    self._plan()

    def test_intake_out_of_scope_nao_publica(self):
        self.context["issue"]["labels"] = []
        with self.assertRaisesRegex(pub.PublicationError, "Intake F1"):
            self._plan()

    def test_sem_acesso_live_negado(self):
        self.context["repository"]["permissions"] = {"pull": True}
        with self.assertRaisesRegex(pub.PublicationError, "ACL"):
            self._plan()

    def test_outbox_legacy_nao_pode_publicar(self):
        self.data.pop("schema")
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        with self.assertRaisesRegex(pub.PublicationError, "legada"):
            self._outbox()

    def test_outbox_legacy_cli_bloqueia_sem_gh_ou_proveniencia(self):
        self.data.pop("schema")
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        stderr = io.StringIO()
        with patch.object(pub, "verify_provenance",
                          side_effect=AssertionError("proveniencia indevida")):
            with patch.object(pub.subprocess, "run",
                              side_effect=AssertionError("gh indevido")):
                with contextlib.redirect_stderr(stderr):
                    result = pub.main([
                        "--outbox", str(self.outbox),
                        "--approval-comment", str(self.approval_id),
                    ])
        self.assertEqual(result, 1)
        self.assertIn("legada", stderr.getvalue())
        self.assertNotIn("proveniencia indevida", stderr.getvalue())
        self.assertNotIn("gh indevido", stderr.getvalue())

    def test_colisao_marcador_de_outro_autor_bloqueia(self):
        marker = pub.MARKER_PREFIX + self.data["execution_id"] + " -->"
        self.context["comments"].append({
            "id": 12, "body": "FALSO\n" + marker,
            "user": {"login": "outro"}, "updated_at": "2026-11-15",
        })
        with self.assertRaisesRegex(pub.PublicationError, "sem autenticidade"):
            self._plan()

    def test_comment_existente_eh_idempotente(self):
        plan = self._plan()
        self.context["comments"].append({
            "id": 99, "body": plan["body"], "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
            "updated_at": "2026-11-15",
        })
        existing = self._plan()
        self.assertEqual(existing["action"], "ALREADY_PUBLISHED")
        self.assertEqual(existing["published_comment_id"], 99)
        result = self._apply(existing)
        self.assertEqual(result["status"], "JA_PUBLICADO")
        self.assertEqual(result["remote_writes"], 0)

    def test_comentario_existente_exige_id_numerico_do_po(self):
        plan = self._plan()
        for identity in (
                {"login": pub.OWNER},
                {"login": pub.OWNER, "id": 12345},
                {"login": pub.OWNER, "id": str(pub.PO_GITHUB_ID)}):
            with self.subTest(identity=identity):
                self.context["comments"] = [{
                    "id": 888, "body": plan["body"], "user": identity,
                }]
                with self.assertRaisesRegex(pub.PublicationError, "sem autenticidade"):
                    self._plan()
        self.context["comments"] = []

    def test_duplicado_remoto_bloqueia(self):
        plan = self._plan()
        for index in (30, 31):
            self.context["comments"].append({
                "id": index, "body": plan["body"],
                "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
            })
        with self.assertRaisesRegex(pub.PublicationError, "Colisao"):
            self._plan()

    def test_race_between_live_snapshots_bloqueia_sem_post(self):
        calls = []
        def reader(*_):
            calls.append("READ")
            if len(calls) == 2:
                self.context["comments"].append({
                    "id": 200, "body": "Alterado externamente",
                    "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
                })
            return self.context
        with self.assertRaisesRegex(pub.PublicationError, "Corrida"):
            self._apply(reader=reader)
        self.assertEqual(calls, ["READ", "READ"])
        self.assertFalse(any(x["event"] == "ATTEMPT_POST" for x in self.audit))

    def test_alteracao_da_aprovacao_bloqueia_antes_de_write(self):
        plan = self._plan()
        self.context["approval"]["updated_at"] = "2026-11-16T12:00:00Z"
        with self.assertRaisesRegex(pub.PublicationError, "Snapshot LIVE mudou"):
            self._apply(plan)

    def test_frase_humana_incorreta_bloqueia(self):
        with self.assertRaisesRegex(pub.PublicationError, "humana"):
            self._apply(answer=lambda _: "sim")
        self.assertEqual(self.audit, [])

    def test_recibo_duravel_pendente_gravado_antes_do_post(self):
        plan = self._plan()
        def poster(*_):
            lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
            payload = json.loads(lock.read_text(encoding="utf-8"))
            self.assertEqual(payload["publication_status"], "PENDENTE_PUBLICACAO")
            self.assertEqual(payload["remote_effect"], "INDETERMINADO")
            self.assertTrue(payload["requires_reconciliation"])
            self.assertFalse(payload["retry_agents"])
            return {"id": 8080}
        with self.assertRaises(pub.PublicationPending):
            self._apply(plan, poster=poster)
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        self.assertEqual(
            json.loads(lock.read_text(encoding="utf-8"))["publication_status"],
            "PENDENTE_PUBLICACAO")

    def test_outbox_reprovada_nos_testes_sem_codex_eh_valida(self):
        self.data["third_attempt_status"] = "TESTES_REPROVADOS"
        self.data["evidence_files"] = list(pub.EVIDENCE_FILES_TESTS_REPROVADOS)
        (self.root / "attempt-03" / "auditoria_codex.md").unlink()
        (self.root / "attempt-03" / "codex.log").unlink()
        state = json.loads((self.root / "execucao.json").read_text(encoding="utf-8"))
        state["attempts"][2]["status"] = "TESTES_REPROVADOS"
        state["attempts"][2]["codex_verdict"] = "NAO_EXECUTADO"
        (self.root / "execucao.json").write_text(
            json.dumps(state), encoding="utf-8")
        self.data["provenance"] = create_provenance(self.root)
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        validated = self._outbox()
        self.assertEqual(validated["third_attempt_status"], "TESTES_REPROVADOS")
        self.assertEqual(validated["evidence_files"],
                         list(pub.EVIDENCE_FILES_TESTS_REPROVADOS))
        self.assertEqual(self._plan()["action"], "POST_COMMENT")

    def test_e3b_string_e_flag_sozinhas_nao_atestam_missao_f7(self):
        from chdevflow.core import attested_executor as e3b
        from chdevflow.core import po_escalation_runtime_receipt as external
        state_path = self.root / "execucao.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["test_execution"] = "docker-attested-e3b-sigstore:" + e3b.IMAGE_ID
        state["os_isolation_verified"] = True
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.data["provenance"] = create_provenance(self.root)
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        with patch(
                "chdevflow.core.po_escalation_provenance.verify_runtime_receipt",
                side_effect=external.ExternalRuntimeReceiptError("nao esta pinado")):
            with self.assertRaisesRegex(
                    external.ExternalRuntimeReceiptError, "nao esta pinado"):
                self._outbox()
        # Mesmo sem alterar SHA do codigo, prova de build nao basta.
        with patch(
                "chdevflow.core.po_escalation_provenance.verify_runtime_receipt",
                return_value={"schema": external.SCHEMA}) as verified:
            self.assertEqual(self._outbox()["execution_id"], self.data["execution_id"])
            verified.assert_called_once()

    def test_e3b_imagem_falsa_ou_flag_false_bloqueia_f7(self):
        state_path = self.root / "execucao.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for image, flag in (("sha256:" + "f" * 64, True),
                            ("sha256:" + "e" * 64, False)):
            with self.subTest(image=image, flag=flag):
                state["test_execution"] = "docker-attested-e3b-sigstore:" + image
                state["os_isolation_verified"] = flag
                state_path.write_text(json.dumps(state), encoding="utf-8")
                self.data["provenance"] = create_provenance(self.root)
                self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Docker isolada"):
                    self._outbox()

    def test_docker_legado_nao_e_mais_publicavel_nem_com_flag_true(self):
        state_path = self.root / "execucao.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["test_execution"] = "docker-readonly-no-network:sha256:" + "c" * 64
        state["os_isolation_verified"] = True
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.data["provenance"] = create_provenance(self.root)
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        self.mock_runtime_receipt.reset_mock()
        with self.assertRaisesRegex(ValueError, "executor E3-B atestado"):
            self._outbox()
        self.mock_runtime_receipt.assert_not_called()
        # No F6, hashes continuam legiveis para diagnostico local.
        self.assertEqual(
            verify_provenance(self.root, self.data),
            self.data["provenance"])

    def test_proveniencia_sem_isolamento_docker_nao_e_publicavel(self):
        state_path = self.root / "execucao.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["test_execution"] = "host"
        state["os_isolation_verified"] = False
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.data["provenance"] = create_provenance(self.root)
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Docker isolada"):
            self._outbox()

    def test_f6_host_preserva_integridade_sem_liberar_publicacao_f7(self):
        state_path = self.root / "execucao.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["test_execution"] = "host"
        state["os_isolation_verified"] = False
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.data["provenance"] = create_provenance(self.root)
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        self.assertEqual(
            verify_provenance(self.root, self.data),
            self.data["provenance"])
        with self.assertRaisesRegex(ValueError, "Docker isolada"):
            self._outbox()

    def test_proveniencia_sem_flag_isolamento_nao_publica(self):
        state_path = self.root / "execucao.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["os_isolation_verified"] = False
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.data["provenance"] = create_provenance(self.root)
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Docker isolada"):
            self._outbox()

    def test_outbox_com_json_duplicado_falha_fechado(self):
        original = self.outbox.read_text(encoding="utf-8")
        self.outbox.write_text(
            original.replace('"schema":', '"schema": "LEGADA", "schema":', 1),
            encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicada"):
            self._outbox()

    def test_estado_execucao_json_duplicado_falha_fechado(self):
        record_path = self.root / "execucao.json"
        original = record_path.read_text(encoding="utf-8")
        record_path.write_text(
            original.replace('"status":', '"status":"AGUARDANDO_PO","status":', 1),
            encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicada"):
            self._outbox()

    def test_prova_de_proveniencia_detecta_log_adulterado(self):
        (self.root / "attempt-01" / "testes.log").write_text(
            "log falsificado", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Hashes"):
            self._outbox()

    def test_prova_de_proveniencia_detecta_historico_adulterado(self):
        state = json.loads((self.root / "execucao.json").read_text(encoding="utf-8"))
        state["returns_used"] = 0
        (self.root / "execucao.json").write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "tres tentativas"):
            self._outbox()

    def test_prova_de_proveniencia_exige_manifesto(self):
        (self.root / "manifesto_missao.json").unlink()
        with self.assertRaises(ValueError):
            self._outbox()

    def test_outbox_v1_sem_causa_terceira_reprovacao_nao_publica(self):
        self.data.pop("third_attempt_status")
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        with self.assertRaisesRegex(pub.PublicationError, "causa"):
            self._outbox()

    def test_resposta_post_exige_id_numerico_autentico_do_po(self):
        # Apenas simulacao de GH; a constante permanece desativada no codigo.
        forged = [
            {"id": 900, "user": {"login": pub.OWNER}},
            {"id": 900, "user": {"login": pub.OWNER, "id": 999}},
            {"id": 900, "user": {"login": pub.OWNER, "id": str(pub.PO_GITHUB_ID)}},
            {"id": 900, "user": {"login": "outro", "id": pub.PO_GITHUB_ID}},
            {"id": 900},
        ]
        with patch.object(pub, "REMOTE_PUBLICATION_ENABLED", True):
            for candidate in forged:
                with self.subTest(candidate=candidate):
                    with patch.object(pub, "_gh_json", return_value=candidate):
                        with self.assertRaisesRegex(
                                pub.PublicationError, "autoria numerica"):
                            pub._post_comment(85, "teste sem POST real")
            valid = {"id": 900, "user": {
                "login": pub.OWNER, "id": pub.PO_GITHUB_ID}}
            with patch.object(pub, "_gh_json", return_value=valid) as gh:
                self.assertEqual(
                    pub._post_comment(85, "teste sem POST real"), valid)
                gh.assert_called_once()

    def test_post_unico_e_readback_verificado(self):
        calls = []
        def poster(issue, body):
            calls.append((issue, body))
            self.context["comments"].append({
                "id": 1234, "body": body, "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
            })
            return {"id": 1234}
        result = self._apply(poster=poster)
        self.assertEqual(result["status"], "PUBLICADO_VERIFICADO")
        self.assertEqual(result["comment_id"], 1234)
        self.assertEqual(len(calls), 1)
        self.assertEqual([event["event"] for event in self.audit],
                         ["ATTEMPT_POST", "PUBLICADO_VERIFICADO"])
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        verified = json.loads(lock.read_text(encoding="utf-8"))
        self.assertEqual(verified["publication_status"], "PUBLICADO_VERIFICADO")
        self.assertEqual(verified["comment_id"], 1234)

    def test_lock_local_bloqueia_publicacao_concorrente(self):
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        lock.write_text("outra tentativa em andamento", encoding="utf-8")
        with self.assertRaisesRegex(pub.PublicationError, "anterior"):
            self._apply(poster=lambda *_: self.fail("POST concorrente"))
        self.assertTrue(lock.exists())

    def test_lock_permanece_apos_post_inconclusivo(self):
        plan = self._plan()
        with self.assertRaises(pub.PublicationPending):
            self._apply(
                plan, poster=lambda *_: (_ for _ in ()).throw(TimeoutError()))
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        self.assertTrue(lock.exists())
        with self.assertRaises(pub.PublicationError):
            self._apply(
                plan, poster=lambda *_: self.fail("retry duplicado"))
        self.assertEqual(self.audit[-1]["event"], "PENDENTE_PUBLICACAO")

    def test_ruleset_ausente_bloqueia_reserva_e_post(self):
        self.gate.side_effect = self.guard_reservation
        with patch.object(pub, "_gh_json", return_value=[]):
            with self.assertRaisesRegex(pub.PublicationError, "imutabilidade"):
                self._apply(poster=lambda *_: self.fail("POST sem ruleset"))
        self.reservations.assert_not_called()

    def test_preflight_exige_ruleset_pinado_e_autor_sem_bypass(self):
        self.gate.side_effect = self.guard_reservation
        rule = {
            "id": pub.RESERVATION_RULESET_ID, "source_type": "Repository",
            "source": pub.REPO, "target": "tag", "enforcement": "active",
            "bypass_actors": [], "current_user_can_bypass": "never",
            "conditions": {"ref_name": {"include": [NAMESPACE + "*"], "exclude": []}},
            "rules": [{"type": "update"}, {"type": "deletion"}],
        }
        po = {"id": pub.PO_GITHUB_ID, "login": pub.OWNER}
        repo = {"full_name": pub.REPO, "permissions": {"push": True}}
        with patch.object(pub, "_gh_json", side_effect=[rule, po, repo]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(pub.main(["--verify-reservation-policy"]), 0)
            self.assertEqual(json.loads(output.getvalue())["ruleset_id"], pub.RESERVATION_RULESET_ID)
        for changed in ({"current_user_can_bypass": "always"}, {"bypass_actors": None},
                        {"id": 123}, {"rules": [{"type": "deletion"}]}):
            with self.subTest(changed=changed):
                with patch.object(pub, "_gh_json", return_value={**rule, **changed}):
                    with self.assertRaisesRegex(pub.PublicationError, "imutabilidade"):
                        self.guard_reservation()
        with patch.object(pub, "_gh_json", side_effect=[rule, {**po, "id": 123}, repo]):
            with self.assertRaisesRegex(pub.PublicationError, "Identidade"):
                self.guard_reservation()

    def test_sem_atestacao_bloqueia_reserva_e_post(self):
        self.attestation.side_effect = self.verify_attestation
        with patch.object(pub, "_f7_remote_trust_policy",
                          side_effect=pub.PublicationError("Politica F7 remota ausente")):
            with self.assertRaisesRegex(pub.PublicationError, "Politica F7 remota"):
                self._apply(poster=lambda *_: self.fail("POST sem atestacao"))
        self.reservations.assert_not_called()

    def test_atestacao_openssh_rejeita_dossie_adulterado_e_assinante_local(self):
        self.attestation.side_effect = self.verify_attestation
        producer_sha = "e" * 40
        origin = "ci-f7:issuer-receipt-1"
        with tempfile.TemporaryDirectory() as isolated_issuer:
            trusted, untrusted = (Path(isolated_issuer) / name for name in ("trusted", "local"))
            for key in (trusted, untrusted):
                subprocess.run(
                    ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                    capture_output=True, check=True)
            key = " ".join(trusted.with_suffix(".pub").read_text(encoding="ascii").split()[:2])
            path = self.root / "f7-attestation.json"

            def sign(statement, signer):
                signed = subprocess.run(
                    ["ssh-keygen", "-Y", "sign", "-n", SSH_NAMESPACE, "-f", str(signer)],
                    input=statement_bytes(statement), capture_output=True, check=True)
                signature = signed.stdout.decode("ascii").replace("\r\n", "\n")
                path.write_text(json.dumps({"statement": statement, "signature": signature}),
                                encoding="ascii")

            def observe():
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    code = pub.main(["--outbox", str(self.outbox), "--verify-attestation"])
                return code, output.getvalue()

            policy = {
                "trusted_key": key, "producer_sha": producer_sha,
                "revocations": "NONE", "producer_workflow_id": 42,
                "source_repo_id": pub.F7_REPOSITORY_ID,
                "v1_workflow_id": 4242,
                "key_fingerprint": "SHA256:teste",
            }
            with (patch.object(pub, "_f7_remote_trust_policy", return_value=policy),
                  patch.object(pub, "verify_v1_producer_origin",
                               return_value={"run_id": 42}) as origin_check):
                original = execution_statement(
                    self._outbox(), producer_sha=producer_sha, producer_run=origin)
                sign(original, trusted)
                code, result = observe()
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(result)["producer_run"], origin)
                origin_check.assert_called()

                (self.root / "attempt-02" / "testes.log").write_text(
                    "Log alterado e hashes locais recalculados", encoding="utf-8")
                self.data["provenance"] = create_provenance(self.root)
                self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
                with contextlib.redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(observe()[0], 1)
                self.assertIn("diverge do dossie", error.getvalue())

                sign(execution_statement(self._outbox(), producer_sha=producer_sha,
                                         producer_run=origin), untrusted)
                with contextlib.redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(observe()[0], 1)
                self.assertIn("nao corresponde ao produtor", error.getvalue())

    def test_politica_remota_f7_nao_herda_chave_do_ambiente(self):
        import base64
        key_blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + b"x" * 32
        key = "ssh-ed25519 " + base64.b64encode(key_blob).decode("ascii")
        vars_ = {
            "CH_F7_TRUSTED_RUNNER_PUBKEY": key,
            "CH_F7_TRUSTED_RUNNER_SHA": "e" * 40,
            "CH_F7_REVOKED_RUNNER_FINGERPRINTS": "NONE",
            "CH_F7_PRODUCER_WORKFLOW_ID": "42",
            "CH_F7_V1_PRODUCER_WORKFLOW_ID": "4242",
        }
        def api(*args):
            endpoint = args[-1]
            if endpoint == f"repos/{pub.REPO}":
                return {"full_name": pub.REPO, "id": pub.F7_REPOSITORY_ID}
            name = endpoint.rsplit("/", 1)[-1]
            return {"name": name, "value": vars_[name]}
        with (patch.object(pub, "_gh_json", side_effect=api) as get,
              patch.object(pub, "F7_TRUST_KEY_FINGERPRINT_PIN",
                           pub.validate_trusted_key(key, "NONE")),
              patch.object(pub, "F7_TRUSTED_PRODUCER_SHA_PIN", "e" * 40),
              patch.object(pub, "F7_TRUSTED_V1_WORKFLOW_ID_PIN", 4242),
              patch.dict(os.environ, {
                  "CH_F7_TRUSTED_RUNNER_PUBKEY": "chave-forjada",
                  "CH_F7_TRUSTED_RUNNER_SHA": "f" * 40,
              })):
            policy = pub._f7_remote_trust_policy()
        self.assertEqual(policy["trusted_key"], key)
        self.assertEqual(policy["producer_sha"], "e" * 40)
        self.assertEqual(policy["producer_workflow_id"], 42)
        self.assertEqual(get.call_count, 6)

    def test_politica_remota_f7_nega_vars_ausentes_ou_violadas(self):
        import base64
        key_blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + b"x" * 32
        key = "ssh-ed25519 " + base64.b64encode(key_blob).decode("ascii")
        base = {
            "CH_F7_TRUSTED_RUNNER_PUBKEY": key,
            "CH_F7_TRUSTED_RUNNER_SHA": "e" * 40,
            "CH_F7_REVOKED_RUNNER_FINGERPRINTS": "NONE",
            "CH_F7_PRODUCER_WORKFLOW_ID": "42",
            "CH_F7_V1_PRODUCER_WORKFLOW_ID": "4242",
        }
        variants = (
            ("missing", "CH_F7_TRUSTED_RUNNER_PUBKEY", None),
            ("bad-sha", "CH_F7_TRUSTED_RUNNER_SHA", "curto"),
            ("bad-workflow", "CH_F7_PRODUCER_WORKFLOW_ID", "0"),
            ("bad-v1-workflow", "CH_F7_V1_PRODUCER_WORKFLOW_ID", "0"),
            ("missing-revocation", "CH_F7_REVOKED_RUNNER_FINGERPRINTS", ""),
        )
        for label, field, changed in variants:
            with self.subTest(label=label):
                data = {**base, field: changed}
                def api(*args):
                    endpoint = args[-1]
                    if endpoint == f"repos/{pub.REPO}":
                        return {"full_name": pub.REPO, "id": pub.F7_REPOSITORY_ID}
                    name = endpoint.rsplit("/", 1)[-1]
                    return {"name": name, "value": data[name]}
                with (patch.object(pub, "_gh_json", side_effect=api),
                      patch.object(pub, "F7_TRUST_KEY_FINGERPRINT_PIN",
                                   pub.validate_trusted_key(key, "NONE")),
                      patch.object(pub, "F7_TRUSTED_PRODUCER_SHA_PIN", "e" * 40),
                      patch.object(pub, "F7_TRUSTED_V1_WORKFLOW_ID_PIN", 4242)):
                    with self.assertRaises(pub.PublicationError):
                        pub._f7_remote_trust_policy()
        with patch.object(pub, "_gh_json",
                          return_value={"id": 999, "full_name": pub.REPO}) as gh:
            with self.assertRaisesRegex(pub.PublicationError, "repositorio"):
                pub._f7_remote_trust_policy()
            gh.assert_called_once()

    def test_trust_key_de_repo_nega_sem_pin_versionado(self):
        import base64
        key_blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + b"x" * 32
        key = "ssh-ed25519 " + base64.b64encode(key_blob).decode("ascii")
        vals = {
            "CH_F7_TRUSTED_RUNNER_PUBKEY": key,
            "CH_F7_TRUSTED_RUNNER_SHA": "e" * 40,
            "CH_F7_REVOKED_RUNNER_FINGERPRINTS": "NONE",
            "CH_F7_PRODUCER_WORKFLOW_ID": "42",
            "CH_F7_V1_PRODUCER_WORKFLOW_ID": "4242",
        }
        def api(*args):
            endpoint = args[-1]
            if endpoint == f"repos/{pub.REPO}":
                return {"full_name": pub.REPO, "id": pub.F7_REPOSITORY_ID}
            name = endpoint.rsplit("/", 1)[-1]
            return {"name": name, "value": vals[name]}
        with patch.object(pub, "_gh_json", side_effect=api):
            with self.assertRaisesRegex(pub.PublicationError, "Politica F7 remota"):
                pub._f7_remote_trust_policy()
            with patch.object(pub, "F7_TRUST_KEY_FINGERPRINT_PIN",
                              "SHA256:" + "x" * 43):
                with self.assertRaisesRegex(pub.PublicationError, "Politica F7 remota"):
                    pub._f7_remote_trust_policy()

    def test_reserva_git_real_sobrevive_post_inconclusivo_e_troca_de_executor(self):
        if os.name == "nt" and "#!sandbox." in str(self.root):
            self.skipTest("sandbox Windows bloqueia o processo Git receive-pack")
        plan = self._plan()
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            remote = root / "remote.git"
            subprocess.run(
                ["git", "init", "--bare", "--template=", str(remote)],
                check=True, capture_output=True)
            hook = remote / "hooks" / "pre-receive"
            hook.parent.mkdir(exist_ok=True)
            hook.write_text(
                "#!/bin/sh\nwhile read old new ref; do\n"
                "  case \"$ref\" in\n"
                "    refs/tags/chdevflow-f7-publication/*)\n"
                "      [ \"$old\" = 0000000000000000000000000000000000000000 ] || exit 1 ;;\n"
                "  esac\ndone\n", encoding="ascii", newline="\n")
            hook.chmod(0o755)
            outboxes = [
                shutil.copytree(self.root, root / name) / self.outbox.name
                for name in ("executor-a", "executor-b", "executor-c")
            ]
            barrier = threading.Barrier(2, timeout=20)
            posts = []

            class ConcurrentStore(GitReservationStore):
                def claim(self, value):
                    barrier.wait()
                    return super().claim(value)

            self.reservations.side_effect = lambda: ConcurrentStore(remote.as_posix())

            def timeout(issue, body):
                posts.append((issue, body))
                raise TimeoutError("resposta HTTP perdida")

            def attempt(outbox):
                try:
                    pub.apply_publication_plan(
                        outbox, plan, plan["digest"], reader=lambda *_: self.context,
                        poster=timeout, audit=lambda _: None,
                        human_prompt=lambda _: "APROVO F7 PUBLICAR " + plan["digest"][:12])
                except pub.PublicationPending as exc:
                    return str(exc)
                self.fail("A publicacao com timeout nao pode terminar confirmada")

            with patch.object(pub, "REMOTE_PUBLICATION_ENABLED", True):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    outcomes = list(pool.map(attempt, outboxes[:2]))
                self.assertTrue(any("nenhum POST autorizado" in item for item in outcomes))
                self.assertTrue(any("Envio inconclusivo" in item for item in outcomes))
                self.assertEqual(posts, [(plan["issue"], plan["body"])])

                store = GitReservationStore(remote.as_posix())
                self.reservations.side_effect = lambda: store
                receipt = pub.reconcile_pending_publication(
                    outboxes[2], plan, reader=lambda *_: self.context)
                self.assertEqual(receipt["status"], "COMENTARIO_NAO_OBSERVADO")
                self.assertEqual(receipt["reservation_sha"], store.read(plan))
                self.assertFalse(receipt["retry_allowed"])
                self.assertIn("nenhum POST autorizado", attempt(outboxes[2]))
                self.assertEqual(len(posts), 1)

            ref = NAMESPACE + plan["execution_id"]
            deletion = subprocess.run(
                ["git", "--git-dir", str(remote), "push", str(remote), ":" + ref],
                capture_output=True, check=False)
            self.assertNotEqual(deletion.returncode, 0)
            self.assertIn(b"pre-receive hook declined", deletion.stdout + deletion.stderr)
            self.assertEqual(receipt["reservation_sha"], store.read(plan))
            with self.assertRaisesRegex(ReservationError, "outro plano"):
                store.read({**plan, "digest": "f" * 64})

            class LostAcknowledgmentStore(GitReservationStore):
                def _git(self, directory, *args, **kwargs):
                    output = super()._git(directory, *args, **kwargs)
                    if args[0] == "push":
                        raise ReservationError("resposta da reserva perdida")
                    return output

            another = {**plan, "execution_id": "d" * 32}
            with self.assertRaisesRegex(ReservationError, "nao confirmada"):
                LostAcknowledgmentStore(remote.as_posix()).claim(another)
            self.assertRegex(store.read(another), r"^[0-9a-f]{40}$")
            with self.assertRaisesRegex(ReservationError, "nao confirmada"):
                store.claim(another)
            replacement = store.read(another)
            mutation = subprocess.run(
                ["git", "--git-dir", str(remote), "push", "--force", str(remote),
                 replacement + ":" + ref], capture_output=True, check=False)
            self.assertIn(b"pre-receive hook declined", mutation.stdout + mutation.stderr)
            self.assertNotEqual(mutation.returncode, 0)
            self.assertEqual(receipt["reservation_sha"], store.read(plan))

    def test_project_existente_preserva_campos_manuais(self):
        project = {
            "items": [{
                "id": "PVTI_123", "Status": "In Progress",
                "Etapa CH": "AGUARDANDO_PO",
                "content": {
                    "type": "Issue", "repository": pub.REPO, "number": 85,
                    "url": "https://github.com/hallanbrito/CHDevFlow/issues/85",
                },
            }], "totalCount": 1,
        }
        self.context["project"] = project
        old = copy.deepcopy(project)
        plan = self._plan()
        self.assertEqual(plan["project_state"], "JA_EXISTE_NO_PROJECT")
        self.assertEqual(plan["remote_project_writes"], 0)
        self.assertEqual(project, old)

    def test_post_inconclusivo_nao_reexecuta_agentes_nem_retry(self):
        calls = []
        def fail(issue, body):
            calls.append("POST")
            raise TimeoutError("quota, segredo-o-que-for")
        with self.assertRaisesRegex(pub.PublicationPending, "reconciliar"):
            self._apply(poster=fail)
        self.assertEqual(calls, ["POST"])
        self.assertEqual(self.audit[-1]["event"], "PENDENTE_PUBLICACAO")
        self.assertNotIn("segredo-o-que-for", json.dumps(self.audit))

    def test_readback_inconclusivo_sinaliza_pendente(self):
        def poster(*_):
            return {"id": 1234}  # Remoto nao apareceu no snapshot
        with self.assertRaisesRegex(pub.PublicationPending, "reconciliar"):
            self._apply(poster=poster)
        self.assertEqual(self.audit[-1]["reason"], "READBACK_INCONCLUSIVO")

    def test_digest_divergente_bloqueia_antes_de_consultar(self):
        plan = self._plan()
        plan["issue"] = 123
        with self.assertRaisesRegex(pub.PublicationError, "Plano/digest"):
            self._apply(plan, reader=lambda *_: self.fail("GH chamado"))

    def test_reconciliacao_pendente_read_only_nao_reexecuta_post(self):
        plan = self._legacy_plan()
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        lock.write_text(json.dumps({
            "schema": pub.RECEIPT_SCHEMA,
            "execution_id": self.data["execution_id"],
            "digest": plan["digest"],
            "publication_status": "PENDENTE_PUBLICACAO",
        }), encoding="utf-8")
        original = lock.read_bytes()
        result = pub.reconcile_pending_publication(
            self.outbox, plan, reader=lambda *_: self.context)
        self.assertEqual(result["status"], "COMENTARIO_NAO_OBSERVADO")
        self.assertFalse(result["retry_allowed"])
        self.assertTrue(result["requires_po_decision"])
        self.assertEqual(result["remote_writes"], 0)
        self.assertEqual(lock.read_bytes(), original)

        self.context["comments"].append({
            "id": 7711, "body": plan["body"],
            "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
            "updated_at": "2026-11-15T15:00:00Z",
        })
        found = pub.reconcile_pending_publication(
            self.outbox, plan, reader=lambda *_: self.context)
        self.assertEqual(found["status"], "COMENTARIO_REMOTO_ENCONTRADO")
        self.assertEqual(found["comment_id"], 7711)
        self.assertEqual(found["remote_writes"], 0)
        self.assertEqual(lock.read_bytes(), original)

    def test_reconciliacao_readback_exige_id_numerico_do_po(self):
        plan = self._legacy_plan()
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        lock.write_text(json.dumps({
            "schema": pub.RECEIPT_SCHEMA,
            "execution_id": self.data["execution_id"],
            "digest": plan["digest"],
            "publication_status": "PENDENTE_PUBLICACAO",
        }), encoding="utf-8")
        for identity in (
                {"login": pub.OWNER},
                {"login": pub.OWNER, "id": 12345},
                {"login": pub.OWNER, "id": str(pub.PO_GITHUB_ID)}):
            with self.subTest(identity=identity):
                self.context["comments"] = [{
                    "id": 992, "body": plan["body"], "user": identity
                }]
                with self.assertRaisesRegex(pub.PublicationError, "nao autentico"):
                    pub.reconcile_pending_publication(
                        self.outbox, plan, reader=lambda *_: self.context)
        self.context["comments"] = []

    def test_reconciliacao_exige_sessao_com_id_numerico_po(self):
        plan = self._legacy_plan()
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        lock.write_text(json.dumps({
            "schema": pub.RECEIPT_SCHEMA,
            "execution_id": self.data["execution_id"],
            "digest": plan["digest"],
            "publication_status": "PENDENTE_PUBLICACAO",
        }), encoding="utf-8")
        original = self.context["who"]
        try:
            for identity in (
                    {"login": pub.OWNER},
                    {"login": pub.OWNER, "id": 12345},
                    {"login": pub.OWNER, "id": str(pub.PO_GITHUB_ID)}):
                with self.subTest(identity=identity):
                    self.context["who"] = identity
                    with self.assertRaisesRegex(pub.PublicationError, "Identidade LIVE"):
                        pub.reconcile_pending_publication(
                            self.outbox, plan, reader=lambda *_: self.context)
        finally:
            self.context["who"] = original

    def test_reconciliacao_apos_revogacao_e_issue_closed(self):
        plan = self._legacy_plan()
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        lock.write_text(json.dumps({
            "schema": pub.RECEIPT_SCHEMA,
            "execution_id": self.data["execution_id"],
            "digest": plan["digest"],
            "publication_status": "PENDENTE_PUBLICACAO",
        }), encoding="utf-8")
        self.context["issue"]["state"] = "CLOSED"
        self.context["approval"]["body"] = "REVOGADA"
        self.context["comments"].append({
            "id": 9090, "body": plan["body"],
            "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
        })
        result = pub.reconcile_pending_publication(
            self.outbox, plan, reader=lambda *_: self.context)
        self.assertEqual(result["comment_id"], 9090)
        self.assertEqual(result["remote_writes"], 0)
        self.assertFalse(result["retry_allowed"])

    def test_reconciliacao_journal_divergente_bloqueia(self):
        plan = self._legacy_plan()
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        lock.write_text(json.dumps({
            "schema": pub.RECEIPT_SCHEMA,
            "execution_id": self.data["execution_id"],
            "digest": "f" * 64,
            "publication_status": "PENDENTE_PUBLICACAO",
        }), encoding="utf-8")
        with self.assertRaisesRegex(pub.PublicationError, "Journal divergente"):
            pub.reconcile_pending_publication(
                self.outbox, plan, reader=lambda *_: self.fail("GH acionado"))

    def test_reconciliacao_cli_mock_sem_post_e_sem_escrita_local(self):
        plan = self._legacy_plan()
        plan_path = self.root / "recon-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        lock.write_text(json.dumps({
            "schema": pub.RECEIPT_SCHEMA,
            "execution_id": self.data["execution_id"],
            "digest": plan["digest"],
            "publication_status": "PENDENTE_PUBLICACAO",
        }), encoding="utf-8")
        with patch.object(pub, "_reconciliation_context", return_value=self.context):
            with patch.object(pub, "_post_comment",
                              side_effect=AssertionError("POST proibido")):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    exit_code = pub.main([
                        "--outbox", str(self.outbox),
                        "--reconcile-plan", str(plan_path),
                    ])
        self.assertEqual(exit_code, 0)
        status = json.loads(output.getvalue())
        self.assertEqual(status["status"], "COMENTARIO_NAO_OBSERVADO")
        self.assertEqual(status["remote_writes"], 0)
        self.assertFalse(status["retry_allowed"])

    def test_api_apply_bloqueia_callback_remoto_com_gate_off(self):
        """Nao basta barrar CLI e _post_comment: a API tambem deve bloquear."""
        plan = self._plan()
        calls = []
        with self.assertRaisesRegex(pub.PublicationError, "desativada"):
            pub.apply_publication_plan(
                self.outbox, plan, plan["digest"],
                reader=lambda *_: calls.append("GET") or self.context,
                poster=lambda *_: calls.append("POST") or {"id": 1},
                human_prompt=lambda *_: calls.append("INPUT") or "sim",
                audit=lambda *_: calls.append("AUDIT"),
            )
        self.assertEqual(calls, [])
        self.assertFalse(list(self.root.glob("f7-publicacao-*.lock")))

    def test_post_real_permanece_desativado_sem_gh(self):
        with patch.object(pub, "_gh_json",
                          side_effect=AssertionError("POST real proibido")):
            with self.assertRaisesRegex(pub.PublicationError, "desativado"):
                pub._post_comment(85, "nao publicar")

    def test_cli_apply_producao_bloqueia_antes_do_journal(self):
        plan_file = self.root / "plano-bloqueado.json"
        plan_file.write_text(json.dumps(self._plan()), encoding="utf-8")
        audit_path = self.root / "auditoria-bloqueada.jsonl"
        with patch.object(pub.subprocess, "run",
                          side_effect=AssertionError("rede proibida")):
            with contextlib.redirect_stderr(io.StringIO()) as error:
                result = pub.main([
                    "--outbox", str(self.outbox),
                    "--apply-plan", str(plan_file),
                    "--confirm", self._plan()["digest"],
                    "--audit-file", str(audit_path),
                ])
        self.assertEqual(result, 1)
        self.assertIn("desativado", error.getvalue())
        self.assertFalse(audit_path.exists())
        self.assertFalse(list(self.root.glob("f7-publicacao-*.lock")))

    def test_gh_bytes_windows_unicode_sem_locale(self):
        response = subprocess.CompletedProcess(
            ["gh"], 0, b'{"title":"A\xc3\xa7\xc3\xa3o"}', b"")
        with patch.object(pub.subprocess, "run", return_value=response) as call:
            parsed = pub._gh_json("issue", "view", "85")
        self.assertEqual(parsed["title"], "Ação")
        self.assertNotIn("text", call.call_args.kwargs)
        self.assertNotIn("encoding", call.call_args.kwargs)

    def test_gh_json_com_chaves_duplicadas_falha_fechado(self):
        response = subprocess.CompletedProcess(
            ["gh"], 0, b'{"id":1,"id":2}', b"")
        with patch.object(pub.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(pub.PublicationError, "JSON/UTF-8"):
                pub._gh_json("api", "user")

    def test_local_json_duplicado_falha_fechado(self):
        path = self.root / "duplicate-plan.json"
        path.write_text('{"digest":"a","digest":"b"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicada"):
            pub._read_local_json(path)

    def test_json_nao_finito_bloqueia_entrada_e_digests(self):
        from chdevflow.core.po_escalation import _json_unique
        for invalid in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "nao finit"):
                    _json_unique('{"nested":{"value":' + invalid + '}}')

    def test_outbox_json_nao_finito_falha_antes_da_publicacao(self):
        original = self.outbox.read_text(encoding="utf-8")
        replacement = original.replace(
            '"attempts": 3', '"attempts": 3, "extra": NaN', 1)
        self.assertNotEqual(original, replacement)
        self.outbox.write_text(replacement, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nao finita"):
            self._outbox()

    def test_gh_bytes_invalidos_falha_fechado(self):
        response = subprocess.CompletedProcess(["gh"], 0, b'{"x":"' + bytes([0x9d]) + b'"}', b"")
        with patch.object(pub.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(pub.PublicationError, "UTF-8"):
                pub._gh_json("api", "user")

    def test_gh_erro_remoto_nao_exibe_token(self):
        response = subprocess.CompletedProcess(
            ["gh"], 1, b"", b"github_pat_SENSIVEL_TOKEN")
        with patch.object(pub.subprocess, "run", return_value=response):
            with self.assertRaises(pub.PublicationError) as ctx:
                pub._gh_json("api", "user")
        self.assertNotIn("SENSIVEL_TOKEN", str(ctx.exception))

    def test_default_legado_so_exibe_nao_publicavel(self):
        self.data.pop("schema")
        self.outbox.write_text(json.dumps(self.data), encoding="utf-8")
        with patch.object(pub.subprocess, "run",
                          side_effect=AssertionError("gh proibido")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = pub.main(["--outbox", str(self.outbox)])
        self.assertEqual(code, 0)
        status = json.loads(output.getvalue())
        self.assertEqual(status["status"], "OUTBOX_LEGADA_NAO_PUBLICAVEL")
        self.assertEqual(status["writes"], 0)

    def test_cli_apply_sem_digest_ou_auditoria_bloqueia(self):
        target = self.root / "plan.json"
        pub._write_json_once(target, self._plan())
        with patch.object(pub, "apply_publication_plan",
                          side_effect=AssertionError("nao deve aplicar")):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = pub.main([
                    "--outbox", str(self.outbox),
                    "--apply-plan", str(target)])
        self.assertEqual(code, 1)
        self.assertIn("BLOQUEADA", err.getvalue())

    def test_cli_falha_remota_cria_recibo_local_pendente(self):
        target = self.root / "plano.json"
        plan = self._plan()
        pub._write_json_once(target, plan)
        audit = self.root / "auditoria.jsonl"
        # Simula unicamente o caminho de escrita autorizado em laboratorio:
        # o gate de producao continua desativado por default.
        with (patch.object(pub, "REMOTE_PUBLICATION_ENABLED", True),
              patch.object(pub, "apply_publication_plan",
                           side_effect=pub.PublicationPending("post inconclusivo"))):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = pub.main([
                    "--outbox", str(self.outbox),
                    "--apply-plan", str(target),
                    "--confirm", plan["digest"],
                    "--audit-file", str(audit)])
        self.assertEqual(code, 1)
        self.assertTrue(audit.exists())
        receipt = audit.with_suffix(".pending.json")
        self.assertTrue(receipt.exists())
        record = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(record["publication_status"], "PENDENTE_PUBLICACAO")
        self.assertEqual(record["remote_effect"], "INDETERMINADO")
        self.assertIs(record["retry_agents"], False)
        self.assertIs(record["requires_reconciliation"], True)
        self.assertNotIn("secret", err.getvalue())

    def test_v1_elegivel_cli_integral_simulada_com_readback(self):
        """Homologacao de laboratorio: CLI real + GH simulado, nenhuma rede."""
        plan_file = self.root / "plano-v1.json"
        audit_file = self.root / "auditoria-v1.jsonl"
        calls = []

        def reader(issue, approval):
            calls.append(("GET_LIVE", issue, approval))
            return copy.deepcopy(self.context)

        def poster(issue, body):
            calls.append(("POST_SIMULADO", issue))
            self.context["comments"].append({
                "id": 987654, "body": body,
                "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
                "updated_at": "2026-11-15T14:00:00Z",
            })
            return {"id": 987654}

        with (patch.object(pub, "_live_context", side_effect=reader),
              patch.object(pub, "_post_comment", side_effect=poster),
              patch.object(pub, "REMOTE_PUBLICATION_ENABLED", True),
              patch.object(pub.subprocess, "run",
                           side_effect=AssertionError("rede proibida"))):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                planned = pub.main([
                    "--outbox", str(self.outbox),
                    "--approval-comment", str(self.approval_id),
                    "--plan-file", str(plan_file),
                ])
            self.assertEqual(planned, 0)
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
            self.assertEqual(plan["action"], "POST_COMMENT")
            self.assertEqual(plan["remote_project_writes"], 0)
            self.assertEqual(json.loads(output.getvalue())["digest"], plan["digest"])
            phrase = "APROVO F7 PUBLICAR " + plan["digest"][:12]
            with patch("builtins.input", return_value=phrase) as human:
                with contextlib.redirect_stdout(io.StringIO()) as result_output:
                    applied = pub.main([
                        "--outbox", str(self.outbox),
                        "--apply-plan", str(plan_file),
                        "--confirm", plan["digest"],
                        "--audit-file", str(audit_file),
                    ])
        self.assertEqual(applied, 0)
        human.assert_called_once()
        result = json.loads(result_output.getvalue())
        self.assertEqual(result["status"], "PUBLICADO_VERIFICADO")
        self.assertEqual(result["comment_id"], 987654)
        self.assertEqual(result["remote_writes"], 1)
        self.assertEqual([event[0] for event in calls].count("POST_SIMULADO"), 1)
        self.assertEqual([event[0] for event in calls].count("GET_LIVE"), 5)
        audit_events = [
            json.loads(row)["event"] for row in
            audit_file.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(audit_events, ["ATTEMPT_POST", "PUBLICADO_VERIFICADO"])
        lock = self.root / ("f7-publicacao-" + self.data["execution_id"] + ".lock")
        self.assertTrue(lock.exists())
        self.assertEqual(len(self.context["comments"]), 1)

    def test_missao_alterada_mesmo_com_digest_novo_eh_bloqueada(self):
        plan = self._plan()
        plan["mission_id"] = "F6-MISSAO-ERRADA"
        plan["digest"] = pub._digest({k: v for k, v in plan.items() if k != "digest"})
        with self.assertRaisesRegex(pub.PublicationError, "nao pertence"):
            self._apply(plan, reader=lambda *_: self.fail("gh nao deve ser chamado"))
        self.assertFalse(self.audit)

    def test_junction_de_pasta_do_dossie_bloqueia_lock(self):
        plan = self._plan()
        with patch.object(pub, "_is_link",
                          side_effect=lambda p: p == self.root):
            with self.assertRaises(pub.PublicationError):
                self._apply(
                    plan, poster=lambda *_: self.fail("post proibido"))
        self.assertFalse(any(x.get("event") == "ATTEMPT_POST" for x in self.audit))

    def test_junction_de_pasta_de_evidencia_bloqueia_outbox(self):
        from chdevflow.core import po_escalation as bridge
        with patch.object(
            bridge, "_is_link", side_effect=lambda p: p == self.root / "attempt-03"
        ):
            with self.assertRaisesRegex(ValueError, "Link/reparse"):
                self._outbox()

    def test_junction_ancestral_da_raiz_bloqueia_dossie(self):
        from chdevflow.core import po_escalation as bridge
        with patch.object(
            bridge, "_is_link", side_effect=lambda p: p == self.root.parent
        ):
            with self.assertRaisesRegex(ValueError, "ancestral"):
                self._outbox()

    def test_evidencia_com_travessia_rejeitada(self):
        from chdevflow.core import po_escalation as bridge
        with self.assertRaisesRegex(ValueError, "fora do dossie"):
            bridge._safe_file_within(self.root, "../fora.txt")

    def test_leitor_rejeita_substituicao_entre_stat_e_open(self):
        from chdevflow.core import po_escalation as bridge

        target = self.root / "original.txt"
        target.write_bytes(b"original")
        replacement = self.root / "replacement.txt"
        replacement.write_bytes(b"substituido")
        real_open = os.open

        def replace_on_open(path, flags, *args, **kwargs):
            if path in (target, target.name):
                replacement.replace(target)
            return real_open(path, flags, *args, **kwargs)

        with patch.object(bridge.os, "open", side_effect=replace_on_open):
            with self.assertRaisesRegex(ValueError, "substituido"):
                bridge._read_evidence_bytes(target)

    def test_leitor_rejeita_link_real_em_ancestral(self):
        from chdevflow.core import po_escalation as bridge

        directory = self.root / "evidencia"
        directory.mkdir()
        (directory / "log").write_bytes(b"evidencia")
        link = self.root / "link"
        if os.name == "nt":
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(directory)],
                capture_output=True, check=False)
            if result.returncode and os.environ.get("GITHUB_ACTIONS") != "true":
                self.skipTest("mklink /J indisponivel neste ambiente Windows")
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            link.symlink_to(directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Link/reparse"):
            bridge._read_evidence_bytes(link / "log")

    @unittest.skipUnless(os.name == "nt", "prefixo de caminho Windows")
    def test_leitor_aceita_prefixo_de_caminho_windows(self):
        from chdevflow.core import po_escalation as bridge

        target = self.root / "evidence.log"
        target.write_bytes(b"evidencia")
        extended = Path("\\\\?\\" + str(target))
        self.assertEqual(bridge._read_evidence_bytes(extended), b"evidencia")

    def test_gate3_vincula_sha_exato_ao_plano_aprovacao_e_comentario(self):
        plan = self._plan()
        self.assertEqual(plan["f7_audited_sha"], self.f7_sha)
        self.assertEqual(plan["f7_audited_tree"], "c" * 40)
        self.assertIn("F7_AUDITED_SHA=" + self.f7_sha, self.context["approval"]["body"])
        self.assertIn("SHA Git F7 auditado/autorizado: " + self.f7_sha, plan["body"])
        self.assertEqual(plan["digest"], pub._digest({
            key: value for key, value in plan.items() if key != "digest"}))

    def test_gate3_rejeita_pin_ausente_local_remote_ou_arvore_divergente(self):
        good = copy.deepcopy(self.context["f7_commit"])
        cases = [
            None,
            {},
            {**good, "policy_sha": "b" * 39},
            {**good, "policy_sha": "f" * 40},
            {**good, "local_sha": "f" * 40},
            {**good, "git_commit": {"sha": "f" * 40, "tree": {"sha": "c" * 40}}},
            {**good, "git_commit": {"sha": good["policy_sha"], "tree": {"sha": "c"}}},
        ]
        for changed in cases:
            with self.subTest(changed=changed):
                self.context["f7_commit"] = changed
                with self.assertRaisesRegex(pub.PublicationError, "commit F7 auditado|Arvore"):
                    self._plan()
        self.context["f7_commit"] = good

    def test_gate3_aprovacao_antiga_ou_sha_diferente_eh_negada(self):
        body = self.context["approval"]["body"]
        for bad in (body.replace(" F7_AUDITED_SHA=" + self.f7_sha, ""),
                    body.replace(self.f7_sha, "f" * 40)):
            with self.subTest(bad=bad):
                self.context["approval"]["body"] = bad
                with self.assertRaisesRegex(pub.PublicationError, "Autorizacao"):
                    self._plan()
        self.context["approval"]["body"] = body

    def test_gate3_pin_muda_entre_snapshots_bloqueia_antes_do_post(self):
        calls = []
        plan = self._plan()
        def reader(*_):
            calls.append("GET")
            if len(calls) == 2:
                self.context["f7_commit"]["policy_sha"] = "f" * 40
                self.context["f7_commit"]["local_sha"] = "f" * 40
                self.context["f7_commit"]["git_commit"]["sha"] = "f" * 40
            return self.context
        with self.assertRaisesRegex(pub.PublicationError, "Autorizacao"):
            self._apply(plan=plan, reader=reader,
                        poster=lambda *_: self.fail("POST antes do gate3"))
        self.assertEqual(calls, ["GET", "GET"])
        self.assertFalse(list(self.root.glob("f7-publicacao-*.lock")))

    def test_gate3_readback_com_arvore_f7_alterada_nao_confirma_publicacao(self):
        plan = self._plan()
        def poster(_issue, body):
            self.context["comments"].append({
                "id": 1290, "body": body, "user": {"login": "hallanbrito", "id": pub.PO_GITHUB_ID},
                "updated_at": "2026-11-16T15:00:00Z",
            })
            self.context["f7_commit"]["git_commit"]["tree"]["sha"] = "f" * 40
            return {"id": 1290}
        with self.assertRaisesRegex(pub.PublicationPending, "reconciliar LIVE"):
            self._apply(plan=plan, poster=poster)
        self.assertEqual(self.audit[-1]["reason"], "READBACK_INCONCLUSIVO")

    def test_gate3_contexto_real_exige_comprovante_runtime(self):
        def api(*args):
            endpoint = args[-1]
            if endpoint.endswith("/CH_F7_AUDITED_COMMIT_SHA"):
                return {"name": pub.F7_AUDIT_VARIABLE, "value": self.f7_sha}
            return {"sha": self.f7_sha, "tree": {"sha": "c" * 40}}
        with (patch.object(pub, "_gh_json", side_effect=api),
              patch.object(pub, "_local_f7_checkout_sha", return_value=self.f7_sha),
              patch.object(pub, "verify_loaded_f7_modules",
                           return_value="e" * 64) as verify):
            result = pub._f7_audit_context()
        self.assertEqual(result["runtime_digest"], "e" * 64)
        verify.assert_called_once()

    def test_gate3_contexto_real_bloqueia_runtime_adulterado(self):
        def api(*args):
            endpoint = args[-1]
            if endpoint.endswith("/CH_F7_AUDITED_COMMIT_SHA"):
                return {"name": pub.F7_AUDIT_VARIABLE, "value": self.f7_sha}
            return {"sha": self.f7_sha, "tree": {"sha": "c" * 40}}
        with (patch.object(pub, "_gh_json", side_effect=api),
              patch.object(pub, "_local_f7_checkout_sha", return_value=self.f7_sha),
              patch.object(pub, "verify_loaded_f7_modules",
                           side_effect=pub.RuntimeIdentityError("adulteracao"))):
            with self.assertRaisesRegex(pub.PublicationError, "Codigo carregado"):
                pub._f7_audit_context()

    def test_gate3_runtime_digest_exigido_e_pinado_no_plano(self):
        plan = self._plan()
        self.assertEqual(plan["f7_runtime_digest"], "e" * 64)
        self.assertIn("f7_audited_commit", plan["snapshot"])
        cases = (None, "curto", "f" * 63, 55)
        for changed in cases:
            with self.subTest(changed=changed):
                self.context["f7_commit"]["runtime_digest"] = changed
                with self.assertRaisesRegex(pub.PublicationError, "codigo executado"):
                    self._plan()
        self.context["f7_commit"]["runtime_digest"] = "e" * 64

    def test_gate3_runtime_drift_entre_snapshots_bloqueia_sem_post(self):
        plan = self._plan()
        calls = []
        def reader(*_):
            calls.append("GET")
            if len(calls) == 2:
                self.context["f7_commit"]["runtime_digest"] = "f" * 64
            return self.context
        with self.assertRaisesRegex(pub.PublicationError, "Corrida"):
            self._apply(plan=plan, reader=reader,
                        poster=lambda *_: self.fail("POST indevido"))
        self.assertEqual(calls, ["GET", "GET"])
        self.reservations.assert_not_called()

    def test_gate3_readback_com_runtime_alterado_nao_confirma(self):
        plan = self._plan()
        def poster(_issue, body):
            self.context["comments"].append({
                "id": 1291, "body": body,
                "user": {"login": pub.OWNER, "id": pub.PO_GITHUB_ID},
                "updated_at": "2026-11-16T16:00:00Z",
            })
            self.context["f7_commit"]["runtime_digest"] = "f" * 64
            return {"id": 1291}
        with self.assertRaisesRegex(pub.PublicationPending, "reconciliar LIVE"):
            self._apply(plan=plan, poster=poster)
        self.assertEqual(self.audit[-1]["reason"], "READBACK_INCONCLUSIVO")

    def test_gate3_plano_antigo_rejeitado_antes_de_reserva_ou_post(self):
        plan = self._plan()
        plan.pop("f7_audited_sha")
        plan["digest"] = pub._digest({key: value for key, value in plan.items()
                                      if key != "digest"})
        with self.assertRaisesRegex(pub.PublicationError, "nao pertence"):
            self._apply(plan=plan, poster=lambda *_: self.fail("POST indevido"))
        self.reservations.assert_not_called()

    def test_gate3_pin_externo_invalido_falha_antes_de_consulta_commit(self):
        with patch.object(pub, "_gh_json", return_value={
                "name": pub.F7_AUDIT_VARIABLE, "value": "curto"}) as gh:
            with self.assertRaisesRegex(pub.PublicationError, "Pin"):
                pub._f7_audit_context()
        gh.assert_called_once()

    def test_gate3_checkout_sujo_ou_git_ausente_falha_fechado(self):
        def completed(result):
            return subprocess.CompletedProcess(["git"], 0, result, b"")
        with patch.object(pub.subprocess, "run",
                          side_effect=[completed(b"b" * 40 + b"\n"),
                                       completed(b" M codigo.py\n")]):
            with self.assertRaisesRegex(pub.PublicationError, "Worktree"):
                pub._local_f7_checkout_sha()
        with patch.object(pub.subprocess, "run", side_effect=OSError("sem git")):
            with self.assertRaisesRegex(pub.PublicationError, "local nao verificavel"):
                pub._local_f7_checkout_sha()

    def test_plan_file_exclusivo(self):
        target = self.root / "plano.json"
        pub._write_json_once(target, self._plan())
        self.assertTrue(target.exists())
        with self.assertRaisesRegex(pub.PublicationError, "ja existe"):
            pub._write_json_once(target, self._plan())


if __name__ == "__main__":
    unittest.main()
