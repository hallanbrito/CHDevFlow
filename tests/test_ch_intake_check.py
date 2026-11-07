"""CH-GOV-01: regressões offline do Gate Universal de Entrada."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ch_intake_check import validate_issue  # noqa: E402

FORM = """### Objetivo e valor

Entregar verificação de entrada de missão.

### Esteira

AGY

### Nível de autonomia

CH-1

### Escopo, exclusões e critérios de aceite

Escopo: testar offline. Aceite: nenhuma escrita em Project ou agentes.

### Baseline Git (branch e SHA)

main f8eea14e03c687c4b2ba2a0f628c7c6948d7a6dd

### Verificações e evidências exigidas

Executar unittest offline e registrar evidências.
"""


def issue(body=FORM, labels=None, number=63):
    return {"number": number, "title": "CH-GOV-01 — Check",
            "labels": [{"name": n} for n in (labels or ["ch:workflow", "ch:agy"])],
            "body": body}


class TestChIntake(unittest.TestCase):
    def test_issue_form_valid_content_never_authorizes(self):
        result = validate_issue(issue())
        self.assertEqual("CONTENT_VALID", result["content_status"])
        self.assertEqual([], result["reasons"])
        self.assertFalse(result["project_fields_verified"])
        self.assertFalse(result["po_authorized"])
        self.assertFalse(result["execution_allowed"])
        self.assertFalse(result["mutation_performed"])

    def test_issue_62_incomplete_is_blocked(self):
        fixture = ROOT / "tests" / "fixtures" / "ch_intake" / "issue62_incomplete.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        result = validate_issue(payload["issue"])
        self.assertEqual("BLOCKED", result["content_status"])
        self.assertIn("EXECUTOR_BODY_LABEL_CONFLICT", result["reasons"])
        self.assertIn("EVIDENCE_PLAN_MISSING", result["reasons"])

    def test_issue_without_workflow_is_triage_not_admitted(self):
        r = validate_issue(issue(labels=["ch:agy"]))
        self.assertEqual("OUT_OF_SCOPE", r["content_status"])
        self.assertFalse(r["project_fields_verified"])

    def test_ambiguous_label_blocked(self):
        r = validate_issue(issue(labels=["ch:workflow", "ch:agy", "ch:codex"]))
        self.assertIn("EXECUTOR_LABEL_MISSING_OR_AMBIGUOUS", r["reasons"])

    def test_executor_label_conflict(self):
        r = validate_issue(issue(labels=["ch:workflow", "ch:codex"]))
        self.assertIn("EXECUTOR_BODY_LABEL_CONFLICT", r["reasons"])

    def test_autonomy_absent(self):
        r = validate_issue(issue(body=FORM.replace("CH-1", "_No response_")))
        self.assertIn("PROPOSED_AUTONOMY_MISSING", r["reasons"])

    def test_baseline_placeholder_not_accepted(self):
        r = validate_issue(issue(body=FORM.replace("main f8eea14e03c687c4b2ba2a0f628c7c6948d7a6dd", "NÃO_VERIFICADO")))
        self.assertIn("BASELINE_SHA_MISSING", r["reasons"])

    def test_forged_admission_label_not_trusted(self):
        r = validate_issue(issue(labels=["ch:workflow", "ch:agy", "ch:admitted"]))
        self.assertEqual("BLOCKED", r["content_status"])
        self.assertIn("ADMISSION_LABEL_UNVERIFIED", r["reasons"])

    def test_issue_payload_malformed_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "INVALID_ISSUE_NUMBER"):
            validate_issue({"number": "63", "labels": [], "body": FORM})
        with self.assertRaisesRegex(ValueError, "INVALID_LABELS"):
            validate_issue({"number": 63, "labels": 4, "body": FORM})

    def test_cli_exit_status_and_no_secret_echo(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "event.json"
            p.write_text(json.dumps({"issue": issue(body="private token ghp_secret")}), encoding="utf-8")
            done = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "ch_intake_check.py"),
                 "--event-json", str(p), "--enforce", "--json"],
                capture_output=True, text=True, check=False, timeout=15,
            )
            self.assertEqual(2, done.returncode, done.stderr)
            self.assertIn('"content_status": "BLOCKED"', done.stdout)
            self.assertNotIn("ghp_secret", done.stdout)

    def test_non_issue_event_returns_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "event.json"
            p.write_text('{"action":"opened"}', encoding="utf-8")
            done = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "ch_intake_check.py"),
                 "--event-json", str(p), "--enforce"],
                capture_output=True, text=True, check=False, timeout=15,
            )
            self.assertEqual(3, done.returncode)

    def test_ch_cli_intake_check_uses_same_contract(self):
        fixture = ROOT / "tests" / "fixtures" / "ch_intake" / "issue62_incomplete.json"
        done = subprocess.run(
            [sys.executable, "-m", "chdevflow", "intake", "check",
             "--event-json", str(fixture), "--enforce", "--json"],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=20,
        )
        self.assertEqual(2, done.returncode, done.stderr)
        payload = json.loads(done.stdout)
        self.assertEqual("BLOCKED", payload["content_status"])
        self.assertFalse(payload["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
