"""KSYNC-03.1: testes de evidência de trabalho com timeline simulada (sem rede)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ch_stage_evidence as stage


def event_pr(number, *, merged="2026-10-19T00:00:00Z",
             repository_url=stage.ISSUE_API, url=None):
    return {"event": "cross-referenced", "source": {
        "issue": {"number": number, "repository_url": repository_url,
                  "pull_request": {
                      "url": url or stage.PR_API + str(number),
                      "merged_at": merged
                  }}}}


def client(*pages):
    calls = []
    def read(*args):
        calls.append(args)
        return json.dumps([list(p) for p in pages])
    return read, calls


class TimelineEvidence(unittest.TestCase):
    def test_realistic_issue8_pr9_and_other_issue_ignored(self):
        read, calls = client(
            [event_pr(9),
             {"event": "cross-referenced", "source": {
                 "issue": {"number": 21, "repository_url": stage.ISSUE_API}}},
             {"event": "labeled"}]
        )
        result = stage.probe(stage.REPO, 8, read)
        self.assertEqual(result["status"], "WORK_FOUND")
        self.assertEqual([e["number"] for e in result["references"]], [9])
        self.assertIn("PR #9 MERGED", stage.format_refs(result))
        self.assertIn("--paginate", calls[0])
        self.assertIn("--slurp", calls[0])
        self.assertTrue(calls[0][-1].endswith("issues/8/timeline?per_page=100"))

    def test_realistic_issue19_pr20(self):
        read, _ = client([{"event": "referenced",
                           "commit_id": "2e66137db44530667ecfb12cb17480e02fe27c9e"},
                          event_pr(20)])
        result = stage.probe(stage.REPO, 19, read)
        self.assertEqual(result["status"], "WORK_FOUND")
        self.assertEqual([x["kind"] for x in result["references"]],
                         ["COMMIT", "PR"])

    def test_no_activity_is_clear_but_not_homologated(self):
        read, _ = client([{"event": "labeled"}, {"event": "assigned"}])
        self.assertEqual(stage.probe(stage.REPO, 21, read),
                         {"status": "CLEAR", "references": []})

    def test_open_pr_still_blocks_backlog(self):
        read, _ = client([event_pr(11, merged=None)])
        result = stage.probe(stage.REPO, 8, read)
        self.assertEqual(result["status"], "WORK_FOUND")
        self.assertIn("não confirmado", stage.format_refs(result))

    def test_duplicate_cross_ref_only_once(self):
        read, _ = client([event_pr(9)], [event_pr(9)])
        result = stage.probe(stage.REPO, 8, read)
        self.assertEqual(len(result["references"]), 1)

    def test_other_repository_pr_fails_closed(self):
        read, _ = client([event_pr(9, repository_url=
                          "https://api.github.com/repos/other/repo")])
        with self.assertRaisesRegex(stage.EvidenceError, "inconsistente"):
            stage.probe(stage.REPO, 8, read)

    def test_foreign_pr_url_fails_closed(self):
        read, _ = client([event_pr(
            9, url="https://api.github.com/repos/other/repo/pulls/9")])
        with self.assertRaises(stage.EvidenceError):
            stage.probe(stage.REPO, 8, read)

    def test_bad_json_fails_closed(self):
        with self.assertRaises(stage.EvidenceError):
            stage.probe(stage.REPO, 8, lambda *_: "invalid-json")

    def test_page_missing_or_invalid_fails_closed(self):
        for data in ("[]", "{}", "[{}]", "[null]"):
            with self.subTest(data=data), self.assertRaises(stage.EvidenceError):
                stage.probe(stage.REPO, 8, lambda *_: data)

    def test_bad_event_fails_closed(self):
        read, _ = client([{"wrong": "event"}])
        with self.assertRaises(stage.EvidenceError):
            stage.probe(stage.REPO, 8, read)

    def test_invalid_issue_and_scope(self):
        def never(*_):
            self.fail("Não consultar API")
        for repo, number in [(stage.REPO, 0), ("other/repo", 8), (stage.REPO, True)]:
            with self.subTest(repo=repo, number=number):
                with self.assertRaises(stage.EvidenceError):
                    stage.probe(repo, number, never)

    def test_pagination_catches_pr_on_later_page(self):
        read, _ = client([{"event": "labeled"}], [event_pr(20)])
        result = stage.probe(stage.REPO, 19, read)
        self.assertEqual(result["references"][0]["number"], 20)


if __name__ == "__main__":
    unittest.main()
