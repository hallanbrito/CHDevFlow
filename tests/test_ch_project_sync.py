"""Testes offline do sincronizador CHDevFlow. NENHUMA chamada ao GitHub real."""
from __future__ import annotations

import contextlib
import copy
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ch_project_sync as sync


REPO = "hallanbrito/CHDevFlow"


def item(number: int, *, labels=None, status="Todo", lane=None,
         stage=None, repo=REPO, include_lane=False, include_stage=False):
    obj = {
        "content": {
            "number": number, "repository": repo, "type": "Issue",
            "title": f"Issue {number}",
            "url": f"https://github.com/{repo}/issues/{number}"
        },
        "labels": labels if labels is not None else ["ch:workflow", "ch:codex"],
        "status": status,
        "id": f"PVTI_example_{number}",
        "title": f"Issue {number}",
    }
    if include_lane or lane is not None:
        obj["esteira"] = lane
    if include_stage or stage is not None:
        obj["etapa CH"] = stage
    return obj


def payload(*items):
    return {"items": list(items), "totalCount": len(items)}


class PlanningTests(unittest.TestCase):
    def test_new_open_issue_fills_lane_and_backlog(self):
        states = []
        def read(repo, num):
            states.append((repo, num))
            return "OPEN"
        result, notes = sync.build_plan(payload(item(12)), REPO, read)
        self.assertEqual(
            [(c.field, c.value) for c in result],
            [("Esteira", "Codex"), ("Etapa CH", "BACKLOG")]
        )
        self.assertEqual(states, [(REPO, 12)])
        self.assertFalse(notes)

    def test_closed_issue_only_receives_missing_lane(self):
        result, notes = sync.build_plan(payload(item(13, labels=["ch:workflow", "ch:agy"])),
                                        REPO, lambda *_: "CLOSED")
        self.assertEqual([(c.field, c.value) for c in result], [("Esteira", "AGY")])
        self.assertIn("homologação", notes[0])

    def test_existing_fields_preserved_and_rerun_idempotent(self):
        first = item(14, labels=["ch:workflow", "ch:chatgpt"],
                     lane="ChatGPT", stage="HOMOLOGADA")
        result, _ = sync.build_plan(payload(first), REPO,
                                    lambda *_: self.fail("Não deve consultar estado"))
        self.assertEqual(result, [])

    def test_conflicting_labels_prevent_any_edit(self):
        result, notes = sync.build_plan(
            payload(item(15, labels=["ch:workflow", "ch:codex", "ch:agy"])),
            REPO, lambda *_: self.fail("Não consultar Issue conflitante")
        )
        self.assertEqual(result, [])
        self.assertIn("conflitantes", notes[0])

    def test_missing_role_is_not_implicitly_assigned(self):
        result, notes = sync.build_plan(
            payload(item(16, labels=["ch:workflow"])),
            REPO, lambda *_: self.fail("Não consultar Issue sem executor")
        )
        self.assertEqual(result, [])
        self.assertIn("sem etiqueta", notes[0])

    def test_existing_manual_stage_not_overwritten(self):
        entry = item(17, lane="Hallan", stage="EM_REVISAO",
                     labels=["ch:workflow", "ch:po"])
        result, _ = sync.build_plan(
            payload(entry), REPO, lambda *_: self.fail("Não consultar estado")
        )
        self.assertEqual(result, [])

    def test_existing_lane_conflict_only_warns(self):
        entry = item(18, lane="Hallan", stage="HOMOLOGADA")
        result, notes = sync.build_plan(
            payload(entry), REPO, lambda *_: self.fail("Não consultar estado")
        )
        self.assertEqual(result, [])
        self.assertIn("preservar", notes[0])

    def test_avoid_backlog_if_status_not_todo(self):
        result, notes = sync.build_plan(
            payload(item(19, status="Done")), REPO,
            lambda *_: self.fail("Estado da Issue não deve ser consultado")
        )
        self.assertEqual([(x.field, x.value) for x in result], [("Esteira", "Codex")])
        self.assertIn("não é Todo", notes[0])

    def test_filter_issue(self):
        result, _ = sync.build_plan(
            payload(item(20), item(21, labels=["ch:workflow", "ch:agy"])),
            REPO, lambda *_: "OPEN", issue_filter=21
        )
        self.assertEqual({x.number for x in result}, {21})
        with self.assertRaisesRegex(RuntimeError, "não encontrada"):
            sync.build_plan(payload(item(20)), REPO, lambda *_: "OPEN", issue_filter=99)

    def test_other_repositories_skipped(self):
        result, _ = sync.build_plan(
            payload(item(20, repo="outro/repo"), item(21)), REPO,
            lambda *_: "OPEN"
        )
        self.assertEqual({x.number for x in result}, {21})

    def test_truncated_or_bad_json_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "incompleto"):
            sync.build_plan({"items": [item(20)], "totalCount": 2}, REPO, lambda *_: "OPEN")
        with self.assertRaisesRegex(RuntimeError, "ausentes"):
            sync.build_plan({"items": []}, REPO, lambda *_: "OPEN")

    def test_duplicate_item_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "duplicada"):
            sync.build_plan(payload(item(20), item(20)), REPO, lambda *_: "OPEN")

    def test_url_mismatch_fails_closed(self):
        entry = item(20)
        entry["content"]["url"] = "https://example.com/injection"
        with self.assertRaisesRegex(RuntimeError, "URL"):
            sync.build_plan(payload(entry), REPO, lambda *_: "OPEN")

    def test_empty_explicit_field_treated_as_empty(self):
        entry = item(20, include_lane=True, include_stage=True, lane=None, stage=None)
        result, _ = sync.build_plan(payload(entry), REPO, lambda *_: "OPEN")
        self.assertEqual(len(result), 2)

    def test_missing_ch_workflow_skipped(self):
        result, notes = sync.build_plan(
            payload(item(22, labels=["ch:codex"])), REPO, lambda *_: "OPEN"
        )
        self.assertFalse(result)
        self.assertIn("sem ch:workflow", notes[0])


class CommandTests(unittest.TestCase):
    @mock.patch.object(sync.shutil, "which", return_value="/usr/bin/gh")
    @mock.patch.object(sync, "gh")
    @mock.patch.object(sync, "issue_state", return_value="OPEN")
    @mock.patch.object(sync, "gh_json")
    def test_preview_never_writes(self, fake_json, fake_state, fake_gh, _which):
        fake_json.return_value = payload(item(23))
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            rc = sync.main(["--issue", "23"])
        self.assertEqual(rc, 0)
        fake_gh.assert_not_called()
        self.assertIn("PRÉVIA", stdout.getvalue())
        fake_state.assert_called_once_with(REPO, 23)
        self.assertIn("--format", fake_json.call_args.args)
        self.assertNotIn("--field", fake_json.call_args.args)

    @mock.patch.object(sync.shutil, "which", return_value="/usr/bin/gh")
    @mock.patch.object(sync, "gh")
    @mock.patch.object(sync, "issue_state", return_value="OPEN")
    @mock.patch.object(sync, "gh_json")
    def test_apply_only_permitted_project_fields(self, fake_json, _state, fake_gh, _which):
        fake_json.return_value = payload(item(24))
        with contextlib.redirect_stdout(io.StringIO()):
            rc = sync.main(["--issue", "24", "--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual(fake_gh.call_count, 2)
        for call in fake_gh.call_args_list:
            args = call.args
            self.assertEqual(args[:2], ("project", "item-edit"))
            self.assertIn("--url", args)
            self.assertIn("--field", args)
            self.assertNotIn("Decisao PO", args)
            self.assertNotIn("Autonomia CH", args)

    @mock.patch.object(sync.shutil, "which", return_value="/usr/bin/gh")
    @mock.patch.object(sync, "gh")
    @mock.patch.object(sync, "gh_json", side_effect=RuntimeError("consulta indisponível"))
    def test_read_error_blocks_before_mutation(self, _json, fake_gh, _which):
        with contextlib.redirect_stderr(io.StringIO()):
            rc = sync.main(["--apply"])
        self.assertEqual(rc, 1)
        fake_gh.assert_not_called()

    def test_invalid_parameter_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                sync.parse_args(["--issue", "-1"])


if __name__ == "__main__":
    unittest.main()
