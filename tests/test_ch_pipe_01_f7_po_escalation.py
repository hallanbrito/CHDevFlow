"""F7: contratos offline para Project #2, SEM chamadas gh nem escrita."""
from __future__ import annotations

import hashlib
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

    def _v1_evidences(self):
        codigo = "def cotar_frete():\n    return 42\n"
        self.payload.update({
            "schema": f7.SCHEMA,
            "code_sha256": hashlib.sha256(codigo.encode("utf-8")).hexdigest(),
            "evidence_files": list(f7.EVIDENCE_FILES),
        })
        self._write()
        for relative in f7.EVIDENCE_FILES:
            p = self.outbox.parent / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                codigo if relative == "attempt-03/codigo.py" else
                "Evidencia somente leitura", encoding="utf-8")
        return codigo

    def test_outbox_v1_sha_e_caminhos_sanitizados(self):
        codigo = self._v1_evidences()
        data = f7._safe_outbox(self.outbox)
        self.assertEqual(data["code_sha256"], hashlib.sha256(
            codigo.encode("utf-8")).hexdigest())
        self.assertEqual(data["evidence_files"], list(f7.EVIDENCE_FILES))
        preview = f7.preview(
            self.outbox, reader=lambda: {"totalCount": 0, "items": []})
        self.assertEqual(preview["code_sha256"], data["code_sha256"])
        self.assertEqual(preview["writes"], 0)
        self.assertNotIn(str(self.outbox.parent), json.dumps(preview))

    def test_outbox_v1_fail_closed_em_tamper_ou_traversal(self):
        self._v1_evidences()
        self.payload["evidence_files"][0] = "../segredo.txt"
        self._write()
        with self.assertRaisesRegex(ValueError, "sanitizadas"):
            f7._safe_outbox(self.outbox)
        self.payload["evidence_files"] = list(f7.EVIDENCE_FILES)
        self._write()
        (self.outbox.parent / "attempt-03" / "codigo.py").write_text(
            "conteudo adulterado", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "nao confere"):
            f7._safe_outbox(self.outbox)
        self.payload["code_sha256"] = "0"*64
        self._write()
        with self.assertRaisesRegex(ValueError, "nao confere"):
            f7._safe_outbox(self.outbox)

    def test_recibo_local_pendente_sem_write_ou_retry_de_agentes(self):
        self._v1_evidences()
        receipt = self.outbox.parent / "pendente_publicacao.json"
        payload = f7.pending_publication_receipt(
            self.outbox, reason="PROJECT_INDISPONIVEL_OU_INCONCLUSIVO")
        f7.write_receipt_once(receipt, payload)
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(saved["publication_status"], "PENDENTE_PUBLICACAO")
        self.assertEqual(saved["remote_writes"], 0)
        self.assertIs(saved["retry_agents"], False)
        self.assertIs(saved["requires_live_po_approval"], True)
        with self.assertRaisesRegex(ValueError, "ja existe"):
            f7.write_receipt_once(receipt, payload)

    def test_preview_idempotente_preserva_projeto(self):
        self._v1_evidences()
        project = {"totalCount": 1, "items": [issue_item()]}
        baseline = json.dumps(project, sort_keys=True)
        one = f7.preview(self.outbox, reader=lambda: project)
        two = f7.preview(self.outbox, reader=lambda: project)
        self.assertEqual(one["digest"], two["digest"])
        self.assertEqual(one["state"], "JA_EXISTE_NO_PROJECT")
        self.assertEqual(json.dumps(project, sort_keys=True), baseline)

    def test_cli_falha_gh_grava_recibo_sem_mutar_remoto(self):
        self._v1_evidences()
        receipt = self.outbox.parent / "pendente_gh.json"
        import subprocess
        completed = subprocess.CompletedProcess(
            ["gh"], 1, "", "offline")
        with patch.object(f7.subprocess, "run", return_value=completed) as run:
            code = f7.main([
                "--outbox", str(self.outbox),
                "--receipt", str(receipt),
                "--json"])
        self.assertEqual(code, 1)
        self.assertTrue(receipt.exists())
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(saved["publication_status"], "PENDENTE_PUBLICACAO")
        self.assertEqual(saved["remote_writes"], 0)
        self.assertEqual(run.call_args.args[0][:3],
                         ["gh", "project", "item-list"])

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
