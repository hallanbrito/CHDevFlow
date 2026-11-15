"""F7 publication: testes offline sem qualquer gh real nem comentario remoto."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from chdevflow.core import po_escalation_publication as pub
from chdevflow.core.manual_pipeline_runner import Mission, SCHEMA as MISSION_SCHEMA
from chdevflow.core.po_escalation_provenance import create_provenance


def issue_body():
    return (
        "### Esteira\nAGY\n"
        "### Nível de autonomia\nCH-0\n"
        "### Objetivo e valor\nEntregar uma missao Python auditavel\n"
        "### Escopo, exclusões e critérios de aceite\n"
        "Codigo Python com testes independentes e gate humano\n"
        "### Baseline Git (branch e SHA)\nfeat/f6 abcdef0123456\n"
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
        self.approval_id = 448200
        statement = (
            "CH-GOV-01 F7 PUBLICAR PROJECT#2 ISSUE#85 "
            "EXECUTION#" + self.data["execution_id"] + " "
            "CODE_SHA256=" + self.data["code_sha256"] + " " +
            "BASE_SHA=" + self.data["provenance"]["base_sha"] + " " +
            "MISSION_DIGEST=" + self.data["provenance"]["mission_digest"] +
            " ACTION=COMMENT_ONLY"
        )
        self.context = {
            "who": {"login": "hallanbrito"},
            "repository": {"permissions": {"push": True}},
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
                "user": {"login": "hallanbrito"},
            },
            "comments": [],
        }
        self.context["approval_history"] = [self.context["approval"]]
        self.audit = []

    def _outbox(self):
        return pub._eligible_outbox(self.outbox)

    def _plan(self):
        return pub.build_publication_plan(self._outbox(), self.context)

    def _apply(self, plan=None, reader=None, poster=None, answer=None):
        plan = plan or self._plan()
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
                "user": {"login": "hallanbrito"},
                "issue_url": "https://api.github.com/repos/hallanbrito/CHDevFlow/issues/63",
                "body": ("CH-GOV-01 F7 PUBLICAR PROJECT#2 ISSUE#85 "
                         "EXECUTION#" + self.data["execution_id"] + " "
                         "CODE_SHA256=" + self.data["code_sha256"] + " " +
            "BASE_SHA=" + self.data["provenance"]["base_sha"] + " " +
            "MISSION_DIGEST=" + self.data["provenance"]["mission_digest"] +
            " ACTION=COMMENT_ONLY"),
            })

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
                    "user": {"login": "hallanbrito"},
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
            "user": {"login": "hallanbrito"},
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
            "user": {"login": "hallanbrito"},
        })
        with self.assertRaisesRegex(pub.PublicationError, "revogada"):
            self._apply(plan, poster=lambda *_: self.fail("POST desautorizado"))
        self.assertFalse(self.audit)

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
            "id": 99, "body": plan["body"], "user": {"login": "hallanbrito"},
            "updated_at": "2026-11-15",
        })
        existing = self._plan()
        self.assertEqual(existing["action"], "ALREADY_PUBLISHED")
        self.assertEqual(existing["published_comment_id"], 99)
        result = self._apply(existing)
        self.assertEqual(result["status"], "JA_PUBLICADO")
        self.assertEqual(result["remote_writes"], 0)

    def test_duplicado_remoto_bloqueia(self):
        plan = self._plan()
        for index in (30, 31):
            self.context["comments"].append({
                "id": index, "body": plan["body"],
                "user": {"login": "hallanbrito"},
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
                    "user": {"login": "hallanbrito"},
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

    def test_post_unico_e_readback_verificado(self):
        calls = []
        def poster(issue, body):
            calls.append((issue, body))
            self.context["comments"].append({
                "id": 1234, "body": body, "user": {"login": "hallanbrito"},
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

    def test_gh_bytes_windows_unicode_sem_locale(self):
        response = subprocess.CompletedProcess(
            ["gh"], 0, b'{"title":"A\xc3\xa7\xc3\xa3o"}', b"")
        with patch.object(pub.subprocess, "run", return_value=response) as call:
            parsed = pub._gh_json("issue", "view", "85")
        self.assertEqual(parsed["title"], "Ação")
        self.assertNotIn("text", call.call_args.kwargs)
        self.assertNotIn("encoding", call.call_args.kwargs)

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
        with patch.object(pub, "apply_publication_plan",
                          side_effect=pub.PublicationPending("post inconclusivo")):
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
                "user": {"login": "hallanbrito"},
                "updated_at": "2026-11-15T14:00:00Z",
            })
            return {"id": 987654}

        with (patch.object(pub, "_live_context", side_effect=reader),
              patch.object(pub, "_post_comment", side_effect=poster),
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

    def test_plan_file_exclusivo(self):
        target = self.root / "plano.json"
        pub._write_json_once(target, self._plan())
        self.assertTrue(target.exists())
        with self.assertRaisesRegex(pub.PublicationError, "ja existe"):
            pub._write_json_once(target, self._plan())


if __name__ == "__main__":
    unittest.main()
