"""F7: ponte de escalonamento CCC-01 -> esteira PO / GitHub Project #2.

APENAS LEITURA/PLANEJAMENTO. Para escrita, o fluxo oficial
scripts/ch_project_assist.py exige aprovacao live do PO, digest e readback.
Nao transforma reprovação de IA em autorizacao de escrita remota.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

OWNER = "hallanbrito"
REPO = "hallanbrito/CHDevFlow"
PROJECT = 2
MAX_ITEMS = 500
SCHEMA = "CHDEVFLOW-F7-OUTBOX/1"
EVIDENCE_FILES = (
    "attempt-03/codigo.py",
    "attempt-03/alteracoes.patch",
    "attempt-03/testes.log",
    "attempt-03/auditoria_codex.md",
    "RELATORIO_COMPLETO_CH1.md",
)
_HEX = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MISSION = re.compile(r"^[A-Za-z0-9_.-]{3,80}$")
_ISSUE_URL = re.compile(
    r"^https://github\.com/hallanbrito/CHDevFlow/issues/([1-9][0-9]*)$")


def _safe_outbox(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 15000:
        raise ValueError("Outbox local ausente, link ou maior que limite")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Outbox JSON invalido")
    if data.get("status") != "AGUARDANDO_PO":
        raise ValueError("Somente terceira reprovação gera escalonamento")
    if data.get("publication_status") != "PENDENTE_DE_AUTORIZACAO":
        raise ValueError("Outbox ja processado ou estado inconclusivo")
    if data.get("attempts") != 3 or data.get("returns") != 2:
        raise ValueError("Contadores CCC-01 divergentes")
    execution = data.get("execution_id")
    if not isinstance(execution, str) or not _HEX.fullmatch(execution):
        raise ValueError("Execution ID invalido")
    mission = data.get("mission_id") or data.get("mission")
    if not isinstance(mission, str) or not _MISSION.fullmatch(mission):
        raise ValueError("Mission ID invalido")
    issue = data.get("issue")
    if isinstance(issue, str):
        match = _ISSUE_URL.fullmatch(issue)
        issue = int(match.group(1)) if match else None
    if type(issue) is not int or issue < 1:
        raise ValueError("Issue de escalonamento invalida")
    code_sha = None
    evidence_files = []
    if "schema" in data:
        if data["schema"] != SCHEMA:
            raise ValueError("Schema da outbox F7 desconhecido")
        code_sha = data.get("code_sha256")
        if not isinstance(code_sha, str) or not _SHA256.fullmatch(code_sha):
            raise ValueError("SHA256 da implementacao invalido")
        evidence_files = data.get("evidence_files")
        if evidence_files != list(EVIDENCE_FILES):
            raise ValueError("Evidencias da outbox nao foram sanitizadas")
    return {"execution_id": execution, "mission_id": mission,
            "issue": issue, "attempts": 3, "returns": 2,
            "status": "AGUARDANDO_PO", "schema": data.get("schema"),
            "code_sha256": code_sha, "evidence_files": evidence_files}


def _project_snapshot() -> dict:
    """Somente gh project item-list; nenhuma mutacao GitHub."""
    try:
        result = subprocess.run(
            ["gh", "project", "item-list", str(PROJECT), "--owner", OWNER,
             "--format", "json", "-L", str(MAX_ITEMS)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Projeto indisponivel, sem efetuar escrita") from exc
    if result.returncode:
        raise ValueError("Nao foi possivel obter Project LIVE; sem escrita")
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError("Resposta Project nao e JSON valido") from exc


def build_escalation_preview(outbox: dict, project: dict) -> dict:
    """Valida estado total e detecta duplicidade antes de sugerir admissao."""
    if (not isinstance(project, dict) or
            not isinstance(project.get("items"), list) or
            type(project.get("totalCount")) is not int or
            project["totalCount"] != len(project["items"]) or
            project["totalCount"] > MAX_ITEMS):
        raise ValueError("Snapshot Project incompleto ou truncado")
    issue = outbox["issue"]
    items = []
    found = set()
    for item in project["items"]:
        if not isinstance(item, dict):
            raise ValueError("Cartao malformado")
        content = item.get("content")
        if not isinstance(content, dict) or content.get("type") != "Issue":
            continue
        if content.get("repository") != REPO:
            continue
        number = content.get("number")
        if type(number) is not int or number <= 0 or number in found:
            raise ValueError("Issue duplicada/malformada no Project")
        found.add(number)
        if content.get("url") != f"https://github.com/{REPO}/issues/{number}":
            raise ValueError("URL de Issue divergiu do Project")
        if number == issue:
            if not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError("Item existe sem ID valido")
            items.append(item["id"])
    if len(items) > 1:
        raise ValueError("Issue aparece mais de uma vez no Project")
    state = "JA_EXISTE_NO_PROJECT" if items else "EXIGE_ADMISSAO_PO"
    base = {
        "schema": "CHDEVFLOW-F7-ESCALATION-PREVIEW/1",
        "execution_id": outbox["execution_id"],
        "mission_id": outbox["mission_id"],
        "issue": issue,
        "status": "AGUARDANDO_PO",
        "code_sha256": outbox.get("code_sha256"),
        "evidence_files": outbox.get("evidence_files", []),
        "project_owner": OWNER, "project_number": PROJECT,
        "project_item_id": items[0] if items else None,
        "state": state, "writes": 0,
        "next_step": (
            "Preservar cartao e consultar PO, sem alterar campos"
            if items else
            "Solicitar aprovacao PO real; executar o fluxo KSYNC-03 admit com "
            "plano digest e readback, nunca publicar automaticamente"
        )
    }
    base["digest"] = hashlib.sha256(
        json.dumps(base, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    return base


def preview(outbox_path: Path, *, reader=_project_snapshot) -> dict:
    return build_escalation_preview(_safe_outbox(outbox_path), reader())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="F7 - leitura/preview de escalonamento Project #2, SEM escrita")
    parser.add_argument("--outbox", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = preview(args.outbox)
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError) as exc:
        print("F7 BLOQUEADO: " + str(exc)[:400], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
