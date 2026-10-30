"""Testes offline da exportação segura e somente-leitura do GitHub Project #2 (CH-ACCESS-01).

Cobre:
- Sucesso com dados estruturados completos (26 itens, 19 campos).
- Casos limites (0 itens, 0 campos).
- Falha fechada (fail-closed) em erros de gh, autorização, timeout e JSON corrompido.
- Rejeição de contagens divergentes (truncamento / dados incompletos).
- Detecção e rejeição de Card IDs duplicados.
- Relato explícito de campos ausentes como 'NÃO_OBSERVADO'.
- Diagnóstico de opções desconhecidas sem inferência de aprovação.
- Exclusão rigorosa de bodies, comentários, assignees e dados pessoais.
- Saneamento de credenciais simuladas e e-mails.
- Permissões locais restritas 0600.
- Execução do script CLI scripts/ch_project_export.py com flags.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

# Adiciona caminhos do projeto ao sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
SENTINELA_PATH = REPO_ROOT / "apps" / "bootstrap" / "sentinela" / "src"
for p in (SRC_PATH, SENTINELA_PATH):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from chdevflow.core.project_export import (
    ProjectExportError,
    ProjectExportIntegrityError,
    export_project_snapshot,
    extrair_valor_campo,
    sanitizar_texto_completo,
    save_snapshot_file,
)


def criar_payload_campos_valido() -> dict:
    """Gera um payload sintético com 19 campos espelhando a estrutura real do Project #2."""
    fields = [
        {"id": "f_title", "name": "Title", "type": "ProjectV2Field"},
        {"id": "f_assignees", "name": "Assignees", "type": "ProjectV2Field"},
        {
            "id": "f_status",
            "name": "Status",
            "type": "ProjectV2SingleSelectField",
            "options": [{"id": "s1", "name": "Todo"}, {"id": "s2", "name": "In Progress"}, {"id": "s3", "name": "Done"}],
        },
        {"id": "f_labels", "name": "Labels", "type": "ProjectV2Field"},
        {"id": "f_prs", "name": "Linked pull requests", "type": "ProjectV2Field"},
        {"id": "f_milestone", "name": "Milestone", "type": "ProjectV2Field"},
        {"id": "f_repo", "name": "Repository", "type": "ProjectV2Field"},
        {"id": "f_reviewers", "name": "Reviewers", "type": "ProjectV2Field"},
        {"id": "f_parent", "name": "Parent issue", "type": "ProjectV2Field"},
        {"id": "f_subissues", "name": "Sub-issues progress", "type": "ProjectV2Field"},
        {"id": "f_created", "name": "Created", "type": "ProjectV2Field"},
        {"id": "f_updated", "name": "Updated", "type": "ProjectV2Field"},
        {"id": "f_closed", "name": "Closed", "type": "ProjectV2Field"},
        {
            "id": "f_etapa",
            "name": "Etapa CH",
            "type": "ProjectV2SingleSelectField",
            "options": [
                {"id": "e1", "name": "BACKLOG"}, {"id": "e2", "name": "PRONTA"},
                {"id": "e3", "name": "EM_EXECUCAO"}, {"id": "e4", "name": "EM_REVISAO"},
                {"id": "e5", "name": "AGUARDANDO_PO"}, {"id": "e6", "name": "APROVADA"},
                {"id": "e7", "name": "PARCIAL"}, {"id": "e8", "name": "CORRECOES"},
                {"id": "e9", "name": "REPROVADA"}, {"id": "e10", "name": "INTEGRADA"},
                {"id": "e11", "name": "HOMOLOGADA"}
            ],
        },
        {
            "id": "f_esteira",
            "name": "Esteira",
            "type": "ProjectV2SingleSelectField",
            "options": [
                {"id": "est1", "name": "Hallan"}, {"id": "est2", "name": "ChatGPT"},
                {"id": "est3", "name": "Codex"}, {"id": "est4", "name": "AGY"}
            ],
        },
        {
            "id": "f_prioridade",
            "name": "Prioridade CH",
            "type": "ProjectV2SingleSelectField",
            "options": [{"id": "p0", "name": "P0"}, {"id": "p1", "name": "P1"}, {"id": "p2", "name": "P2"}, {"id": "p3", "name": "P3"}],
        },
        {
            "id": "f_risco",
            "name": "Risco CH",
            "type": "ProjectV2SingleSelectField",
            "options": [{"id": "r1", "name": "BAIXO"}, {"id": "r2", "name": "MEDIO"}, {"id": "r3", "name": "ALTO"}, {"id": "r4", "name": "CRITICO"}],
        },
        {
            "id": "f_autonomia",
            "name": "Autonomia CH",
            "type": "ProjectV2SingleSelectField",
            "options": [{"id": "a0", "name": "CH-0"}, {"id": "a1", "name": "CH-1"}, {"id": "a2", "name": "CH-2"}, {"id": "a3", "name": "CH-3"}],
        },
        {
            "id": "f_decisao",
            "name": "Decisao PO",
            "type": "ProjectV2SingleSelectField",
            "options": [
                {"id": "d1", "name": "PENDENTE"}, {"id": "d2", "name": "APROVADO"},
                {"id": "d3", "name": "PARCIAL"}, {"id": "d4", "name": "AJUSTES"},
                {"id": "d5", "name": "REPROVADO"}
            ],
        },
    ]
    return {"fields": fields, "totalCount": len(fields)}


def criar_payload_itens_valido(quantidade: int = 26) -> dict:
    """Gera um payload sintético com a quantidade desejada de itens com IDs únicos."""
    items = []
    for i in range(1, quantidade + 1):
        items.append({
            "id": f"PVTI_card_{i:04d}",
            "title": f"Fatia W{i}: Tarefa de teste",
            "status": "Todo" if i % 2 == 0 else "In Progress",
            "etapa CH": "PRONTA" if i % 2 == 0 else "EM_EXECUCAO",
            "esteira": "AGY" if i % 2 == 0 else "ChatGPT",
            "autonomia CH": "CH-2",
            "labels": ["ch:workflow", "ch:agy"],
            "content": {
                "type": "Issue",
                "number": i + 10,
                "title": f"Fatia W{i}: Tarefa de teste",
                "repository": "hallanbrito/CHDevFlow",
                "url": f"https://github.com/hallanbrito/CHDevFlow/issues/{i + 10}",
                "body": "Corpo que deve ser estritamente omitido",
            },
            "assignees": ["usuario_secreto"],
        })
    return {"items": items, "totalCount": quantidade}


class TestProjectExport(unittest.TestCase):
    """Testes unitários e de integração offline do exportador de projeto."""

    def test_export_offline_success(self) -> None:
        """Exporta com sucesso 26 cartões e 19 campos via payloads sintéticos."""
        fields_raw = criar_payload_campos_valido()
        items_raw = criar_payload_itens_valido(26)

        snapshot = export_project_snapshot(
            items_raw=items_raw,
            fields_raw=fields_raw,
            source_override="SNAPSHOT_OFFLINE",
        )

        self.assertEqual(snapshot["schema_version"], "chdevflow.project-snapshot/1.0")
        self.assertEqual(snapshot["source"], "SNAPSHOT_OFFLINE")
        self.assertEqual(snapshot["project_number"], 2)
        self.assertEqual(snapshot["project_owner"], "hallanbrito")

        integ = snapshot["integrity"]
        self.assertEqual(integ["total_items_reported"], 26)
        self.assertEqual(integ["total_items_received"], 26)
        self.assertTrue(integ["items_count_match"])
        self.assertEqual(integ["total_fields_reported"], 19)
        self.assertEqual(integ["total_fields_received"], 19)
        self.assertTrue(integ["fields_count_match"])
        self.assertTrue(integ["unique_card_ids"])
        self.assertEqual(len(integ["anomalies"]), 0)
        self.assertTrue(len(integ["snapshot_digest"]) == 64)

        self.assertEqual(len(snapshot["items"]), 26)
        self.assertEqual(len(snapshot["fields"]), 19)

    def test_export_zero_items(self) -> None:
        """Exporta com sucesso um projeto com zero itens."""
        fields_raw = criar_payload_campos_valido()
        items_raw = {"items": [], "totalCount": 0}

        snapshot = export_project_snapshot(
            items_raw=items_raw,
            fields_raw=fields_raw,
            source_override="SNAPSHOT_OFFLINE",
        )

        self.assertEqual(snapshot["integrity"]["total_items_received"], 0)
        self.assertEqual(len(snapshot["items"]), 0)
        self.assertTrue(snapshot["integrity"]["items_count_match"])

    def test_export_zero_fields(self) -> None:
        """Exporta com sucesso um projeto com zero campos."""
        fields_raw = {"fields": [], "totalCount": 0}
        items_raw = {"items": [], "totalCount": 0}

        snapshot = export_project_snapshot(
            items_raw=items_raw,
            fields_raw=fields_raw,
            source_override="SNAPSHOT_OFFLINE",
        )

        self.assertEqual(snapshot["integrity"]["total_fields_received"], 0)
        self.assertEqual(len(snapshot["fields"]), 0)

    def test_export_gh_failure_fail_closed(self) -> None:
        """Simula falha do GitHub CLI e garante bloqueio fail-closed sem fixture sintética."""
        class MockLeitorFalha:
            def listar_campos_projeto(self, **kwargs):
                raise RuntimeError("Falha de autenticação gh: token expirado.")
            def listar_itens_projeto(self, **kwargs):
                raise RuntimeError("Não deve ser chamado.")

        with self.assertRaises(ProjectExportError) as ctx:
            export_project_snapshot(leitor=MockLeitorFalha())

        self.assertIn("Falha na consulta ao GitHub Project #2", str(ctx.exception))
        self.assertIn("Falha de autenticação gh", str(ctx.exception))

    def test_export_incomplete_items_count_mismatch(self) -> None:
        """Rejeita snapshot onde totalCount diverge da lista de itens recebidos."""
        fields_raw = criar_payload_campos_valido()
        items_raw = criar_payload_itens_valido(26)
        items_raw["totalCount"] = 25  # Inconsistência proposital

        with self.assertRaises(Exception) as ctx:
            export_project_snapshot(
                items_raw=items_raw,
                fields_raw=fields_raw,
            )
        self.assertTrue(
            "Project incompleto" in str(ctx.exception)
            or "Divergência de contagem" in str(ctx.exception)
        )

    def test_export_incomplete_fields_count_mismatch(self) -> None:
        """Rejeita snapshot onde totalCount diverge da lista de campos recebidos."""
        fields_raw = criar_payload_campos_valido()
        fields_raw["totalCount"] = 20  # Inconsistência proposital
        items_raw = criar_payload_itens_valido(5)

        with self.assertRaises(Exception) as ctx:
            export_project_snapshot(
                items_raw=items_raw,
                fields_raw=fields_raw,
            )
        self.assertTrue(
            "Campos do Project incompletos" in str(ctx.exception)
            or "Divergência de contagem" in str(ctx.exception)
        )

    def test_export_duplicate_card_ids_rejected(self) -> None:
        """Rejeita projeto com IDs de cartão duplicados."""
        fields_raw = criar_payload_campos_valido()
        items_raw = criar_payload_itens_valido(3)
        # Duplica o ID do primeiro cartão no segundo
        items_raw["items"][1]["id"] = items_raw["items"][0]["id"]

        with self.assertRaises(ProjectExportIntegrityError) as ctx:
            export_project_snapshot(
                items_raw=items_raw,
                fields_raw=fields_raw,
            )
        self.assertIn("Card ID duplicado detectado", str(ctx.exception))

    def test_export_missing_field_reported_nao_observado(self) -> None:
        """Campos ausentes em um item devem ser preenchidos com NÃO_OBSERVADO."""
        fields_raw = criar_payload_campos_valido()
        items_raw = {
            "items": [
                {
                    "id": "PVTI_teste_vazio",
                    "title": "Item sem campos preenchidos",
                    "content": {
                        "type": "Issue",
                        "number": 99,
                        "title": "Issue 99",
                        "url": "https://github.com/hallanbrito/CHDevFlow/issues/99",
                    },
                }
            ],
            "totalCount": 1,
        }

        snapshot = export_project_snapshot(
            items_raw=items_raw,
            fields_raw=fields_raw,
        )

        item = snapshot["items"][0]
        self.assertEqual(item["status"], "NÃO_OBSERVADO")
        self.assertEqual(item["esteira"], "NÃO_OBSERVADO")
        self.assertEqual(item["etapa_ch"], "NÃO_OBSERVADO")
        self.assertEqual(item["prioridade_ch"], "NÃO_OBSERVADO")
        self.assertEqual(item["risco_ch"], "NÃO_OBSERVADO")
        self.assertEqual(item["autonomia_ch"], "NÃO_OBSERVADO")
        self.assertEqual(item["decisao_po"], "NÃO_OBSERVADO")

    def test_export_unknown_option_flagged_as_anomaly(self) -> None:
        """Opção desconhecida em campo seletor é diagnosticada em 'anomalies' sem inferir aprovação."""
        fields_raw = criar_payload_campos_valido()
        items_raw = {
            "items": [
                {
                    "id": "PVTI_anomalia",
                    "title": "Item com opção inválida",
                    "status": "OPCAO_INVENTADA_NAO_PERMITIDA",
                    "content": {"type": "Issue", "number": 88, "title": "Item 88"},
                }
            ],
            "totalCount": 1,
        }

        snapshot = export_project_snapshot(
            items_raw=items_raw,
            fields_raw=fields_raw,
        )

        anomalias = snapshot["integrity"]["anomalies"]
        self.assertEqual(len(anomalias), 1)
        self.assertEqual(anomalias[0]["field"], "Status")
        self.assertEqual(anomalias[0]["value"], "OPCAO_INVENTADA_NAO_PERMITIDA")
        self.assertEqual(anomalias[0]["error"], "OPCAO_DESCONHECIDA")

    def test_export_body_comments_personal_info_excluded(self) -> None:
        """Corpos de issue, comentários e nomes de pessoas são estritamente omitidos do snapshot."""
        fields_raw = criar_payload_campos_valido()
        items_raw = {
            "items": [
                {
                    "id": "PVTI_sigilo",
                    "title": "Item com dados sensíveis",
                    "assignees": ["joao_silva", "maria_souza"],
                    "comments": ["comentário privado que não pode vazar"],
                    "content": {
                        "type": "Issue",
                        "number": 77,
                        "title": "Título Seguro",
                        "body": "Conteúdo altamente confidencial e longo",
                        "author": "dev_privado",
                    },
                }
            ],
            "totalCount": 1,
        }

        snapshot = export_project_snapshot(
            items_raw=items_raw,
            fields_raw=fields_raw,
        )

        item = snapshot["items"][0]
        self.assertNotIn("body", item)
        self.assertNotIn("comments", item)
        self.assertNotIn("assignees", item)
        self.assertNotIn("author", item)

        # Serializa para texto e confirma ausência total de strings proibidas
        texto_serializado = json.dumps(snapshot)
        self.assertNotIn("Conteúdo altamente confidencial", texto_serializado)
        self.assertNotIn("comentário privado", texto_serializado)
        self.assertNotIn("joao_silva", texto_serializado)

    def test_export_secret_and_email_sanitization(self) -> None:
        """Tokens GitHub e e-mails pessoais são mascarados automaticamente."""
        texto_com_segredos = (
            "Erro com token ghp_1234567890abcdefghijklmnopqrstuvwxyz "
            "e chave AIzaSyD12345678901234567890123456789012 "
            "contatar dev@empresa.com.br urgente"
        )
        limpo = sanitizar_texto_completo(texto_com_segredos)
        self.assertNotIn("ghp_", limpo)
        self.assertNotIn("AIza", limpo)
        self.assertNotIn("dev@empresa.com.br", limpo)
        self.assertIn("[CREDENCIAL_OCULTADA]", limpo)
        self.assertIn("[DADO_PESSOAL_OCULTADO]", limpo)

    def test_save_snapshot_file_permissions_0600(self) -> None:
        """Garante que o arquivo de snapshot seja gravado com permissões estritas 0600."""
        snapshot = {
            "schema_version": "chdevflow.project-snapshot/1.0",
            "source": "SNAPSHOT_TEST",
            "captured_at_utc": "2026-10-30T12:00:00Z",
            "items": [],
            "fields": [],
        }

        with tempfile.TemporaryDirectory(prefix="test_snap_perm_") as tmpdir:
            destino = Path(tmpdir) / "subpasta" / "snapshot_privado.json"
            salvo = save_snapshot_file(snapshot, destino)

            self.assertTrue(salvo.is_file())
            # Verifica permissões UNIX (apenas 0o600 / rw-------)
            perm = stat.S_IMODE(os.stat(salvo).st_mode)
            self.assertEqual(
                perm,
                0o600,
                f"Permissões do snapshot devem ser 0600 (rw-------), obtido {oct(perm)}.",
            )

    def test_script_cli_execution_with_fixtures(self) -> None:
        """Executa scripts/ch_project_export.py via subprocess com fixtures offline."""
        with tempfile.TemporaryDirectory(prefix="test_cli_export_") as tmpdir:
            items_file = Path(tmpdir) / "items.json"
            fields_file = Path(tmpdir) / "fields.json"
            out_file = Path(tmpdir) / "out_snapshot.json"

            items_file.write_text(json.dumps(criar_payload_itens_valido(4)), encoding="utf-8")
            fields_file.write_text(json.dumps(criar_payload_campos_valido()), encoding="utf-8")

            cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "ch_project_export.py"),
                "--fixture-items", str(items_file),
                "--fixture-fields", str(fields_file),
                "--output", str(out_file),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, f"Script falhou: {proc.stderr}")
            self.assertIn("Exportação do GitHub Project #2 Concluída", proc.stdout)
            self.assertTrue(out_file.is_file())

            # Verifica integridade do arquivo gerado
            with open(out_file, "r", encoding="utf-8") as f:
                dados = json.load(f)
            self.assertEqual(dados["integrity"]["total_items_received"], 4)
            self.assertEqual(dados["source"], "SNAPSHOT_OFFLINE")

    def test_script_cli_stdout_flag(self) -> None:
        """Executa scripts/ch_project_export.py com flag --stdout e valida saída JSON."""
        with tempfile.TemporaryDirectory(prefix="test_cli_stdout_") as tmpdir:
            items_file = Path(tmpdir) / "items.json"
            fields_file = Path(tmpdir) / "fields.json"

            items_file.write_text(json.dumps(criar_payload_itens_valido(2)), encoding="utf-8")
            fields_file.write_text(json.dumps(criar_payload_campos_valido()), encoding="utf-8")

            cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "ch_project_export.py"),
                "--fixture-items", str(items_file),
                "--fixture-fields", str(fields_file),
                "--stdout",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0)
            parsed = json.loads(proc.stdout)
            self.assertEqual(parsed["schema_version"], "chdevflow.project-snapshot/1.0")
            self.assertEqual(len(parsed["items"]), 2)

    def test_script_cli_dry_run_flag(self) -> None:
        """Flag --dry-run não deve gravar arquivo no disco."""
        with tempfile.TemporaryDirectory(prefix="test_cli_dry_") as tmpdir:
            items_file = Path(tmpdir) / "items.json"
            fields_file = Path(tmpdir) / "fields.json"
            out_file = Path(tmpdir) / "nao_deve_existir.json"

            items_file.write_text(json.dumps(criar_payload_itens_valido(2)), encoding="utf-8")
            fields_file.write_text(json.dumps(criar_payload_campos_valido()), encoding="utf-8")

            cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "ch_project_export.py"),
                "--fixture-items", str(items_file),
                "--fixture-fields", str(fields_file),
                "--output", str(out_file),
                "--dry-run",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("DRY_RUN", proc.stdout)
            self.assertFalse(out_file.exists(), "Flag --dry-run não deve criar o arquivo.")

    def test_script_cli_failure_exits_code_1_fail_closed(self) -> None:
        """Script falha com código 1 e fail-closed diante de fixtures ausentes ou corrompidas."""
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "ch_project_export.py"),
            "--fixture-items", "/caminho/inexistente/items.json",
            "--fixture-fields", "/caminho/inexistente/fields.json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("ERRO", proc.stderr)


if __name__ == "__main__":
    unittest.main()
