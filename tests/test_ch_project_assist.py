"""KSYNC-03: testes offline. Nenhum acesso ao GitHub remoto ou escrita real."""
import contextlib
import copy
import io
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ch_project_assist as app

REPO = app.REPO


def item(n, *, lane=None, stage=None, labels=None, status="Todo", repo=REPO):
    obj = {"id": f"PVTI_{n}", "status": status,
           "content": {"type": "Issue", "number": n, "repository": repo,
                       "url": f"https://github.com/{repo}/issues/{n}"},
           "labels": labels if labels is not None else ["ch:workflow", "ch:chatgpt"]}
    if lane is not None:
        obj["esteira"] = lane
    if stage is not None:
        obj["etapa CH"] = stage
    return obj


def payload(*entries):
    return {"items": list(entries), "totalCount": len(entries)}


class Planning(unittest.TestCase):
    def setUp(self):
        self.stage_probe = mock.patch.object(
            app.legacy.ch_stage_evidence, "probe",
            return_value={"status": "CLEAR", "references": []}
        )
        self.stage_probe.start()
        self.addCleanup(self.stage_probe.stop)

    def test_issues_8_19_pr_evidence_never_suggests_backlog(self):
        items = payload(item(8), item(19))
        def evidence(_repo, number):
            return {"status": "WORK_FOUND", "references": [
                {"kind": "PR", "number": {8: 9, 19: 20}[number],
                 "merged_at": "2026-10-18T15:27:28Z"}
            ]}
        changes, notes, _ = app.inspect(
            items, [8, 19], lambda *_: "OPEN", activity_reader=evidence
        )
        self.assertEqual({(x["number"], x["field"]) for x in changes},
                         {(8, "Esteira"), (19, "Esteira")})
        self.assertEqual(len(notes), 2)
        self.assertTrue(all(s.startswith("ETAPA_PENDENTE_PO:") for s in notes))

    def test_pr_evidence_plan_only_lane(self):
        with mock.patch.object(
            app.legacy.ch_stage_evidence, "probe",
            return_value={"status": "WORK_FOUND", "references": [
                {"kind": "PR", "number": 20, "merged_at": "2026-10-19T00:04:13Z"}]}
        ):
            plan = app.make_plan(payload(item(19)), [19], lambda *_: "OPEN")
        self.assertEqual(
            [(e["field"], e["value"]) for e in plan["changes"]],
            [("Esteira", "ChatGPT")]
        )

    def test_timeline_timeout_blocks_backlog_and_keeps_lane(self):
        def timed_out(*_):
            raise subprocess.TimeoutExpired(cmd=["gh", "api"], timeout=45)
        changes, notes, _ = app.inspect(
            payload(item(19)), [19], lambda *_: "OPEN",
            activity_reader=timed_out
        )
        self.assertEqual([(x["field"], x["value"]) for x in changes],
                         [("Esteira", "ChatGPT")])
        self.assertIn("ETAPA_PENDENTE_PO", notes[0])
        self.assertIn("histórico falhou", notes[0])

    def test_cli_timeout_preview_reports_warning_without_traceback_or_write(self):
        with mock.patch.object(app, "fetch_project", return_value=payload(item(19))):
            with mock.patch.object(app.legacy, "issue_state", return_value="OPEN"):
                with mock.patch.object(
                    app.legacy.ch_stage_evidence, "probe",
                    side_effect=subprocess.TimeoutExpired(["gh", "api"], timeout=45)
                ):
                    with mock.patch.object(app.legacy, "gh") as writer:
                        with contextlib.redirect_stdout(io.StringIO()) as stdout:
                            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                                rc = app.main(["--issues", "19"])
        self.assertEqual(rc, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("ETAPA_PENDENTE_PO", stdout.getvalue())
        self.assertNotIn("Etapa CH: (vazio) -> BACKLOG", stdout.getvalue())
        writer.assert_not_called()

    def test_main_catches_project_fetch_timeout_without_traceback(self):
        with mock.patch.object(
            app, "fetch_project",
            side_effect=subprocess.TimeoutExpired(["gh", "project"], timeout=45)
        ):
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                rc = app.main([])
        self.assertEqual(rc, 1)
        self.assertIn("BLOQUEADO:", stderr.getvalue())

    def test_unavailable_timeline_does_not_offer_backlog(self):
        def unavailable(*_):
            raise RuntimeError("timeline unavailable")
        changes, notes, _ = app.inspect(
            payload(item(19)), [19], lambda *_: "OPEN",
            activity_reader=unavailable
        )
        self.assertEqual([x["field"] for x in changes], ["Esteira"])
        self.assertIn("histórico falhou", notes[0])

    def test_new_open_has_only_two_safe_changes(self):
        changes, notes, hashes = app.inspect(payload(item(21)), [21], lambda *_: "OPEN")
        self.assertEqual({(c["field"], c["value"]) for c in changes},
                         {("Esteira", "ChatGPT"), ("Etapa CH", "BACKLOG")})
        self.assertEqual(notes, [])
        self.assertIn("21", hashes)

    def test_closed_is_skipped_completely(self):
        changes, notes, _ = app.inspect(payload(item(22)), [22], lambda *_: "CLOSED")
        self.assertEqual(changes, [])
        self.assertIn("CLOSED", notes[0])

    def test_cross_repo_skipped(self):
        entries = payload(item(20, repo="outro/repo"), item(21))
        changes, _, _ = app.inspect(entries, None, lambda *_: "OPEN")
        self.assertEqual({x["number"] for x in changes}, {21})

    def test_conflicting_labels_and_fields_fail_closed(self):
        multi = item(20, labels=["ch:workflow", "ch:codex", "ch:agy"])
        changes, notes, _ = app.inspect(payload(multi), [20], lambda *_: self.fail())
        self.assertFalse(changes)
        self.assertIn("ambíguo", notes[0])
        with self.assertRaisesRegex(ValueError, "inseguro"):
            app.make_plan(payload(multi), [20], lambda *_: "OPEN")
        with self.assertRaisesRegex(ValueError, "inseguro"):
            app.make_plan(payload(item(20, lane="Codex")), [20], lambda *_: "OPEN")

    def test_preserves_existing_stage_and_lane(self):
        changes, _, _ = app.inspect(payload(item(23, lane="ChatGPT", stage="HOMOLOGADA")),
                                    [23], lambda *_: "OPEN")
        self.assertEqual(changes, [])

    def test_not_todo_cannot_get_backlog_or_lane(self):
        changes, _, _ = app.inspect(payload(item(23, status="Done")), [23], lambda *_: "OPEN")
        self.assertFalse(changes)

    def test_malformed_missing_duplicate_and_wrong_url(self):
        with self.assertRaisesRegex(ValueError, "incompleto"):
            app.inspect({"items": [item(1)], "totalCount": 2}, [1], lambda *_: "OPEN")
        with self.assertRaisesRegex(ValueError, "duplicada"):
            app.inspect(payload(item(1), item(1)), [1], lambda *_: "OPEN")
        bad = item(1)
        bad["content"]["url"] = "https://evil.example/1"
        with self.assertRaisesRegex(ValueError, "URL"):
            app.inspect(payload(bad), [1], lambda *_: "OPEN")
        with self.assertRaisesRegex(ValueError, "não estão"):
            app.inspect(payload(item(1)), [2], lambda *_: "OPEN")

    def test_filter_and_batch_limit(self):
        self.assertEqual(app.parse_numbers("9,2"), [2, 9])
        for s in ["1,1", "0", "a", "1,2,3,4,5,6"]:
            with self.subTest(s=s), self.assertRaises(ValueError):
                app.parse_numbers(s)
        self.assertEqual({x["number"] for x in app.inspect(
            payload(item(2), item(3)), [3], lambda *_: "OPEN")[0]}, {3})

    def test_plan_digest_prevents_edits(self):
        p = app.make_plan(payload(item(25)), [25], lambda *_: "OPEN")
        self.assertEqual(app.validate_plan(p), [25])
        changed = copy.deepcopy(p)
        changed["changes"][0]["value"] = "AGY"
        with self.assertRaisesRegex(ValueError, "alterado"):
            app.validate_plan(changed)
        changed["digest"] = app.digest({k: v for k, v in changed.items() if k != "digest"})
        with self.assertRaisesRegex(ValueError, "Estado remoto"):
            app.apply_plan(changed, changed["digest"], reader=lambda: payload(item(25)),
                           state_reader=lambda *_: "OPEN", interactive=True,
                           prompt=lambda *_: "WRONG")


class Execution(unittest.TestCase):
    def setUp(self):
        self.stage_probe = mock.patch.object(
            app.legacy.ch_stage_evidence, "probe",
            return_value={"status": "CLEAR", "references": []}
        )
        self.stage_probe.start()
        self.addCleanup(self.stage_probe.stop)
        self.live = payload(item(42))
        self.state = lambda *_: "OPEN"
        self.plan = app.make_plan(self.live, [42], self.state)
        self.writer = mock.Mock()

    def test_no_interactivity_never_writes(self):
        with self.assertRaisesRegex(ValueError, "interativo"):
            app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                           state_reader=self.state, writer=self.writer, interactive=False)
        self.writer.assert_not_called()

    def test_wrong_digest_or_confirmation_never_writes(self):
        with self.assertRaisesRegex(ValueError, "Digest"):
            app.apply_plan(self.plan, "wrong", reader=lambda: self.live,
                           state_reader=self.state, writer=self.writer, interactive=True)
        with self.assertRaisesRegex(ValueError, "Confirmação"):
            app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                           state_reader=self.state, writer=self.writer, interactive=True,
                           prompt=lambda *_: "não")
        self.writer.assert_not_called()

    def test_changed_snapshot_blocks_before_writes(self):
        self.live["items"][0]["title"] = "edited"
        with self.assertRaisesRegex(ValueError, "Estado remoto"):
            app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                           state_reader=self.state, writer=self.writer, interactive=True)
        self.writer.assert_not_called()

    def test_success_rechecks_per_field_and_is_idempotent(self):
        def write(*args):
            self.writer(*args)
            field = args[args.index("--field") + 1]
            value = args[args.index("--value") + 1]
            self.live["items"][0]["esteira" if field == "Esteira" else "etapa CH"] = value
        done = app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                              state_reader=self.state, writer=write, interactive=True,
                              prompt=lambda s: "APROVO KSYNC-03 " + self.plan["digest"][:12])
        self.assertEqual(len(done), 2)
        self.assertEqual(self.writer.call_count, 2)
        self.assertEqual(app.inspect(self.live, [42], self.state)[0], [])

    def test_failure_midway_reports_partial_never_retries(self):
        def write(*args):
            self.writer(*args)
            if self.writer.call_count == 2:
                raise RuntimeError("Falha de rede")
            self.live["items"][0]["esteira"] = "ChatGPT"
        with self.assertRaisesRegex(RuntimeError, "PARCIAL POSSÍVEL \\(1 confirmadas\\)"):
            app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                           state_reader=self.state, writer=write, interactive=True,
                           prompt=lambda s: "APROVO KSYNC-03 " + self.plan["digest"][:12])
        self.assertEqual(self.writer.call_count, 2)

    def test_race_before_next_write_blocks(self):
        def write(*args):
            self.writer(*args)
            self.live["items"][0]["esteira"] = "ChatGPT"
            self.live["items"][0]["status"] = "Done"
        with self.assertRaisesRegex(RuntimeError, "PARCIAL"):
            app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                           state_reader=self.state, writer=write, interactive=True,
                           prompt=lambda s: "APROVO KSYNC-03 " + self.plan["digest"][:12])
        self.assertEqual(self.writer.call_count, 1)

    def test_wrong_value_after_write_never_reports_success(self):
        events = []
        def write(*args):
            self.writer(*args)
            field = args[args.index("--field") + 1]
            self.live["items"][0]["esteira" if field == "Esteira" else "etapa CH"] = (
                "ChatGPT" if field == "Esteira" else "EM_REVISAO"
            )
        with self.assertRaisesRegex(RuntimeError, "INDETERMINADO em #42 Etapa CH"):
            app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                           state_reader=self.state, writer=write, interactive=True,
                           prompt=lambda *_: "APROVO KSYNC-03 " + self.plan["digest"][:12],
                           audit=events.append)
        self.assertEqual(self.writer.call_count, 2)
        self.assertEqual(len([e for e in events if e["event"] == "VERIFIED"]), 1)
        self.assertEqual(events[-1]["event"], "ABORT")
        self.assertEqual(events[-1]["confirmed"], 1)

    def test_unrelated_field_change_after_write_fails_snapshot(self):
        def write(*args):
            self.writer(*args)
            self.live["items"][0]["esteira"] = "ChatGPT"
            self.live["items"][0]["prioridade CH"] = "P0"
        with self.assertRaisesRegex(RuntimeError, "snapshot divergiu"):
            app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                           state_reader=self.state, writer=write, interactive=True,
                           prompt=lambda *_: "APROVO KSYNC-03 " + self.plan["digest"][:12])
        self.assertEqual(self.writer.call_count, 1)

    def test_change_between_two_fields_is_blocked(self):
        reads = [0]
        def read():
            reads[0] += 1
            if reads[0] == 4:
                self.live["items"][0]["risco CH"] = "Alto"
            return self.live
        def write(*args):
            self.writer(*args)
            self.live["items"][0]["esteira"] = "ChatGPT"
        with self.assertRaisesRegex(RuntimeError, "snapshot divergiu"):
            app.apply_plan(self.plan, self.plan["digest"], reader=read,
                           state_reader=self.state, writer=write, interactive=True,
                           prompt=lambda *_: "APROVO KSYNC-03 " + self.plan["digest"][:12])
        self.assertEqual(self.writer.call_count, 1)

    def test_prewrite_conflict_is_audited_without_mutation(self):
        events = []
        self.live["items"][0]["risk"] = "changed"
        with self.assertRaisesRegex(ValueError, "Estado remoto"):
            app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                           state_reader=self.state, writer=self.writer, interactive=True,
                           audit=events.append)
        self.writer.assert_not_called()
        self.assertEqual([e["event"] for e in events],
                         ["PREFLIGHT", "BLOCKED_PREWRITE"])

    def test_network_failure_after_remote_write_is_indeterminate(self):
        events = []
        def write(*args):
            self.writer(*args)
            self.live["items"][0]["esteira"] = "ChatGPT"
            raise RuntimeError("connection dropped")
        with self.assertRaisesRegex(RuntimeError, "0 confirmadas.*INDETERMINADO"):
            app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                           state_reader=self.state, writer=write, interactive=True,
                           prompt=lambda *_: "APROVO KSYNC-03 " + self.plan["digest"][:12],
                           audit=events.append)
        self.assertEqual(self.writer.call_count, 1)
        self.assertEqual([e["event"] for e in events],
                         ["PREFLIGHT", "START", "ATTEMPT", "ABORT"])
        self.assertEqual(events[-1]["uncertain"], {"number": 42, "field": "Esteira"})

    def test_audit_records_exact_before_after_and_completion(self):
        events = []
        def write(*args):
            field = args[args.index("--field") + 1]
            value = args[args.index("--value") + 1]
            self.live["items"][0]["esteira" if field == "Esteira" else "etapa CH"] = value
        app.apply_plan(self.plan, self.plan["digest"], reader=lambda: self.live,
                       state_reader=self.state, writer=write, interactive=True,
                       prompt=lambda *_: "APROVO KSYNC-03 " + self.plan["digest"][:12],
                       audit=events.append)
        verified = [e for e in events if e["event"] == "VERIFIED"]
        self.assertEqual([(x["field"], x["before"], x["after"]) for x in verified],
                         [("Esteira", None, "ChatGPT"), ("Etapa CH", None, "BACKLOG")])
        self.assertEqual(events[-1], {"event": "COMPLETE", "confirmed": 2})

    def test_audit_file_is_exclusive_jsonl_and_private(self):
        with tempfile.TemporaryDirectory() as td:
            import os
            path = Path(td) / "audit.jsonl"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                audit = app._audit_writer(handle)
                audit({"event": "START", "digest": self.plan["digest"]})
            records = [json.loads(x) for x in path.read_text().splitlines()]
            self.assertEqual(records[0]["protocol"], "RUC/1.0")
            self.assertEqual(records[0]["mission"], "KSYNC-03/#19")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

    def test_cli_requires_audit_file_for_apply_path(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(app.main(["--apply-plan", "/fake", "--confirm", "x"]), 1)
            self.assertEqual(app.main(["--audit-file", "/tmp/x"]), 1)
        self.writer.assert_not_called()

    @mock.patch.object(app, "fetch_project")
    def test_cli_preview_never_writes_and_saves_exclusive_plan(self, fetch):
        fetch.return_value = payload(item(43))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "plan.json"
            with mock.patch.object(app.legacy, "issue_state", return_value="OPEN"):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(app.main(["--issues", "43", "--plan-file", str(path)]), 0)
                    self.assertEqual(app.main(["--issues", "43", "--plan-file", str(path)]), 1)
            self.assertEqual(app.validate_plan(json.loads(path.read_text())), [43])



# W-F2.2: todos os caminhos usam fixtures e adaptadores falsos — zero mutacao remota.
class AdmissionOffline(unittest.TestCase):
    def setUp(self):
        self.number = 84
        self.issue = {
            "number": self.number, "id": "I_issue84",
            "state": "OPEN", "title": "W: Entrada controlada",
            "url": f"https://github.com/{REPO}/issues/{self.number}",
            "labels": [{"name": "ch:workflow"}, {"name": "ch:chatgpt"}],
            "body": (
                "- **Executor declarado**: ChatGPT\n"
                "- **Autonomia proposta**: CH-2 (PENDENTE DE AUTORIZAÇÃO HUMANA)\n"
                "- **Objetivo / valor**: Entrada controlada\n"
                "- **Escopo permitido**: Validar a entrada de uma Issue\n"
                "- **Critérios de aceitação**: Testes offline aprovados\n"
                "- **Base SHA**: " + "a" * 40 + "\n"
                "- **Verificações e evidências exigidas**: Testes e RUC\n"
            ),
        }
        options = {
            "Esteira": ["Hallan", "ChatGPT", "Codex", "AGY"],
            "Etapa CH": ["BACKLOG", "PRONTA"],
            "Autonomia CH": ["CH-0", "CH-1", "CH-2"],
        }
        self.context = {
            "issue": self.issue,
            "project": {"id": "PVT_project2"},
            "fields": {"fields": [
                {"id": f"FIELD_{name}", "name": name,
                 "type": "ProjectV2SingleSelectField",
                 "options": [{"id": f"OPT_{name}_{value}", "name": value}
                             for value in values]}
                for name, values in options.items()
            ]},
            "items": {"totalCount": 0, "items": []},
            "activity": {"status": "CLEAR"},
        }
        self.approval = {
            "id": 9875, "user": {"login": "hallanbrito"},
            "issue_url": f"https://api.github.com/repos/{REPO}/issues/63",
            "updated_at": "2026-11-07T12:00:00Z",
            "body": f"CH-GOV-01 ADMIT PROJECT#2 ISSUE#{self.number} "
                    "ESTEIRA=ChatGPT ETAPA=BACKLOG AUTONOMIA=CH-0",
        }
        self.calls = []
        self.events = []

    def read(self, number):
        self.assertEqual(number, self.number)
        return copy.deepcopy(self.context)

    def read_approval(self, comment_id):
        self.assertEqual(comment_id, self.approval["id"])
        return copy.deepcopy(self.approval)

    def write(self, operation, params):
        self.calls.append((operation, copy.deepcopy(params)))
        if operation == "add":
            self.assertEqual(params["contentId"], "I_issue84")
            new_item = item(self.number)
            new_item["id"] = "PVTI_new"
            self.context["items"]["items"].append(new_item)
            self.context["items"]["totalCount"] += 1
            return "PVTI_new"
        self.assertEqual(operation, "set")
        self.assertEqual(params["itemId"], "PVTI_new")
        mapping = {f"FIELD_{name}": name for name in app.ADMIT_FIELDS}
        field_name = mapping[params["fieldId"]]
        field = [f for f in self.context["fields"]["fields"]
                 if f["name"] == field_name][0]
        target = [v["name"] for v in field["options"]
                  if v["id"] == params["optionId"]][0]
        self.context["items"]["items"][0][field_name] = target
        return "PVTI_new"

    def plan(self, *, autonomy="CH-0", approval=True):
        proof = self.approval if approval else None
        return app.make_admit_plan(self.number, self.read(self.number),
                                   autonomy=autonomy, approval=proof)

    def apply(self, plan=None, writer=None):
        plan = plan or self.plan()
        return app.apply_admit_plan(
            plan, plan["digest"], reader=self.read,
            approval_reader=self.read_approval,
            graphql=writer or self.write,
            interactive=True,
            prompt=lambda *_: "APROVO ADMISSAO " + plan["digest"][:12],
            audit=self.events.append,
        )

    def test_f1_content_valid_but_not_authorized(self):
        plan = self.plan(approval=False)
        self.assertEqual(plan["action"], "ADD")
        self.assertIsNone(plan["approval_id"])
        self.assertEqual(plan["autonomy"], "CH-0")
        self.assertEqual([f["name"] for f in plan["fields"]],
                         list(app.ADMIT_FIELDS))
        with self.assertRaisesRegex(ValueError, "autorizacao"):
            self.apply(plan)
        self.assertFalse(self.calls)

    def test_full_sequence_add_three_fields_and_readback(self):
        plan = self.plan()
        self.assertEqual(self.apply(plan), "PVTI_new")
        self.assertEqual([op for op, _ in self.calls], ["add", "set", "set", "set"])
        self.assertEqual([event["event"] for event in self.events],
                         ["PREFLIGHT", "ATTEMPT_ADD", "VERIFIED_ADD",
                          "ATTEMPT_FIELD", "VERIFIED_FIELD",
                          "ATTEMPT_FIELD", "VERIFIED_FIELD",
                          "ATTEMPT_FIELD", "VERIFIED_FIELD", "COMPLETE"])
        self.assertEqual(self.context["items"]["items"][0]["Autonomia CH"], "CH-0")
        self.assertEqual(self.context["items"]["items"][0]["Esteira"], "ChatGPT")
        self.assertEqual(self.context["items"]["items"][0]["Etapa CH"], "BACKLOG")
        self.assertFalse(self.events[-1]["execution_authorized"])

    def test_idempotent_already_complete_no_writes(self):
        entry = item(self.number, lane="ChatGPT", stage="BACKLOG")
        entry["Autonomia CH"] = "CH-0"
        self.context["items"] = payload(entry)
        plan = self.plan()
        self.assertEqual(plan["action"], "ALREADY_REGISTERED")
        self.assertEqual(self.apply(plan), entry["id"])
        self.assertFalse(self.calls)

    def test_existing_partial_blocks_without_repair(self):
        self.context["items"] = payload(item(self.number, lane="ChatGPT"))
        with self.assertRaisesRegex(ValueError, "parcial/conflitante"):
            self.plan()
        self.assertFalse(self.calls)

    def test_duplicate_cards_blocks(self):
        self.context["items"] = payload(item(self.number), item(self.number))
        with self.assertRaisesRegex(ValueError, "duplicada"):
            self.plan()

    def test_missing_field_or_option_blocks(self):
        for mode in ["field", "option"]:
            saved = copy.deepcopy(self.context)
            if mode == "field":
                self.context["fields"]["fields"].pop()
            else:
                self.context["fields"]["fields"][-1]["options"] = []
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.plan()
            self.context = saved

    def test_po_approval_verifies_author_and_exact_values(self):
        for change in [
            ("user", {"login": "outro"}),
            ("body", "AUTORIZO GENÉRICO"),
            ("issue_url", f"https://api.github.com/repos/{REPO}/issues/999"),
        ]:
            saved = copy.deepcopy(self.approval)
            self.approval[change[0]] = change[1]
            with self.subTest(change=change[0]), self.assertRaises(ValueError):
                self.plan()
            self.approval = saved
        self.assertEqual(self.plan()["autonomy"], "CH-0")

    def test_higher_autonomy_cannot_be_copied_from_issue_body(self):
        with self.assertRaisesRegex(ValueError, "nao aprovou"):
            self.plan(autonomy="CH-2")
        self.assertEqual(self.plan()["autonomy"], "CH-0")

    def test_digest_and_changed_snapshot_block_before_writes(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, "Digest"):
            app.apply_admit_plan(plan, "0" * 64, reader=self.read,
                                 approval_reader=self.read_approval,
                                 interactive=True, audit=self.events.append)
        self.context["items"]["items"].append(item(999))
        self.context["items"]["totalCount"] += 1
        with self.assertRaisesRegex(ValueError, "Plano obsoleto"):
            self.apply(plan)
        self.assertFalse(self.calls)

    def test_po_approval_edit_between_plan_and_apply_blocks(self):
        plan = self.plan()
        self.approval["updated_at"] = "2026-11-07T12:01:00Z"
        with self.assertRaisesRegex(ValueError, "Plano obsoleto"):
            self.apply(plan)
        self.assertFalse(self.calls)

    def test_noninteractive_and_wrong_confirmation_block(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, "interativo"):
            app.apply_admit_plan(plan, plan["digest"], reader=self.read,
                                 approval_reader=self.read_approval,
                                 interactive=False, audit=self.events.append)
        with self.assertRaisesRegex(ValueError, "Confirmacao"):
            app.apply_admit_plan(plan, plan["digest"], reader=self.read,
                                 approval_reader=self.read_approval, interactive=True,
                                 prompt=lambda *_: "INCORRETO", audit=self.events.append)
        self.assertFalse(self.calls)

    def test_timeout_after_add_never_retries(self):
        plan = self.plan()
        def uncertain(operation, params):
            if operation == "add":
                self.write(operation, params)
                raise RuntimeError("connection dropped after add")
            self.fail("Unexpected field write")
        with self.assertRaisesRegex(RuntimeError, "nao repetir"):
            self.apply(plan, writer=uncertain)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.events[-1]["uncertain"], "addProjectV2ItemById")

    def test_failure_after_one_field_is_partial_and_blocked(self):
        plan = self.plan()
        def fail_second(operation, params):
            if operation == "set" and len(self.calls) == 2:
                self.calls.append(("set-failed", params))
                raise RuntimeError("network failed")
            return self.write(operation, params)
        with self.assertRaisesRegex(RuntimeError, "nao repetir"):
            self.apply(plan, writer=fail_second)
        self.assertEqual(self.events[-1]["verified_fields"], ["Esteira"])
        self.assertEqual(self.events[-1]["uncertain"], "Etapa CH")
        self.assertEqual(self.context["items"]["items"][0]["esteira"], "ChatGPT")

    def test_readback_wrong_value_blocks(self):
        plan = self.plan()
        def bad_write(operation, params):
            if operation == "set":
                self.calls.append((operation, params))
                return "PVTI_new"  # Finge sucesso sem alterar os campos.
            return self.write(operation, params)
        with self.assertRaisesRegex(RuntimeError, "nao repetir"):
            self.apply(plan, writer=bad_write)
        self.assertEqual(self.events[-1]["uncertain"], "Esteira")
        self.assertEqual(len(self.calls), 2)

    def test_dry_run_main_never_calls_graphql(self):
        writer = mock.Mock()
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(app.admit_main(
                ["--issue", str(self.number), "--dry-run"],
                reader=self.read, approval_reader=self.read_approval,
                graphql=writer), 0)
        self.assertIn("SEM ESCRITA", stdout.getvalue())
        self.assertIn("Autonomia CH: CH-0", stdout.getvalue())
        writer.assert_not_called()

    def test_plan_file_exclusive_and_permission(self):
        with tempfile.TemporaryDirectory() as td:
            filename = Path(td) / "plan.json"
            command = ["--issue", str(self.number), "--plan-file", str(filename),
                       "--approval-comment", str(self.approval["id"])]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(app.admit_main(
                    command, reader=self.read,
                    approval_reader=self.read_approval), 0)
            data = json.loads(filename.read_text())
            self.assertEqual(data["digest"], self.plan()["digest"])
            self.assertEqual(filename.stat().st_mode & 0o777, 0o600)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(app.admit_main(
                    command, reader=self.read,
                    approval_reader=self.read_approval), 1)

    def test_preview_and_legacy_cli_paths_stay_separate(self):
        with mock.patch.object(app, "fetch_project", return_value=payload(item(43))), \
             mock.patch.object(app.legacy, "issue_state", return_value="OPEN"), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(["--issues", "43"]), 0)

    def test_graphql_adapter_uses_two_explicit_mutations(self):
        output = {
            "data": {
                "addProjectV2ItemById": {"item": {"id": "PVTI_NEW"}},
                "updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_NEW"}},
            }
        }
        with mock.patch.object(app.legacy, "gh_json", return_value=output) as gh:
            self.assertEqual(app._admit_graphql(
                "add", {"projectId": "PVT", "contentId": "I1"}), "PVTI_NEW")
            self.assertIn("addProjectV2ItemById", gh.call_args.args[3])
            self.assertEqual(app._admit_graphql(
                "set", {"projectId": "PVT", "itemId": "PVTI_NEW",
                        "fieldId": "F1", "optionId": "O1"}), "PVTI_NEW")
            self.assertIn("updateProjectV2ItemFieldValue", gh.call_args.args[3])

    def test_ch_cli_routes_only_no_domain_logic(self):
        from chdevflow.cli import main as ch_main
        fake = subprocess.CompletedProcess(args=[], returncode=0)
        with mock.patch("chdevflow.cli.subprocess.run", return_value=fake) as called:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ch_main(["project", "admit", "--issue",
                                         str(self.number), "--dry-run"]), 0)
        args = called.call_args.args[0]
        self.assertIn("ch_project_assist.py", args[1])
        self.assertEqual(args[2:], ["admit", "--issue", str(self.number), "--dry-run"])

if __name__ == "__main__":
    unittest.main()
