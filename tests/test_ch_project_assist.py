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
                rc = app.main()
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


if __name__ == "__main__":
    unittest.main()
