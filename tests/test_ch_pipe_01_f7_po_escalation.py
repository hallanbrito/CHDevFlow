"""F7: contratos offline para Project #2, SEM chamadas gh nem escrita."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from chdevflow.core import po_escalation as f7


def issue_item(number=85, item_id="PVTI_123"):
    return {
        "id": item_id,
        "content": {
            "type": "Issue", "repository": "hallanbrito/CHDevFlow",
            "number": number,
            "url": f"https://github.com/hallanbrito/CHDevFlow/issues/{number}",
        },
        "Status": "In Progress", "Etapa CH": "AGUARDANDO_PO",
    }


class EscalationPreviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.outbox = Path(temp.name) / "escalonamento_po.json"
        self.payload = {
            "execution_id": "a"*32, "mission_id": "F6-TEST-001",
            "issue": 85, "status": "AGUARDANDO_PO",
            "publication_status": "PENDENTE_DE_AUTORIZACAO",
            "attempts": 3, "returns": 2,
        }
        self._write()

    def _write(self):
        self.outbox.write_text(
            json.dumps(self.payload), encoding="utf-8")

    def test_issue_existente_nao_gera_mutacao(self):
        project = {"totalCount": 1, "items": [issue_item()]}
        plan = f7.preview(self.outbox, reader=lambda: project)
        self.assertEqual(plan["state"], "JA_EXISTE_NO_PROJECT")
        self.assertEqual(plan["project_item_id"], "PVTI_123")
        self.assertEqual(plan["writes"], 0)

    def test_issue_ausente_exige_admissao_do_po(self):
        plan = f7.preview(
            self.outbox, reader=lambda: {"totalCount": 0, "items": []})
        self.assertEqual(plan["state"], "EXIGE_ADMISSAO_PO")
        self.assertEqual(plan["writes"], 0)
        self.assertIn("KSYNC-03", plan["next_step"])

    def test_terceira_reprovacao_obrigatoria(self):
        for value in (1, 2, 4):
            self.payload["attempts"] = value
            self._write()
            with self.subTest(value=value), self.assertRaises(ValueError):
                f7._safe_outbox(self.outbox)
        self.payload["attempts"] = 3
        self.payload["returns"] = 1
        self._write()
        with self.assertRaises(ValueError):
            f7._safe_outbox(self.outbox)

    def test_sem_status_aguardando_po_ou_publicado_bloqueia(self):
        self.payload["status"] = "APROVADO_AGUARDANDO_CH1"
        self._write()
        with self.assertRaises(ValueError):
            f7._safe_outbox(self.outbox)
        self.payload["status"] = "AGUARDANDO_PO"
        self.payload["publication_status"] = "PUBLICADO"
        self._write()
        with self.assertRaises(ValueError):
            f7._safe_outbox(self.outbox)

    def test_legacy_f5_url_e_mission_suportados(self):
        self.payload.pop("mission_id")
        self.payload["mission"] = "CH-PIPE-01-F5-ESTOQUE"
        self.payload["issue"] = "https://github.com/hallanbrito/CHDevFlow/issues/78"
        self._write()
        data = f7._safe_outbox(self.outbox)
        self.assertEqual(data["issue"], 78)

    def test_snapshot_truncado_e_duplicate_fail_closed(self):
        item = issue_item()
        for project in (
            {"totalCount": 2, "items": [item]},
            {"totalCount": 2, "items": [item, item]},
            {"totalCount": 1, "items": [{**item, "content": {
                **item["content"], "url": "https://attacker.example/issues/85"}}]},
        ):
            with self.subTest(project=project), self.assertRaises(ValueError):
                f7.build_escalation_preview(f7._safe_outbox(self.outbox), project)

    def test_releitura_necessaria_sem_gh_real(self):
        with patch.object(f7, "_project_snapshot",
                          side_effect=AssertionError("Leitura LIVE nao autorizada")):
            result = f7.preview(
                self.outbox, reader=lambda: {"totalCount": 0, "items": []})
        self.assertEqual(result["writes"], 0)

    def test_segredo_nao_esta_no_plano(self):
        self.payload["token"] = "segredo-que-nao-deve-sair"
        self._write()
        result = f7.preview(self.outbox, reader=lambda: {
            "totalCount": 0, "items": []})
        self.assertNotIn("segredo-que-nao-deve-sair", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
