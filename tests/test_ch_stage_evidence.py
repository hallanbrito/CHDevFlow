"""KSYNC-03.1: testes de evidência de trabalho com timeline simulada (sem rede)."""
from __future__ import annotations

import json
import re
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
        match = re.search(r"[?&]page=(\d+)$", args[-1])
        if not match:
            raise AssertionError("Page parameter missing")
        page_number = int(match.group(1))
        if page_number > len(pages):
            raise AssertionError("Unexpected extra page request")
        return json.dumps(list(pages[page_number - 1]))
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
        self.assertNotIn("--paginate", calls[0])
        self.assertNotIn("--slurp", calls[0])
        self.assertTrue(calls[0][-1].endswith("issues/8/timeline?per_page=100&page=1"))
        self.assertEqual(len(calls), 1)

    def test_realistic_issue19_pr20(self):
        sha = "2e66137db44530667ecfb12cb17480e02fe27c9e"
        read, _ = client([{"event": "referenced", "commit_id": sha,
                           "commit_url": f"https://api.github.com/repos/{stage.REPO}/commits/{sha}"},
                          event_pr(20)])
        result = stage.probe(stage.REPO, 19, read)
        self.assertEqual(result["status"], "WORK_FOUND")
        self.assertEqual([x["kind"] for x in result["references"]],
                         ["COMMIT", "PR"])

    def test_empty_timeline_is_valid_clear(self):
        read, calls = client([])
        self.assertEqual(stage.probe(stage.REPO, 21, read)["status"], "CLEAR")
        self.assertEqual(len(calls), 1)

    def test_manual_pagination_max_requests_fail_closed(self):
        full_page = [{"event": "labeled"}] * 100
        read, calls = client(*([full_page] * stage.MAX_PAGES))
        with self.assertRaisesRegex(stage.EvidenceError, "limite de páginas"):
            stage.probe(stage.REPO, 25, read)
        self.assertEqual(len(calls), stage.MAX_PAGES)
        self.assertFalse(any("--paginate" in call or "--slurp" in call for call in calls))

    def test_partial_page_finishes_without_more_requests(self):
        read, calls = client([{"event": "labeled"}] * 99)
        self.assertEqual(stage.probe(stage.REPO, 21, read)["status"], "CLEAR")
        self.assertEqual(len(calls), 1)

    def test_page_over_100_events_is_rejected(self):
        read, calls = client([{"event": "labeled"}] * 101)
        with self.assertRaisesRegex(stage.EvidenceError, "tamanho inválido"):
            stage.probe(stage.REPO, 21, read)
        self.assertEqual(len(calls), 1)

    def test_external_commit_url_fails_closed_without_fabricated_local_link(self):
        sha = "a" * 40
        read, _ = client([{
            "event": "referenced", "commit_id": sha,
            "commit_url": f"https://api.github.com/repos/foreign/repo/commits/{sha}"
        }])
        with self.assertRaisesRegex(stage.EvidenceError, "Procedência"):
            stage.probe(stage.REPO, 21, read)

    def test_missing_commit_provenance_fails_closed(self):
        sha = "a" * 40
        read, _ = client([{"event": "referenced", "commit_id": sha}])
        with self.assertRaisesRegex(stage.EvidenceError, "Procedência"):
            stage.probe(stage.REPO, 21, read)

    def test_valid_same_repo_commit_link(self):
        sha = "f" * 40
        read, _ = client([{"event": "committed", "commit_id": sha,
                           "commit_url": f"https://api.github.com/repos/{stage.REPO}/commits/{sha}"}])
        result = stage.probe(stage.REPO, 21, read)
        self.assertEqual(result["status"], "WORK_FOUND")
        self.assertEqual(result["references"][0]["url"],
                         f"https://github.com/{stage.REPO}/commit/{sha}")

    def test_forged_commit_sha_fails_closed(self):
        read, _ = client([{"event": "referenced", "commit_id": "not-a-sha",
                           "commit_url": "https://example.invalid/commit/not-a-sha"}])
        with self.assertRaisesRegex(stage.EvidenceError, "SHA inválido"):
            stage.probe(stage.REPO, 21, read)

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
        read, calls = client([event_pr(9)] + [{"event": "labeled"}] * 99,
                             [event_pr(9)])
        result = stage.probe(stage.REPO, 8, read)
        self.assertEqual(len(result["references"]), 1)
        self.assertEqual(len(calls), 2)

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
        for data in ("{}", "[{}]", "[null]", '"unexpected"'):
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
        read, calls = client([{"event": "labeled"}] * 100, [event_pr(20)])
        result = stage.probe(stage.REPO, 19, read)
        self.assertEqual(result["references"][0]["number"], 20)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
